#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vapor - biblioteca estilo Steam para ArkOS (R36S y compatibles).

Normalmente se ejecuta desde ports/Vapor.sh. Para probar en un PC con Linux:
    python3 main.py --window 640x480 --home /ruta/a/home --es-dir /ruta/a/es
"""
import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

VERSION = "1.0.0"


def parse_args(argv):
    p = argparse.ArgumentParser(description="Vapor - biblioteca estilo Steam para ArkOS")
    p.add_argument("--data", default=os.environ.get("VAPOR_DATA", os.path.join(HERE, "data")),
                   help="carpeta de datos (categorias, historial)")
    p.add_argument("--es-dir", default=os.environ.get("VAPOR_ES_DIR", "/etc/emulationstation"),
                   help="carpeta de configuracion de EmulationStation")
    p.add_argument("--home", default=os.environ.get("HOME", os.path.expanduser("~")))
    p.add_argument("--launch-file", default=os.environ.get("VAPOR_LAUNCH"),
                   help="fichero donde se escribe el comando del juego a lanzar")
    p.add_argument("--exclude", action="append", default=[],
                   help="rutas a ocultar (p. ej. el propio Vapor.sh)")
    p.add_argument("--window", default=None, help="modo ventana, p. ej. 640x480")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--version", action="version", version=VERSION)
    return p.parse_args(argv)


class Log(object):
    def __init__(self, path):
        self.path = path
        try:
            self.f = open(path, "w")
        except (IOError, OSError):
            self.f = None

    def __call__(self, *a):
        msg = " ".join(str(x) for x in a)
        line = "[%s] %s\n" % (time.strftime("%H:%M:%S"), msg)
        if self.f:
            self.f.write(line)
            self.f.flush()
        sys.stderr.write(line)


def create_display(sdl, args, log):
    sdl.SDL_SetHint(b"SDL_RENDER_SCALE_QUALITY", b"1")
    sdl.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
    if sdl.SDL_Init(sdl.SDL_INIT_VIDEO | sdl.SDL_INIT_JOYSTICK | sdl.SDL_INIT_EVENTS) != 0:
        raise RuntimeError("SDL_Init: " + sdl.error())
    if sdl.TTF_Init() != 0:
        raise RuntimeError("TTF_Init: " + sdl.error())
    if sdl.IMG_Init is not None:
        sdl.IMG_Init(sdl.IMG_INIT_JPG | sdl.IMG_INIT_PNG)
    else:
        log("SDL2_image no disponible: no se mostraran caratulas")
    if args.window:
        w, h = [int(v) for v in args.window.lower().split("x")]
        flags = sdl.SDL_WINDOW_SHOWN
    else:
        mode = sdl.SDL_DisplayMode()
        if sdl.SDL_GetDesktopDisplayMode(0, sdl.byref(mode)) == 0 and mode.w > 0:
            w, h = mode.w, mode.h
        else:
            w, h = 640, 480
        flags = sdl.SDL_WINDOW_SHOWN | sdl.SDL_WINDOW_FULLSCREEN
    win = sdl.SDL_CreateWindow(b"Vapor", sdl.SDL_WINDOWPOS_UNDEFINED, sdl.SDL_WINDOWPOS_UNDEFINED,
                               w, h, flags)
    if not win:
        raise RuntimeError("SDL_CreateWindow: " + sdl.error())
    ren = None
    for rflags in (sdl.SDL_RENDERER_ACCELERATED | sdl.SDL_RENDERER_TARGETTEXTURE |
                   sdl.SDL_RENDERER_PRESENTVSYNC,
                   sdl.SDL_RENDERER_ACCELERATED | sdl.SDL_RENDERER_TARGETTEXTURE,
                   sdl.SDL_RENDERER_SOFTWARE):
        ren = sdl.SDL_CreateRenderer(win, -1, rflags)
        if ren:
            break
    if not ren:
        raise RuntimeError("SDL_CreateRenderer: " + sdl.error())
    ow, oh = sdl.c_int(), sdl.c_int()
    sdl.SDL_GetRendererOutputSize(ren, sdl.byref(ow), sdl.byref(oh))
    if ow.value > 0 and oh.value > 0:
        w, h = ow.value, oh.value
    sdl.SDL_ShowCursor(0)
    log("Pantalla %dx%d" % (w, h))
    return win, ren, w, h


def draw_loading(sdl, g, frac, label):
    import theme as C
    from strings import T
    g.vgradient(0, 0, g.w, g.h, C.BG_TOP, C.BG_BOTTOM)
    cx, cy = g.w // 2, g.h // 2 - g.S(20)
    s = g.S(44)
    g.icon("circle", cx - s // 2, cy - s - g.S(30), s, C.ACCENT)
    g.icon("play", cx - g.S(9), cy - s - g.S(30) + g.S(12), g.S(20), C.TEXT)
    g.text("VAPOR", cx, cy - g.S(10), 30, C.TEXT, bold=True, align="center")
    g.text(T("loading"), cx, cy + g.S(32), 12, C.TEXT2, align="center")
    bw, bh = g.S(240), g.S(4)
    bx, by = cx - bw // 2, cy + g.S(56)
    g.round_rect(bx, by, bw, bh, bh // 2, (255, 255, 255, 30))
    g.round_rect(bx, by, max(bh, int(bw * frac)), bh, bh // 2, C.ACCENT)
    if label:
        g.text(label, cx, by + g.S(14), 10, C.TEXT3, align="center", max_w=bw + g.S(80))
    sdl.SDL_RenderPresent(g.ren)
    # mantener vivo el bucle de eventos durante la carga
    ev = sdl.new_event_buffer()
    while sdl.SDL_PollEvent(ev):
        pass


def show_error(sdl, g, msg):
    import theme as C
    g.vgradient(0, 0, g.w, g.h, C.BG_TOP, C.BG_BOTTOM)
    g.text("Vapor: error", g.w // 2, g.S(120), 20, C.RED, bold=True, align="center")
    for i, l in enumerate(g.wrap(msg, 12, g.w - g.S(60), max_lines=10)):
        g.text(l, g.w // 2, g.S(160) + i * g.line_h(12), 12, C.TEXT, align="center")
    sdl.SDL_RenderPresent(g.ren)
    ev = sdl.new_event_buffer()
    end = time.time() + 8
    while time.time() < end:
        if sdl.SDL_WaitEventTimeout(ev, 200):
            e = sdl.decode_event(ev)
            if e.type in (sdl.SDL_JOYBUTTONDOWN, sdl.SDL_KEYDOWN, sdl.SDL_QUIT):
                break


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if not os.path.isdir(args.data):
        os.makedirs(args.data)
    log = Log(os.path.join(args.data, "vapor.log"))
    log("Vapor", VERSION, "python", sys.version.split()[0])
    try:
        import sdl
    except OSError as e:
        log("ERROR cargando SDL2:", e)
        return 2

    from gfx import Gfx
    from library import Library
    from store import Store
    from inputmap import Input
    from app import App
    from views import LibraryScreen
    from strings import set_lang

    win = ren = g = inp = None
    code = 0
    try:
        win, ren, w, h = create_display(sdl, args, log)
        g = Gfx(ren, w, h)
        store = Store(args.data)
        set_lang(store.get("lang"))
        state = {"t": 0}

        def progress(i, n, name):
            now = time.time()
            if now - state["t"] > 0.05 or i >= n:
                state["t"] = now
                draw_loading(sdl, g, float(i) / max(1, n), name)

        draw_loading(sdl, g, 0.0, "")
        t0 = time.time()
        excl = list(args.exclude)
        if os.environ.get("VAPOR_SELF"):
            excl.append(os.environ["VAPOR_SELF"])
        lib = Library(args.es_dir, args.home,
                      None if args.no_cache else os.path.join(args.data, "cache.pickle"),
                      exclude=excl)
        lib.load(progress, use_cache=not args.no_cache)
        log("Biblioteca: %d juegos, %d sistemas en %.2fs" % (len(lib.games), len(lib.systems),
                                                             time.time() - t0))
        log("Configuracion: %s" % lib.cfg_used)
        for err in lib.errors:
            log("Aviso:", err)
        for name, path, info in lib.report:
            log("  %-12s %-28s %s" % (name, path, info))
        if store.fix_paths(lib.by_path):
            log("Rutas de listas actualizadas (ROMs movidas de sitio)")
        # Se importan las colecciones de ES la primera vez que hay juegos (si la
        # biblioteca salio vacia, por ejemplo por un error de lectura, se reintenta).
        if lib.games and not store.data.get("es_import_ok"):
            n = store.import_from_es(lib.collections_dir(), lib.home, set(lib.by_path))
            store.data["es_import_ok"] = True
            log("Colecciones de ES importadas: %d juegos" % n)
            store.save()

        inp = Input(lib.input_cfg_paths(),
                    swap_ab=lib.settings.get("InvertButtons", "false") == "true")
        inp.open_all()
        launch_file = args.launch_file or os.path.join(args.data, "launch.cmd")
        app = App(g, lib, store, inp, launch_file)
        ls = LibraryScreen(app)
        app.push(ls)
        ls.apply_resume()
        result = app.run()
        if result and result[0] == "launch":
            log("Lanzando:", result[2])
        store.save()
    except Exception as e:
        log("ERROR:", traceback.format_exc())
        code = 3  # error ya mostrado en pantalla
        if g is not None:
            try:
                show_error(sdl, g, "%s\n\n%s" % (e, os.path.join(args.data, "vapor.log")))
            except Exception:
                pass
    finally:
        if inp is not None:
            inp.close_all()
        if g is not None:
            g.destroy()
        if ren:
            sdl.SDL_DestroyRenderer(ren)
        if win:
            sdl.SDL_DestroyWindow(win)
        sdl.TTF_Quit()
        sdl.SDL_Quit()
    return code


if __name__ == "__main__":
    sys.exit(main())
