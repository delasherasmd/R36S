#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Anula un stick analogico averiado (por ejemplo, trabado marcando 'arriba')
en toda la consola: EmulationStation, Vapor, RetroArch y los demas emuladores.

Como funciona (lo ejecuta como root el servicio anular-stick, que se instala
abriendo "Anular stick" desde Ports, antes de que arranque EmulationStation):
  1. abre el mando de la consola y lo toma en exclusiva (EVIOCGRAB);
  2. crea un mando virtual identico (mismo nombre e identificadores: ES,
     RetroArch y los emuladores lo configuran igual que el de siempre);
  3. le pasa todos los botones y ejes menos los del stick anulado, que se
     quedan siempre en el centro;
  4. aparta el archivo del mando real (/dev/input/eventN -> /dev/.anular-stick/)
     para que los juegos que se abran despues solo vean el virtual.
Al terminar, o con --restore, todo vuelve a quedar como estaba. Al apagar,
/dev se crea de nuevo, asi que un fallo nunca dura mas alla de un reinicio.

Solo usa la biblioteca estandar de Python.
"""
import errno
import fcntl
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import time

# ------------------------------------------------------------ linux/input.h
EV_SYN, EV_KEY, EV_ABS, EV_MSC, EV_SW = 0x00, 0x01, 0x03, 0x04, 0x05
SYN_REPORT, SYN_DROPPED = 0, 3
ABS_X, ABS_Y, ABS_RX, ABS_RY = 0x00, 0x01, 0x03, 0x04
KEY_CNT, ABS_CNT, PROP_CNT = 0x300, 0x40, 0x20
BUS_HOST = 0x19
# botones propios de un mando (para reconocer el de la consola)
GAMEPAD_KEYS = set(range(0x120, 0x140)) | set(range(0x220, 0x224)) | set(range(0x2c0, 0x2e8))

STICKS = {"left": (ABS_X, ABS_Y), "right": (ABS_RX, ABS_RY),
          "both": (ABS_X, ABS_Y, ABS_RX, ABS_RY)}
_WORDS = {"left": "left", "izquierdo": "left", "izq": "left",
          "right": "right", "derecho": "right", "der": "right",
          "both": "both", "ambos": "both", "los dos": "both"}

PHYS = "anular-stick/input0"  # asi se reconoce el mando virtual
HIDE_DIR = "/dev/.anular-stick"
STATUS = "/dev/shm/anular_stick.json"
HOTKEY_DAEMONS = ("ogage", "oga_events")


def _ioc(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


_R, _W, _N = 2, 1, 0
EVIOCGID = _ioc(_R, "E", 0x02, 8)
EVIOCGRAB = _ioc(_W, "E", 0x90, 4)


def EVIOCGNAME(n):
    return _ioc(_R, "E", 0x06, n)


def EVIOCGPHYS(n):
    return _ioc(_R, "E", 0x07, n)


def EVIOCGPROP(n):
    return _ioc(_R, "E", 0x09, n)


def EVIOCGBIT(ev, n):
    return _ioc(_R, "E", 0x20 + ev, n)


def EVIOCGABS(code):
    return _ioc(_R, "E", 0x40 + code, 24)


UI_DEV_CREATE = _ioc(_N, "U", 1, 0)
UI_DEV_DESTROY = _ioc(_N, "U", 2, 0)
UI_SET_EVBIT = _ioc(_W, "U", 100, 4)
UI_SET_KEYBIT = _ioc(_W, "U", 101, 4)
UI_SET_ABSBIT = _ioc(_W, "U", 103, 4)
UI_SET_MSCBIT = _ioc(_W, "U", 104, 4)
UI_SET_SWBIT = _ioc(_W, "U", 109, 4)
UI_SET_PROPBIT = _ioc(_W, "U", 110, 4)
UI_SET_PHYS = _ioc(_W, "U", 108, struct.calcsize("P"))

EVENT = struct.Struct("llHHi")  # struct input_event (timeval nativo)
ABSINFO = struct.Struct("6i")
USER_DEV = struct.Struct("80sHHHHI%di" % (ABS_CNT * 4))  # struct uinput_user_dev


class Sys(object):
    """Acceso al sistema (en las pruebas se sustituye por uno falso)."""
    input_dir = "/dev/input"
    hide_dir = HIDE_DIR
    uinput = "/dev/uinput"

    def open(self, path, flags):
        return os.open(path, flags)

    def close(self, fd):
        os.close(fd)

    def ioctl(self, fd, req, arg=0):
        if isinstance(arg, bytearray):
            fcntl.ioctl(fd, req, arg, True)
            return arg
        return fcntl.ioctl(fd, req, arg)

    def read(self, fd, n):
        return os.read(fd, n)

    def write(self, fd, data):
        return os.write(fd, data)

    def listdir(self, path):
        return os.listdir(path)

    def exists(self, path):
        return os.path.lexists(path)

    def rename(self, a, b):
        os.rename(a, b)

    def makedirs(self, path):
        if not os.path.isdir(path):
            os.makedirs(path, 0o700)

    def rmdir(self, path):
        os.rmdir(path)


def parse_mode(text):
    """Primera palabra util del archivo de configuracion -> left/right/both/off."""
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            return _WORDS.get(line, "off")
    return "off"


def read_mode(path):
    try:
        with open(path) as f:
            return parse_mode(f.read())
    except (IOError, OSError):
        return "off"


def _bits(buf):
    return [i for i in range(len(buf) * 8) if buf[i // 8] >> (i % 8) & 1]


class DevInfo(object):
    def __init__(self):
        self.name = ""
        self.phys = ""
        self.id = (0, 0, 0, 0)  # bustype, vendor, product, version
        self.evbits = []
        self.bits = {}  # tipo -> [codigos]
        self.props = []
        self.abs = {}   # codigo -> (value, min, max, fuzz, flat, resolution)

    def is_gamepad(self):
        keys = set(self.bits.get(EV_KEY, ()))
        axes = self.abs
        return bool(keys & GAMEPAD_KEYS) and ABS_X in axes and ABS_Y in axes \
            and not self.phys.startswith(PHYS.split("/")[0])

    def center(self, code):
        _v, lo, hi = self.abs[code][:3]
        return (lo + hi) // 2

    def to_dict(self):
        return {"name": self.name, "phys": self.phys, "id": list(self.id),
                "abs": {str(k): list(v[:3]) for k, v in sorted(self.abs.items())}}


def probe(io, fd):
    info = DevInfo()

    def text(req):
        buf = io.ioctl(fd, req(256), bytearray(256))
        return bytes(buf).split(b"\0", 1)[0].decode("utf-8", "replace")

    info.name = text(EVIOCGNAME)
    try:
        info.phys = text(EVIOCGPHYS)
    except OSError:
        info.phys = ""
    info.id = struct.unpack("4H", bytes(io.ioctl(fd, EVIOCGID, bytearray(8))))
    info.evbits = _bits(io.ioctl(fd, EVIOCGBIT(0, 4), bytearray(4)))
    sizes = {EV_KEY: KEY_CNT // 8, EV_ABS: ABS_CNT // 8, EV_MSC: 1, EV_SW: 4}
    for ev, n in sizes.items():
        if ev in info.evbits:
            info.bits[ev] = _bits(io.ioctl(fd, EVIOCGBIT(ev, n), bytearray(n)))
    try:
        info.props = _bits(io.ioctl(fd, EVIOCGPROP(PROP_CNT // 8), bytearray(PROP_CNT // 8)))
    except OSError:
        info.props = []
    for code in info.bits.get(EV_ABS, ()):
        info.abs[code] = ABSINFO.unpack(bytes(io.ioctl(fd, EVIOCGABS(code), bytearray(24))))
    return info


def _event_nodes(io):
    try:
        names = io.listdir(io.input_dir)
    except OSError:
        return []
    nodes = [n for n in names if n.startswith("event") and n[5:].isdigit()]
    return [os.path.join(io.input_dir, n) for n in sorted(nodes, key=lambda n: int(n[5:]))]


def find_gamepad(io, name=None):
    """(ruta, DevInfo) del mando de la consola: el primero con botones de mando y
    stick; se prefiere el integrado (bus HOST) o el que tenga el nombre pedido."""
    found = []
    for path in _event_nodes(io):
        try:
            fd = io.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            info = probe(io, fd)
        except OSError:
            continue
        finally:
            io.close(fd)
        if info.is_gamepad():
            found.append((path, info))
    if not found:
        return None, None

    def score(item):
        info = item[1]
        return (bool(name) and info.name == name, info.id[0] == BUS_HOST)

    return max(found, key=score)  # max() se queda con el primero si empatan


def create_virtual(io, info, neutral):
    """Crea el mando virtual (API clasica de uinput: vale para el kernel 4.4)."""
    fd = io.open(io.uinput, os.O_WRONLY | os.O_NONBLOCK)
    try:
        setbits = {EV_KEY: UI_SET_KEYBIT, EV_ABS: UI_SET_ABSBIT, EV_MSC: UI_SET_MSCBIT,
                   EV_SW: UI_SET_SWBIT}
        for ev in info.evbits:
            if ev == EV_SYN or ev in setbits:
                io.ioctl(fd, UI_SET_EVBIT, ev)
        for ev, req in setbits.items():
            for code in info.bits.get(ev, ()):
                io.ioctl(fd, req, code)
        for opt_req, arg in [(UI_SET_PROPBIT, p) for p in info.props] + \
                [(UI_SET_PHYS, PHYS.encode("ascii") + b"\0")]:
            try:
                io.ioctl(fd, opt_req, arg)
            except OSError:
                pass  # kernels antiguos: no es imprescindible
        absmax, absmin, absfuzz, absflat = ([0] * ABS_CNT for _ in range(4))
        for code, (_v, lo, hi, fuzz, flat, _res) in info.abs.items():
            absmin[code], absmax[code], absfuzz[code], absflat[code] = lo, hi, fuzz, flat
        io.write(fd, USER_DEV.pack(info.name.encode("utf-8")[:79], info.id[0], info.id[1],
                                   info.id[2], info.id[3], 0,
                                   *(absmax + absmin + absfuzz + absflat)))
        io.ioctl(fd, UI_DEV_CREATE)
        # estado inicial: el stick anulado en el centro, el resto como esta
        out = b"".join(EVENT.pack(0, 0, EV_ABS, code,
                                  info.center(code) if code in neutral else v[0])
                       for code, v in sorted(info.abs.items()))
        io.write(fd, out + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
        return fd
    except Exception:
        io.close(fd)
        raise


def filter_events(data, neutral):
    """Eventos del mando real -> los que recibe el virtual."""
    out = []
    n = EVENT.size
    for off in range(0, len(data) - n + 1, n):
        _s, _u, typ, code, val = EVENT.unpack_from(data, off)
        if typ == EV_ABS and code in neutral:
            continue
        if typ == EV_SYN and code == SYN_DROPPED:
            continue
        out.append(EVENT.pack(0, 0, typ, code, val))
    return b"".join(out)


def hide(io, path):
    """Aparta el archivo del mando real para que nadie mas lo abra."""
    io.makedirs(io.hide_dir)
    dst = os.path.join(io.hide_dir, os.path.basename(path))
    io.rename(path, dst)
    return dst


def restore(io):
    """Devuelve a /dev/input los mandos apartados. Devuelve cuantos."""
    try:
        names = io.listdir(io.hide_dir)
    except OSError:
        return 0
    n = 0
    for name in names:
        src = os.path.join(io.hide_dir, name)
        dst = os.path.join(io.input_dir, name)
        try:
            if not io.exists(dst):
                io.rename(src, dst)
                n += 1
        except OSError:
            pass
    try:
        io.rmdir(io.hide_dir)
    except OSError:
        pass
    return n


def notify_ready():
    """Avisa a systemd (Type=notify) de que el mando virtual ya existe."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr[0] == "@":
        addr = "\0" + addr[1:]
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(addr)
            s.sendall(b"READY=1")
        finally:
            s.close()
    except OSError:
        pass


