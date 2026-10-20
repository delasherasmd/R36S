#!/usr/bin/env python3
"""Ejecuta Vapor sin pantalla (SDL offscreen), simula botones y guarda capturas.

Uso: python3 tools/shots.py /tmp/fakeark docs/screenshots
"""
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ports", "vapor"))

from PIL import Image  # noqa: E402

import sdl  # noqa: E402
import main as M  # noqa: E402
from app import App  # noqa: E402
from gfx import Gfx  # noqa: E402
from inputmap import Input  # noqa: E402
from library import Library  # noqa: E402
from store import Store  # noqa: E402
from strings import set_lang  # noqa: E402
from views import LibraryScreen  # noqa: E402


class Harness(object):
    def __init__(self, root, size="640x480", data=None, lang="es"):
        self.root = root
        data = data or os.path.join(root, "data")
        args = M.parse_args(["--window", size, "--home", os.path.join(root, "home"),
                             "--es-dir", os.path.join(root, "etc"), "--data", data])
        self.log = lambda *a: None
        self.win, self.ren, w, h = M.create_display(sdl, args, self.log)
        self.g = Gfx(self.ren, w, h)
        self.store = Store(data)
        self.store.set("lang", lang)
        set_lang(lang)
        self.lib = Library(args.es_dir, args.home, os.path.join(data, "cache.pickle"),
                           exclude=[os.path.join(root, "roms", "ports", "Vapor.sh")])
        self.lib.load()
        if not self.store.data.get("es_imported"):
            self.store.import_from_es(self.lib.collections_dir(), self.lib.home,
                                      set(self.lib.by_path))
        self.inp = Input(self.lib.input_cfg_paths())
        self.app = App(self.g, self.lib, self.store, self.inp,
                       os.path.join(data, "launch.cmd"))
        self.ls = LibraryScreen(self.app)
        self.app.push(self.ls)
        self.ls.apply_resume()

    def settle(self, max_s=3.0):
        end = time.time() + max_s
        quiet = 0
        while time.time() < end:
            anim = self.app.step(0)
            if anim or self.app.busy():
                quiet = 0
                time.sleep(0.005)
            else:
                quiet += 1
                if quiet > 5:
                    break
        self.app.dirty = True
        self.app.step(0)

    def press(self, *acts):
        for a in acts:
            self.app.inp.pressed.clear()
            self.app.dispatch([a])
            self.settle()

    def shot(self, path):
        self.app.draw()
        raw = self.app.read_pixels()
        img = Image.frombytes("RGBA", (self.g.w, self.g.h), raw).convert("RGB")
        img.save(path)
        return img

    def close(self):
        self.g.destroy()
        sdl.SDL_DestroyRenderer(self.ren)
        sdl.SDL_DestroyWindow(self.win)


def demo_lists(h):
    """Listas de ejemplo para las capturas."""
    st = h.store
    lib = h.lib
    pick = lambda name: [g.path for g in lib.games if g.name == name][0]
    if st.find("Jugando ahora") is None:
        st.create("Jugando ahora", pinned=True)
        for n in ("Golden Sun", "Chrono Trigger", "Final Fantasy VII", "Tetris"):
            st.add("Jugando ahora", pick(n))
        st.create("Pendientes", pinned=True)
        for n in ("EarthBound", "Secret of Mana", "Phantasy Star IV", "Mega Man 2",
                  "Link's Awakening", "Gunstar Heroes"):
            st.add("Pendientes", pick(n))
        st.create("Con amigos")
        for n in ("Mario Kart Super Circuit", "Tekken 3", "Street Fighter II Turbo"):
            st.add("Con amigos", pick(n))
        st.save()
    h.ls.build_tabs()
    h.ls.refresh_all()


def clock_shots(h, out, zone="America/Argentina/Buenos_Aires"):
    """Fecha y hora: el reloj de verdad no se toca (los comandos no hacen nada)."""
    import tempfile
    from settings_ui import SettingsScreen
    from system import ZONEINFO, Clock
    tmp = tempfile.mkdtemp()
    link = os.path.join(tmp, "localtime")
    os.symlink(os.path.join(ZONEINFO, zone), link)
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = ":" + os.path.join(ZONEINFO, zone)
    time.tzset()
    try:
        h.app.clock = Clock(os.path.join(tmp, "saved"), localtime=link,
                            timezone_file=os.path.join(tmp, "tz"), route="/nonexistent",
                            run=lambda cmd: True)
        h.app.toast_text = ""
        h.ls.tab = 0
        scr = SettingsScreen(h.app, h.ls)
        h.app.push(scr)
        h.settle()
        scr.sel = [r["kind"] for r in scr.rows].index("datetime")
        h.press("a", "right")
        h.shot(os.path.join(out, "16_fecha_hora.png"))
        h.press("b")
        scr.sel = [r["kind"] for r in scr.rows].index("timezone")
        h.press("a")
        h.shot(os.path.join(out, "17_zona_horaria.png"))
        h.press("b", "b")
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fakeark"
    out = sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots"
    os.makedirs(out, exist_ok=True)
    h = Harness(root)
    demo_lists(h)
    h.settle()
    h.shot(os.path.join(out, "01_biblioteca.png"))
    h.press("right", "right", "down")
    h.shot(os.path.join(out, "02_seleccion.png"))
    h.press("a")
    h.shot(os.path.join(out, "03_ficha.png"))
    h.press("x")
    h.shot(os.path.join(out, "04_listas_del_juego.png"))
    h.press("b", "b")
    # pestanas: TODOS, FAVORITOS, JUGANDO AHORA, PENDIENTES, RECIENTES, LISTAS...
    h.press("r1", "r1")
    h.shot(os.path.join(out, "05_lista_como_pestana.png"))
    h.press("r1", "right", "r2")
    h.shot(os.path.join(out, "06_prioridad_juegos.png"))
    h.press("r1", "r1")
    h.shot(os.path.join(out, "07_pestana_listas.png"))
    h.press("right", "x")
    h.shot(os.path.join(out, "08_opciones_lista.png"))
    h.press("b", "start")
    for _ in range(3):
        h.press("down")
    h.shot(os.path.join(out, "09_menu.png"))
    h.press("a")
    h.press("down", "a", "down")
    h.shot(os.path.join(out, "10_ordenar_listas.png"))
    h.press("a", "b")
    h.shot(os.path.join(out, "11_listas_reordenadas.png"))
    h.press("left", "a")
    h.shot(os.path.join(out, "12_teclado.png"))
    h.press("b", "r1")
    h.shot(os.path.join(out, "13_sistemas.png"))
    h.press("select")
    h.press("l1", "l1", "l1", "l1", "l1", "l1")
    h.shot(os.path.join(out, "14_vista_detalles.png"))
    h.press("select")
    clock_shots(h, out)
    h.close()
    print("Capturas en", out)


if __name__ == "__main__":
    main()
