"""Arranque en Vapor, brillo y temas."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

import system  # noqa: E402
import theme  # noqa: E402

# Parecido al emulationstation.sh real de ArkOS (simplificado)
ES_SH = """#!/bin/bash

export SDL_ASSERT="always_ignore"
esdir="$(dirname "$0")"
cd "$esdir"
while true; do
    rm -f /tmp/es-restart
    echo "ES" >> "$LOG"
    [ -f /tmp/es-restart ] && continue
    break
done
"""


class AutostartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.es = os.path.join(self.tmp, "emulationstation.sh")
        with open(self.es, "w") as f:
            f.write(ES_SH)
        self.data = os.path.join(self.tmp, "ports", "vapor", "data")
        os.makedirs(self.data)
        self.vapor = os.path.join(self.tmp, "ports", "Vapor.sh")
        # Vapor.sh falso: apunta cada ejecucion y si VAPOR_BOOT llega bien
        with open(self.vapor, "w") as f:
            f.write('#!/bin/bash\necho "boot=$VAPOR_BOOT" >> "%s/runs"\n' % self.tmp)
        self.done = "/dev/shm/vapor_boot_done"
        self._clean_done()

    def tearDown(self):
        self._clean_done()
        shutil.rmtree(self.tmp)

    def _clean_done(self):
        if os.path.exists(self.done):
            os.remove(self.done)

    def run_es(self):
        env = dict(os.environ, LOG=os.path.join(self.tmp, "es.log"))
        subprocess.run(["bash", self.es], env=env, check=True, timeout=20)

    def runs(self):
        p = os.path.join(self.tmp, "runs")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return f.read().split()

    def test_hook_text_roundtrip(self):
        block = system.hook_block(self.vapor, self.data)
        new = system.add_hook(ES_SH, block)
        self.assertTrue(new.startswith("#!/bin/bash\n" + system.BEGIN))
        self.assertEqual(system.add_hook(new, block), new)  # idempotente
        self.assertEqual(system.strip_hook(new), ES_SH)
        self.assertTrue(system._bash_ok(new))

    def test_paths_with_quotes_and_spaces(self):
        block = system.hook_block("/roms/ports/It's Vapor.sh", "/roms/ports/my data")
        self.assertTrue(system._bash_ok("#!/bin/bash\n" + block))

    def test_enable_boot_flow_and_disable(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        self.assertTrue(a.supported)
        self.assertFalse(a.enabled())
        ok, why = a.enable()
        self.assertTrue(ok, why)
        self.assertTrue(a.enabled())
        self.assertTrue(os.path.exists(self.es + ".vapor-backup"))
        # primer encendido: abre Vapor (con VAPOR_BOOT=1) y luego sigue ES
        self.run_es()
        self.assertEqual(self.runs(), ["boot=1"])
        with open(os.path.join(self.tmp, "es.log")) as f:
            self.assertEqual(f.read().strip(), "ES")
        # reiniciar ES en el mismo encendido: no vuelve a abrir Vapor
        self.run_es()
        self.assertEqual(self.runs(), ["boot=1"])
        # desactivar deja el script como estaba
        a.disable()
        with open(self.es) as f:
            self.assertEqual(f.read(), ES_SH)
        self.assertFalse(a.enabled())

    def test_safety_when_previous_boot_hung(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        a.enable()
        # un arranque anterior se quedo colgado antes de mostrar Vapor
        open(os.path.join(self.data, "boot_pending"), "w").close()
        self.run_es()
        self.assertEqual(self.runs(), [])  # va directo a EmulationStation
        self.assertFalse(os.path.exists(os.path.join(self.data, "autostart")))

    def test_flag_off_means_no_vapor(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        a.enable()
        a.disable(remove_hook=False)
        self.run_es()
        self.assertEqual(self.runs(), [])

    def test_unsupported_without_es_script(self):
        a = system.Autostart(self.vapor, self.data, scripts=["/no/existe.sh"])
        self.assertFalse(a.supported)
        self.assertEqual(a.enable(), (False, "no_es_script"))


class BacklightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make(self, name, cur, mx):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        with open(os.path.join(d, "brightness"), "w") as f:
            f.write("%d\n" % cur)
        with open(os.path.join(d, "max_brightness"), "w") as f:
            f.write("%d\n" % mx)
        return d

    def test_clone_with_other_backlight_name(self):
        # en algunos clones no se llama 'backlight' (EmulationStation no lo encuentra)
        d = self.make("pwm-backlight.0", 128, 255)
        bl = system.Backlight(self.tmp)
        self.assertTrue(bl.available)
        self.assertEqual(bl.get_percent(), 50)
        self.assertTrue(bl.set_percent(20))
        with open(os.path.join(d, "brightness")) as f:
            self.assertEqual(int(f.read()), 51)
        bl.set_percent(0)  # nunca deja la pantalla negra
        with open(os.path.join(d, "brightness")) as f:
            self.assertGreater(int(f.read()), 0)

    def test_no_backlight(self):
        bl = system.Backlight(os.path.join(self.tmp, "nada"))
        self.assertFalse(bl.available)
        self.assertIsNone(bl.get_percent())


class ThemeTest(unittest.TestCase):
    def tearDown(self):
        theme.apply()

    def test_all_presets_and_accents(self):
        for key, _n, top, bottom, bar, acc in theme.PRESETS:
            theme.apply(key)
            self.assertEqual(theme.BG_TOP[:3], top)
            self.assertEqual(theme.ACCENT[:3], acc)
            for akey, _an, color in theme.ACCENTS:
                theme.apply(key, akey)
                if color is not None:
                    self.assertEqual(theme.ACCENT[:3], color)
                self.assertEqual(len(theme.DIALOG), 4)

    def test_cycle_and_unknown_values(self):
        self.assertEqual(theme.cycle(theme.PRESETS, "steam", 1), theme.PRESETS[1][0])
        self.assertEqual(theme.cycle(theme.PRESETS, "steam", -1), theme.PRESETS[-1][0])
        theme.apply("no-existe", "tampoco", "x")
        self.assertEqual(theme.BG_TOP[:3], theme.PRESETS[0][2])
        theme.apply(tile_size="large")
        self.assertEqual(theme.TILE_MIN, 140)


if __name__ == "__main__":
    unittest.main()