def restart_hotkey_daemon(proc="/proc", run=None):
    """ogage (volumen y brillo con HOTKEY) abre los mandos al arrancar: se reinicia
    para que lea el virtual. Devuelve lo que se hizo (para el registro)."""
    run = run or (lambda cmd: subprocess.call(cmd, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL))
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return ""
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "comm")) as f:
                comm = f.read().strip()
        except (IOError, OSError):
            continue
        if comm not in HOTKEY_DAEMONS:
            continue
        unit = ""
        try:
            with open(os.path.join(proc, pid, "cgroup")) as f:
                for line in f:
                    last = line.strip().rsplit("/", 1)[-1]
                    if last.endswith(".service") and "oga" in last:
                        unit = last
        except (IOError, OSError):
            pass
        if unit:
            # --no-block: si ogage se ordena detras de ES (y ES detras de nosotros)
            # esperar aqui bloquearia el arranque
            run(["systemctl", "--no-block", "restart", unit])
            return "reiniciado %s" % unit
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                cmd = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
            os.kill(int(pid), signal.SIGTERM)
            time.sleep(0.3)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return "relanzado %s" % " ".join(cmd)
        except (IOError, OSError, ValueError) as e:
            return "no se pudo reiniciar %s: %s" % (comm, e)
    return ""


