# -*- coding: utf-8 -*-
"""Vistas principales: biblioteca con pestanas, cuadricula/lista de juegos,
mosaicos de categorias y ficha del juego."""
import os
import time

import theme as C
from app import Screen, smooth
from dialogs import (ChecklistDialog, ConfirmDialog, InfoDialog, KeyboardDialog, MenuDialog,
                     ReorderDialog)
from library import sort_key
import sdl
from strings import T, current_lang, set_lang

SORTS = ("name", "system", "recent", "playtime", "playcount")
# en listas y favoritos el primer orden es tu prioridad
SORTS_LIST = ("priority", "name", "system", "recent", "playtime", "playcount")


# ---------------------------------------------------------------- formato
def fmt_playtime(secs):
    if secs <= 0:
        return T("never")
    if secs < 60:
        return T("less_minute")
    if secs < 3600:
        return T("minutes", secs // 60)
    h = secs / 3600.0
    txt = ("%.1f" % h) if h < 100 else ("%d" % h)
    if T("hours", "x").startswith("x") and T("on") == "sí":
        txt = txt.replace(".", ",")
    return T("hours", txt)


def fmt_ago(ts):
    if not ts:
        return T("never")
    now = time.time()
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    if ts >= midnight:
        return T("today")
    days = int((midnight - ts) // 86400) + 1
    if days == 1:
        return T("yesterday")
    if days < 14:
        return T("days_ago", days)
    if days < 60:
        return T("weeks_ago", days // 7)
    if days < 365:
        return T("months_ago", days // 30)
    return T("years_ago")


def fmt_count(n):
    return T("one_game") if n == 1 else T("n_games", n)


def first_letter(game):
    s = game.sortname[:1]
    return s.upper() if s.isalpha() else "#"


# ------------------------------------------------------------ comunes
def draw_tile_art(app, game, x, y, w, h, thumb_w, thumb_h, focused, show_fav=True):
    """Caratula de un juego (o un diseno con su nombre si no tiene imagen)."""
    g = app.g
    r = g.S(C.RADIUS)
    path = game.cover()
    ent = g.image(path, thumb_w, thumb_h) if path else None
    if ent:
        g.round_rect(x, y, w, h, r, (10, 13, 18, 255))
        g.draw_image(ent, x, y, w, h)
    else:
        state = g.image_state(path, thumb_w, thumb_h) if path else "missing"
        base = C.system_color(game.system.name)
        g.round_rect(x, y, w, h, r, base)
        g.fade(x, y, w, h // 2, (255, 255, 255, 28), "top")
        if state == "missing":
            lines = g.wrap(game.name, 12, w - g.S(14), max_lines=4, bold=True)
            lh = g.line_h(12, True)
            ty = y + (h - lh * len(lines)) // 2 - g.S(6)
            for i, l in enumerate(lines):
                g.text(l, x + w // 2, ty + i * lh, 12, C.TEXT, bold=True, align="center")
            g.text(game.system.name.upper(), x + w // 2, y + h - g.S(18), 9, (255, 255, 255, 150),
                   bold=True, align="center", max_w=w - g.S(10))
    if show_fav and app.store.is_favorite(game):
        s = g.S(18)
        g.icon("circle", x + w - s - g.S(4), y + g.S(4), s, (0, 0, 0, 170))
        g.icon("star", x + w - s - g.S(1), y + g.S(7), s - g.S(6), C.GOLD)


def draw_rank(g, n, x, y, focused):
    """Insignia '#n' de prioridad en la esquina de una caratula o lista."""
    label = "#%d" % n
    w = g.text_w(label, 11, True) + g.S(10)
    h = g.S(18)
    bx, by = x + g.S(4), y + g.S(4)
    g.round_rect(bx, by, w, h, g.S(9), C.ACCENT if focused or n <= 3 else (0, 0, 0, 190))
    g.text(label, bx + w // 2, by + h // 2, 11, C.TEXT, bold=True, align="center",
           valign="middle")


def draw_header(app, title, count_text, right_text="", right_icon=None, back=False):
    g = app.g
    y = g.S(C.TOPBAR_H)
    h = g.S(C.HEADER_H)
    x = g.S(C.MARGIN)
    cy = y + h // 2 + g.S(1)
    if back:
        g.icon("back", x - g.S(4), cy - g.S(7), g.S(14), C.TEXT2)
        x += g.S(14)
    x += g.text(title, x, cy, 14, C.TEXT, bold=True, valign="middle", max_w=g.w // 2)
    if count_text:
        g.text(count_text, x + g.S(8), cy + g.S(1), 11, C.TEXT3, valign="middle")
    if right_text:
        rx = g.w - g.S(C.MARGIN)
        rx -= g.text(right_text, rx, cy, 11, C.TEXT2, align="right", valign="middle")
        if right_icon:
            g.icon(right_icon, rx - g.S(18), cy - g.S(6), g.S(12), C.TEXT2)


def draw_empty(app, x, y, w, h, title, hint, icon="gamepad"):
    g = app.g
    cy = y + h // 2 - g.S(30)
    g.icon(icon, x + w // 2 - g.S(24), cy - g.S(40), g.S(48), (255, 255, 255, 50))
    g.text(title, x + w // 2, cy + g.S(20), 16, C.TEXT, bold=True, align="center")
    lines = g.wrap(hint, 12, min(w - g.S(60), g.S(420)), max_lines=4)
    for i, l in enumerate(lines):
        g.text(l, x + w // 2, cy + g.S(46) + i * g.line_h(12), 12, C.TEXT2, align="center")


# ------------------------------------------------------------ vista juegos
class GameView(object):
    """Lista de juegos en cuadricula o lista (todos, favoritos, una categoria...)."""

    def __init__(self, ls, kind, key=None, title=None):
        self.ls = ls
        self.app = ls.app
        self.g = ls.g
        self.kind = kind
        self.key = key
        self.title = title
        self.games = []
        self.sel = 0
        self.scroll = 0.0
        self.t = self.app.now
        self.refresh()
        self.scroll = self._target()

    # ---- datos
    def compute(self):
        lib, st = self.app.lib, self.app.store
        k = self.kind
        if k == "all":
            games = list(lib.games)
        elif k == "fav":
            games = st.favorites_ordered(lib.games)
        elif k == "recent":
            games = [g for g in lib.games if st.last_played(g) > 0]
            games.sort(key=lambda g: -st.last_played(g))
            return games[:100]
        elif k == "category":
            games = [lib.by_path[p] for p in st.games_in(self.key) if p in lib.by_path]
        elif k == "system":
            games = []
            for s in lib.systems:
                if s.name == self.key:
                    games = list(s.games)
        elif k == "genre":
            games = [g for g in lib.games if self.key in g.genres()]
        elif k == "search":
            q = sort_key(self.key)
            games = [g for g in lib.games if q in g.sortname or q in sort_key(g.system.fullname)]
        else:
            games = []
        return self.sort(games)

    def ordered(self):
        """Listas y favoritos tienen un orden propio (prioridad)."""
        return self.kind in ("category", "fav")

    def sort_mode(self):
        st = self.app.store
        if self.ordered():
            m = st.get("sort_list")
            return m if m in SORTS_LIST else "priority"
        m = st.get("sort")
        return m if m in SORTS else "name"

    def by_priority(self):
        return self.ordered() and self.sort_mode() == "priority"

    def sort(self, games):
        st = self.app.store
        mode = self.sort_mode()
        if mode == "priority":
            return games
        if mode == "system":
            games.sort(key=lambda g: (sort_key(g.system.fullname), g.sortname))
        elif mode == "recent":
            games.sort(key=lambda g: (-st.last_played(g), g.sortname))
        elif mode == "playtime":
            games.sort(key=lambda g: (-st.playtime(g), g.sortname))
        elif mode == "playcount":
            games.sort(key=lambda g: (-st.play_count(g), g.sortname))
        else:
            games.sort(key=lambda g: g.sortname)
        return games

    def refresh(self):
        cur = self.current()
        self.games = self.compute()
        if cur is not None:
            for i, g in enumerate(self.games):
                if g is cur:
                    self.sel = i
                    break
        self.sel = max(0, min(self.sel, len(self.games) - 1))

    def current(self):
        if 0 <= self.sel < len(self.games):
            return self.games[self.sel]
        return None

    def select_path(self, path):
        for i, g in enumerate(self.games):
            if g.path == path:
                self.sel = i
                self.scroll = self._target()
                return True
        return False

    def heading(self):
        if self.title:
            return self.title
        return T({"all": "title_all", "fav": "title_fav", "recent": "title_recent"}
                 .get(self.kind, "title_all"))

    # ---- geometria
    def mode(self):
        return self.app.store.get("view")

    def layout(self):
        g = self.g
        x, y, w, h = self.ls.content_rect()
        m = g.S(C.MARGIN)
        if self.mode() == "list":
            rh = g.S(46)
            return dict(x=x + m, y=y, w=w - 2 * m, h=h, cols=1, tw=w - 2 * m, th=rh - g.S(4),
                        rh=rh, list=True)
        tw, th, cols, gap = self.ls.tile_size()
        return dict(x=x + m, y=y, w=w - 2 * m, h=h, cols=cols, tw=tw, th=th, rh=th + gap,
                    list=False, gap=gap)

    def _target(self):
        L = self.layout()
        n = len(self.games)
        if not n:
            return 0.0
        rows = (n + L["cols"] - 1) // L["cols"]
        row = self.sel // L["cols"]
        pad = self.g.S(12)
        total = rows * L["rh"] + pad * 2
        maxs = max(0, total - L["h"])
        t = pad + row * L["rh"] - (L["h"] - L["rh"]) / 2.0
        return float(max(0, min(maxs, t)))

    def update(self, now):
        dt = now - self.t
        self.t = now
        target = self._target()
        old = self.scroll
        self.scroll = smooth(self.scroll, target, dt)
        return abs(self.scroll - old) > 0.05

    # ---- entrada
    def action(self, act):
        n = len(self.games)
        L = self.layout()
        cols = L["cols"]
        if act in ("up", "down", "left", "right") and n:
            if L["list"]:
                vis = max(1, L["h"] // L["rh"])
                step = {"up": -1, "down": 1, "left": -vis, "right": vis}[act]
                self.sel = max(0, min(n - 1, self.sel + step))
            elif act == "left":
                if self.sel % cols == 0:
                    return False
                self.sel -= 1
            elif act == "right":
                if self.sel % cols < cols - 1 and self.sel < n - 1:
                    self.sel += 1
            elif act == "up":
                if self.sel >= cols:
                    self.sel -= cols
            elif act == "down":
                if self.sel + cols < n:
                    self.sel += cols
                elif self.sel // cols < (n - 1) // cols:
                    self.sel = n - 1
            return True
        if act in ("l2", "r2") and n:
            if self.by_priority():
                self.move_priority(1 if act == "r2" else -1)
            else:
                self.jump(1 if act == "r2" else -1)
            return True
        game = self.current()
        if act == "a" and game is not None:
            self.app.push(DetailScreen(self.app, self.ls, self.games, self.sel))
            return True
        if act == "x" and game is not None:
            open_categories(self.app, game)
            return True
        if act == "y" and game is not None:
            on = self.app.store.toggle_favorite(game)
            self.app.store.save()
            self.app.toast(T("fav_on") if on else T("fav_off"))
            if self.kind == "fav":
                self.refresh()
            return True
        if act == "select":
            self.app.store.set("view", "list" if self.mode() == "grid" else "grid")
            self.app.store.save()
            self.ls.relayout()
            return True
        return False

    def move_priority(self, d=None, index=None):
        """Sube/baja el juego seleccionado en la lista (o en favoritos)."""
        game = self.current()
        if game is None:
            return
        st = self.app.store
        visible = [g.path for g in self.games]
        if self.kind == "fav":
            ok = st.move_favorite(visible, game.path, d, index)
        else:
            ok = st.move_game(self.key, visible, game.path, d, index)
        if not ok:
            return
        st.save()
        self.refresh()
        self.app.toast(T("prio_n", self.sel + 1), 900)

    def jump(self, d):
        """L2/R2: salta a la siguiente/anterior letra (o una pagina)."""
        n = len(self.games)
        if self.sort_mode() != "name" or self.kind == "recent":
            L = self.layout()
            page = max(1, L["h"] // L["rh"]) * L["cols"]
            self.sel = max(0, min(n - 1, self.sel + d * page))
            return
        cur = first_letter(self.games[self.sel])
        i = self.sel
        if d > 0:
            while i < n and first_letter(self.games[i]) == cur:
                i += 1
            self.sel = min(i, n - 1)
        else:
            if i > 0 and first_letter(self.games[i - 1]) == cur:
                while i > 0 and first_letter(self.games[i - 1]) == cur:
                    i -= 1
            else:
                i = max(0, i - 1)
                prev = first_letter(self.games[i])
                while i > 0 and first_letter(self.games[i - 1]) == prev:
                    i -= 1
            self.sel = i
        self.app.toast(first_letter(self.games[self.sel]), 600)

    # ---- dibujo
    def draw(self):
        g = self.g
        sort_label = T("sort_" + self.sort_mode()) if self.kind != "recent" else ""
        draw_header(self.app, self.heading(), fmt_count(len(self.games)),
                    T("sort_short", sort_label) if sort_label else "",
                    "list" if self.mode() == "list" else "grid",
                    back=len(self.ls.stack()) > 1)
        L = self.layout()
        ax, ay, aw, ah = self.ls.content_rect()
        if not self.games:
            self.draw_empty(ax, ay, aw, ah)
            return
        g.push_clip(ax, ay, aw, ah)
        if L["list"]:
            self.draw_list(L)
        else:
            self.draw_grid(L)
        g.pop_clip()
        # sombras de desplazamiento arriba/abajo
        if self.scroll > 1:
            g.fade(ax, ay, aw, g.S(14), (0, 0, 0, 120), "top")

    def draw_empty(self, x, y, w, h):
        k = self.kind
        if k == "fav":
            draw_empty(self.app, x, y, w, h, T("empty_fav"), T("empty_fav_hint"), "star")
        elif k == "recent":
            draw_empty(self.app, x, y, w, h, T("empty_recent"), T("empty_recent_hint"), "clock")
        elif k == "category":
            draw_empty(self.app, x, y, w, h, T("empty_cat"), T("empty_cat_hint"), "tag")
        elif k == "search":
            draw_empty(self.app, x, y, w, h, T("empty_search"), T("empty_search_hint"), "search")
        else:
            hint = T("no_games_hint")
            if self.app.lib.errors:
                hint = self.app.lib.errors[0] + "\n\n" + hint
            draw_empty(self.app, x, y, w, h, T("no_games"), hint)

    def draw_grid(self, L):
        g = self.g
        cols, tw, th, rh = L["cols"], L["tw"], L["th"], L["rh"]
        gap = L["gap"]
        pad = g.S(12)
        n = len(self.games)
        first_row = max(0, int((self.scroll - pad) // rh) - 1)
        last_row = int((self.scroll + L["h"]) // rh) + 1
        focus_rect = None
        prio = self.by_priority()
        for row in range(first_row, last_row + 1):
            for col in range(cols):
                i = row * cols + col
                if i >= n:
                    break
                x = L["x"] + col * (tw + gap)
                y = int(L["y"] + pad + row * rh - self.scroll)
                if i == self.sel:
                    focus_rect = (x, y)
                    continue
                g.shadow(x, y + g.S(2), tw, th, g.S(5), 90)
                draw_tile_art(self.app, self.games[i], x, y, tw, th, tw, th, False)
                if prio:
                    draw_rank(g, i + 1, x, y, False)
        # la seleccionada se dibuja al final, algo mas grande (estilo Steam)
        if focus_rect is not None:
            x, y = focus_rect
            grow = g.S(5)
            fx, fy, fw, fh = x - grow, y - grow, tw + 2 * grow, th + 2 * grow
            g.shadow(fx, fy + g.S(4), fw, fh, g.S(12), 200)
            g.round_rect(fx - g.S(2), fy - g.S(2), fw + g.S(4), fh + g.S(4), g.S(C.RADIUS + 2),
                         C.FOCUS)
            draw_tile_art(self.app, self.games[self.sel], fx, fy, fw, fh, tw, th, True)
            if prio:
                draw_rank(g, self.sel + 1, fx, fy, True)

    def draw_list(self, L):
        g = self.g
        st = self.app.store
        rh = L["rh"]
        pad = g.S(12)
        n = len(self.games)
        first = max(0, int((self.scroll - pad) // rh) - 1)
        last = min(n - 1, int((self.scroll + L["h"]) // rh) + 1)
        thw, thh = g.S(32), g.S(40)
        prio = self.by_priority()
        for i in range(first, last + 1):
            game = self.games[i]
            x = L["x"]
            y = int(L["y"] + pad + i * rh - self.scroll)
            w = L["w"]
            h = rh - g.S(4)
            focused = i == self.sel
            if focused:
                g.round_rect(x, y, w, h, g.S(6), C.FOCUS)
            elif i % 2 == 0:
                g.round_rect(x, y, w, h, g.S(6), (255, 255, 255, 8))
            tcol = C.DARK_TEXT if focused else C.TEXT
            scol = (70, 80, 92, 255) if focused else C.TEXT3
            # miniatura
            path = game.cover()
            ent = g.image(path, thw, thh) if path else None
            tx = x + g.S(6)
            ty = y + (h - thh) // 2
            if ent:
                g.draw_image(ent, tx, ty, thw, thh)
            else:
                g.round_rect(tx, ty, thw, thh, g.S(3), C.system_color(game.system.name))
            nx = tx + thw + g.S(10)
            if prio:
                g.text("#%d" % (i + 1), nx, y + h // 2, 13, C.ACCENT if not focused else C.DARK_TEXT,
                       bold=True, valign="middle")
                nx += g.S(34)
            right = x + w - g.S(10)
            # columna derecha: tiempo de juego / favorito
            pt = st.playtime(game)
            if pt:
                right -= g.text(fmt_playtime(pt), right, y + h // 2, 11, scol, align="right",
                                valign="middle") + g.S(8)
            if st.is_favorite(game):
                g.icon("star", right - g.S(14), y + h // 2 - g.S(7), g.S(14), C.GOLD)
                right -= g.S(20)
            g.text(game.name, nx, y + g.S(6), 13, tcol, bold=True, max_w=right - nx)
            sub = game.system.fullname
            cats = st.categories_of(game.path)
            if cats:
                sub += "  ·  " + ", ".join(cats)
            g.text(sub, nx, y + g.S(24), 11, scol, max_w=right - nx)

    def status(self):
        game = self.current()
        if game is None:
            return ""
        return "%s  ·  %s" % (game.name, game.system.fullname)

    def hints(self):
        h = []
        if self.current() is not None:
            h += [("A", T("h_details")), ("X", T("h_cats"))]
            if self.by_priority() and len(self.games) > 1:
                h.append(("L2/R2", T("h_priority")))
            else:
                h.append(("Y", T("h_fav")))
        if len(self.ls.stack()) > 1:
            h.append(("B", T("h_back")))
        h.append(("START", T("h_menu")))
        return h


# ------------------------------------------------------- vista colecciones
class CollectionView(object):
    """Mosaicos de categorias, sistemas o generos."""

    def __init__(self, ls, kind):
        self.ls = ls
        self.app = ls.app
        self.g = ls.g
        self.kind = kind
        self.items = []
        self.sel = 0
        self.scroll = 0.0
        self.t = self.app.now
        self.refresh()

    def refresh(self):
        lib, st = self.app.lib, self.app.store
        cur = self.items[self.sel]["key"] if 0 <= self.sel < len(self.items) else None
        items = []
        if self.kind == "cats":
            items.append({"key": "__new__", "title": T("new_cat"), "games": [], "icon": "plus"})
            for c in st.categories():
                games = [lib.by_path[p] for p in c["games"] if p in lib.by_path]
                items.append({"key": c["name"], "title": c["name"], "games": games,
                              "icon": "tag"})
        elif self.kind == "systems":
            for s in lib.systems:
                items.append({"key": s.name, "title": s.fullname, "games": s.games,
                              "icon": "system"})
        elif self.kind == "genres":
            groups = {}
            for game in lib.games:
                for gen in game.genres():
                    groups.setdefault(gen, []).append(game)
            for gen in sorted(groups, key=sort_key):
                items.append({"key": gen, "title": gen, "games": groups[gen], "icon": "tag"})
        self.items = items
        if cur is not None:
            for i, it in enumerate(items):
                if it["key"] == cur:
                    self.sel = i
                    break
        self.sel = max(0, min(self.sel, len(items) - 1))

    def heading(self):
        return T({"cats": "title_cats", "systems": "title_systems",
                  "genres": "title_genres"}[self.kind])

    def layout(self):
        g = self.g
        x, y, w, h = self.ls.content_rect()
        m = g.S(C.MARGIN)
        gap = g.S(12)
        cols = max(2, int((w - 2 * m + gap) // (g.S(180) + gap)))
        tw = (w - 2 * m - (cols - 1) * gap) // cols
        th = g.S(128)
        return dict(x=x + m, y=y, w=w - 2 * m, h=h, cols=cols, tw=tw, th=th, gap=gap,
                    rh=th + gap)

    def _target(self):
        L = self.layout()
        n = len(self.items)
        if not n:
            return 0.0
        rows = (n + L["cols"] - 1) // L["cols"]
        row = self.sel // L["cols"]
        pad = self.g.S(12)
        total = rows * L["rh"] + pad * 2
        maxs = max(0, total - L["h"])
        t = pad + row * L["rh"] - (L["h"] - L["rh"]) / 2.0
        return float(max(0, min(maxs, t)))

    def update(self, now):
        dt = now - self.t
        self.t = now
        old = self.scroll
        self.scroll = smooth(self.scroll, self._target(), dt)
        return abs(self.scroll - old) > 0.05

    def current(self):
        if 0 <= self.sel < len(self.items):
            return self.items[self.sel]
        return None

    def action(self, act):
        n = len(self.items)
        cols = self.layout()["cols"]
        if act in ("up", "down", "left", "right") and n:
            if act == "left":
                if self.sel % cols == 0:
                    return False
                self.sel -= 1
            elif act == "right":
                if self.sel % cols < cols - 1 and self.sel < n - 1:
                    self.sel += 1
            elif act == "up":
                if self.sel >= cols:
                    self.sel -= cols
            elif act == "down":
                if self.sel + cols < n:
                    self.sel += cols
                elif self.sel // cols < (n - 1) // cols:
                    self.sel = n - 1
            return True
        it = self.current()
        if it is None:
            return False
        if act == "a":
            if it["key"] == "__new__":
                create_category(self.app, on_created=lambda name: self._created(name))
            else:
                kind = {"cats": "category", "systems": "system", "genres": "genre"}[self.kind]
                self.ls.open_view(GameView(self.ls, kind, it["key"], it["title"]))
            return True
        if act == "x" and self.kind == "cats" and it["key"] != "__new__":
            category_options(self.app, self.ls, it["key"])
            return True
        if act in ("l2", "r2") and self.kind == "cats" and it["key"] != "__new__":
            st = self.app.store
            if st.move(it["key"], -1 if act == "l2" else 1):
                st.save()
                refresh_library(self.app)
                self.select_key(it["key"])
                self.app.toast(T("prio_n", st.priority(it["key"])), 900)
            return True
        return False

    def _created(self, name):
        self.refresh()
        for i, it in enumerate(self.items):
            if it["key"] == name:
                self.sel = i

    def draw(self):
        g = self.g
        n = len(self.items)
        count = ""
        if self.kind == "cats":
            count = T("one_cat") if n - 1 == 1 else T("n_cats", n - 1)
        if self.kind == "systems":
            count = fmt_count(len(self.app.lib.games))
        draw_header(self.app, self.heading(), count)
        L = self.layout()
        ax, ay, aw, ah = self.ls.content_rect()
        g.push_clip(ax, ay, aw, ah)
        pad = g.S(12)
        first_row = max(0, int((self.scroll - pad) // L["rh"]) - 1)
        last_row = int((self.scroll + L["h"]) // L["rh"]) + 1
        for row in range(first_row, last_row + 1):
            for col in range(L["cols"]):
                i = row * L["cols"] + col
                if i >= n:
                    break
                x = L["x"] + col * (L["tw"] + L["gap"])
                y = int(L["y"] + pad + row * L["rh"] - self.scroll)
                self.draw_tile(self.items[i], x, y, L["tw"], L["th"], i == self.sel)
        g.pop_clip()
        if self.kind == "cats" and n == 1:
            g.text(T("empty_cat_hint"), g.w // 2, ay + pad + L["th"] + g.S(40), 12, C.TEXT2,
                   align="center")

    def draw_tile(self, it, x, y, w, h, focused):
        g = self.g
        r = g.S(8)
        if focused:
            g.shadow(x, y + g.S(4), w, h, g.S(12), 200)
            g.round_rect(x - g.S(3), y - g.S(3), w + g.S(6), h + g.S(6), r + g.S(3), C.FOCUS)
        else:
            g.shadow(x, y + g.S(2), w, h, g.S(6), 100)
        if it["key"] == "__new__":
            g.round_rect(x, y, w, h, r, (34, 46, 62, 255))
            g.round_frame(x + g.S(6), y + g.S(6), w - g.S(12), h - g.S(12), r - g.S(2),
                          (255, 255, 255, 40), 1, (34, 46, 62, 255))
            s = g.S(30)
            g.icon("plus", x + (w - s) // 2, y + h // 2 - s, s, C.ACCENT_SOFT)
            g.text(it["title"], x + w // 2, y + h // 2 + g.S(12), 13, C.TEXT, bold=True,
                   align="center", max_w=w - g.S(16))
            return
        base = C.system_color(it["title"], 0.22, 0.35)
        g.round_rect(x, y, w, h, r, base)
        strip_h = h - g.S(44)
        games = [gm for gm in it["games"] if gm.cover()][:4]
        tw, th, _cols, _gap = self.ls.tile_size()
        if games:
            k = len(games)
            cw = (w - g.S(8) - (k - 1) * g.S(4)) // k
            for j, gm in enumerate(games):
                cx = x + g.S(4) + j * (cw + g.S(4))
                ent = g.image(gm.cover(), tw, th)
                if ent:
                    g.draw_image(ent, cx, y + g.S(4), cw, strip_h - g.S(4), mode="cover")
                else:
                    g.fill(cx, y + g.S(4), cw, strip_h - g.S(4), (0, 0, 0, 60))
            g.fade(x, y + strip_h - g.S(30), w, g.S(30), (0, 0, 0, 140), "bottom")
        else:
            s = g.S(40)
            g.icon(it["icon"], x + (w - s) // 2, y + (strip_h - s) // 2 + g.S(2), s,
                   (255, 255, 255, 70))
        # pie con nombre y numero de juegos
        foot = C.mix(base, (8, 11, 16, 255), 0.75)
        g.fill(x, y + strip_h, w, h - strip_h - r, foot)
        g.round_rect(x, y + h - 2 * r, w, 2 * r, r, foot)
        g.text(it["title"], x + g.S(10), y + strip_h + g.S(6), 13, C.TEXT, bold=True,
               max_w=w - g.S(20))
        n = len(it["games"])
        g.text(fmt_count(n) if n else T("no_games_cat"), x + g.S(10), y + strip_h + g.S(24), 11,
               C.TEXT2, max_w=w - g.S(20))
        if self.kind == "cats":
            st = self.app.store
            draw_rank(g, st.priority(it["key"]), x, y, focused)
            if st.is_pinned(it["key"]):
                s = g.S(20)
                g.icon("circle", x + w - s - g.S(4), y + g.S(4), s, (0, 0, 0, 170))
                g.icon("pin", x + w - s - g.S(1), y + g.S(7), s - g.S(6), C.ACCENT_SOFT)

    def status(self):
        it = self.current()
        if it is None or it["key"] == "__new__":
            return ""
        return "%s  ·  %s" % (it["title"], fmt_count(len(it["games"])))

    def hints(self):
        h = [("A", T("h_open"))]
        it = self.current()
        if self.kind == "cats" and it is not None and it["key"] != "__new__":
            h.append(("X", T("h_options")))
            if len(self.items) > 2:
                h.append(("L2/R2", T("h_priority")))
        h.append(("START", T("h_menu")))
        return h

    def select_key(self, key):
        for i, it in enumerate(self.items):
            if it["key"] == key:
                self.sel = i
                self.scroll = self._target()
                return True
        return False


# ------------------------------------------------- acciones compartidas
def create_category(app, on_created=None, add_game=None):
    def done(name):
        if not name:
            return
        if not app.store.create(name, pinned=True):
            app.toast(T("cat_exists"))
            return
        if add_game is not None:
            app.store.add(name, add_game.path)
        app.store.save()
        app.toast(T("added_to", name) if add_game is not None else T("cat_created", name))
        if on_created:
            on_created(name)
        refresh_library(app)

    app.push(KeyboardDialog(app, T("new_cat_title"), done))


def open_categories(app, game):
    st = app.store

    def items():
        return [(name, st.contains(name, game.path)) for name in st.category_names()]

    def toggle(name):
        added = st.toggle(name, game.path)
        st.save()
        app.toast(T("added_to", name) if added else T("removed_from", name), 1500)
        refresh_library(app)

    def new():
        create_category(app, add_game=game)

    app.push(ChecklistDialog(app, T("cats_of", game.name), items, toggle, T("new_cat") + "…",
                             new))


def category_options(app, ls, name):
    st = app.store

    def rename():
        def done(new):
            if not new or new == name:
                return
            if not st.rename(name, new):
                app.toast(T("cat_exists"))
                return
            st.save()
            ls.rename_category(name, new)
            refresh_library(app)

        app.push(KeyboardDialog(app, T("rename_title", name), done, initial=name))

    def delete():
        def yes():
            st.delete(name)
            st.save()
            ls.category_deleted(name)
            refresh_library(app)
            app.toast(T("deleted"))

        app.push(ConfirmDialog(app, T("delete_confirm", name), yes, danger=True))

    cur = {"name": name}

    def move(d=None, index=None):
        def fn():
            if index is not None:
                st.move_to(cur["name"], index)
            else:
                st.move(cur["name"], d)
            st.save()
            refresh_library(app)
            app.toast(T("prio_n", st.priority(cur["name"])), 1200)
        return fn

    def pin():
        on = not st.is_pinned(cur["name"])
        st.set_pinned(cur["name"], on)
        st.save()
        refresh_library(app)
        app.toast(T("pinned_on", cur["name"]) if on else T("pinned_off", cur["name"]))

    items = [
        {"label": lambda: T("pin_tab", T("on") if st.is_pinned(cur["name"]) else T("off")),
         "fn": pin, "keep": True, "icon": "pin"},
        {"label": T("move_top"), "fn": move(index=0), "icon": "star"},
        {"label": T("move_up"), "fn": move(-1), "icon": "up"},
        {"label": T("move_down"), "fn": move(1), "icon": "down"},
        {"label": T("reorder_lists"), "fn": lambda: reorder_lists(app), "icon": "list"},
        {"label": T("rename_cat"), "fn": rename, "icon": "tag"},
        {"label": T("delete_cat"), "fn": delete, "danger": True, "icon": "trash"},
    ]
    app.push(MenuDialog(app, T("manage_cat", name), items,
                        subtitle=T("prio_n", st.priority(name)) + "  \u00b7  " +
                        T("priority_hint")))


def reorder_lists(app):
    """Pantalla para ordenar las listas: A coge, arriba/abajo mueve, A suelta."""
    st = app.store
    if not st.category_names():
        app.toast(T("no_lists"))
        return

    def items():
        return [(n, n) for n in st.category_names()]

    def move(name, d):
        ok = st.move(name, d)
        if ok:
            st.save()
            refresh_library(app)
        return ok

    app.push(ReorderDialog(app, T("reorder_lists_title"), items, move, T("reorder_sub")))


def reorder_games(app, view):
    """Igual, pero para los juegos de una lista o de Favoritos."""
    st = app.store

    def items():
        return [(gm.path, "%s  \u00b7  %s" % (gm.name, gm.system.name.upper()))
                for gm in view.games]

    def move(path, d):
        visible = [gm.path for gm in view.games]
        if view.kind == "fav":
            ok = st.move_favorite(visible, path, d)
        else:
            ok = st.move_game(view.key, visible, path, d)
        if ok:
            st.save()
            view.refresh()
        return ok

    title = T("reorder_games_title", T("title_fav") if view.kind == "fav" else view.key)
    dlg = ReorderDialog(app, title, items, move, T("reorder_sub"))
    dlg.sel = view.sel
    app.push(dlg)


def refresh_library(app):
    for scr in app.screens:
        if isinstance(scr, LibraryScreen):
            scr.build_tabs()
            scr.refresh_all()
        elif isinstance(scr, DetailScreen):
            scr.refresh()


# ---------------------------------------------------------- biblioteca
class LibraryScreen(Screen):
    TAB_KEYS = ("all", "fav", "recent", "cats", "systems", "genres")

    def __init__(self, app):
        Screen.__init__(self, app)
        self.tabs = []
        self.stacks = {}
        self.tab = 0
        self.ul_x = 0.0
        self.ul_w = 0.0
        self.tab_off = 0.0
        self.t = app.now
        self.build_tabs()
        key = app.store.get("tab")
        if key in self.tabs:
            self.tab = self.tabs.index(key)

    def build_tabs(self):
        # Las listas marcadas como pestana van justo despues de Favoritos,
        # en su orden de prioridad.
        keys = ["all", "fav"] + ["list:" + n for n in self.app.store.pinned_names()]
        keys += ["recent", "cats", "systems"]
        if self.app.store.get("show_genres") and any(g.genres() for g in self.app.lib.games):
            keys.append("genres")
        old = self.tabs[self.tab] if self.tabs else None
        self.tabs = keys
        for k in list(self.stacks):
            if k not in keys:
                del self.stacks[k]
        for k in keys:
            if k not in self.stacks:
                self.stacks[k] = [self.root_view(k)]
        self.tab = keys.index(old) if old in keys else min(self.tab, len(keys) - 1)

    def root_view(self, key):
        if key.startswith("list:"):
            name = key[5:]
            return GameView(self, "category", name, name)
        if key in ("all", "fav", "recent"):
            return GameView(self, key)
        return CollectionView(self, key)

    def tab_label(self, key):
        if key.startswith("list:"):
            return self.g.ellipsize(key[5:].upper(), 11, True, self.g.S(110))
        return T("tab_" + key)

    def stack(self):
        return self.stacks[self.tabs[self.tab]]

    def view(self):
        return self.stack()[-1]

    def open_view(self, v):
        self.stack().append(v)

    def content_rect(self):
        g = self.g
        y = g.S(C.TOPBAR_H + C.HEADER_H)
        return 0, y, g.w, g.h - y - g.S(C.HINTBAR_H)

    def tile_size(self):
        g = self.g
        _x, _y, w, _h = self.content_rect()
        m = g.S(C.MARGIN)
        gap = g.S(C.GAP)
        cols = max(2, int((w - 2 * m + gap) // (g.S(C.TILE_MIN) + gap)))
        tw = (w - 2 * m - (cols - 1) * gap) // cols
        th = int(tw * 1.25)
        return tw, th, cols, gap

    def relayout(self):
        for st in self.stacks.values():
            for v in st:
                v.scroll = v._target()

    def refresh_all(self):
        for st in self.stacks.values():
            for v in st:
                v.refresh()

    def rename_category(self, old, new):
        ok, nk = "list:" + old, "list:" + new
        if ok in self.stacks:
            self.stacks[nk] = self.stacks.pop(ok)
        self.tabs = [nk if k == ok else k for k in self.tabs]
        for st in self.stacks.values():
            for v in st:
                if isinstance(v, GameView) and v.kind == "category" and v.key == old:
                    v.key = new
                    v.title = new

    def category_deleted(self, name):
        self.stacks.pop("list:" + name, None)
        for k, st in self.stacks.items():
            self.stacks[k] = [v for v in st if not (isinstance(v, GameView) and
                                                    v.kind == "category" and v.key == name)]

    def on_resume(self):
        self.refresh_all()

    # ---- reanudar tras jugar
    def save_resume(self, game, detail):
        st = []
        for v in self.stack()[1:]:
            if isinstance(v, GameView):
                st.append([v.kind, v.key, v.title])
        self.app.store.set("resume", {"tab": self.tabs[self.tab], "stack": st,
                                      "game": game.path if game else None,
                                      "detail": bool(detail)})

    def apply_resume(self):
        store = self.app.store
        r = store.get("resume")
        if not isinstance(r, dict):
            return
        store.set("resume", None)
        if r.get("tab") in self.tabs:
            self.tab = self.tabs.index(r["tab"])
        root = self.stack()[0]
        for kind, key, title in r.get("stack") or []:
            if isinstance(root, CollectionView):
                root.select_key(key)
            self.open_view(GameView(self, kind, key, title))
        path = r.get("game")
        v = self.view()
        if path and isinstance(v, GameView) and v.select_path(path):
            if r.get("detail"):
                self.app.push(DetailScreen(self.app, self, v.games, v.sel))
                self.app.inp.reset()

    # ---- entrada
    def action(self, act):
        if act in ("l1", "r1"):
            d = -1 if act == "l1" else 1
            self.tab = (self.tab + d) % len(self.tabs)
            self.app.store.set("tab", self.tabs[self.tab])
            self.view().refresh()
            return
        v = self.view()
        if v.action(act):
            return
        if act == "b":
            if len(self.stack()) > 1:
                self.stack().pop()
                self.view().refresh()
            else:
                self.app.push(ConfirmDialog(self.app, T("quit_confirm"), self.app.quit,
                                            default_yes=True))
        elif act == "start":
            self.open_menu()
        elif act == "select":
            st = self.app.store
            st.set("view", "list" if st.get("view") == "grid" else "grid")
            st.save()
            self.relayout()
            self.app.toast(T("view_grid") if st.get("view") == "grid" else T("view_list"), 1200)

    def open_menu(self):
        app = self.app
        st = app.store
        v = self.view()
        items = [{"label": T("search"), "fn": self.search, "icon": "search"},
                 {"label": T("customize"), "fn": self.customize, "icon": "gear"}]
        if app.audio is not None and app.audio.available:
            items.append({"label": lambda: T("menu_unmute") if app.audio.muted
                          else T("menu_mute"),
                          "fn": lambda: app.set_system_mute(not app.audio.muted), "keep": True,
                          "icon": "mute" if not app.audio.muted else "speaker"})
        if isinstance(v, GameView) and v.kind != "recent":
            key, opts = ("sort_list", SORTS_LIST) if v.ordered() else ("sort", SORTS)

            def cycle_sort():
                i = opts.index(v.sort_mode()) if v.sort_mode() in opts else 0
                st.set(key, opts[(i + 1) % len(opts)])
                st.save()
                self.refresh_all()
                self.relayout()
            items.append({"label": lambda: T("sort", T("sort_" + v.sort_mode())),
                          "fn": cycle_sort, "keep": True, "icon": "list"})
            if v.by_priority() and v.current() is not None and v.sel > 0:
                items.append({"label": T("game_top"), "fn": lambda: v.move_priority(index=0),
                              "icon": "star"})

        def toggle_view():
            st.set("view", "list" if st.get("view") == "grid" else "grid")
            st.save()
            self.relayout()
        items.append({"label": lambda: T("view_grid") if st.get("view") == "grid"
                      else T("view_list"), "fn": toggle_view, "keep": True, "icon": "grid"})
        items.append({"label": T("new_cat") + "…", "fn": lambda: create_category(app),
                      "icon": "plus"})
        items.append({"label": T("reorder_lists"), "fn": lambda: reorder_lists(app),
                      "icon": "list"})
        if isinstance(v, GameView) and v.ordered() and len(v.games) > 1:
            label = T("reorder_favs") if v.kind == "fav" else T("reorder_games", v.key)
            items.append({"label": label, "fn": lambda: reorder_games(app, v), "icon": "up"})
        if isinstance(v, GameView) and v.kind == "category":
            name = v.key
            game = v.current()
            if game is not None:
                def remove():
                    st.remove(name, game.path)
                    st.save()
                    refresh_library(app)
                    app.toast(T("removed_from", name))
                items.append({"label": T("remove_from_cat", name), "fn": remove, "icon": "tag"})
            items.append({"label": T("manage_cat", name),
                          "fn": lambda: category_options(app, self, name), "icon": "gear"})
        items.append({"label": T("export_es"), "fn": self.export_es, "icon": "export"})
        items.append({"label": T("import_es"), "fn": self.import_es, "icon": "import"})
        items.append({"label": T("rescan"), "fn": self.rescan, "icon": "refresh"})

        def toggle_genres():
            st.set("show_genres", not st.get("show_genres"))
            st.save()
            self.build_tabs()
        items.append({"label": lambda: T("genres_tab", T("on") if st.get("show_genres")
                                         else T("off")),
                      "fn": toggle_genres, "keep": True, "icon": "tag"})

        def toggle_lang():
            st.set("lang", "en" if st.get("lang") == "es" else "es")
            st.save()
            set_lang(st.get("lang"))
            self.refresh_all()
        items.append({"label": lambda: T("language"), "fn": toggle_lang, "keep": True,
                      "icon": "globe"})
        items.append({"label": T("help"), "icon": "gamepad",
                      "fn": lambda: app.push(InfoDialog(app, T("help"),
                                                        table=T("help_lines")))})
        items.append({"label": T("about"), "icon": "info",
                      "fn": lambda: app.push(InfoDialog(app, T("about"), T("about_text")))})
        items.append({"label": T("quit"), "fn": app.quit, "icon": "exit"})
        app.push(MenuDialog(app, T("menu"), items))

    def customize(self):
        from settings_ui import SettingsScreen
        self.app.push(SettingsScreen(self.app, self))

    def search(self):
        def done(q):
            if not q:
                return
            self.open_view(GameView(self, "search", q, T("results", q)))
        self.app.push(KeyboardDialog(self.app, T("search_title"), done))

    def export_es(self):
        app = self.app
        try:
            n = app.store.export_to_es(app.lib.collections_dir())
            app.push(InfoDialog(app, T("export_es"), T("export_done", n)))
        except (IOError, OSError) as e:
            app.toast(T("export_fail", str(e)))

    def import_es(self):
        app = self.app
        n = app.store.import_from_es(app.lib.collections_dir(), app.lib.home,
                                     set(app.lib.by_path))
        app.store.save()
        self.refresh_all()
        app.toast(T("import_done", n))

    def rescan(self):
        app = self.app
        g = self.g
        g.vgradient(0, 0, g.w, g.h, C.BG_TOP, C.BG_BOTTOM)
        g.text(T("loading"), g.w // 2, g.h // 2, 16, C.TEXT, bold=True, align="center",
               valign="middle")
        sdl.SDL_RenderPresent(g.ren)
        app.lib.load(use_cache=False)
        app.store.fix_paths(app.lib.by_path)
        self.stacks = {}
        self.build_tabs()
        self.relayout()

    # ---- dibujo
    def _tab_layout(self):
        g = self.g
        labels = [self.tab_label(k) for k in self.tabs]
        widths = [g.text_w(l, 11, True) for l in labels]
        l1w = g.text_w("L1", 8, True) + g.S(10)
        status_w = g.S(108)
        left = g.S(10) + l1w + g.S(8)
        right = g.w - g.S(10) - status_w - l1w - g.S(6)
        avail = right - left
        pad = g.S(18)
        total = sum(widths) + pad * len(widths)
        while total > avail and pad > g.S(12):
            pad -= 1
            total = sum(widths) + pad * len(widths)
        rel = []
        x = 0
        for w in widths:
            rel.append((x + pad // 2, w))
            x += w + pad
        scroll = total > avail
        return dict(labels=labels, rel=rel, left=left, avail=avail, total=total, pad=pad,
                    scroll=scroll, r1x=(right + g.S(6)) if scroll else left + total)

    def _tab_offset_target(self, L):
        if not L["scroll"]:
            return 0.0
        x, w = L["rel"][self.tab]
        off = self.tab_off
        margin = L["pad"] + self.g.S(16)
        if x - off < margin:
            off = x - margin
        if x + w - off > L["avail"] - margin:
            off = x + w - L["avail"] + margin
        return float(max(0, min(L["total"] - L["avail"], off)))

    def _tab_target(self):
        L = self._tab_layout()
        x, w = L["rel"][self.tab]
        return float(L["left"] + x - self.tab_off), float(w)

    def update(self, now):
        dt = now - self.t
        self.t = now
        anim = False
        for st in self.stacks.values():
            for v in st[-1:]:
                if v.update(now):
                    anim = True
        L = self._tab_layout()
        oo = self.tab_off
        self.tab_off = smooth(self.tab_off, self._tab_offset_target(L), dt, 0.3)
        tx, tw = self._tab_target()
        ox, ow = self.ul_x, self.ul_w
        self.ul_x = smooth(self.ul_x, tx, dt, 0.3)
        self.ul_w = smooth(self.ul_w, tw, dt, 0.3)
        if abs(self.ul_x - ox) > 0.05 or abs(self.ul_w - ow) > 0.05 or \
                abs(self.tab_off - oo) > 0.05:
            anim = True
        return anim

    def draw(self):
        g = self.g
        g.vgradient(0, 0, g.w, g.h, C.BG_TOP, C.BG_BOTTOM)
        self.view().draw()
        # barra superior con pestanas
        bh = g.S(C.TOPBAR_H)
        g.fill(0, 0, g.w, bh, C.BAR)
        g.fill(0, bh - 1, g.w, 1, C.BAR_LINE)
        L = self._tab_layout()
        cy = bh // 2
        self.app.draw_glyph("L1", g.S(10), cy)
        g.push_clip(L["left"], 0, L["avail"], bh)
        for i, (label, (x, w)) in enumerate(zip(L["labels"], L["rel"])):
            col = C.TEXT if i == self.tab else C.TEXT3
            if self.tabs[i].startswith("list:") and i != self.tab:
                col = C.mix(C.TEXT3, C.ACCENT_SOFT, 0.45)
            g.text(label, int(L["left"] + x - self.tab_off), cy, 11, col, bold=True,
                   valign="middle")
        if self.ul_w <= 0:
            self.ul_x, self.ul_w = self._tab_target()
        g.round_rect(int(self.ul_x), bh - g.S(4), int(self.ul_w), g.S(3), g.S(1), C.ACCENT)
        g.pop_clip()
        self.app.draw_glyph("R1", L["r1x"], cy)
        self.app.draw_status_icons(g.w - g.S(10), cy)

    def hints(self):
        return self.view().hints()

    def status(self):
        return self.view().status()


# --------------------------------------------------------------- ficha
class DetailScreen(Screen):
    BUTTONS = ("play", "fav", "cats")

    def __init__(self, app, ls, games, index):
        Screen.__init__(self, app)
        self.ls = ls
        self.games = games
        self.index = index
        self.focus = 0
        self.desc_scroll = 0
        self.t = app.now

    @property
    def game(self):
        return self.games[self.index]

    def refresh(self):
        pass

    def action(self, act):
        if act == "left":
            self.focus = max(0, self.focus - 1)
        elif act == "right":
            self.focus = min(len(self.BUTTONS) - 1, self.focus + 1)
        elif act == "up":
            self.desc_scroll = max(0, self.desc_scroll - 1)
        elif act == "down":
            self.desc_scroll += 1
        elif act in ("l1", "r1") and len(self.games) > 1:
            d = -1 if act == "l1" else 1
            self.index = (self.index + d) % len(self.games)
            self.desc_scroll = 0
            v = self.ls.view()
            if isinstance(v, GameView) and v.games is self.games:
                v.sel = self.index
        elif act == "a":
            b = self.BUTTONS[self.focus]
            if b == "play":
                self.play()
            elif b == "fav":
                self.toggle_fav()
            else:
                open_categories(self.app, self.game)
        elif act == "x":
            open_categories(self.app, self.game)
        elif act == "y":
            self.toggle_fav()
        elif act == "b":
            self.app.pop(self)

    def toggle_fav(self):
        on = self.app.store.toggle_favorite(self.game)
        self.app.store.save()
        self.app.toast(T("fav_on") if on else T("fav_off"))

    def play(self):
        self.ls.save_resume(self.game, True)
        self.app.launch(self.game)

    def draw(self):
        g = self.g
        app = self.app
        st = app.store
        game = self.game
        W, H = g.w, g.h
        g.vgradient(0, 0, W, H, C.BG_TOP, C.BG_BOTTOM)
        hero_h = g.S(262)
        hero = game.hero()
        ent = g.image(hero, W, W) if hero else None
        if ent:
            g.draw_image(ent, 0, 0, W, hero_h, mode="cover", alpha=95)
        else:
            col = C.system_color(game.system.name, 0.28, 0.4)
            g.fade(0, 0, W, hero_h, (col[0], col[1], col[2], 160), "top")
        g.fade(0, hero_h // 3, W, hero_h - hero_h // 3, C.BG_BOTTOM, "bottom")
        g.fade(0, 0, W, g.S(40), (0, 0, 0, 120), "top")
        # migas de pan
        g.icon("back", g.S(12), g.S(11), g.S(12), C.TEXT2)
        g.text(T("library"), g.S(28), g.S(10), 10, C.TEXT2, bold=True)
        app.draw_status_icons(W - g.S(12), g.S(17))
        # poster
        px, py, pw, ph = g.S(24), g.S(40), g.S(150), g.S(196)
        poster = game.poster()
        pent = g.image(poster, pw, ph) if poster else None
        if pent:
            rx, ry, rw, rh = g.fit_rect(pent, px, py, pw, ph, align="bottom")
            g.shadow(rx, ry + g.S(4), rw, rh, g.S(10), 170)
            g.draw_image(pent, px, py, pw, ph, align="bottom")
        else:
            g.shadow(px, py, pw, ph, g.S(10), 170)
            draw_tile_art(app, game, px, py, pw, ph, pw, ph, False, show_fav=False)
        # titulo y datos
        tx = px + pw + g.S(20)
        tw = W - tx - g.S(20)
        g.text(game.system.fullname.upper(), tx, g.S(72), 11, C.ACCENT_SOFT, bold=True,
               max_w=tw)
        lines = g.wrap(game.name, 22, tw, max_lines=3, bold=True)
        lh = g.line_h(22, True)
        y = g.S(90)
        for l in lines:
            g.text(l, tx, y, 22, C.TEXT, bold=True)
            y += lh
        meta = [x for x in (game.year, game.developer or game.publisher) if x]
        if meta:
            g.text("  ·  ".join(meta), tx, y + g.S(4), 12, C.TEXT2, max_w=tw)
            y += g.S(22)
        if game.rating > 0:
            stars = int(round(game.rating * 5))
            for k in range(5):
                g.icon("star" if k < stars else "star_outline", tx + k * g.S(16), y + g.S(6),
                       g.S(13), C.GOLD if k < stars else (255, 255, 255, 70))
        # barra de acciones
        by = g.S(252)
        bh = g.S(58)
        g.fill(0, by, W, bh, (10, 14, 20, 170))
        g.fill(0, by, W, 1, (255, 255, 255, 14))
        bx = g.S(24)
        btn_h = g.S(38)
        btn_y = by + (bh - btn_h) // 2
        btn_w = g.S(138)
        focused = self.BUTTONS[self.focus]
        if focused == "play":
            g.round_rect(bx - g.S(3), btn_y - g.S(3), btn_w + g.S(6), btn_h + g.S(6), g.S(8),
                         C.FOCUS)
        g.round_rect(bx, btn_y, btn_w, btn_h, g.S(6), C.GREEN_BOTTOM)
        g.push_clip(bx, btn_y, btn_w, btn_h)
        g.fade(bx, btn_y, btn_w, btn_h, C.GREEN_TOP, "top")
        g.pop_clip()
        g.icon("play", bx + g.S(22), btn_y + (btn_h - g.S(16)) // 2, g.S(16), C.TEXT)
        g.text(T("play"), bx + g.S(46), btn_y + btn_h // 2, 15, C.TEXT, bold=True,
               valign="middle")
        # estadisticas
        sx = bx + btn_w + g.S(22)
        for label, value in ((T("last_played"), fmt_ago(st.last_played(game))),
                             (T("playtime"), fmt_playtime(st.playtime(game)))):
            g.text(label, sx, btn_y + g.S(2), 9, C.TEXT3, bold=True)
            w = g.text(value, sx, btn_y + g.S(17), 13, C.TEXT)
            sx += max(w, g.text_w(label, 9, True)) + g.S(22)
        # botones redondos: favorito y categorias
        cs = g.S(38)
        cx = W - g.S(24) - cs * 2 - g.S(10)
        fav = st.is_favorite(game)
        for name, icon, active in (("fav", "star" if fav else "star_outline", fav),
                                   ("cats", "tag", bool(st.categories_of(game.path)))):
            if focused == name:
                g.icon("circle", cx - g.S(3), btn_y - g.S(3), cs + g.S(6), C.FOCUS)
            g.icon("circle", cx, btn_y, cs, C.PANEL_HI)
            col = C.GOLD if (name == "fav" and active) else (C.ACCENT_SOFT if active else C.TEXT)
            g.icon(icon, cx + g.S(10), btn_y + g.S(10), cs - g.S(20), col)
            cx += cs + g.S(10)
        # descripcion y detalles
        top = by + bh + g.S(12)
        bottom = H - g.S(C.HINTBAR_H) - g.S(8)
        colw = g.S(184)
        dx = g.S(24)
        dw = W - dx - colw - g.S(36)
        desc = game.desc or T("no_desc")
        dlines = g.wrap(desc, 12, dw)
        dlh = g.line_h(12)
        vis = max(1, (bottom - top) // dlh)
        self.desc_scroll = max(0, min(self.desc_scroll, max(0, len(dlines) - vis)))
        g.push_clip(dx, top, dw, bottom - top)
        for i, l in enumerate(dlines[self.desc_scroll:self.desc_scroll + vis + 1]):
            g.text(l, dx, top + i * dlh, 12, C.TEXT2 if game.desc else C.TEXT3)
        g.pop_clip()
        if len(dlines) > vis:
            trk = bottom - top
            th = max(g.S(14), trk * vis // len(dlines))
            ty = top + (trk - th) * self.desc_scroll // max(1, len(dlines) - vis)
            g.round_rect(dx + dw + g.S(6), ty, g.S(3), th, g.S(2), (255, 255, 255, 60))
        # columna derecha
        cx = W - colw - g.S(20)
        g.round_rect(cx, top - g.S(4), colw, bottom - top + g.S(4), g.S(8), (255, 255, 255, 10))
        y = top + g.S(4)
        rows = []
        if game.genre and game.genre.lower() != "unknown":
            rows.append((T("genre"), game.genre))
        if game.players and game.players not in ("1", ""):
            rows.append((T("players"), game.players))
        if game.publisher and game.publisher != game.developer:
            rows.append((T("publisher"), game.publisher))
        if not rows:
            rows.append((T("file"), os.path.basename(game.path)))
        for label, value in rows[:3]:
            g.text(label.upper(), cx + g.S(10), y, 9, C.TEXT3, bold=True)
            g.text(value, cx + g.S(10), y + g.S(12), 11, C.TEXT, max_w=colw - g.S(20))
            y += g.S(30)
        g.text(T("in_cats").upper(), cx + g.S(10), y, 9, C.TEXT3, bold=True)
        y += g.S(14)
        cats = st.categories_of(game.path)
        if not cats:
            g.text(T("no_cats_yet"), cx + g.S(10), y, 11, C.TEXT3, max_w=colw - g.S(20))
        else:
            chx = cx + g.S(10)
            for name in cats:
                w = min(g.text_w(name, 10, True) + g.S(14), colw - g.S(20))
                if chx + w > cx + colw - g.S(10):
                    chx = cx + g.S(10)
                    y += g.S(22)
                if y > bottom - g.S(18):
                    break
                g.round_rect(chx, y, w, g.S(18), g.S(9), (26, 159, 255, 70))
                g.text(name, chx + w // 2, y + g.S(9), 10, C.TEXT, bold=True, align="center",
                       valign="middle", max_w=w - g.S(8))
                chx += w + g.S(6)

    def hints(self):
        b = self.BUTTONS[self.focus]
        first = {"play": T("h_play"), "fav": T("h_fav"), "cats": T("h_cats")}[b]
        h = [("A", first), ("B", T("h_back")), ("X", T("h_cats")), ("Y", T("h_fav"))]
        if len(self.games) > 1:
            h.insert(2, ("L1/R1", T("h_game")))
        return h

    def status(self):
        return ""
