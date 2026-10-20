# -*- coding: utf-8 -*-
"""Nucleo de la interfaz: bucle principal, pila de pantallas, barra de ayudas
de botones y avisos."""
import ctypes
import os
import time

import sdl
import theme as C
from strings import T


class Screen(object):
    """Pantalla o dialogo. Los dialogos (modal=True) se dibujan sobre la anterior."""
    modal = False
    dim = True  # oscurecer lo de detras (los paneles con vista previa no lo hacen)

    def __init__(self, app):
        self.app = app
        self.g = app.g

    def action(self, act):
        pass

    def update(self, now):
        """Devuelve True si hay una animacion en curso (hay que redibujar)."""
        return False

    def draw(self):
        pass

    def hints(self):
        return []

    def status(self):
        """Texto a la izquierda de la barra inferior."""
        return ""

    def on_resume(self):
        pass


def smooth(cur, target, dt_ms, rate=0.28):
    """Acerca 'cur' a 'target' de forma suave e independiente de los FPS."""
    if abs(target - cur) < 0.5:
        return target
    k = 1.0 - pow(1.0 - rate, max(1.0, dt_ms) / 16.0)
    return cur + (target - cur) * k


class Battery(object):
    def __init__(self):
        self.path = None
        self.status_path = None
        self.value = None
        self.charging = False
        self.t = 0
        base = "/sys/class/power_supply"
        try:
            for name in sorted(os.listdir(base)):
                d = os.path.join(base, name)
                try:
                    with open(os.path.join(d, "type")) as f:
                        typ = f.read().strip()
                except (IOError, OSError):
                    typ = ""
                if typ == "Battery" and os.path.isfile(os.path.join(d, "capacity")):
                    self.path = os.path.join(d, "capacity")
                    self.status_path = os.path.join(d, "status")
                    break
        except OSError:
            pass

    def read(self, now):
        if self.path is None:
            return None
        if self.value is None or now - self.t > 30000:
            self.t = now
            try:
                with open(self.path) as f:
                    self.value = max(0, min(100, int(f.read().strip())))
                with open(self.status_path) as f:
                    self.charging = f.read().strip() == "Charging"
            except (IOError, OSError, ValueError):
                self.value = None
        return self.value


