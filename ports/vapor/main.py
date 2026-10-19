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

VERSION = "1.3.0"


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
    """Pantalla de carga: el logo de Vapor (assets/splash.jpg) con una barra de neon."""
    import theme as C
    from strings import T
    cx = g.w // 2
    if g.draw_static("splash.jpg", 0, 0, g.w, g.h):
        # la imagen ya trae 'CARGANDO'; la barra va justo encima, sobre la rejilla
        bw, bh = g.S(200), g.S(4)
        bx, by = cx - bw // 2, g.h - g.S(58)
        g.round_rect(bx - g.S(3), by - g.S(3), bw + g.S(6), bh + g.S(6), g.S(5), (10, 2, 24, 200))
    else:
        g.background()
        g.text("VAPOR", cx, g.h // 2 - g.S(40), 30, C.TEXT, bold=True, align="center")
        g.text(T("loading"), cx, g.h // 2, 12, C.TEXT2, align="center")
        bw, bh = g.S(240), g.S(4)
        bx, by = cx - bw // 2, g.h // 2 + g.S(28)
    g.round_rect(bx, by, bw, bh, bh // 2, (255, 255, 255, 40))
    fw = max(bh, int(bw * frac))
    g.round_rect(bx, by, fw, bh, bh // 2, C.ACCENT)
    g.fill(bx + bh // 2, by, max(0, fw - bh), max(1, bh // 3), (255, 255, 255, 90))
    _ = label
    sdl.SDL_RenderPresent(g.ren)
    # mantener vivo el bucle de eventos durante la carga
    ev = sdl.new_event_buffer()
    while sdl.SDL_PollEvent(ev):
        pass


def show_error(sdl, g, msg):
    import theme as C
    g.background()
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
    from settings_ui import apply_theme
    from music import MusicPlayer, music_dirs
    from system import Autostart, Backlight, SystemAudio
    from library import load_es_settings

    win = ren = g = inp = music = None
    code = 0
    boot = os.environ.get("VAPOR_BOOT") == "1"
    try:
        win, ren, w, h = create_display(sdl, args, log)
        g = Gfx(ren, w, h)
        store = Store(args.data)
        set_lang(store.get("lang"))
        # el tema Vapor (colores del logo) pasa a ser el principal; quien tenia el
        # tema por defecto anterior (Steam) lo recibe una vez
        if store.get("theme_v") != 2:
            if store.get("theme") in (None, "steam"):
                store.set("theme", "vapor")
            store.set("theme_v", 2)
            store.save()
        apply_theme(store)

        # musica de fondo (empieza ya, mientras carga la biblioteca)
        es_settings = load_es_settings(os.path.join(args.home, ".emulationstation",
                                                    "es_settings.cfg"))
        music = MusicPlayer(music_dirs(HERE, args.home, es_settings))
        log("Musica: %d canciones, audio %s" % (len(music.songs),
                                                "si" if music.available else "no"))
        audio = SystemAudio(os.path.join(args.data, "volume_before_mute"))
        log("Volumen del sistema: control %s, silenciado %s" % (audio.control, audio.muted))
        # si la consola esta silenciada no se pone musica
        music.start(bool(store.get("music")) and not audio.muted,
                    int(store.get("music_volume")))
        if music.error:
            log("Aviso musica:", music.error)

        # brillo guardado en Vapor: se aplica una vez por encendido
        backlight = Backlight()
        log("Brillo: %s" % (", ".join(backlight.devices) or "sin control"))
        marker = "/dev/shm/vapor_brightness_applied"
        if store.get("brightness") is not None and backlight.available and \
                not os.path.exists(marker):
            backlight.set_percent(store.get("brightness"))
            try:
                open(marker, "w").close()
            except (IOError, OSError):
                pass
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
        app.music = music
        app.backlight = backlight
        app.audio = audio
        app.autostart = Autostart(os.environ.get("VAPOR_SELF", ""), args.data)
        if app.autostart.needs_update():
            # bloque de arranque de una version anterior: se actualiza solo
            ok, why = app.autostart.enable()
            log("Arranque automatico actualizado: %s %s" % ("ok" if ok else "fallo", why))
        last = app.autostart.last_boot()
        if last:
            log("Ultimo arranque:", last)
        # diagnostico del arranque automatico (en segundo plano)
        import threading
        from system import write_diagnostics
        extra = ["Vapor %s, python %s, abierto %s" % (
            VERSION, sys.version.split()[0],
            "al encender (VAPOR_BOOT=1)" if boot else "desde Ports/terminal"),
            "estado del arranque automatico: %s" % app.autostart.status()]
        t = threading.Thread(target=write_diagnostics,
                             args=(os.path.join(args.data, "diagnostico.txt"), app.autostart,
                                   extra))
        t.daemon = True
        t.start()
        ls = LibraryScreen(app)
        app.push(ls)
        ls.apply_resume()
        app.draw()
        if boot:
            # Vapor llego a mostrarse en el arranque: todo bien
            app.autostart.boot_ok()
            log("Arranque directo en Vapor")
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
        if music is not None:
            try:
                music.stop(fade_ms=250)
            except Exception:
                pass
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
