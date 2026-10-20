# -*- coding: utf-8 -*-
"""Integracion con el sistema: brillo, arranque directo en Vapor, silencio y hora."""
import os
import re
import subprocess
import tempfile
import threading
import time

# ----------------------------------------------------------------- brillo
BACKLIGHT_DIR = "/sys/class/backlight"


def _sudo_write(path, text):
    """Escribe en un fichero del sistema; si no hay permiso, usa 'sudo -n tee'
    (en ArkOS el usuario ark puede usar sudo sin contrasena)."""
    try:
        with open(path, "w") as f:
            f.write(text)
        return True
    except (IOError, OSError):
        pass
    try:
        r = subprocess.run(["sudo", "-n", "tee", path], input=text.encode("ascii"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Backlight(object):
    """Control de brillo directo. EmulationStation solo usa
    /sys/class/backlight/backlight; aqui se prueban todos los que haya, que es
    lo que hace falta en algunos clones de la R36S."""
    MIN_PERCENT = 5

    def __init__(self, base=BACKLIGHT_DIR):
        self.devices = []
        try:
            names = sorted(os.listdir(base), key=lambda n: (n != "backlight", n))
        except OSError:
            names = []
        for n in names:
            d = os.path.join(base, n)
            if os.path.isfile(os.path.join(d, "brightness")) and \
                    os.path.isfile(os.path.join(d, "max_brightness")):
                self.devices.append(d)

    @property
    def available(self):
        return bool(self.devices)

    @staticmethod
    def _read_int(path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (IOError, OSError, ValueError):
            return None

    def get_percent(self):
        for d in self.devices:
            mx = self._read_int(os.path.join(d, "max_brightness"))
            cur = self._read_int(os.path.join(d, "brightness"))
            if mx and cur is not None:
                return int(round(100.0 * cur / mx))
        return None

    def set_percent(self, pct):
        pct = max(self.MIN_PERCENT, min(100, int(pct)))
        ok = False
        for d in self.devices:
            mx = self._read_int(os.path.join(d, "max_brightness"))
            if not mx:
                continue
            value = max(1, int(round(mx * pct / 100.0)))
            if _sudo_write(os.path.join(d, "brightness"), "%d\n" % value):
                ok = True
        return ok


# ------------------------------------------------------- arranque en Vapor
ES_SCRIPTS = ("/usr/bin/emulationstation/emulationstation.sh",
              "/usr/bin/emulationstation/emulationstation.sh.es")
BEGIN = "# >>> VAPOR-AUTOSTART"
END = "# <<< VAPOR-AUTOSTART"
HOOK_VERSION = "v2"

# Linea que arranca el programa de EmulationStation dentro de emulationstation.sh
# (p. ej. './emulationstation "$@"' o '"$esdir/emulationstation" ...'), no la de
# 'cd /usr/bin/emulationstation' ni la del propio emulationstation.sh.
_ES_LAUNCH = re.compile(
    r"""^(?P<indent>[ \t]*)(?:[A-Za-z_][A-Za-z0-9_]*=\S*[ \t]+)*"""
    r"""(?:(?:exec|sudo|nice[ \t]+-n[ \t]+-?\d+|nohup)[ \t]+)*"""
    r"""["']?(?:\./|[\w${}"'./-]*/)?emulationstation["']?(?:[ \t]|$)""")


def _q(s):
    """Comillas seguras para bash."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def hook_block(vapor_sh, data_dir, indent=""):
    """Bloque que se anade al script de arranque de EmulationStation.

    - Solo hace algo si existe data/autostart (se activa/desactiva desde Vapor).
    - Una sola vez por encendido (no al reiniciar EmulationStation).
    - Quita la pantalla de carga (plymouth) para que Vapor pueda usar la pantalla.
    - Deja un registro en data/boot.log.
    - Seguridad: si un arranque anterior no llego a mostrar Vapor (se colgo y se
      apago la consola), se desactiva solo y arranca EmulationStation."""
    flag = _q(os.path.join(data_dir, "autostart"))
    pending = _q(os.path.join(data_dir, "boot_pending"))
    log = _q(os.path.join(data_dir, "boot.log"))
    lines = [
        BEGIN + " " + HOOK_VERSION +
        " (lo gestiona Vapor: START > Personalizar > Abrir Vapor al encender)",
        "if [ -f %s ] && [ -f %s ] && [ ! -f /dev/shm/vapor_boot_done ]; then"
        % (flag, _q(vapor_sh)),
        "  touch /dev/shm/vapor_boot_done",
        "  if [ -f %s ]; then" % pending,
        "    echo \"$(date '+%%F %%T') el arranque anterior no llego a mostrar Vapor:"
        " arranque automatico desactivado\" >> %s" % log,
        "    rm -f %s %s" % (flag, pending),
        "  else",
        "    echo \"$(date '+%%F %%T') abriendo Vapor (usuario $(id -un))\" >> %s" % log,
        "    touch %s" % pending,
        "    command -v plymouth >/dev/null 2>&1 && sudo -n plymouth hide-splash"
        " >/dev/null 2>&1",
        "    VAPOR_BOOT=1 /bin/bash %s" % _q(vapor_sh),
        "    vapor_rc=$?",
        "    echo \"$(date '+%%F %%T') Vapor se cerro (codigo $vapor_rc)\" >> %s" % log,
        "    rm -f %s" % pending,
        "  fi",
        "fi",
        END,
    ]
    return "".join(indent + l + "\n" for l in lines)


def strip_hook(text):
    out = []
    skip = False
    for line in text.splitlines(True):
        if line.lstrip().startswith(BEGIN):
            skip = True
            continue
        if skip:
            if line.lstrip().startswith(END):
                skip = False
            continue
        out.append(line)
    return "".join(out)


def _launch_lines(lines):
    out = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "emulationstation.sh" in line or stripped.startswith("cd "):
            continue
        if _ES_LAUNCH.match(line.rstrip("\n")):
            out.append(i)
    return out


def add_hook(text, vapor_sh, data_dir):
    """Inserta el bloque justo antes de cada linea que arranca EmulationStation
    (cuando ArkOS ya preparo pantalla, tarjetas y permisos). Si no se encuentra,
    se pone tras la primera linea (#!/bin/bash). Devuelve el texto nuevo."""
    text = strip_hook(text)
    lines = text.splitlines(True)
    targets = _launch_lines(lines)
    if targets:
        out = []
        for i, line in enumerate(lines):
            if i in targets:
                indent = re.match(r"[ \t]*", line).group(0)
                out.append(hook_block(vapor_sh, data_dir, indent))
            out.append(line)
        new = "".join(out)
        if _bash_ok(new):
            return new
    block = hook_block(vapor_sh, data_dir)
    if lines and lines[0].startswith("#!"):
        first = lines[0] if lines[0].endswith("\n") else lines[0] + "\n"
        return first + block + "".join(lines[1:])
    return "#!/bin/bash\n" + block + text


def has_hook(text):
    return BEGIN in text and END in text


def hook_is_current(text):
    return (BEGIN + " " + HOOK_VERSION) in text


def _bash_ok(text):
    fd, tmp = tempfile.mkstemp(prefix="vapor_es_", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        r = subprocess.run(["bash", "-n", tmp], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _run_cmd(cmd, use_sudo_fallback=True, timeout=10):
    """Ejecuta un comando; si falla (p. ej. sin permiso), lo reintenta con 'sudo -n'."""
    for c in ([cmd, ["sudo", "-n"] + cmd] if use_sudo_fallback else [cmd]):
        try:
            if subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=timeout).returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    return False


def _install_text(path, new_text):
    """Sustituye path por new_text (con sudo si hace falta), conservando permisos y
    guardando una copia de seguridad la primera vez.

    Se escribe un archivo nuevo y se renombra encima del original: asi el script
    que ArkOS esta ejecutando en ese momento no se corrompe (bash lo sigue leyendo
    del archivo antiguo)."""
    if not _bash_ok(new_text):
        return False
    try:
        st = os.stat(path)
    except OSError:
        return False
    tmpdir = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
    fd, tmp = tempfile.mkstemp(prefix="vapor_es_", dir=tmpdir)
    newp = path + ".vapor-new"
    try:
        with os.fdopen(fd, "w") as f:
            f.write(new_text)
        backup = path + ".vapor-backup"
        if not os.path.exists(backup) and not _run_cmd(["cp", "-p", path, backup]):
            return False
        mode = "%o" % (st.st_mode & 0o7777)
        if not _run_cmd(["install", "-m", mode, "-o", str(st.st_uid), "-g", str(st.st_gid),
                         tmp, newp]):
            return False
        if not _run_cmd(["mv", "-f", newp, path]):
            _run_cmd(["rm", "-f", newp])
            return False
        try:
            with open(path) as f:
                return f.read() == new_text
        except (IOError, OSError):
            return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


class Autostart(object):
    def __init__(self, vapor_sh, data_dir, scripts=ES_SCRIPTS):
        self.vapor_sh = vapor_sh
        self.data_dir = data_dir
        self.scripts = [p for p in scripts if os.path.isfile(p)]
        self.flag = os.path.join(data_dir, "autostart")

    @property
    def supported(self):
        return bool(self.scripts) and bool(self.vapor_sh)

    def enabled(self):
        return os.path.isfile(self.flag) and self.hook_installed()

    def hook_installed(self):
        for p in self.scripts[:1]:
            try:
                with open(p) as f:
                    return has_hook(f.read())
            except (IOError, OSError):
                return False
        return False

    def enable(self):
        """Devuelve (ok, motivo)."""
        if not self.scripts:
            return False, "no_es_script"
        if not self.vapor_sh or not os.path.isfile(self.vapor_sh):
            return False, "no_vapor_sh"
        for p in self.scripts:
            try:
                with open(p) as f:
                    text = f.read()
            except (IOError, OSError):
                return False, "read"
            new = add_hook(text, self.vapor_sh, self.data_dir)
            if new != text and not _install_text(p, new):
                return False, "write"
        with open(self.flag, "w") as f:
            f.write("1\n")
        return True, ""

    def disable(self, remove_hook=True):
        try:
            os.remove(self.flag)
        except OSError:
            pass
        if not remove_hook:
            return True
        ok = True
        for p in self.scripts:
            try:
                with open(p) as f:
                    text = f.read()
            except (IOError, OSError):
                continue
            if has_hook(text):
                ok = _install_text(p, strip_hook(text)) and ok
        return ok

    def needs_update(self):
        """El bloque instalado es de una version anterior (o de otra ruta)."""
        if not os.path.isfile(self.flag) or not self.vapor_sh:
            return False
        for p in self.scripts[:1]:
            try:
                with open(p) as f:
                    text = f.read()
            except (IOError, OSError):
                return False
            return has_hook(text) and (not hook_is_current(text) or
                                       _q(self.vapor_sh) not in text)
        return False

    def status(self):
        """Texto corto con el estado para el panel Personalizar."""
        if not self.supported:
            return "no_script" if not self.scripts else "no_vapor_sh"
        if not os.path.isfile(self.flag):
            return "off"
        if not self.hook_installed():
            return "not_installed"
        last = self.last_boot()
        if not last:
            return "waiting"  # activado pero aun no se ha encendido la consola
        if "desactivado" in last or ("codigo" in last and "codigo 0)" not in last):
            return "failed"
        return "ok"

    def last_boot(self):
        """Ultima linea de data/boot.log (o '')."""
        try:
            with open(os.path.join(self.data_dir, "boot.log")) as f:
                lines = [l.strip() for l in f if l.strip()]
            return lines[-1] if lines else ""
        except (IOError, OSError):
            return ""

    def boot_ok(self):
        """Vapor llego a mostrarse: se quita la marca de seguridad del arranque."""
        try:
            os.remove(os.path.join(self.data_dir, "boot_pending"))
        except OSError:
            pass


def _cmd_output(cmd, timeout=6):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        return r.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.SubprocessError) as e:
        return "(no se pudo ejecutar %s: %s)" % (cmd[0], e)


def write_diagnostics(path, autostart, extra_lines=()):
    """Escribe data/diagnostico.txt con lo necesario para entender por que el
    arranque directo en Vapor no funciona en una consola concreta."""
    out = []
    add = out.append
    add("VAPOR - diagnostico del arranque")
    add("fecha: %s" % _cmd_output(["date", "+%F %T"]))
    add("usuario: %s  (HOME=%s)" % (_cmd_output(["id"]), os.environ.get("HOME", "")))
    add("sudo sin contrasena: %s" % ("si" if _run_cmd(["sudo", "-n", "true"],
                                                       use_sudo_fallback=False) else "NO"))
    for l in extra_lines:
        add(l)
    if autostart is not None:
        add("Vapor.sh: %s (existe: %s)" % (autostart.vapor_sh,
                                           os.path.isfile(autostart.vapor_sh or "")))
        add("carpeta de datos: %s" % autostart.data_dir)
        add("marca 'autostart' (opcion activada): %s" % os.path.isfile(autostart.flag))
        add("scripts de arranque encontrados: %s" % (", ".join(autostart.scripts) or "NINGUNO"))
        for p in autostart.scripts:
            try:
                with open(p) as f:
                    text = f.read()
            except (IOError, OSError) as e:
                add("  %s: no se pudo leer (%s)" % (p, e))
                continue
            lines = text.splitlines()
            hooks = [i + 1 for i, l in enumerate(lines) if BEGIN in l]
            launches = [i + 1 for i in _launch_lines([l + "\n" for l in lines])]
            add("  %s: %d lineas, bloque Vapor en lineas %s (version actual: %s), "
                "lineas que abren ES: %s" % (p, len(lines), hooks or "NINGUNA",
                                             hook_is_current(text), launches or "NINGUNA"))
        add("")
        add("---- boot.log (ultimas lineas) ----")
        try:
            with open(os.path.join(autostart.data_dir, "boot.log")) as f:
                add("".join(f.readlines()[-20:]).rstrip() or "(vacio)")
        except (IOError, OSError):
            add("(no existe: el bloque de arranque nunca se ejecuto)")
    add("")
    add("---- systemctl cat emulationstation ----")
    add(_cmd_output(["systemctl", "cat", "emulationstation"]))
    add("")
    add("---- montajes ----")
    try:
        with open("/proc/mounts") as f:
            add("".join(l for l in f if "/roms" in l or " / " in l).rstrip())
    except (IOError, OSError):
        pass
    add("")
    add("---- hora ----")
    add(_cmd_output(["timedatectl"]))
    rtcs = sorted(n for n in os.listdir("/dev") if n.startswith("rtc")) \
        if os.path.isdir("/dev") else []
    add("reloj de la placa: %s" % (", ".join(rtcs) or "NINGUNO"))
    for p in (autostart.scripts if autostart is not None else ES_SCRIPTS)[:1]:
        add("")
        add("---- %s ----" % p)
        try:
            with open(p) as f:
                for i, l in enumerate(f):
                    add("%4d  %s" % (i + 1, l.rstrip("\n")))
        except (IOError, OSError) as e:
            add("(no se pudo leer: %s)" % e)
    try:
        with open(path, "w") as f:
            f.write("\n".join(out) + "\n")
        return True
    except (IOError, OSError):
        return False


# ------------------------------------------------------------ silencio total
class SystemAudio(object):
    """Silencio de todo el sistema (tambien en los juegos) con 'amixer'.

    ArkOS usa el control ALSA 'Playback' (es el que suben/bajan los botones de
    volumen). Si el control tiene interruptor se apaga; si no, se pone a 0 % y se
    guarda el volumen anterior para devolverlo al quitar el silencio. No se toca
    la salida (altavoz/auriculares), asi subir el volumen con los botones de la
    consola siempre devuelve el sonido. ArkOS guarda el estado al apagar."""
    PREFERRED = ("Playback", "Master", "PCM", "Speaker", "Headphone", "DAC", "Digital")
    DEFAULT_RESTORE = 60

    def __init__(self, state_path, amixer="amixer"):
        self.state_path = state_path
        self.amixer = amixer
        self.control = None
        self.has_switch = False
        self.muted = False
        self.last_check = 0
        self._detect()

    def _run(self, *args):
        try:
            r = subprocess.run([self.amixer] + list(args), stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=4)
            return r.returncode, r.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return 1, ""

    def _detect(self):
        import re
        rc, out = self._run("scontrols")
        if rc != 0:
            return
        names = re.findall(r"Simple mixer control '([^']+)',0", out)
        candidates = [n for n in self.PREFERRED if n in names] + \
            [n for n in names if n not in self.PREFERRED]
        for name in candidates:
            info = self._get(name)
            if info is not None and info[0] is not None:
                self.control = name
                self.has_switch = info[2]
                self.muted = self._is_muted(info)
                return

    def _get(self, name=None):
        """(porcentaje, interruptor_encendido o None, tiene_interruptor)"""
        import re
        rc, out = self._run("sget", name or self.control)
        if rc != 0:
            return None
        caps = ""
        for line in out.splitlines():
            if "Capabilities:" in line:
                caps = line
        if "volume" not in caps:
            return (None, None, False)
        pcts = [int(x) for x in re.findall(r"\[(\d+)%\]", out)]
        sws = re.findall(r"\[(on|off)\]", out)
        has_switch = "pswitch" in caps or ("switch" in caps and "cswitch" not in caps)
        sw = None
        if sws:
            sw = any(s == "on" for s in sws)
        return (max(pcts) if pcts else None, sw, has_switch and bool(sws))

    @staticmethod
    def _is_muted(info):
        pct, sw, _has = info
        return (sw is False) or (pct == 0)

    @property
    def available(self):
        return self.control is not None

    def refresh(self, now=None):
        if not self.available:
            return False
        info = self._get()
        if info is not None:
            self.muted = self._is_muted(info)
        if now is not None:
            self.last_check = now
        return self.muted

    def _saved(self):
        try:
            with open(self.state_path) as f:
                v = int(f.read().strip())
            return v if 0 < v <= 100 else self.DEFAULT_RESTORE
        except (IOError, OSError, ValueError):
            return self.DEFAULT_RESTORE

    def _save(self, pct):
        try:
            with open(self.state_path, "w") as f:
                f.write("%d\n" % pct)
        except (IOError, OSError):
            pass

    def set_muted(self, on):
        if not self.available:
            return False
        info = self._get()
        if info is None:
            return False
        pct, sw, has_switch = info
        if on:
            if pct:
                self._save(pct)
            if has_switch:
                ok = self._run("-q", "sset", self.control, "mute")[0] == 0
            else:
                ok = self._run("-q", "sset", self.control, "0%")[0] == 0
        else:
            ok = True
            if has_switch and sw is False:
                ok = self._run("-q", "sset", self.control, "unmute")[0] == 0
            if not pct:
                ok = self._run("-q", "sset", self.control, "%d%%" % self._saved())[0] == 0 and ok
        self.refresh()
        return ok

    def toggle(self):
        self.set_muted(not self.refresh())
        return self.muted


# ------------------------------------------------------------- fecha y hora
ZONEINFO = "/usr/share/zoneinfo"
# Un reloj antes de esta fecha esta desconfigurado seguro (la consola perdio la
# hora al apagarse): Vapor no existia todavia.
CLOCK_FLOOR = 1767225600  # 2026-01-01 00:00 UTC

# Zonas que se ofrecen (las que existan en la consola), con su nombre en espanol
ZONES = (
    ("America/Argentina/Buenos_Aires", "Argentina"),
    ("America/La_Paz", "Bolivia"),
    ("America/Sao_Paulo", "Brasil (São Paulo)"),
    ("America/Santiago", "Chile"),
    ("America/Bogota", "Colombia"),
    ("America/Costa_Rica", "Costa Rica"),
    ("America/Havana", "Cuba"),
    ("America/Guayaquil", "Ecuador"),
    ("America/El_Salvador", "El Salvador"),
    ("Europe/Madrid", "España"),
    ("Atlantic/Canary", "España (Canarias)"),
    ("America/New_York", "EE. UU. (Este)"),
    ("America/Chicago", "EE. UU. (Centro)"),
    ("America/Denver", "EE. UU. (Montaña)"),
    ("America/Los_Angeles", "EE. UU. (Pacífico)"),
    ("America/Guatemala", "Guatemala"),
    ("America/Tegucigalpa", "Honduras"),
    ("America/Mexico_City", "México (Centro)"),
    ("America/Cancun", "México (Cancún)"),
    ("America/Tijuana", "México (Tijuana)"),
    ("America/Managua", "Nicaragua"),
    ("America/Panama", "Panamá"),
    ("America/Asuncion", "Paraguay"),
    ("America/Lima", "Perú"),
    ("America/Puerto_Rico", "Puerto Rico"),
    ("America/Santo_Domingo", "República Dominicana"),
    ("America/Montevideo", "Uruguay"),
    ("America/Caracas", "Venezuela"),
    ("Europe/London", "Reino Unido"),
    ("Europe/Lisbon", "Portugal"),
    ("Europe/Paris", "Francia"),
    ("Europe/Berlin", "Alemania"),
    ("Europe/Rome", "Italia"),
    ("Asia/Tokyo", "Japón"),
    ("Asia/Shanghai", "China"),
    ("Australia/Sydney", "Australia (Sídney)"),
    ("Etc/UTC", "UTC"),
)
_UTC_ALIASES = ("UTC", "UCT", "Universal", "Zulu", "GMT", "GMT0", "GMT+0", "GMT-0",
                "Greenwich", "Etc/UCT", "Etc/Universal", "Etc/Zulu", "Etc/GMT", "Etc/GMT0",
                "Etc/GMT+0", "Etc/GMT-0", "Etc/Greenwich")
# zonas fijas por si el pais no esta en la lista (Etc/GMT+3 es UTC-3)
FIXED_ZONES = tuple("Etc/GMT%s%d" % ("-" if h > 0 else "+", abs(h))
                    for h in range(-12, 15) if h != 0)

# Para poner la hora por internet se usa http y no https: con el reloj mal, los
# certificados parecen caducados y la conexion segura falla.
SYNC_URLS = ("http://clients3.google.com/generate_204",
             "http://www.msftconnecttest.com/connecttest.txt",
             "http://captive.apple.com/")


def zone_offset(zone, when=None, zoneinfo=ZONEINFO):
    """Diferencia con UTC (en segundos) de una zona horaria en un momento dado."""
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = ":" + os.path.join(zoneinfo, zone)
        time.tzset()
        return time.localtime(when).tm_gmtoff
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def fmt_offset(secs):
    """3600 -> 'UTC+1', -10800 -> 'UTC-3', 19800 -> 'UTC+5:30'"""
    if not secs:
        return "UTC"
    sign = "-" if secs < 0 else "+"
    secs = abs(int(secs))
    h, m = secs // 3600, secs % 3600 // 60
    return "UTC%s%d%s" % (sign, h, ":%02d" % m if m else "")


def canonical_zone(zone):
    """Los distintos nombres de UTC cuentan como uno solo."""
    return "Etc/UTC" if zone in _UTC_ALIASES else zone


def zone_label(zone, lang="es", fixed_fmt="%s"):
    zone = canonical_zone(zone)
    if zone.startswith("Etc/GMT") and zone[7:]:
        try:
            return fixed_fmt % fmt_offset(-int(zone[7:]) * 3600)
        except ValueError:
            pass
    if lang == "es":
        for z, name in ZONES:
            if z == zone:
                return name
    return zone.split("/")[-1].replace("_", " ")


def http_time(urls=SYNC_URLS, timeout=4):
    """Hora UTC (epoch) segun la cabecera Date de una web, o None."""
    import email.utils
    import urllib.error
    import urllib.request
    for url in urls:
        t0 = time.time()
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Vapor"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                date = r.headers.get("Date")
        except urllib.error.HTTPError as e:
            date = e.headers.get("Date") if e.headers else None
        except Exception:
            continue
        parsed = email.utils.parsedate_tz(date) if date else None
        if parsed:
            return email.utils.mktime_tz(parsed) + max(0.0, time.time() - t0) / 2.0
    return None


class Clock(object):
    """Fecha, hora y zona horaria del sistema.

    ArkOS no tiene una opcion para cambiar la hora y algunas R36S la pierden al
    apagarse. La hora se cambia con 'date' y se guarda tambien en el reloj de la
    placa ('hwclock'); la zona con 'timedatectl' (o enlazando /etc/localtime).
    Con WiFi se puede poner en hora sola. Ademas Vapor recuerda la ultima hora
    buena: si al encender el reloj vuelve a una fecha imposible, pone esa."""

    def __init__(self, state_path, zoneinfo=ZONEINFO, localtime="/etc/localtime",
                 timezone_file="/etc/timezone", rtc="/dev/rtc0", route="/proc/net/route",
                 run=None, fetch=None):
        self.state_path = state_path
        self.zoneinfo = zoneinfo
        self.localtime = localtime
        self.timezone_file = timezone_file
        self.rtc = rtc
        self.route = route
        self.run = run or _run_cmd
        self.fetch = fetch or http_time
        self.syncing = False
        self.last_sync = None  # (ok, clave del mensaje, segundos corregidos)

    # ---------------------------------------------------------------- zona
    def zone(self):
        """Zona actual ('America/Argentina/Buenos_Aires') o '' si no se sabe."""
        return canonical_zone(self._zone())

    def _zone(self):
        if os.path.islink(self.localtime):
            target = os.readlink(self.localtime)
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(self.localtime), target)
            target = os.path.normpath(target)
            for base in (self.zoneinfo, os.path.realpath(self.zoneinfo)):
                base = base.rstrip("/") + "/"
                if target.startswith(base):
                    return target[len(base):]
            i = target.find("/zoneinfo/")
            if i >= 0:
                z = target[i + len("/zoneinfo/"):]
                for pre in ("posix/", "right/"):
                    if z.startswith(pre):
                        z = z[len(pre):]
                return z
        try:
            with open(self.timezone_file) as f:
                z = f.read().strip()
            if z and os.path.isfile(os.path.join(self.zoneinfo, z)):
                return z
        except (IOError, OSError):
            pass
        return ""

    def _valid_zone(self, zone):
        return bool(zone) and ".." not in zone.split("/") and \
            os.path.isfile(os.path.join(self.zoneinfo, zone))

    def zones(self, lang="es", fixed_fmt="%s"):
        """[(zona, nombre, desfase en segundos)] de las zonas disponibles."""
        import unicodedata

        def key(item):
            name = unicodedata.normalize("NFKD", item[1])
            return "".join(c for c in name if not unicodedata.combining(c)).lower()

        now = time.time()
        named = [(z, zone_label(z, lang), zone_offset(z, now, self.zoneinfo))
                 for z, _ in ZONES if self._valid_zone(z)]
        named.sort(key=key)
        fixed = [(z, zone_label(z, lang, fixed_fmt), zone_offset(z, now, self.zoneinfo))
                 for z in FIXED_ZONES if self._valid_zone(z)]
        fixed.sort(key=lambda it: it[2])
        out = named + fixed
        cur = self.zone()
        if cur and self._valid_zone(cur) and cur not in [z for z, _n, _o in out]:
            out.insert(0, (cur, zone_label(cur, lang, fixed_fmt),
                           zone_offset(cur, now, self.zoneinfo)))
        return out

    def set_zone(self, zone):
        if not self._valid_zone(zone):
            return False
        self.run(["timedatectl", "--no-ask-password", "set-timezone", zone])
        if self.zone() != canonical_zone(zone):
            self.run(["ln", "-sf", os.path.join(self.zoneinfo, zone), self.localtime])
        ok = self.zone() == canonical_zone(zone)
        if ok and os.path.isfile(self.timezone_file):
            try:
                with open(self.timezone_file) as f:
                    stale = f.read().strip() != zone
            except (IOError, OSError):
                stale = True
            if stale:
                _sudo_write(self.timezone_file, zone + "\n")
        time.tzset()  # la hora que muestra Vapor cambia ya
        return ok

    # ---------------------------------------------------------------- hora
    def set_time(self, epoch):
        """Pone el reloj del sistema en 'epoch' (segundos UTC)."""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(round(epoch))))
        if not self.run(["date", "-u", "-s", stamp]):
            return False
        if os.path.exists(self.rtc):
            # tambien en el reloj de la placa, para que dure al apagar
            self.run(["hwclock", "-w"])
        self.save(epoch)
        return True

    def save(self, epoch=None):
        """Recuerda la hora (solo si es creible)."""
        t = time.time() if epoch is None else epoch
        if t < CLOCK_FLOOR:
            return
        try:
            with open(self.state_path, "w") as f:
                f.write("%d\n" % int(t))
        except (IOError, OSError):
            pass

    def saved(self):
        try:
            with open(self.state_path) as f:
                return int(f.read().strip())
        except (IOError, OSError, ValueError):
            return None

    @staticmethod
    def looks_wrong(now=None):
        return (time.time() if now is None else now) < CLOCK_FLOOR

    def restore_if_reset(self):
        """Si la consola perdio la hora al apagarse, pone la ultima conocida."""
        if not self.looks_wrong():
            return False
        last = self.saved()
        if last is None or last < CLOCK_FLOOR:
            return False
        return self.set_time(last)

    # ------------------------------------------------------------ internet
    def online(self):
        """Hay una ruta por defecto (WiFi o red conectada)."""
        try:
            with open(self.route) as f:
                next(f, None)
                for line in f:
                    p = line.split()
                    if len(p) > 2 and p[1] == "00000000":
                        return True
        except (IOError, OSError):
            pass
        return False

    def sync(self):
        """Pone en hora por internet. Devuelve (ok, clave del mensaje, segundos corregidos)."""
        if not self.online():
            return (False, "sync_offline", 0)
        t = self.fetch()
        if t is None:
            return (False, "sync_noresp", 0)
        diff = t - time.time()
        if abs(diff) < 2:
            self.save()
            return (True, "sync_ok", diff)
        if not self.set_time(t):
            return (False, "sync_noperm", diff)
        return (True, "sync_ok", diff)

    def sync_async(self, done=None, wait_online=0):
        """Como sync() pero en segundo plano. Al encender, el WiFi tarda en
        conectar: se espera hasta wait_online segundos."""
        if self.syncing:
            return False
        self.syncing = True

        def work():
            res = (False, "sync_noresp", 0)
            try:
                end = time.monotonic() + wait_online
                while not self.online() and time.monotonic() < end:
                    time.sleep(3)
                res = self.sync()
            except Exception:
                pass
            finally:
                self.last_sync = res
                self.syncing = False
            if done is not None:
                done(res)

        t = threading.Thread(target=work)
        t.daemon = True
        t.start()
        return True
