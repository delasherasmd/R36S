import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

import library  # noqa: E402

SYSTEMS = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>snes</name>
    <fullname>Super Nintendo</fullname>
    <path>{roms}/snes/</path>
    <extension>.sfc .SFC .zip</extension>
    <command>sudo perfmax %GOVERNOR% %ROM%; nice -n -19 /usr/local/bin/%EMULATOR% -L /home/ark/.config/%EMULATOR%/cores/%CORE%_libretro.so %ROM%; sudo perfnorm</command>
    <emulators>
      <emulator name="retroarch">
        <cores><core>snes9x</core><core>snes9x2010</core></cores>
      </emulator>
      <emulator name="standalone" command="/usr/local/bin/sa.sh %ROM% %BASENAME%">
        <cores><core>x</core></cores>
      </emulator>
    </emulators>
    <platform>snes</platform>
  </system>
  <system>
    <name>ports</name><fullname>Ports</fullname><path>{roms}/ports/</path>
    <extension>.sh</extension><command>%ROM%</command>
  </system>
  <system>
    <name>retropie</name><fullname>Options</fullname><path>/opt/system/</path>
    <extension>.sh</extension>
    <command>sudo chmod 666 /dev/tty1; %ROM% 2>&1 > /dev/tty1; printf "\033c" >> /dev/tty1</command>
  </system>
  <system>
    <name>broken</name><path>{roms}/broken/</path><extension>.x</extension>
  </system>
</systemList>
"""

GAMELIST = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Chrono Trigger (USA).sfc</path>
    <name>Chrono Trigger</name>
    <desc>RPG</desc>
    <image>./images/ct.png</image>
    <genre>RPG / Action</genre>
    <favorite>true</favorite>
    <lastplayed>20240310T201500</lastplayed>
    <playcount>4</playcount>
    <core>snes9x2010</core>
  </game>
  <game>
    <path>./Hidden.sfc</path>
    <name>Oculto</name>
    <hidden>true</hidden>
  </game>
  <game>
    <path>./sub/Deep.sfc</path>
    <name>Profundo</name>
    <emulator>standalone</emulator>
  </game>
</gameList>
"""


