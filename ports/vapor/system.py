# -*- coding: utf-8 -*-
"""Integracion con el sistema: brillo de pantalla y arranque directo en Vapor."""
import os
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


def _q(s):
    """Comillas seguras para bash."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


def hook_block(vapor_sh, data_dir):
    """Bloque que se anade al script de arranque de EmulationStation.

    - Solo hace algo si existe data/autostart (se activa/desactiva desde Vapor).
    - Una sola vez por encendido (no al reiniciar EmulationStation).
    - Seguridad: si un arranque anterior no llego a mostrar Vapor (se colgo y se
      apago la consola), se desactiva solo y arranca EmulationStation."""
    flag = os.path.join(data_dir, "autostart")
    pending = os.path.join(data_dir, "boot_pending")
    return "\n".join([
        BEGIN + " (lo gestiona Vapor: START > Personalizar > Abrir Vapor al encender)",
        "if [ -f %s ] && [ -f %s ] && [ ! -f /dev/shm/vapor_boot_done ]; then"
        % (_q(flag), _q(vapor_sh)),
        "  touch /dev/shm/vapor_boot_done",
        "  if [ -f %s ]; then" % _q(pending),
        "    rm -f %s %s" % (_q(flag), _q(pending)),
        "  else",
        "    touch %s" % _q(pending),
        "    VAPOR_BOOT=1 /bin/bash %s" % _q(vapor_sh),
        "    rm -f %s" % _q(pending),
        "  fi",
        "fi",
        END,
    ]) + "\n"


def strip_hook(text):
    out = []
    skip = False
    for line in text.splitlines(True):
        if line.startswith(BEGIN):
            skip = True
            continue
        if skip:
            if line.startswith(END):
                skip = False
            continue
        out.append(line)
    return "".join(out)


def add_hook(text, block):
    """Inserta el bloque justo despues de la primera linea (#!/bin/bash)."""
    text = strip_hook(text)
    lines = text.splitlines(True)
    if lines and lines[0].startswith("#!"):
        first = lines[0] if lines[0].endswith("\n") else lines[0] + "\n"
        return first + block + "".join(lines[1:])
    return "#!/bin/bash\n" + block + text


def has_hook(text):
    return BEGIN in text and END in text


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
        block = hook_block(self.vapor_sh, self.data_dir)
        for p in self.scripts:
            try:
                with open(p) as f:
                    text = f.read()
            except (IOError, OSError):
                return False, "read"
            new = add_hook(text, block)
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

    def boot_ok(self):
        """Vapor llego a mostrarse: se quita la marca de seguridad del arranque."""
        try:
            os.remove(os.path.join(self.data_dir, "boot_pending"))
        except OSError:
            pass
