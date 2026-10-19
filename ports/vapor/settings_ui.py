# -*- coding: utf-8 -*-
"""Panel 'Personalizar': colores, caratulas, brillo, musica y arranque.

Es un panel lateral sin oscurecer el fondo, asi los cambios de color se ven en
vivo sobre la biblioteca."""
import theme as C
from app import Screen, smooth
from strings import T, current_lang


def apply_theme(store):
    C.apply(store.get("theme"), store.get("accent"), store.get("tile_size"))


class SettingsScreen(Screen):
    modal = True
    dim = False
    WIDTH = 300
    ROW = 34

    def __init__(self, app, ls):
        Screen.__init__(self, app)
        self.ls = ls
        self.sel = 0
        self.scroll = 0.0
        self.t = app.now
        self.rows = self.build()
        self.sel = next(i for i, r in enumerate(self.rows) if r["kind"] != "header")

    # ------------------------------------------------------------- filas
    def build(self):
        rows = [
            {"kind": "header", "label": T("sec_look")},
            {"kind": "choice", "key": "theme", "label": T("opt_theme"), "table": C.PRESETS},
            {"kind": "choice", "key": "accent", "label": T("opt_accent"), "table": C.ACCENTS},
            {"kind": "choice", "key": "tile_size", "label": T("opt_tiles"),
             "table": C.TILE_SIZES},
            {"kind": "header", "label": T("sec_screen")},
            {"kind": "brightness", "label": T("opt_brightness")},
            {"kind": "header", "label": T("sec_music")},
            {"kind": "mute", "label": T("opt_mute")},
            {"kind": "music_on", "label": T("opt_music")},
            {"kind": "volume", "label": T("opt_volume")},
            {"kind": "next_song", "label": T("opt_next_song")},
            {"kind": "header", "label": T("sec_boot")},
            {"kind": "autostart", "label": T("opt_autostart")},
            {"kind": "reset", "label": T("opt_reset")},
        ]
        return rows

    def selectable(self, i):
        return self.rows[i]["kind"] != "header"

    # ----------------------------------------------------------- acciones
    def action(self, act):
        n = len(self.rows)
        if act in ("up", "down"):
            d = -1 if act == "up" else 1
            i = self.sel
            for _ in range(n):
                i = (i + d) % n
                if self.selectable(i):
                    break
            self.sel = i
        elif act in ("left", "right"):
            self.change(self.rows[self.sel], -1 if act == "left" else 1)
        elif act == "a":
            self.activate(self.rows[self.sel])
        elif act in ("b", "start"):
            self.app.store.save()
            self.app.pop(self)

    def change(self, row, d):
        app = self.app
        st = app.store
        k = row["kind"]
        if k == "choice":
            st.set(row["key"], C.cycle(row["table"], st.get(row["key"]), d))
            apply_theme(st)
            if row["key"] == "tile_size":
                self.ls.relayout()
        elif k == "brightness":
            bl = app.backlight
            if bl is None or not bl.available:
                app.toast(T("no_backlight"))
                return
            cur = st.get("brightness")
            if cur is None:
                cur = bl.get_percent() or 50
            new = max(bl.MIN_PERCENT, min(100, int(cur) + 5 * d))
            if bl.set_percent(new):
                st.set("brightness", new)
            else:
                app.toast(T("brightness_fail"))
        elif k == "music_on":
            self.toggle_music()
        elif k == "volume":
            v = max(0, min(100, int(st.get("music_volume")) + 10 * d))
            st.set("music_volume", v)
            if app.music:
                app.music.set_volume(v)
        elif k == "autostart":
            self.toggle_autostart()
        elif k == "mute":
            a = app.audio
            app.set_system_mute(not (a is not None and a.muted))

    def activate(self, row):
        k = row["kind"]
        if k in ("choice", "brightness", "volume"):
            self.change(row, 1)
        elif k == "music_on":
            self.toggle_music()
        elif k == "next_song":
            m = self.app.music
            if m is None or not m.available:
                self.app.toast(T("no_mixer"))
            elif not m.songs:
                self.app.toast(T("no_songs"))
            else:
                if not m.enabled:
                    self.toggle_music()
                else:
                    m.play_next()
        elif k in ("autostart", "mute"):
            self.change(row, 1)
        elif k == "reset":
            st = self.app.store
            for key, val in (("theme", C.DEFAULT_THEME), ("accent", "auto"),
                             ("tile_size", "normal")):
                st.set(key, val)
            apply_theme(st)
            self.ls.relayout()

    def toggle_music(self):
        app = self.app
        st = app.store
        on = not st.get("music")
        st.set("music", on)
        m = app.music
        if m is None or not m.available:
            app.toast(T("no_mixer"))
            return
        if on and not m.songs:
            app.toast(T("no_songs"))
        m.set_enabled(on)

    def toggle_autostart(self):
        app = self.app
        a = app.autostart
        if a is None or not a.supported:
            app.toast(T("autostart_unsupported"))
            return
        if a.enabled():
            a.disable()
            app.toast(T("autostart_off"))
        else:
            ok, why = a.enable()
            app.toast(T("autostart_on") if ok else T("autostart_fail", why), 5000)
            if ok:
                from system import write_diagnostics
                write_diagnostics(a.data_dir + "/diagnostico.txt", a,
                                  ["estado tras activar: %s" % a.status()])

    # --------------------------------------------------------------- valores
    def value(self, row):
        app = self.app
        st = app.store
        lang = current_lang()
        k = row["kind"]
        if k == "choice":
            return C.label(row["table"], st.get(row["key"]), lang)
        if k == "brightness":
            bl = app.backlight
            if bl is None or not bl.available:
                return T("not_available")
            v = st.get("brightness")
            if v is None:
                v = bl.get_percent()
            return "%d%%" % v if v is not None else "?"
        if k == "music_on":
            if app.music is None or not app.music.available:
                return T("not_available")
            return T("on") if st.get("music") else T("off")
        if k == "volume":
            return "%d%%" % st.get("music_volume")
        if k == "autostart":
            a = app.autostart
            if a is None or not a.supported:
                return T("not_available")
            return T("on") if a.enabled() else T("off")
        if k == "mute":
            a = app.audio
            if a is None or not a.available:
                return T("not_available")
            return T("on") if a.muted else T("off")
        return ""

    def subtitle(self, row):
        app = self.app
        k = row["kind"]
        if k == "next_song":
            m = app.music
            if m is None or not m.available:
                return T("no_mixer")
            if not m.songs:
                return T("no_songs")
            name = m.current_name() if (app.store.get("music") and m.enabled) else ""
            return T("now_playing", name) if name else T("songs_n", len(m.songs))
        if k == "autostart":
            a = app.autostart
            if a is None:
                return ""
            st = a.status()
            if st == "ok":
                return T("as_ok", a.last_boot()[:16])
            return T("as_" + st)
        if k == "mute":
            return T("mute_sub")
        return ""

    # ----------------------------------------------------------------- dibujo
    def update(self, now):
        dt = now - self.t
        self.t = now
        target = self._target()
        old = self.scroll
        self.scroll = smooth(self.scroll, target, dt)
        return abs(self.scroll - old) > 0.05

    def _row_h(self, row):
        g = self.g
        if row["kind"] == "header":
            return g.S(26)
        return g.S(46) if self.subtitle(row) else g.S(self.ROW)

    def _target(self):
        g = self.g
        y = 0
        for i, r in enumerate(self.rows):
            if i == self.sel:
                break
            y += self._row_h(r)
        view_h = g.h - g.S(C.HINTBAR_H) - g.S(60)
        total = sum(self._row_h(r) for r in self.rows)
        return float(max(0, min(total - view_h, y - view_h // 2)))

    def draw(self):
        g = self.g
        W = min(g.S(self.WIDTH), g.w - g.S(40))
        x = g.w - W
        H = g.h - g.S(C.HINTBAR_H)
        g.shadow(x, 0, W, H, g.S(16), 190)
        g.fill(x, 0, W, H, C.DIALOG)
        g.fill(x, 0, 1, H, (255, 255, 255, 25))
        g.icon("gear", x + g.S(16), g.S(16), g.S(18), C.ACCENT)
        g.text(T("custom_title"), x + g.S(42), g.S(14), 16, C.TEXT, bold=True)
        g.fill(x + g.S(12), g.S(48), W - g.S(24), 1, (255, 255, 255, 20))
        top = g.S(54)
        g.push_clip(x, top, W, H - top)
        y = int(top - self.scroll)
        for i, row in enumerate(self.rows):
            h = self._row_h(row)
            if y + h >= top and y < H:
                self.draw_row(row, x + g.S(8), y, W - g.S(16), h, i == self.sel)
            y += h
        g.pop_clip()

    def draw_row(self, row, x, y, w, h, focused):
        g = self.g
        k = row["kind"]
        if k == "header":
            g.text(row["label"], x + g.S(8), y + h - g.S(8), 9, C.ACCENT_SOFT, bold=True,
                   valign="middle")
            return
        if focused:
            g.round_rect(x, y + 1, w, h - 2, g.S(6), C.ACCENT)
        tcol = C.TEXT
        sub = self.subtitle(row)
        cy = y + (g.S(17) if sub else h // 2)
        g.text(row["label"], x + g.S(10), cy, 12, tcol, bold=focused, valign="middle",
               max_w=w // 2)
        if sub:
            g.text(sub, x + g.S(10), y + g.S(33), 9, C.TEXT if focused else C.TEXT3,
                   valign="middle", max_w=w - g.S(20))
        val = self.value(row)
        right = x + w - g.S(10)
        if k in ("choice", "brightness", "volume", "music_on", "autostart", "mute") and val:
            # flechas < valor >
            vw = g.text_w(val, 12, True)
            sw = 0
            swatch = self.swatch(row)
            if swatch is not None:
                sw = g.S(18)
            total = vw + sw + g.S(28)
            vx = right - total
            arrow_col = C.TEXT if focused else C.TEXT3
            g.text("‹", vx, cy, 14, arrow_col, bold=True, valign="middle")
            cx = vx + g.S(10)
            if swatch is not None:
                g.round_rect(cx, cy - g.S(6), g.S(12), g.S(12), g.S(3), swatch)
                cx += sw
            g.text(val, cx, cy, 12, C.TEXT, bold=True, valign="middle")
            g.text("›", right - g.S(6), cy, 14, arrow_col, bold=True, valign="middle")
            if k in ("brightness", "volume"):
                self.draw_bar(row, x + g.S(10), y + h - g.S(6), w - g.S(20), focused)
        elif k in ("next_song", "reset"):
            g.icon("play" if k == "next_song" else "refresh", right - g.S(14), cy - g.S(7),
                   g.S(14), C.TEXT if focused else C.TEXT2)

    def draw_bar(self, row, x, y, w, focused):
        g = self.g
        st = self.app.store
        if row["kind"] == "volume":
            v = st.get("music_volume")
        else:
            v = st.get("brightness")
            if v is None and self.app.backlight is not None and self.app.backlight.available:
                v = self.app.backlight.get_percent()
        if v is None:
            return
        g.fill(x, y, w, g.S(2), (255, 255, 255, 40))
        g.fill(x, y, int(w * v / 100.0), g.S(2), C.TEXT if focused else C.ACCENT)

    def swatch(self, row):
        if row["kind"] != "choice":
            return None
        st = self.app.store
        if row["key"] == "theme":
            return C.preset(st.get("theme"))["accent"] + (255,)
        if row["key"] == "accent":
            return C.ACCENT
        return None

    def hints(self):
        return [("\u2190\u2192", T("h_change")), ("A", T("h_select")), ("B", T("h_close"))]

    def status(self):
        return ""