def touch(path):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    open(path, "w").close()


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.roms = os.path.join(self.tmp, "roms")
        self.home = os.path.join(self.tmp, "home")
        self.etc = os.path.join(self.tmp, "etc")
        os.makedirs(os.path.join(self.home, ".emulationstation"))
        os.makedirs(self.etc)
        with open(os.path.join(self.etc, "es_systems.cfg"), "w") as f:
            f.write(SYSTEMS.format(roms=self.roms))
        snes = os.path.join(self.roms, "snes")
        for n in ("Chrono Trigger (USA).sfc", "Hidden.sfc", "sub/Deep.sfc", "Zelda (It's $5!).sfc",
                  "media/ignored.sfc", ".hidden.sfc", "notes.txt", "Mario.SFC"):
            touch(os.path.join(snes, n))
        touch(os.path.join(snes, "images", "Mario-thumb.png"))
        with open(os.path.join(snes, "gamelist.xml"), "w") as f:
            f.write(GAMELIST)
        touch(os.path.join(self.roms, "ports", "Vapor.sh"))
        touch(os.path.join(self.roms, "ports", "Doom.sh"))
        with open(os.path.join(self.home, ".emulationstation", "es_settings.cfg"), "w") as f:
            f.write('<?xml version="1.0"?>\n<string name="GlobalPerformanceGovernor" '
                    'value="ondemand" />\n<string name="HiddenSystems" value="" />\n')
        self.lib = library.Library(self.etc, self.home, os.path.join(self.tmp, "cache.pickle"),
                                   exclude=[os.path.join(self.roms, "ports", "Vapor.sh")])
        self.lib.load()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def game(self, name):
        for g in self.lib.games:
            if g.name == name:
                return g
        self.fail("no existe " + name)

    def test_scan_like_emulationstation(self):
        names = sorted(g.name for g in self.lib.games)
        self.assertEqual(names, ["Chrono Trigger", "Doom", "Mario", "Profundo",
                                 "Zelda (It's $5!)"])
        self.assertEqual([s.name for s in self.lib.systems], ["snes", "ports"])

    def test_metadata(self):
        ct = self.game("Chrono Trigger")
        self.assertTrue(ct.es_favorite)
        self.assertEqual(ct.es_playcount, 4)
        self.assertGreater(ct.es_lastplayed, 0)
        self.assertEqual(ct.image, os.path.join(self.roms, "snes", "images", "ct.png"))
        self.assertEqual(ct.genres(), ["RPG"])

    def test_local_art_fallback(self):
        mario = self.game("Mario")
        self.assertTrue(mario.thumbnail.endswith("images/Mario-thumb.png"))

    def test_es_escape(self):
        self.assertEqual(library.es_escape("/roms/snes/Zelda (It's $5!).sfc"),
                         "/roms/snes/Zelda\\ \\(It\\'s\\ \\$5\\!\\).sfc")

    def test_launch_command_defaults(self):
        cmd = self.lib.launch_command(self.game("Zelda (It's $5!)"))
        self.assertEqual(
            cmd,
            "sudo perfmax ondemand %s/snes/Zelda\\ \\(It\\'s\\ \\$5\\!\\).sfc; nice -n -19 "
            "/usr/local/bin/retroarch -L /home/ark/.config/retroarch/cores/snes9x_libretro.so "
            "%s/snes/Zelda\\ \\(It\\'s\\ \\$5\\!\\).sfc; sudo perfnorm" % (self.roms, self.roms))

    def test_launch_command_per_game_core(self):
        cmd = self.lib.launch_command(self.game("Chrono Trigger"))
        self.assertIn("snes9x2010_libretro.so", cmd)

    def test_launch_command_custom_emulator(self):
        cmd = self.lib.launch_command(self.game("Profundo"))
        self.assertEqual(cmd, "/usr/local/bin/sa.sh %s/snes/sub/Deep.sfc Deep" % self.roms)

    def test_system_setting_core(self):
        self.lib.settings["snes.core"] = "snes9x2010"
        self.lib.settings["snes.governor"] = "powersave"
        cmd = self.lib.launch_command(self.game("Mario"))
        self.assertIn("snes9x2010_libretro.so", cmd)
        self.assertTrue(cmd.startswith("sudo perfmax powersave "))

    def test_cache_roundtrip(self):
        lib2 = library.Library(self.etc, self.home, os.path.join(self.tmp, "cache.pickle"))
        lib2.load()
        self.assertEqual(sorted(g.path for g in lib2.games if g.system.name == "snes"),
                         sorted(g.path for g in self.lib.games if g.system.name == "snes"))

    def test_arkos_unescaped_ampersand_in_es_systems(self):
        # ArkOS escribe "2>&1" sin escapar; EmulationStation (pugixml) lo acepta
        self.assertEqual(self.lib.errors, [])
        self.assertEqual([s.name for s in self.lib.systems], ["snes", "ports"])

    def test_regex_fallback_for_very_broken_xml(self):
        path = os.path.join(self.etc, "es_systems.cfg")
        with open(path) as f:
            txt = f.read()
        # comentario invalido ("--" dentro) y '<' suelto en un comando
        txt = txt.replace("<systemList>", "<systemList><!-- roto -- comentario -->")
        txt = txt.replace("<command>%ROM%</command>", "<command>%ROM% < /dev/null</command>")
        with open(path, "w") as f:
            f.write(txt)
        lib = library.Library(self.etc, self.home, None)
        lib.load(use_cache=False)
        self.assertEqual([s.name for s in lib.systems], ["snes", "ports"])
        cmd = lib.launch_command([g for g in lib.games if g.name == "Profundo"][0])
        self.assertIn("/usr/local/bin/sa.sh", cmd)

    def test_broken_gamelist_fallback(self):
        with open(os.path.join(self.roms, "snes", "gamelist.xml"), "w") as f:
            f.write("<gameList><game><path>./Mario.SFC</path><name>Mario & Co</name></game>")
        lib = library.Library(self.etc, self.home, None)
        lib.load(use_cache=False)
        self.assertIn("Mario & Co", [g.name for g in lib.games])


if __name__ == "__main__":
    unittest.main()
