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

# Parecido al emulationstation.sh real de ArkOS (simplificado): primero prepara
# el sistema y quita la pantalla de carga (plymouth), luego lanza ES en bucle.
ES_SH = """#!/bin/bash

export SDL_ASSERT="always_ignore"
esdir="$(dirname "$0")"
cd "$esdir"
echo "splash-hidden" >> "$LOG"
while true; do
    rm -f /tmp/es-restart-vapor-test
    ./emulationstation "$@"
    [ -f /tmp/es-restart-vapor-test ] && continue
    break
done
"""

# Sin linea reconocible que lance ES: el bloque va arriba
ES_SH_UNKNOWN = """#!/bin/bash
echo "splash-hidden" >> "$LOG"
run_frontend
"""

FAKE_ES = '#!/bin/bash\necho "ES" >> "$LOG"\n'


class AutostartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.es = os.path.join(self.tmp, "emulationstation.sh")
        with open(self.es, "w") as f:
            f.write(ES_SH)
        fake = os.path.join(self.tmp, "emulationstation")
        with open(fake, "w") as f:
            f.write(FAKE_ES)
        os.chmod(fake, 0o755)
        self.data = os.path.join(self.tmp, "ports", "vapor", "data")
        os.makedirs(self.data)
        self.vapor = os.path.join(self.tmp, "ports", "Vapor.sh")
        # Vapor.sh falso: apunta cada ejecucion y si VAPOR_BOOT llega bien
        with open(self.vapor, "w") as f:
            f.write('#!/bin/bash\necho "VAPOR boot=$VAPOR_BOOT" >> "$LOG"\nexit ${VAPOR_RC:-0}\n')
        self.done = "/dev/shm/vapor_boot_done"
        self._clean_done()

    def tearDown(self):
        self._clean_done()
        shutil.rmtree(self.tmp)

    def _clean_done(self):
        if os.path.exists(self.done):
            os.remove(self.done)

    def run_es(self, **env):
        e = dict(os.environ, LOG=os.path.join(self.tmp, "es.log"))
        e.update(env)
        subprocess.run(["bash", self.es], env=e, check=True, timeout=20)

    def log(self):
        p = os.path.join(self.tmp, "es.log")
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [l.strip() for l in f]

    def boot_log(self):
        p = os.path.join(self.data, "boot.log")
        with open(p) as f:
            return f.read()

    def test_hook_goes_right_before_es_launch(self):
        new = system.add_hook(ES_SH, self.vapor, self.data)
        lines = new.splitlines()
        i_hook = next(i for i, l in enumerate(lines) if system.BEGIN in l)
        i_es = next(i for i, l in enumerate(lines) if l.strip().startswith("./emulationstation"))
        i_splash = next(i for i, l in enumerate(lines) if "splash-hidden" in l)
        self.assertLess(i_splash, i_hook)
        self.assertLess(i_hook, i_es)
        self.assertTrue(lines[i_hook].startswith("    "))  # misma sangria que la linea de ES
        self.assertEqual(system.add_hook(new, self.vapor, self.data), new)  # idempotente
        self.assertEqual(system.strip_hook(new), ES_SH)
        self.assertTrue(system._bash_ok(new))

    def test_fallback_to_top_when_no_launch_line(self):
        new = system.add_hook(ES_SH_UNKNOWN, self.vapor, self.data)
        self.assertTrue(new.startswith("#!/bin/bash\n" + system.BEGIN))
        self.assertIn("plymouth hide-splash", new)
        self.assertEqual(system.strip_hook(new), ES_SH_UNKNOWN)

    def test_launch_line_detection(self):
        lines = ["cd /usr/bin/emulationstation\n", "  ./emulationstation \"$@\"\n",
                 "\"$esdir/emulationstation\" --no-splash\n",
                 "sudo kill $(pidof emulationstation)\n",
                 "/usr/bin/emulationstation/emulationstation.sh &\n",
                 "# ./emulationstation\n",
                 "  nice -n -19 /usr/bin/emulationstation/emulationstation --x\n",
                 "    emulationstation \"$@\"\n",
                 "systemctl restart emulationstation\n",
                 "killall emulationstation\n"]
        self.assertEqual(system._launch_lines(lines), [1, 2, 6, 7])

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
        # primer encendido: ArkOS prepara todo, abre Vapor y luego sigue ES
        self.run_es()
        self.assertEqual(self.log(), ["splash-hidden", "VAPOR boot=1", "ES"])
        self.assertIn("abriendo Vapor", self.boot_log())
        self.assertIn("codigo 0)", self.boot_log())
        # reiniciar ES en el mismo encendido: no vuelve a abrir Vapor
        self.run_es()
        self.assertEqual(self.log()[3:], ["splash-hidden", "ES"])
        # desactivar deja el script como estaba
        a.disable()
        with open(self.es) as f:
            self.assertEqual(f.read(), ES_SH)
        self.assertFalse(a.enabled())

    def test_failed_boot_is_logged(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        a.enable()
        self.run_es(VAPOR_RC="3")
        self.assertIn("codigo 3)", a.last_boot())
        self.assertEqual(self.log()[-1], "ES")  # siempre acaba en EmulationStation

    def test_safety_when_previous_boot_hung(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        a.enable()
        # un arranque anterior se quedo colgado antes de mostrar Vapor
        open(os.path.join(self.data, "boot_pending"), "w").close()
        self.run_es()
        self.assertEqual(self.log(), ["splash-hidden", "ES"])  # directo a EmulationStation
        self.assertFalse(os.path.exists(os.path.join(self.data, "autostart")))
        self.assertIn("desactivado", a.last_boot())

    def test_flag_off_means_no_vapor(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        a.enable()
        a.disable(remove_hook=False)
        self.run_es()
        self.assertEqual(self.log(), ["splash-hidden", "ES"])

    def test_old_hook_is_updated(self):
        # bloque v1 (version anterior): arriba del todo y sin quitar la pantalla de carga
        old = ("#!/bin/bash\n# >>> VAPOR-AUTOSTART (viejo)\nif false; then :; fi\n"
               "# <<< VAPOR-AUTOSTART\n" + ES_SH.split("\n", 1)[1])
        with open(self.es, "w") as f:
            f.write(old)
        open(os.path.join(self.data, "autostart"), "w").close()
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        self.assertTrue(a.needs_update())
        ok, _why = a.enable()
        self.assertTrue(ok)
        self.assertFalse(a.needs_update())
        with open(self.es) as f:
            text = f.read()
        self.assertEqual(text.count(system.BEGIN), 1)
        self.run_es()
        self.assertEqual(self.log(), ["splash-hidden", "VAPOR boot=1", "ES"])

    def test_install_replaces_file_safely(self):
        # ArkOS esta ejecutando emulationstation.sh mientras se modifica: hay que
        # crear un archivo nuevo (otro inodo) y conservar los permisos
        os.chmod(self.es, 0o755)
        before = os.stat(self.es)
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        ok, why = a.enable()
        self.assertTrue(ok, why)
        after = os.stat(self.es)
        self.assertNotEqual(before.st_ino, after.st_ino)
        self.assertEqual(after.st_mode & 0o7777, 0o755)
        self.assertFalse(os.path.exists(self.es + ".vapor-new"))
        with open(self.es + ".vapor-backup") as f:
            self.assertEqual(f.read(), ES_SH)

    def test_status_and_diagnostics(self):
        a = system.Autostart(self.vapor, self.data, scripts=[self.es])
        self.assertEqual(a.status(), "off")
        a.enable()
        self.assertEqual(a.status(), "waiting")
        self.run_es()
        self.assertEqual(a.status(), "ok")
        self._clean_done()
        self.run_es(VAPOR_RC="3")
        self.assertEqual(a.status(), "failed")
        diag = os.path.join(self.data, "diagnostico.txt")
        self.assertTrue(system.write_diagnostics(diag, a, ["extra de prueba"]))
        with open(diag) as f:
            text = f.read()
        for part in ("extra de prueba", "marca 'autostart' (opcion activada): True",
                     "bloque Vapor en lineas [", "lineas que abren ES: [", "---- boot.log",
                     "codigo 3)", "---- systemctl cat emulationstation", "./emulationstation"):
            self.assertIn(part, text)

    def test_unsupported_without_es_script(self):
        a = system.Autostart(self.vapor, self.data, scripts=["/no/existe.sh"])
        self.assertFalse(a.supported)
        self.assertEqual(a.enable(), (False, "no_es_script"))


FAKE_AMIXER = r"""#!/usr/bin/env python3
import json, os, sys
path = os.environ["FAKE_AMIXER_STATE"]
st = json.load(open(path))
args = [a for a in sys.argv[1:] if a != "-q"]
ctl = st["control"]
if args[0] == "scontrols":
    print("Simple mixer control 'Playback Path',0")
    print("Simple mixer control '%s',0" % ctl)
elif args[0] == "sget":
    if args[1] != ctl:
        print("Simple mixer control '%s',0\n  Capabilities: enum" % args[1]); sys.exit(0)
    caps = "pvolume pswitch" if st["switch"] is not None else "volume"
    sw = "" if st["switch"] is None else (" [on]" if st["switch"] else " [off]")
    print("Simple mixer control '%s',0\n  Capabilities: %s\n  Limits: 0 - 255" % (ctl, caps))
    print("  Front Left: %d [%d%%]%s" % (st["pct"] * 255 // 100, st["pct"], sw))
elif args[0] == "sset":
    v = args[2]
    if v == "mute": st["switch"] = False
    elif v == "unmute": st["switch"] = True
    elif v.endswith("%"): st["pct"] = int(v[:-1])
    json.dump(st, open(path, "w"))
"""


class SystemAudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.amixer = os.path.join(self.tmp, "amixer")
        with open(self.amixer, "w") as f:
            f.write(FAKE_AMIXER)
        os.chmod(self.amixer, 0o755)
        self.state = os.path.join(self.tmp, "state.json")
        os.environ["FAKE_AMIXER_STATE"] = self.state

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("FAKE_AMIXER_STATE", None)

    def write(self, **st):
        import json
        with open(self.state, "w") as f:
            json.dump(st, f)

    def read(self):
        import json
        with open(self.state) as f:
            return json.load(f)

    def test_volume_only_control_like_arkos(self):
        # 'Playback' de ArkOS: solo volumen, sin interruptor
        self.write(control="Playback", pct=72, switch=None)
        a = system.SystemAudio(os.path.join(self.tmp, "saved"), amixer=self.amixer)
        self.assertEqual(a.control, "Playback")
        self.assertFalse(a.muted)
        self.assertTrue(a.toggle())
        self.assertEqual(self.read()["pct"], 0)
        self.assertFalse(a.toggle())
        self.assertEqual(self.read()["pct"], 72)  # vuelve el volumen de antes

    def test_control_with_switch(self):
        self.write(control="Master", pct=50, switch=True)
        a = system.SystemAudio(os.path.join(self.tmp, "saved"), amixer=self.amixer)
        a.set_muted(True)
        self.assertTrue(a.muted)
        self.assertEqual(self.read(), {"control": "Master", "pct": 50, "switch": False})
        a.set_muted(False)
        self.assertEqual(self.read()["switch"], True)

    def test_volume_raised_with_buttons_counts_as_unmuted(self):
        self.write(control="Playback", pct=0, switch=None)
        a = system.SystemAudio(os.path.join(self.tmp, "saved"), amixer=self.amixer)
        self.assertTrue(a.muted)
        self.write(control="Playback", pct=30, switch=None)  # botones de volumen
        self.assertFalse(a.refresh())
        # sin volumen guardado se usa uno razonable
        self.write(control="Playback", pct=0, switch=None)
        a.set_muted(False)
        self.assertEqual(self.read()["pct"], system.SystemAudio.DEFAULT_RESTORE)

    def test_no_amixer(self):
        a = system.SystemAudio(os.path.join(self.tmp, "saved"), amixer="/no/existe")
        self.assertFalse(a.available)
        self.assertFalse(a.set_muted(True))


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