def write_status(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.chmod(tmp, 0o644)
        os.rename(tmp, path)
    except (IOError, OSError):
        pass


def remove_status(path):
    try:
        os.remove(path)
    except OSError:
        pass


class _Stop(Exception):
    pass


def _on_signal(signum, frame):
    raise _Stop()


def run(io, mode, log, status_path=STATUS, device_name=None, ready=notify_ready,
        hotkeys=restart_hotkey_daemon):
    """Hace el trabajo hasta que llegue una senal. Devuelve el codigo de salida."""
    restore(io)  # restos de una ejecucion anterior
    if mode not in STICKS:
        log("stick anulado: ninguno, nada que hacer")
        return 0
    path, info = find_gamepad(io, device_name)
    if path is None:
        log("ERROR: no se encontro el mando de la consola en %s" % io.input_dir)
        return 1
    neutral = [c for c in STICKS[mode] if c in info.abs]
    if not neutral:
        log("ERROR: el mando '%s' no tiene ese stick" % info.name)
        return 1
    src = io.open(path, os.O_RDONLY)
    dst = None
    hidden = None
    try:
        io.ioctl(src, EVIOCGRAB, 1)
        dst = create_virtual(io, info, neutral)
        try:
            hidden = hide(io, path)
        except OSError as e:
            log("aviso: no se pudo apartar %s (%s)" % (path, e))
        log("mando '%s' (%s): stick %s anulado; ejes al empezar %s" % (
            info.name, path, mode, {k: v[:3] for k, v in info.abs.items()}))
        ready()
        done = hotkeys()
        if done:
            log("teclas rapidas: %s" % done)
        write_status(status_path, {"pid": os.getpid(), "stick": mode, "path": path,
                                   "hidden": bool(hidden), "since": int(time.time()),
                                   "device": info.to_dict()})
        while True:
            data = io.read(src, EVENT.size * 64)
            if not data:
                raise OSError(errno.ENODEV, "el mando desaparecio")
            out = filter_events(data, neutral)
            if out:
                io.write(dst, out)
    except _Stop:
        log("parado")
        return 0
    except OSError as e:
        log("ERROR: %s" % e)
        return 1
    finally:
        restore(io)
        if dst is not None:
            try:
                io.ioctl(dst, UI_DEV_DESTROY)
            except OSError:
                pass
            io.close(dst)
        try:
            io.ioctl(src, EVIOCGRAB, 0)
        except OSError:
            pass
        io.close(src)
        remove_status(status_path)


def wait_confirm(io, seconds, status_path=STATUS):
    """Espera a que se pulse un boton del mando virtual: asi se comprueba que la
    consola sigue teniendo mando. True si se pulso a tiempo."""
    end = time.time() + seconds
    path = None
    while path is None and time.time() < end:
        try:
            with open(status_path) as f:
                json.load(f)
            for p in _event_nodes(io):
                try:
                    fd = io.open(p, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    continue
                try:
                    if probe(io, fd).phys == PHYS:
                        path = p
                finally:
                    io.close(fd)
        except (IOError, OSError, ValueError):
            pass
        if path is None:
            time.sleep(0.2)
    if path is None:
        return False
    import select
    fd = io.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        while True:
            left = end - time.time()
            if left <= 0:
                return False
            r, _w, _x = select.select([fd], [], [], left)
            if not r:
                continue
            try:
                data = io.read(fd, EVENT.size * 64)
            except OSError:
                continue
            n = EVENT.size
            for off in range(0, len(data) - n + 1, n):
                _s, _u, typ, _code, val = EVENT.unpack_from(data, off)
                if typ == EV_KEY and val == 1:
                    return True
    finally:
        io.close(fd)


def make_logger(path):
    def log(msg):
        line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
        sys.stdout.write(line)
        sys.stdout.flush()
        if not path:
            return
        try:
            if os.path.getsize(path) > 64 * 1024:
                os.rename(path, path + ".old")
        except OSError:
            pass
        try:
            with open(path, "a") as f:
                f.write(line)
        except (IOError, OSError):
            pass
    return log


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Anula un stick analogico averiado")
    ap.add_argument("--config", help="archivo con: izquierdo, derecho o ambos")
    ap.add_argument("--stick", choices=sorted(STICKS), help="sin usar archivo")
    ap.add_argument("--device", help="nombre del mando (por defecto, el integrado)")
    ap.add_argument("--log", help="registro (por defecto, stickfix.log junto a --config)")
    ap.add_argument("--restore", action="store_true", help="solo deshacer lo hecho")
    ap.add_argument("--confirm", type=int, metavar="SEG",
                    help="esperar a que se pulse un boton del mando virtual")
    args = ap.parse_args(argv)
    if args.confirm:
        return 0 if wait_confirm(Sys(), args.confirm) else 1
    log_path = args.log or (os.path.join(os.path.dirname(args.config), "stickfix.log")
                            if args.config else None)
    log = make_logger(log_path)
    io = Sys()
    if args.restore:
        n = restore(io)
        if n:
            log("restaurados %d mandos apartados" % n)
        remove_status(STATUS)
        return 0
    mode = args.stick or (read_mode(args.config) if args.config else "off")
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, _on_signal)
    return run(io, mode, log, device_name=args.device)


if __name__ == "__main__":
    sys.exit(main())
