"""Anular stick: el demonio con un sistema falso (mando de la R36S trabado arriba)."""
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

import stickfix as S  # noqa: E402

BTN_SOUTH, BTN_EAST, BTN_DPAD_UP, BTN_TRIGGER_HAPPY5 = 0x130, 0x131, 0x220, 0x2c4
KEY_POWER = 116


def ev(typ, code, val):
    return S.EVENT.pack(1, 2, typ, code, val)


def unpack_all(data):
    n = S.EVENT.size
    return [S.EVENT.unpack_from(data, o)[2:] for o in range(0, len(data), n)]


class FakeDev(object):
    def __init__(self, name, phys, ident, keys, absinfo=None):
        self.name, self.phys, self.id = name, phys, ident
        self.keys = keys
        self.abs = absinfo or {}
        self.evbits = [S.EV_SYN, S.EV_KEY] + ([S.EV_ABS] if self.abs else [])


def _setbits(buf, codes):
    for c in codes:
        buf[c // 8] |= 1 << (c % 8)


class FakeIO(S.Sys):
    def __init__(self, root, devs):
        self.input_dir = os.path.join(root, "input")
        self.hide_dir = os.path.join(root, ".anular-stick")
        self.uinput = os.path.join(root, "uinput")
        os.makedirs(self.input_dir)
        open(self.uinput, "w").close()
        self.devs = {}
        for node, d in devs.items():
            open(os.path.join(self.input_dir, node), "w").close()
            self.devs[node] = d
        self.fds = {}
        self.next = 10
        self.calls = []       # ioctls sobre uinput
        self.written = b""    # lo que llega al mando virtual
        self.grabbed = None
        self.reads = []

    def open(self, path, flags):
        if not os.path.exists(path):
            raise OSError(2, "no existe")
        self.next += 1
        self.fds[self.next] = path
        return self.next

    def close(self, fd):
        self.fds.pop(fd, None)

    def _dev(self, fd):
        return self.devs.get(os.path.basename(self.fds[fd]))

    def ioctl(self, fd, req, arg=0):
        if self.fds.get(fd) == self.uinput:
            self.calls.append((req, arg))
            return 0
        d = self._dev(fd)
        if req == S.EVIOCGRAB:
            self.grabbed = os.path.basename(self.fds[fd]) if arg else None
            return 0
        if req == S.EVIOCGNAME(256):
            arg[:len(d.name)] = d.name.encode()
        elif req == S.EVIOCGPHYS(256):
            arg[:len(d.phys)] = d.phys.encode()
        elif req == S.EVIOCGID:
            arg[:] = struct.pack("4H", *d.id)
        elif req == S.EVIOCGBIT(0, 4):
            _setbits(arg, d.evbits)
        elif req == S.EVIOCGBIT(S.EV_KEY, S.KEY_CNT // 8):
            _setbits(arg, d.keys)
        elif req == S.EVIOCGBIT(S.EV_ABS, S.ABS_CNT // 8):
            _setbits(arg, d.abs)
        elif req == S.EVIOCGPROP(S.PROP_CNT // 8):
            pass
        else:
            for code, info in d.abs.items():
                if req == S.EVIOCGABS(code):
                    arg[:] = S.ABSINFO.pack(*info)
                    break
            else:
                raise OSError(25, "ioctl desconocido %x" % req)
        return arg

    def read(self, fd, n):
        if not self.reads:
            raise S._Stop()
        item = self.reads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, fd, data):
        if self.fds.get(fd) == self.uinput:
            self.written += data
        return len(data)


def r36s_pad(y=-1800):
    a = (0, -1800, 1800, 0, 0, 0)
    return FakeDev("GO-Super Gamepad", "odroidgo3_joypad/input0", (S.BUS_HOST, 0x484B, 0x1101, 0x100),
                   [BTN_SOUTH, BTN_EAST, BTN_DPAD_UP, BTN_TRIGGER_HAPPY5],
                   {S.ABS_X: a, S.ABS_Y: (y, -1800, 1800, 0, 0, 0), S.ABS_RX: a, S.ABS_RY: a})


class StickfixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.io = FakeIO(self.tmp, {
            "event0": FakeDev("rk805 pwrkey", "rk805_pwrkey/input0", (0x19, 0, 0, 0), [KEY_POWER]),
            "event2": r36s_pad(),
            "event10": FakeDev("USB pad", "usb-1/input0", (0x03, 1, 2, 3),
                               [BTN_SOUTH], {S.ABS_X: (0, 0, 255, 0, 0, 0),
                                             S.ABS_Y: (0, 0, 255, 0, 0, 0)}),
        })
        self.status = os.path.join(self.tmp, "status.json")
        self.logs = []
        self.ready = []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_daemon(self, mode="left"):
        return S.run(self.io, mode, self.logs.append, self.status,
                     ready=lambda: self.ready.append(self.io.grabbed),
                     hotkeys=lambda: "")

    def test_mode_words(self):
        self.assertEqual(S.parse_mode("# comentario\n  Izquierdo \n"), "left")
        self.assertEqual(S.parse_mode("derecho"), "right")
        self.assertEqual(S.parse_mode("ambos"), "both")
        self.assertEqual(S.parse_mode("cualquier cosa"), "off")
        self.assertEqual(S.parse_mode(""), "off")

    def test_finds_builtin_pad(self):
        path, info = S.find_gamepad(self.io)
        self.assertEqual(os.path.basename(path), "event2")
        self.assertEqual(info.name, "GO-Super Gamepad")
        self.assertEqual(info.abs[S.ABS_Y][:3], (-1800, -1800, 1800))
        # con el nombre se puede elegir otro
        path, _ = S.find_gamepad(self.io, "USB pad")
        self.assertEqual(os.path.basename(path), "event10")

    def test_filters_stuck_stick_and_restores(self):
        self.io.reads = [
            ev(S.EV_ABS, S.ABS_Y, -1790) + ev(S.EV_SYN, 0, 0),
            ev(S.EV_KEY, BTN_SOUTH, 1) + ev(S.EV_ABS, S.ABS_RX, 900) + ev(S.EV_SYN, 0, 0),
            ev(S.EV_ABS, S.ABS_X, 50) + ev(S.EV_SYN, S.SYN_DROPPED, 0),
        ]
        self.assertEqual(self.run_daemon("left"), 0)
        # el virtual se crea igual que el real
        reqs = [r for r, _a in self.io.calls]
        self.assertIn((S.UI_SET_EVBIT, S.EV_ABS), self.io.calls)
        self.assertIn((S.UI_SET_KEYBIT, BTN_TRIGGER_HAPPY5), self.io.calls)
        self.assertIn((S.UI_SET_ABSBIT, S.ABS_RY), self.io.calls)
        self.assertIn((S.UI_SET_PHYS, b"anular-stick/input0\0"), self.io.calls)
        self.assertEqual(reqs[-2:], [S.UI_DEV_CREATE, S.UI_DEV_DESTROY])
        dev = S.USER_DEV.unpack(self.io.written[:S.USER_DEV.size])
        self.assertEqual(dev[0].rstrip(b"\0"), b"GO-Super Gamepad")
        self.assertEqual(dev[1:5], (S.BUS_HOST, 0x484B, 0x1101, 0x100))
        absmax = dev[6:6 + 64]
        absmin = dev[6 + 64:6 + 128]
        self.assertEqual((absmin[S.ABS_Y], absmax[S.ABS_Y]), (-1800, 1800))
        events = unpack_all(self.io.written[S.USER_DEV.size:])
        # estado inicial: el stick izquierdo en el centro
        self.assertIn((S.EV_ABS, S.ABS_Y, 0), events[:5])
        self.assertNotIn((S.EV_ABS, S.ABS_Y, -1800), events)
        # despues: nada del stick izquierdo; botones y stick derecho, si
        rest = events[5:]
        self.assertIn((S.EV_KEY, BTN_SOUTH, 1), rest)
        self.assertIn((S.EV_ABS, S.ABS_RX, 900), rest)
        self.assertFalse([e for e in rest if e[0] == S.EV_ABS and e[1] in (S.ABS_X, S.ABS_Y)])
        self.assertNotIn((S.EV_SYN, S.SYN_DROPPED, 0), rest)
        # mientras funcionaba: real tomado en exclusiva y apartado
        self.assertEqual(self.ready, ["event2"])
        # al terminar todo vuelve a su sitio
        self.assertTrue(os.path.exists(os.path.join(self.io.input_dir, "event2")))
        self.assertFalse(os.path.exists(self.io.hide_dir))
        self.assertIsNone(self.io.grabbed)
        self.assertFalse(os.path.exists(self.status))
        self.assertEqual(self.io.fds, {})

    def test_hidden_while_running(self):
        seen = {}

        def check():
            seen["hidden"] = not os.path.exists(os.path.join(self.io.input_dir, "event2"))
            seen["grab"] = self.io.grabbed
        S.run(self.io, "both", self.logs.append, self.status, ready=check, hotkeys=lambda: "")
        self.assertEqual(seen, {"hidden": True, "grab": "event2"})

    def test_device_lost_exits_with_error_and_restores(self):
        self.io.reads = [OSError(19, "No such device")]
        self.assertEqual(self.run_daemon("right"), 1)
        self.assertTrue(os.path.exists(os.path.join(self.io.input_dir, "event2")))
        self.assertTrue(any("ERROR" in l for l in self.logs))

    def test_restore_leftovers_and_no_pad(self):
        S.hide(self.io, os.path.join(self.io.input_dir, "event2"))
        self.assertEqual(S.restore(self.io), 1)
        self.assertTrue(os.path.exists(os.path.join(self.io.input_dir, "event2")))
        io = FakeIO(os.path.join(self.tmp, "otro"), {"event0": FakeDev(
            "rk805 pwrkey", "x", (0x19, 0, 0, 0), [KEY_POWER])})
        self.assertEqual(S.run(io, "left", self.logs.append, self.status, ready=lambda: None,
                               hotkeys=lambda: ""), 1)
        self.assertEqual(S.run(io, "off", self.logs.append, self.status, ready=lambda: None,
                               hotkeys=lambda: ""), 0)

    def test_hotkey_daemon_restart(self):
        proc = os.path.join(self.tmp, "proc")
        for pid, comm, cg in (("1", "systemd", "0::/init.scope"),
                              ("77", "ogage", "1:name=systemd:/system.slice/ogage.service")):
            os.makedirs(os.path.join(proc, pid))
            for n, t in (("comm", comm + "\n"), ("cgroup", cg + "\n")):
                with open(os.path.join(proc, pid, n), "w") as f:
                    f.write(t)
        cmds = []
        self.assertEqual(S.restart_hotkey_daemon(proc, cmds.append), "reiniciado ogage.service")
        self.assertEqual(cmds, [["systemctl", "--no-block", "restart", "ogage.service"]])

    def test_boot_waits_for_card_and_falls_back(self):
        sys_conf = os.path.join(self.tmp, "opt", "stickfix.conf")
        card = os.path.join(self.tmp, "roms", "ports", "anularstick")
        os.makedirs(os.path.dirname(sys_conf))
        with open(sys_conf, "w") as f:
            f.write("izquierdo\n")
        user = os.path.join(card, "stickfix.conf")
        slept = []
        # la tarjeta no se monta: se usa la copia del sistema tras esperar
        mode, logp = S.resolve_mode(sys_conf, user, 5, slept.append)
        self.assertEqual((mode, len(slept)), ("left", 5))
        self.assertEqual(logp, os.path.join(self.tmp, "opt", "stickfix.log"))
        # la tarjeta se monta a los 2 s: manda su archivo
        os.makedirs(card)
        with open(user, "w") as f:
            f.write("derecho\n")
        calls = []

        def isdir(d):
            calls.append(d)
            return len(calls) > 2
        self.assertEqual(S.resolve_mode(sys_conf, user, 20, lambda s: None, isdir)[0], "right")
        self.assertEqual(len(calls), 4)
        # borrado desde el PC: se quita aunque quede la copia del sistema
        os.remove(user)
        self.assertEqual(S.resolve_mode(sys_conf, user, 20, slept.append)[0], "off")

    def test_waits_for_pad_at_boot(self):
        hidden = os.path.join(self.tmp, "tarde")
        os.remove(os.path.join(self.io.input_dir, "event10"))  # solo el integrado
        os.rename(os.path.join(self.io.input_dir, "event2"), hidden)
        ticks = []

        def sleep(_s):
            ticks.append(1)
            if len(ticks) == 3:  # el mando aparece al tercer segundo
                os.rename(hidden, os.path.join(self.io.input_dir, "event2"))
        self.assertEqual(S.run(self.io, "left", self.logs.append, self.status,
                               ready=lambda: None, hotkeys=lambda: "", wait=10, sleep=sleep), 0)
        self.assertEqual(len(ticks), 3)
        self.assertIn((S.UI_DEV_CREATE, 0), self.io.calls)

    def test_filter_events_alone(self):
        data = ev(S.EV_ABS, S.ABS_Y, -1800) + ev(S.EV_KEY, BTN_EAST, 0) + ev(S.EV_SYN, 0, 0)
        self.assertEqual(unpack_all(S.filter_events(data, (S.ABS_X, S.ABS_Y))),
                         [(S.EV_KEY, BTN_EAST, 0), (S.EV_SYN, 0, 0)])


class StickFixServiceTest(unittest.TestCase):
    """Lo que hace Vapor en Personalizar > Mando (sin tocar el sistema de verdad)."""

    def setUp(self):
        import system
        self.system = system
        self.tmp = tempfile.mkdtemp()
        self.app = os.path.join(self.tmp, "vapor")
        self.data = os.path.join(self.app, "data")
        os.makedirs(self.data)
        open(os.path.join(self.app, "stickfix.py"), "w").close()
        os.makedirs(os.path.join(self.tmp, "systemd"))
        self.unit = os.path.join(self.tmp, "anular-stick.service")
        self.status = os.path.join(self.tmp, "status.json")
        self.cmds = []
        self.daemon_ok = True

        def run(cmd, timeout=10):
            self.cmds.append(cmd)
            if cmd[:2] == ["systemctl", "restart"] and self.daemon_ok:
                with open(self.status, "w") as f:
                    f.write('{"pid": %d}' % os.getpid())
            if cmd[:2] == ["rm", "-f"]:
                os.remove(cmd[2])
            return True

        def write(path, text):
            with open(path, "w") as f:
                f.write(text)
            return True
        self.sf = system.StickFix(self.app, self.data, python="/usr/bin/python3",
                                  unit_path=self.unit, sys_dir=os.path.join(self.tmp, "opt"),
                                  status_path=self.status,
                                  systemd_dir=os.path.join(self.tmp, "systemd"),
                                  run=run, write=write)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_enable_and_disable(self):
        self.assertEqual(self.sf.status(), "off")
        self.assertEqual(self.sf.apply("left"), (True, ""))
        self.assertEqual(self.sf.mode(), "left")
        self.assertEqual(self.sf.status(), "active")
        with open(self.unit) as f:
            text = f.read()
        # la misma unidad que instala 'Anular stick' desde Ports, con la copia en /opt
        self.assertTrue(text.startswith("# anular-stick v2\n"))
        self.assertIn('--user-config "%s"' % self.sf.conf, text)
        self.assertNotIn("ConditionPathExists", text)
        self.assertIn(["systemctl", "enable", "anular-stick.service"], self.cmds)
        self.assertEqual(S.read_mode(self.sf.conf), "left")
        self.assertEqual(self.sf.apply("off"), (True, ""))
        self.assertEqual(self.sf.mode(), "off")
        self.assertFalse(os.path.exists(self.unit))
        self.assertIn(["systemctl", "disable", "--now", "anular-stick.service"], self.cmds)

    def test_daemon_that_does_not_start_is_reported(self):
        self.daemon_ok = False
        with open(self.sf.log_path, "w") as f:
            f.write("[x] ERROR: no se encontro el mando de la consola\n")
        ok, why = self.sf.apply("right")
        self.assertFalse(ok)
        self.assertIn("no se encontro el mando", why)
        self.assertEqual(self.sf.status(), "failed")


if __name__ == "__main__":
    unittest.main()
