"""Prueba del bucle de Vapor.sh: lanzar juego, apuntar tiempo y volver a abrir Vapor."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "ports", "Vapor.sh")

FAKE_MAIN = r'''
import os, sys
data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
count_file = os.path.join(data, "runs")
n = int(open(count_file).read()) if os.path.exists(count_file) else 0
open(count_file, "w").write(str(n + 1))
launch = os.environ["VAPOR_LAUNCH"]
if n == 0:
    # primera vez: el usuario elige un juego
    open(launch + ".rom", "w").write("/roms/gba/Golden Sun.gba\n")
    open(launch, "w").write("echo jugando > '%s/played'; sleep 1\n" % data)
sys.exit(0)
'''


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ports = os.path.join(self.tmp, "ports")
        os.makedirs(os.path.join(self.ports, "vapor", "data"))
        shutil.copy(SCRIPT, os.path.join(self.ports, "Vapor.sh"))
        os.chmod(os.path.join(self.ports, "Vapor.sh"), stat.S_IRWXU)
        with open(os.path.join(self.ports, "vapor", "main.py"), "w") as f:
            f.write(FAKE_MAIN)

    def tearDown(self):
        shutil.rmtree(self.tmp)
        for p in ("/dev/shm/vapor_launch.cmd", "/dev/shm/vapor_launch.cmd.rom"):
            if os.path.exists(p):
                os.remove(p)

    def test_loop(self):
        r = subprocess.run(["bash", os.path.join(self.ports, "Vapor.sh")], timeout=30,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = os.path.join(self.ports, "vapor", "data")
        with open(os.path.join(data, "runs")) as f:
            self.assertEqual(f.read(), "2")  # se volvio a abrir tras el juego
        self.assertTrue(os.path.exists(os.path.join(data, "played")))
        with open(os.path.join(data, "history.log")) as f:
            line = f.read().strip().split("\t")
        self.assertEqual(line[2], "/roms/gba/Golden Sun.gba")
        self.assertGreaterEqual(int(line[1]), 1)


if __name__ == "__main__":
    unittest.main()
