"""Prueba de extremo a extremo de la interfaz sin pantalla (SDL 'offscreen')."""
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))
os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")

try:
    import sdl
except OSError:
    sdl = None

SYSTEMS = """<?xml version="1.0"?>
<systemList>
  <system>
    <name>gba</name><fullname>Game Boy Advance</fullname><path>{roms}/gba/</path>
    <extension>.gba</extension>
    <command>sudo perfmax %GOVERNOR% %ROM%; /usr/local/bin/%EMULATOR% -L %CORE% %ROM%; sudo perfnorm</command>
    <emulators><emulator name="retroarch"><cores><core>mgba</core></cores></emulator></emulators>
  </system>
</systemList>
"""


@unittest.skipIf(sdl is None, "SDL2 no disponible")
class UISmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        roms = os.path.join(self.tmp, "roms", "gba")
        os.makedirs(roms)
        for n in ("Golden Sun.gba", "Advance Wars.gba", "Metroid Fusion.gba", "Zelda Minish.gba"):
            open(os.path.join(roms, n), "w").close()
        self.etc = os.path.join(self.tmp, "etc")
        os.makedirs(self.etc)
        with open(os.path.join(self.etc, "es_systems.cfg"), "w") as f:
            f.write(SYSTEMS.format(roms=os.path.join(self.tmp, "roms")))
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".emulationstation"))
        self.data = os.path.join(self.tmp, "data")

        import main as M
        from app import App
        from gfx import Gfx
        from inputmap import Input
        from library import Library
        from store import Store
        from views import LibraryScreen
        args = M.parse_args(["--window", "640x480", "--home", self.home, "--es-dir", self.etc,
                             "--data", self.data])
        self.win, self.ren, w, h = M.create_display(sdl, args, lambda *a: None)
        self.g = Gfx(self.ren, w, h)
        self.store = Store(self.data)
        self.lib = Library(self.etc, self.home, None)
        self.lib.load(use_cache=False)
        self.launch = os.path.join(self.data, "launch.cmd")
        self.app = App(self.g, self.lib, self.store, Input([]), self.launch)
        self.ls = LibraryScreen(self.app)
        self.app.push(self.ls)

    def tearDown(self):
        self.g.destroy()
        sdl.SDL_DestroyRenderer(self.ren)
        sdl.SDL_DestroyWindow(self.win)
        shutil.rmtree(self.tmp)

    def press(self, *acts):
        for a in acts:
            self.app.inp.pressed.clear()
            self.app.dispatch([a])
            for _ in range(3):
                self.app.step(0)
            if not self.app.running:
                return

    def type_text(self, text):
        """Escribe con el teclado en pantalla moviendo el cursor como un usuario."""
        from dialogs import KeyboardDialog
        kb = self.app.top()
        self.assertIsInstance(kb, KeyboardDialog)
        for ch in text:
            rows = kb.keys()
            for r, row in enumerate(rows):
                if ch.lower() in row.lower():
                    kb.row, kb.col = r, row.lower().index(ch.lower())
                    break
            else:
                self.fail("tecla no encontrada: " + ch)
            self.press("a")

    def test_full_flow(self):
        tabs = self.ls.tabs
        self.assertEqual(tabs[:2], ["all", "fav"])
        # crear dos listas desde la pestana LISTAS con el teclado en pantalla
        for name in ("rpg", "luego"):
            self.ls.tab = self.ls.tabs.index("cats")
            self.ls.view().sel = 0
            self.press("a")
            self.type_text(name)
            self.press("start")
        self.assertEqual(self.store.category_names(), ["Rpg", "Luego"])
        # las listas nuevas aparecen como pestanas despues de Favoritos
        self.assertEqual(self.ls.tabs[2:4], ["list:Rpg", "list:Luego"])
        # ordenar listas: "Luego" pasa a ser la #1
        from views import reorder_lists
        reorder_lists(self.app)
        self.press("down", "a", "up", "a", "b")
        self.assertEqual(self.store.category_names(), ["Luego", "Rpg"])
        self.assertEqual(self.ls.tabs[2:4], ["list:Luego", "list:Rpg"])
        # anadir juegos a "Rpg" con X desde TODOS
        self.ls.tab = 0
        for i in (0, 1, 2):
            self.ls.view().sel = i
            self.press("x")  # dialogo de listas: fila 0 = nueva, 1 = Luego, 2 = Rpg
            self.press("down", "down", "a", "b")
        self.assertEqual(len(self.store.games_in("Rpg")), 3)
        # prioridad de juegos dentro de la lista con R2
        self.ls.tab = self.ls.tabs.index("list:Rpg")
        v = self.ls.view()
        v.refresh()
        first = v.games[0].path
        self.press("r2")
        self.assertEqual(self.store.games_in("Rpg")[1], first)
        # favorito con Y
        self.press("y")
        self.assertTrue(self.store.is_favorite(v.current()))
        # ficha y JUGAR
        self.press("a", "a")
        self.assertFalse(self.app.running)
        with open(self.launch) as f:
            cmd = f.read().strip()
        self.assertIn("/usr/local/bin/retroarch -L mgba", cmd)
        self.assertTrue(cmd.startswith("sudo perfmax performance "))
        with open(self.launch + ".rom") as f:
            self.assertEqual(f.read().strip(), first)
        # al volver se reabre la misma ficha
        self.store.save()
        from app import App
        from store import Store
        from views import DetailScreen, LibraryScreen
        st2 = Store(self.data)
        app2 = App(self.g, self.lib, st2, self.app.inp, self.launch)
        ls2 = LibraryScreen(app2)
        app2.push(ls2)
        ls2.apply_resume()
        self.assertIsInstance(app2.top(), DetailScreen)
        self.assertEqual(app2.top().game.path, first)
        self.assertEqual(ls2.tabs[ls2.tab], "list:Rpg")

    def test_all_screens_render(self):
        # recorre pestanas, menu, ayuda y vista detalles sin errores
        for _ in range(len(self.ls.tabs)):
            self.press("r1")
        self.press("start")
        for _ in range(20):
            self.press("down")
        self.press("b", "select", "l1", "select")
        start = time.time()
        self.app.draw()
        self.assertLess(time.time() - start, 2.0)


if __name__ == "__main__":
    unittest.main()