class App(object):
    def __init__(self, gfx, lib, store, inp, launch_file=None):
        self.g = gfx
        self.lib = lib
        self.store = store
        self.inp = inp
        self.launch_file = launch_file
        self.screens = []
        self.running = True
        self.result = None
        self.dirty = True
        self.toast_text = ""
        self.toast_until = 0
        self.now = sdl.SDL_GetTicks()
        self.last_frame = self.now
        self.battery = Battery()
        self.clock_text = ""
        self.ev = sdl.new_event_buffer()
        # servicios opcionales (los crea main.py)
        self.music = None
        self.backlight = None
        self.autostart = None
        self.audio = None
        self.clock = None
        self.notes = []  # avisos que llegan desde otros hilos

    # ----------------------------------------------------------- pantallas
    def push(self, scr):
        self.screens.append(scr)
        self.inp.reset()
        self.dirty = True

    def pop(self, scr=None):
        if not self.screens:
            return
        if scr is None or self.screens[-1] is scr:
            self.screens.pop()
        elif scr in self.screens:
            self.screens.remove(scr)
        self.inp.reset()
        if self.screens:
            self.screens[-1].on_resume()
        self.dirty = True

    def top(self):
        return self.screens[-1] if self.screens else None

    def toast(self, text, ms=2200):
        self.toast_text = text
        self.toast_until = self.now + ms
        self.dirty = True

    def toast_later(self, text, ms=3500):
        """Aviso desde otro hilo: se muestra en el bucle principal."""
        self.notes.append((text, ms))

    def time_text(self, t=None):
        """Hora para mostrar, en formato 24 h o 12 h segun la opcion."""
        tm = time.localtime(t)
        if self.store.get("clock_24h") is False:
            return "%d:%02d %s" % (tm.tm_hour % 12 or 12, tm.tm_min,
                                   "AM" if tm.tm_hour < 12 else "PM")
        return "%02d:%02d" % (tm.tm_hour, tm.tm_min)

    def quit(self):
        self.result = None
        self.running = False

    # ------------------------------------------------------------ silencio
    def set_system_mute(self, on):
        a = self.audio
        if a is None or not a.available:
            self.toast(T("no_amixer"))
            return
        if not a.set_muted(on):
            self.toast(T("no_amixer"))
            return
        self.on_mute_changed()
        self.toast(T("muted_on") if a.muted else T("muted_off"))
        self.dirty = True

    def on_mute_changed(self):
        """Con la consola en silencio se para la musica de Vapor; al quitarlo vuelve."""
        m = self.music
        if m is None:
            return
        if self.audio is not None and self.audio.muted:
            if m.enabled:
                m.set_enabled(False)
        elif self.store.get("music") and not m.enabled:
            m.set_enabled(True)

    # ------------------------------------------------------------- lanzar
    def launch(self, game):
        """Prepara el lanzamiento: Vapor.sh ejecutara el comando y volvera a abrir Vapor."""
        cmd = self.lib.launch_command(game)
        self.store.mark_launch(game)
        self.store.save()
        if self.launch_file:
            try:
                with open(self.launch_file + ".rom", "wb") as f:
                    f.write(os.fsencode(game.path) + b"\n")
                with open(self.launch_file, "wb") as f:
                    f.write(os.fsencode(cmd) + b"\n")
            except (IOError, OSError) as e:
                self.toast("Error: %s" % e)
                return
        self.result = ("launch", game, cmd)
        self.draw_launching(game)
        self.running = False

    def draw_launching(self, game):
        """Pantalla 'Iniciando' con la estetica del logo."""
        g = self.g
        if g.draw_static("splash.jpg", 0, 0, g.w, g.h):
            g.fill(0, 0, g.w, g.h, (10, 2, 24, 150))
            # tapa el 'CARGANDO' de la imagen
            g.fade(0, g.h - g.S(90), g.w, g.S(90), (10, 2, 24, 255), "bottom")
        else:
            g.background()
        cy = g.h // 2
        g.text_spaced(T("launching_title"), g.w // 2, cy - g.S(34), 12, C.ACCENT_SOFT, bold=True,
                      spacing=7)
        lines = g.wrap(game.name, 22, g.w - g.S(60), max_lines=2, bold=True)
        lh = g.line_h(22, True)
        for i, l in enumerate(lines):
            g.text(l, g.w // 2, cy - g.S(8) + i * lh, 22, C.TEXT, bold=True, align="center")
        y = cy - g.S(8) + len(lines) * lh + g.S(10)
        g.text(game.system.fullname.upper(), g.w // 2, y, 10, C.ACCENT, bold=True, align="center")
        sdl.SDL_RenderPresent(g.ren)

    # -------------------------------------------------------------- dibujo
    def draw_glyph(self, btn, x, cy, size=11):
        """Dibuja el simbolo de un boton del mando. Devuelve el ancho."""
        g = self.g
        d = g.S(16)
        if getattr(self.inp, "swap_ab", False) and btn in ("A", "B"):
            btn = "B" if btn == "A" else "A"
        if btn in ("A", "B", "X", "Y"):
            g.icon("circle", x, cy - d // 2, d, C.GLYPH_BG)
            g.text(btn, x + d // 2 + 1, cy, 10, C.DARK_TEXT, bold=True, align="center",
                   valign="middle")
            return d
        label = {"START": "START", "SELECT": "SELECT"}.get(btn, btn)
        tw = g.text_w(label, 8, True)
        w = tw + g.S(10)
        g.round_rect(x, cy - d // 2, w, d, d // 2, C.GLYPH_BG)
        g.text(label, x + w // 2, cy, 8, C.DARK_TEXT, bold=True, align="center",
               valign="middle")
        return w

    def hints_width(self, hints):
        g = self.g
        w = 0
        for btn, label in hints:
            if btn in ("A", "B", "X", "Y"):
                bw = g.S(16)
            else:
                bw = g.text_w(btn, 8, True) + g.S(10)
            w += bw + g.S(5) + g.text_w(label, 11) + g.S(12)
        return w

    def draw_hints(self, hints, status=""):
        g = self.g
        h = g.S(C.HINTBAR_H)
        y = g.h - h
        g.fill(0, y, g.w, h, C.BAR)
        g.fill(0, y, g.w, 1, C.BAR_LINE)
        cy = y + h // 2
        total = self.hints_width(hints)
        x = g.w - g.S(10) - total
        left_space = x - g.S(20)
        if status and left_space > g.S(40):
            g.text(status, g.S(12), cy, 11, C.TEXT2, valign="middle", max_w=left_space)
        for btn, label in hints:
            x += self.draw_glyph(btn, x, cy) + g.S(5)
            x += g.text(label, x, cy, 11, C.TEXT, valign="middle") + g.S(12)

    def draw_status_icons(self, right, cy):
        """Reloj y bateria arriba a la derecha. Devuelve la x donde empiezan."""
        g = self.g
        x = right
        if self.audio is not None and self.audio.muted:
            s = g.S(14)
            x -= s
            g.icon("mute", x, cy - s // 2, s, C.RED)
            x -= g.S(8)
        val = self.battery.read(self.now)
        if val is not None:
            bw, bh = g.S(20), g.S(10)
            x -= bw
            col = C.RED if val <= 15 and not self.battery.charging else C.TEXT2
            g.outline(x, cy - bh // 2, bw - g.S(2), bh, col)
            g.fill(x + bw - g.S(2), cy - bh // 4, g.S(2), bh // 2, col)
            fillw = int((bw - g.S(2) - 4) * val / 100.0)
            g.fill(x + 2, cy - bh // 2 + 2, max(1, fillw), bh - 4,
                   C.GREEN_TOP if self.battery.charging else col)
            x -= g.S(4)
            x -= g.text("%d%%" % val, x, cy, 10, C.TEXT2, align="right", valign="middle")
            x -= g.S(10)
        self.clock_text = self.time_text()
        x -= g.text(self.clock_text, x, cy, 12, C.TEXT, bold=True, align="right",
                    valign="middle")
        return x - g.S(10)

    def draw_toast(self):
        if not self.toast_text or self.now > self.toast_until:
            return
        g = self.g
        lines = g.wrap(self.toast_text, 12, g.w - g.S(120), max_lines=4)
        lh = g.line_h(12)
        w = max(g.text_w(l, 12) for l in lines) + g.S(28)
        h = lh * len(lines) + g.S(16)
        x = (g.w - w) // 2
        y = g.h - g.S(C.HINTBAR_H) - h - g.S(12)
        g.shadow(x, y, w, h, g.S(8), 140)
        g.round_rect(x, y, w, h, g.S(8), (50, 64, 82, 250))
        g.fill(x + g.S(8), y, w - g.S(16), 2, C.ACCENT)
        for i, l in enumerate(lines):
            g.text(l, g.w // 2, y + g.S(8) + i * lh, 12, C.TEXT, align="center")

    def draw(self):
        g = self.g
        # se dibuja desde la ultima pantalla opaca hacia arriba
        start = 0
        for i in range(len(self.screens) - 1, -1, -1):
            if not self.screens[i].modal:
                start = i
                break
        g.clear(C.BG_BOTTOM)
        for scr in self.screens[start:]:
            if scr.modal and scr.dim:
                g.fill(0, 0, g.w, g.h, C.DIM)
            scr.draw()
        top = self.top()
        if top is not None:
            self.draw_hints(top.hints(), top.status())
        self.draw_toast()
        sdl.SDL_RenderPresent(g.ren)

    # --------------------------------------------------------------- bucle
    def dispatch(self, acts):
        for act in acts:
            p = self.inp.pressed
            # SELECT + START (o HOTKEY + START) sale de Vapor, como en ArkOS
            if act in ("start", "select", "hotkey") and "start" in p and \
                    ("select" in p or "hotkey" in p):
                self.quit()
                return
            top = self.top()
            if top is not None:
                top.action(act)
                self.dirty = True
            if not self.running:
                return

    def step(self, timeout_ms):
        """Procesa eventos durante como mucho timeout_ms y dibuja si hace falta."""
        ev = self.ev
        got = sdl.SDL_WaitEventTimeout(ev, int(max(0, timeout_ms)))
        self.now = sdl.SDL_GetTicks()
        while got:
            e = sdl.decode_event(ev)
            if e.type == sdl.SDL_QUIT:
                self.quit()
                return
            if e.type in (sdl.SDL_WINDOWEVENT, sdl.SDL_RENDER_TARGETS_RESET,
                          sdl.SDL_RENDER_DEVICE_RESET):
                self.dirty = True
            acts = self.inp.handle(e, self.now)
            if acts:
                self.dispatch(acts)
                if not self.running:
                    return
            got = sdl.SDL_PollEvent(ev)
        reps = self.inp.repeats(self.now)
        if reps:
            self.dispatch(reps)
            if not self.running:
                return
        animating = False
        for scr in self.screens:
            if scr.update(self.now):
                animating = True
        if self.g.pump_images(3):
            self.dirty = True
        if self.music is not None and self.music.tick(self.now):
            self.dirty = True
        # el volumen puede cambiar con los botones de la consola: se mira cada 4 s
        if self.audio is not None and self.audio.available and \
                self.now - self.audio.last_check > 4000:
            was = self.audio.muted
            if self.audio.refresh(self.now) != was:
                self.on_mute_changed()
                self.dirty = True
        if animating:
            self.dirty = True
        if self.toast_text and self.now > self.toast_until:
            self.toast_text = ""
            self.dirty = True
        if self.notes:
            self.toast(*self.notes.pop(0))
        if self.time_text() != self.clock_text:
            self.dirty = True
        if self.dirty:
            self.dirty = False
            self.draw()
        self.last_frame = self.now
        return animating

    def busy(self):
        ld = self.g.loader
        return bool(ld.pending) or bool(ld.done)

    def run(self):
        animating = True
        while self.running and self.screens:
            if animating or self.busy():
                timeout = 16
            else:
                timeout = 1000
                nr = self.inp.next_repeat_ms(self.now)
                if nr is not None:
                    timeout = min(timeout, nr)
                if self.toast_text:
                    timeout = min(timeout, max(1, self.toast_until - self.now))
            animating = self.step(timeout)
            if not self.screens:
                break
        self.store.save()
        return self.result

    def read_pixels(self):
        """RGBA de la pantalla actual (para capturas en pruebas)."""
        g = self.g
        buf = ctypes.create_string_buffer(g.w * g.h * 4)
        sdl.SDL_RenderReadPixels(g.ren, None, sdl.SDL_PIXELFORMAT_ABGR8888, buf, g.w * 4)
        return buf.raw
