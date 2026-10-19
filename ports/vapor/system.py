# -*- coding: utf-8 -*-
"""Integracion con el sistema: brillo de pantalla y arranque directo en Vapor."""
import os
import re
import subprocess
import tempfile

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


def _install_text(path, new_text):
    """Copia new_text sobre path (con sudo si hace falta), conservando permisos y
    guardando una copia de seguridad la primera vez."""
    if not _bash_ok(new_text):
        return False
    tmpdir = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
    fd, tmp = tempfile.mkstemp(prefix="vapor_es_", dir=tmpdir)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(new_text)
        backup = path + ".vapor-backup"
        cmds = []
        if not os.path.exists(backup):
            cmds.append(["cp", "-p", path, backup])
        cmds.append(["cp", tmp, path])
        for cmd in cmds:
            ok = False
            try:
                ok = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
            if not ok:
                try:
                    ok = subprocess.run(["sudo", "-n"] + cmd, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=10).returncode == 0
                except (OSError, subprocess.SubprocessError):
                    ok = False
            if not ok:
                return False
        return True
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
