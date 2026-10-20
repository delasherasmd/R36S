"""Fecha, hora y zona horaria (sin tocar el reloj de verdad)."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

import system  # noqa: E402
from system import CLOCK_FLOOR, Clock, fmt_offset, zone_label, zone_offset  # noqa: E402

ZI = system.ZONEINFO
HAVE_TZDATA = os.path.isfile(os.path.join(ZI, "America/Argentina/Buenos_Aires"))
ROUTE_HEAD = "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"


class FakeRun(object):
    """Hace de 'sudo': apunta los comandos y simula ln/date/hwclock."""

    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        if not self.ok:
            return False
        if cmd[0] == "ln":
            dst = cmd[-1]
            if os.path.lexists(dst):
                os.remove(dst)
            os.symlink(cmd[-2], dst)
            return True
        return cmd[0] in ("date", "hwclock")

    def names(self):
        return [c[0] for c in self.calls]


class OffsetTest(unittest.TestCase):
    def test_fmt_offset(self):
        self.assertEqual(fmt_offset(0), "UTC")
        self.assertEqual(fmt_offset(-10800), "UTC-3")
        self.assertEqual(fmt_offset(3600), "UTC+1")
        self.assertEqual(fmt_offset(19800), "UTC+5:30")
        self.assertEqual(fmt_offset(-34200), "UTC-9:30")

    def test_labels(self):
        self.assertEqual(zone_label("America/Argentina/Buenos_Aires"), "Argentina")
        self.assertEqual(zone_label("America/Argentina/Buenos_Aires", "en"), "Buenos Aires")
        self.assertEqual(zone_label("Etc/GMT+3", "es", "%s fija"), "UTC-3 fija")
        self.assertEqual(zone_label("Etc/GMT-14"), "UTC+14")
        self.assertEqual(zone_label("Pacific/Port_Moresby"), "Port Moresby")
        self.assertEqual(len(system.FIXED_ZONES), 26)

    @unittest.skipUnless(HAVE_TZDATA, "sin tzdata")
    def test_zone_offset_restores_tz(self):
        before = time.localtime(1e9).tm_gmtoff
        self.assertEqual(zone_offset("America/Argentina/Buenos_Aires", 1.8e9), -10800)
        self.assertEqual(zone_offset("Etc/GMT+3"), -10800)
        # Madrid: +1 en invierno, +2 en verano
        self.assertEqual(zone_offset("Europe/Madrid", 1768000000), 3600)
        self.assertEqual(zone_offset("Europe/Madrid", 1784000000), 7200)
        self.assertEqual(time.localtime(1e9).tm_gmtoff, before)
        self.assertNotIn("TZ", os.environ)


class ClockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.localtime = os.path.join(self.tmp, "localtime")
        self.tzfile = os.path.join(self.tmp, "timezone")
        self.route = os.path.join(self.tmp, "route")
        self.rtc = os.path.join(self.tmp, "rtc0")
        self.state = os.path.join(self.tmp, "clock_saved")
        self.run = FakeRun()
        self.fetched = []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def clock(self, fetch=None):
        return Clock(self.state, ZI, self.localtime, self.tzfile, self.rtc, self.route,
                     run=self.run, fetch=fetch)

    def online(self, on=True):
        with open(self.route, "w") as f:
            f.write(ROUTE_HEAD)
            if on:
                f.write("wlan0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\n")
            f.write("wlan0\t0001A8C0\t00000000\t0001\t0\t0\t600\t00FFFFFF\n")

    @unittest.skipUnless(HAVE_TZDATA, "sin tzdata")
    def test_zone_detection_and_change(self):
        c = self.clock()
        self.assertEqual(c.zone(), "")
        os.symlink(os.path.join(ZI, "Etc/UTC"), self.localtime)
        with open(self.tzfile, "w") as f:
            f.write("Etc/UTC\n")
        self.assertEqual(c.zone(), "Etc/UTC")
        os.remove(self.localtime)
        os.symlink(os.path.join(ZI, "UTC"), self.localtime)
        self.assertEqual(c.zone(), "Etc/UTC")  # mismo reloj, un solo nombre
        self.assertEqual([z[0] for z in c.zones()].count("Etc/UTC"), 1)
        self.assertTrue(c.set_zone("America/Argentina/Buenos_Aires"))
        self.assertEqual(c.zone(), "America/Argentina/Buenos_Aires")
        # primero timedatectl, y si no cambio nada, el enlace de /etc/localtime
        self.assertEqual(self.run.names(), ["timedatectl", "ln"])
        with open(self.tzfile) as f:
            self.assertEqual(f.read().strip(), "America/Argentina/Buenos_Aires")
        # zonas inventadas o con '..' no se aceptan
        self.assertFalse(c.set_zone("Marte/Olympus"))
        self.assertFalse(c.set_zone("../../etc/passwd"))
        self.assertEqual(c.zone(), "America/Argentina/Buenos_Aires")

    @unittest.skipUnless(HAVE_TZDATA, "sin tzdata")
    def test_zone_from_timezone_file_and_relative_link(self):
        c = self.clock()
        with open(self.tzfile, "w") as f:
            f.write("Europe/Madrid\n")
        self.assertEqual(c.zone(), "Europe/Madrid")
        os.symlink("../usr/share/zoneinfo/posix/America/Lima", self.localtime)
        self.assertEqual(c.zone(), "America/Lima")

    @unittest.skipUnless(HAVE_TZDATA, "sin tzdata")
    def test_zone_list(self):
        os.symlink(os.path.join(ZI, "Africa/Nairobi"), self.localtime)
        zones = self.clock().zones("es", "%s fija")
        names = [z[0] for z in zones]
        # la zona actual aparece aunque no este en la lista
        self.assertEqual(names[0], "Africa/Nairobi")
        labels = [z[1] for z in zones]
        self.assertIn("Argentina", labels)
        self.assertLess(labels.index("España"), labels.index("Uruguay"))
        self.assertLess(labels.index("Perú"), labels.index("Puerto Rico"))
        arg = zones[names.index("America/Argentina/Buenos_Aires")]
        self.assertEqual(arg[2], -10800)
        fixed = [z for z in zones if z[0].startswith("Etc/GMT")]
        self.assertEqual(fixed[0][1], "UTC-12 fija")
        self.assertEqual(fixed[-1][1], "UTC+14 fija")

    def test_set_time_uses_utc_and_rtc(self):
        c = self.clock()
        t = 1792500000  # 2026-10-20 ...
        self.assertTrue(c.set_time(t))
        self.assertEqual(self.run.calls, [["date", "-u", "-s", "2026-10-20 12:40:00"]])
        self.assertEqual(c.saved(), t)
        open(self.rtc, "w").close()
        self.assertTrue(c.set_time(t + 60))
        self.assertEqual(self.run.calls[-1], ["hwclock", "-w"])
        self.run.ok = False
        self.assertFalse(c.set_time(t))
        self.assertEqual(c.saved(), t + 60)

    def test_restore_after_power_loss(self):
        c = self.clock()
        good = CLOCK_FLOOR + 86400 * 290
        # con la hora bien no se toca nada
        self.assertFalse(c.restore_if_reset())
        c.save(good)
        with mock.patch("system.time.time", return_value=1560000000.0):  # 2019
            self.assertTrue(c.looks_wrong())
            # una hora imposible nunca se guarda encima de la buena
            c.save()
            self.assertEqual(c.saved(), good)
            self.assertTrue(c.restore_if_reset())
        self.assertEqual(self.run.calls[0][:3], ["date", "-u", "-s"])
        with open(self.state, "w") as f:
            f.write("basura\n")
        with mock.patch("system.time.time", return_value=1560000000.0):
            self.assertFalse(c.restore_if_reset())

    def test_sync(self):
        now = time.time()
        c = self.clock(fetch=lambda: now + 3600)
        self.online(False)
        self.assertEqual(c.sync(), (False, "sync_offline", 0))
        self.assertEqual(self.run.calls, [])
        self.online(True)
        ok, key, diff = c.sync()
        self.assertTrue(ok)
        self.assertEqual(key, "sync_ok")
        self.assertAlmostEqual(diff, 3600, delta=5)
        self.assertEqual(self.run.names(), ["date"])
        # ya en hora: no hace falta sudo
        c.fetch = lambda: time.time()
        self.assertTrue(c.sync()[0])
        self.assertEqual(self.run.names(), ["date"])
        c.fetch = lambda: None
        self.assertEqual(c.sync()[:2], (False, "sync_noresp"))
        c.fetch = lambda: time.time() - 7200
        self.run.ok = False
        self.assertEqual(c.sync()[:2], (False, "sync_noperm"))

    def test_sync_async_waits_for_wifi(self):
        c = self.clock(fetch=lambda: time.time() + 600)
        self.online(False)
        done = threading.Event()
        res = []

        def cb(r):
            res.append(r)
            done.set()

        with mock.patch("system.time.sleep", side_effect=lambda s: self.online(True)):
            self.assertTrue(c.sync_async(cb, wait_online=30))
            self.assertFalse(c.sync_async(cb))  # ya hay una en marcha
            self.assertTrue(done.wait(10))
        self.assertTrue(res[0][0])
        self.assertFalse(c.syncing)
        self.assertEqual(c.last_sync, res[0])


class HttpTimeTest(unittest.TestCase):
    def test_reads_date_header(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self.send_response(204)
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever)
        t.daemon = True
        t.start()
        try:
            url = "http://127.0.0.1:%d/" % srv.server_address[1]
            with mock.patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}):
                got = system.http_time(("http://127.0.0.1:1/", url), timeout=3)
            self.assertIsNotNone(got)
            self.assertAlmostEqual(got, time.time(), delta=3)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
