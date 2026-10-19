# -*- coding: utf-8 -*-
"""Dialogos: menu, lista con casillas, teclado en pantalla, confirmacion e info."""
import theme as C
from app import Screen, smooth
from strings import T


def _panel(g, x, y, w, h):
    g.shadow(x, y, w, h, g.S(14), 170)
    g.round_rect(x, y, w, h, g.S(10), C.DIALOG)
    g.fill(x + g.S(10), y, w - g.S(20), 1, (255, 255, 255, 22))


class ListDialog(Screen):
    """Base para dialogos con una lista vertical desplazable."""
    modal = True
    ROW = 32
    MAX_ROWS = 8
    WIDTH = 380

    def __init__(self, app, title, subtitle=""):
        Screen.__init__(self, app)
        self.title = title
        self.subtitle = subtitle
        self.sel = 0
        self.scroll = 0.0
        self.t = app.now

    def rows(self):
        return []

    def draw_row(self, i, row, x, y, w, h, focused):
        pass

    def activate(self, i):
        pass

    def action(self, act):
        n = len(self.rows())
        if act == "up" and n:
            self.sel = (self.sel - 1) % n
        elif act == "down" and n:
            self.sel = (self.sel + 1) % n
        elif act == "l1" and n:
            self.sel = max(0, self.sel - self.MAX_ROWS)
        elif act == "r1" and n:
            self.sel = min(n - 1, self.sel + self.MAX_ROWS)
        elif act == "a" and n:
            self.activate(self.sel)
        elif act == "b":
            self.app.pop(self)

    def update(self, now):
        dt = now - self.t
        self.t = now
        target = self._target_scroll()
        old = self.scroll
        self.scroll = smooth(self.scroll, target, dt)
        return abs(self.scroll - old) > 0.01

    def _target_scroll(self):
        n = len(self.rows())
        vis = min(n, self.MAX_ROWS)
        top = self.sel - vis // 2
        return float(max(0, min(n - vis, top)))

    def geometry(self):
        g = self.g
        n = len(self.rows())
        vis = max(1, min(n, self.MAX_ROWS))
        rh = g.S(self.ROW)
        head = g.S(46 if not self.subtitle else 62)
        w = min(g.S(self.WIDTH), g.w - g.S(40))
        h = head + vis * rh + g.S(12)
        x = (g.w - w) // 2
        y = max(g.S(20), (g.h - g.S(C.HINTBAR_H) - h) // 2)
        return x, y, w, h, head, rh, vis

    def draw(self):
        g = self.g
        x, y, w, h, head, rh, vis = self.geometry()
        _panel(g, x, y, w, h)
        g.text(self.title, x + g.S(18), y + g.S(14), 15, C.TEXT, bold=True, max_w=w - g.S(36))
        if self.subtitle:
            g.text(self.subtitle, x + g.S(18), y + g.S(36), 11, C.TEXT2, max_w=w - g.S(36))
        g.fill(x + g.S(12), y + head - g.S(6), w - g.S(24), 1, (255, 255, 255, 20))
        rows = self.rows()
        top = y + head
        g.push_clip(x, top, w, vis * rh + g.S(4))
        first = int(self.scroll)
        off = (self.scroll - first) * rh
        for k in range(first, min(len(rows), first + vis + 1)):
            ry = int(top + (k - first) * rh - off)
            self.draw_row(k, rows[k], x + g.S(8), ry, w - g.S(16), rh, k == self.sel)
        g.pop_clip()
        n = len(rows)
        if n > vis:
            # barra de desplazamiento
            th = max(g.S(16), int(vis * rh * vis / float(n)))
            ty = top + int((vis * rh - th) * self.scroll / float(max(1, n - vis)))
            g.round_rect(x + w - g.S(6), ty, g.S(3), th, g.S(2), (255, 255, 255, 60))

    def draw_focus(self, x, y, w, h):
        g = self.g
        g.round_rect(x, y + 1, w, h - 2, g.S(6), C.ACCENT)


class MenuDialog(ListDialog):
    """items: lista de dicts {label, fn, keep, icon, danger, value}"""

    def __init__(self, app, title, items, subtitle=""):
        ListDialog.__init__(self, app, title, subtitle)
        self.items = items

    def rows(self):
        return self.items

    def label(self, it):
        lab = it.get("label")
        return lab() if callable(lab) else lab

    def draw_row(self, i, it, x, y, w, h, focused):
        g = self.g
        if focused:
            self.draw_focus(x, y, w, h)
        tx = x + g.S(12)
        if it.get("icon"):
            g.icon(it["icon"], tx, y + (h - g.S(14)) // 2, g.S(14),
                   C.TEXT if focused else C.TEXT2)
            tx += g.S(22)
        col = C.RED if it.get("danger") and not focused else C.TEXT
        g.text(self.label(it), tx, y + h // 2, 13, col, valign="middle",
               max_w=x + w - tx - g.S(10))

    def activate(self, i):
        it = self.items[i]
        if not it.get("keep"):
            self.app.pop(self)
        fn = it.get("fn")
        if fn:
            fn()

    def hints(self):
        return [("A", T("h_select")), ("B", T("h_back"))]


class ChecklistDialog(ListDialog):
    """Lista con casillas. La primera fila puede ser 'Nueva ...'."""
    MAX_ROWS = 7

    def __init__(self, app, title, get_items, on_toggle, new_label=None, on_new=None,
                 subtitle=""):
        ListDialog.__init__(self, app, title, subtitle)
        self.get_items = get_items
        self.on_toggle = on_toggle
        self.new_label = new_label
        self.on_new = on_new

    def rows(self):
        rows = []
        if self.new_label:
            rows.append(("__new__", self.new_label, None))
        for name, checked in self.get_items():
            rows.append((name, name, checked))
        return rows

    def draw_row(self, i, row, x, y, w, h, focused):
        g = self.g
        key, label, checked = row
        if focused:
            self.draw_focus(x, y, w, h)
        bx = x + g.S(12)
        bs = g.S(16)
        by = y + (h - bs) // 2
        if key == "__new__":
            g.icon("plus", bx, by, bs, C.TEXT if focused else C.ACCENT_SOFT)
            g.text(label, bx + bs + g.S(10), y + h // 2, 13,
                   C.TEXT if focused else C.ACCENT_SOFT, bold=True, valign="middle",
                   max_w=w - g.S(60))
            return
        if checked:
            g.round_rect(bx, by, bs, bs, g.S(4), C.TEXT if focused else C.ACCENT)
            g.icon("check", bx + g.S(2), by + g.S(2), bs - g.S(4),
                   C.ACCENT if focused else C.TEXT)
        else:
            g.round_frame(bx, by, bs, bs, g.S(4), C.TEXT2 if not focused else C.TEXT, g.S(2),
                          C.ACCENT if focused else C.DIALOG)
        g.text(label, bx + bs + g.S(10), y + h // 2, 13, C.TEXT, valign="middle",
               max_w=w - g.S(60))

    def activate(self, i):
        rows = self.rows()
        key = rows[i][0]
        if key == "__new__":
            if self.on_new:
                self.on_new()
        else:
            self.on_toggle(key)

    def hints(self):
        return [("A", T("h_toggle")), ("B", T("h_ok"))]


class ConfirmDialog(Screen):
    modal = True

    def __init__(self, app, text, on_yes, yes=None, no=None, default_yes=False, danger=False):
        Screen.__init__(self, app)
        self.text = text
        self.on_yes = on_yes
        self.yes = yes or T("yes")
        self.no = no or T("no")
        self.sel = 0 if default_yes else 1
        self.danger = danger

    def action(self, act):
        if act in ("left", "right", "up", "down"):
            self.sel = 1 - self.sel
        elif act == "a":
            self.app.pop(self)
            if self.sel == 0:
                self.on_yes()
        elif act == "b":
            self.app.pop(self)

    def draw(self):
        g = self.g
        w = min(g.S(400), g.w - g.S(40))
        lines = g.wrap(self.text, 14, w - g.S(40), max_lines=6)
        lh = g.line_h(14)
        h = g.S(30) + lh * len(lines) + g.S(70)
        x = (g.w - w) // 2
        y = (g.h - g.S(C.HINTBAR_H) - h) // 2
        _panel(g, x, y, w, h)
        for i, l in enumerate(lines):
            g.text(l, g.w // 2, y + g.S(24) + i * lh, 14, C.TEXT, align="center")
        bw, bh = g.S(130), g.S(34)
        by = y + h - bh - g.S(18)
        for k, label in enumerate((self.yes, self.no)):
            bx = g.w // 2 - bw - g.S(8) if k == 0 else g.w // 2 + g.S(8)
            focused = k == self.sel
            if focused:
                col = C.RED if (self.danger and k == 0) else C.ACCENT
                g.round_rect(bx, by, bw, bh, g.S(6), col)
            else:
                g.round_rect(bx, by, bw, bh, g.S(6), C.PANEL_HI)
            g.text(label, bx + bw // 2, by + bh // 2, 13, C.TEXT, bold=True, align="center",
                   valign="middle")

    def hints(self):
        return [("A", T("h_select")), ("B", T("h_cancel"))]


class InfoDialog(Screen):
    """Texto o tabla (boton, descripcion)."""
    modal = True

    def __init__(self, app, title, text="", table=None):
        Screen.__init__(self, app)
        self.title = title
        self.text = text
        self.table = table or []

    def action(self, act):
        if act in ("a", "b", "start"):
            self.app.pop(self)

    def draw(self):
        g = self.g
        w = min(g.S(470), g.w - g.S(30))
        lh = g.line_h(13)
        if self.table:
            body_h = len(self.table) * (lh + g.S(4))
        else:
            lines = g.wrap(self.text, 13, w - g.S(40), max_lines=14)
            body_h = len(lines) * lh
        h = g.S(56) + body_h + g.S(20)
        x = (g.w - w) // 2
        y = max(g.S(8), (g.h - g.S(C.HINTBAR_H) - h) // 2)
        _panel(g, x, y, w, h)
        g.text(self.title, x + g.S(20), y + g.S(16), 16, C.TEXT, bold=True)
        g.fill(x + g.S(14), y + g.S(44), w - g.S(28), 1, (255, 255, 255, 20))
        ty = y + g.S(54)
        if self.table:
            colw = g.S(150)
            for btn, desc in self.table:
                g.text(btn, x + g.S(20), ty, 13, C.ACCENT_SOFT, bold=True)
                g.text(desc, x + g.S(20) + colw, ty, 13, C.TEXT, max_w=w - colw - g.S(40))
                ty += lh + g.S(4)
        else:
            for l in lines:
                g.text(l, x + g.S(20), ty, 13, C.TEXT)
                ty += lh

    def hints(self):
        return [("A", T("h_ok"))]


class KeyboardDialog(Screen):
    """Teclado en pantalla para escribir nombres de categorias o buscar."""
    modal = True
    LAYERS = [
        ["1234567890", "qwertyuiop", "asdfghjklñ", "zxcvbnm-.'"],
        ["1234567890", "áéíóúüç¡¿!", "?&:;,\"()+*",
         "/#@%_=[]<>"],
    ]
    BOTTOM = ("layer", "shift", "space", "back", "ok")

    def __init__(self, app, title, on_done, initial="", max_len=40):
        Screen.__init__(self, app)
        self.title = title
        self.on_done = on_done
        self.text = initial
        self.max_len = max_len
        self.layer = 0
        # primera letra en mayuscula automaticamente (como en el movil)
        self.upper = not initial
        self.auto_upper = self.upper
        self.row = 1
        self.col = 0
        self.blink_t = app.now

    def keys(self):
        rows = self.LAYERS[self.layer]
        if self.upper:
            rows = [r.upper() for r in rows]
        return rows

    def _type(self, ch):
        if len(self.text) < self.max_len:
            self.text += ch
            if self.auto_upper:
                self.upper = False
                self.auto_upper = False

    def _press(self):
        if self.row < 4:
            self._type(self.keys()[self.row][self.col])
            return
        k = self.BOTTOM[self.col // 2]
        if k == "layer":
            self.layer = 1 - self.layer
        elif k == "shift":
            self.upper = not self.upper
            self.auto_upper = False
        elif k == "space":
            self._type(" ")
        elif k == "back":
            self.text = self.text[:-1]
        elif k == "ok":
            self._done()

    def _done(self):
        self.app.pop(self)
        self.on_done(self.text.strip())

    def action(self, act):
        self.blink_t = self.app.now
        if act == "up":
            self.row = (self.row - 1) % 5
        elif act == "down":
            self.row = (self.row + 1) % 5
        elif act == "left":
            if self.row == 4:
                self.col = (self.col // 2 * 2 - 2) % 10
            else:
                self.col = (self.col - 1) % 10
        elif act == "right":
            if self.row == 4:
                self.col = (self.col // 2 * 2 + 2) % 10
            else:
                self.col = (self.col + 1) % 10
        elif act == "a":
            self._press()
        elif act == "b":
            if self.text:
                self.text = self.text[:-1]
            else:
                self.app.pop(self)
        elif act == "y":
            self._type(" ")
        elif act == "x":
            self.upper = not self.upper
            self.auto_upper = False
        elif act == "l1":
            self.layer = 1 - self.layer
        elif act == "start":
            self._done()
        elif act == "select":
            self.app.pop(self)

    def update(self, now):
        # parpadeo del cursor
        return (now - self.blink_t) % 1000 < 40

    def draw(self):
        g = self.g
        pad = g.S(14)
        gap = g.S(5)
        w = min(g.S(580), g.w - g.S(16))
        kw = (w - 2 * pad - 9 * gap) // 10
        kh = g.S(32)
        h = g.S(40) + g.S(40) + 5 * (kh + gap) + pad
        x = (g.w - w) // 2
        y = max(g.S(6), (g.h - g.S(C.HINTBAR_H) - h) // 2)
        _panel(g, x, y, w, h)
        g.text(self.title, x + pad, y + g.S(12), 14, C.TEXT, bold=True, max_w=w - 2 * pad)
        # campo de texto
        fy = y + g.S(38)
        fh = g.S(32)
        g.round_rect(x + pad, fy, w - 2 * pad, fh, g.S(6), (12, 16, 22, 255))
        g.round_frame(x + pad, fy, w - 2 * pad, fh, g.S(6), C.ACCENT, 1, None)
        g.round_rect(x + pad + 1, fy + 1, w - 2 * pad - 2, fh - 2, g.S(6), (12, 16, 22, 255))
        shown = self.text
        maxw = w - 2 * pad - g.S(24)
        while shown and g.text_w(shown, 15) > maxw:
            shown = shown[1:]
        tw = g.text(shown, x + pad + g.S(10), fy + fh // 2, 15, C.TEXT, valign="middle")
        if (self.app.now - self.blink_t) % 1000 < 550:
            g.fill(x + pad + g.S(11) + tw, fy + g.S(7), g.S(2), fh - g.S(14), C.ACCENT_SOFT)
        # teclas
        ky = fy + fh + g.S(10)
        rows = self.keys()
        for r in range(4):
            for c in range(10):
                kx = x + pad + c * (kw + gap)
                focused = self.row == r and self.col == c
                g.round_rect(kx, ky, kw, kh, g.S(5), C.ACCENT if focused else C.PANEL_HI)
                g.text(rows[r][c], kx + kw // 2, ky + kh // 2, 14, C.TEXT, bold=focused,
                       align="center", valign="middle")
            ky += kh + gap
        labels = {
            "layer": "#+=" if self.layer == 0 else "ABC",
            "shift": T("h_caps"),
            "space": T("h_space"),
            "back": T("h_delete"),
            "ok": T("h_ok"),
        }
        for i, k in enumerate(self.BOTTOM):
            kx = x + pad + i * 2 * (kw + gap)
            bw = 2 * kw + gap
            focused = self.row == 4 and self.col // 2 == i
            col = C.PANEL_HI
            if k == "ok":
                col = C.PLAY_BOTTOM
            if k == "shift" and self.upper:
                col = C.SEL
            if focused:
                col = C.ACCENT
            g.round_rect(kx, ky, bw, kh, g.S(5), col)
            g.text(labels[k], kx + bw // 2, ky + kh // 2, 12, C.TEXT, bold=True, align="center",
                   valign="middle", max_w=bw - g.S(6))

    def hints(self):
        return [("A", T("h_type")), ("B", T("h_delete")), ("Y", T("h_space")),
                ("START", T("h_ok"))]


class ReorderDialog(ListDialog):
    """Ordenar por prioridad: A coge un elemento, arriba/abajo lo mueve, A lo suelta.

    get_items() -> [(clave, texto)] en el orden actual
    move(clave, delta) -> True si se movio
    """
    MAX_ROWS = 8
    WIDTH = 420

    def __init__(self, app, title, get_items, move, subtitle="", on_close=None):
        ListDialog.__init__(self, app, title, subtitle)
        self.get_items = get_items
        self.move = move
        self.on_close = on_close
        self.grabbed = False

    def rows(self):
        return self.get_items()

    def action(self, act):
        rows = self.rows()
        n = len(rows)
        if self.grabbed and act in ("up", "down", "l1", "r1") and n:
            key = rows[self.sel][0]
            d = {"up": -1, "down": 1, "l1": -self.MAX_ROWS, "r1": self.MAX_ROWS}[act]
            moved = False
            for _ in range(abs(d)):
                if self.move(key, 1 if d > 0 else -1):
                    moved = True
                    self.sel = max(0, min(n - 1, self.sel + (1 if d > 0 else -1)))
            if not moved:
                return
            return
        if act == "a" and n:
            self.grabbed = not self.grabbed
            return
        if act == "b":
            if self.grabbed:
                self.grabbed = False
                return
            self.app.pop(self)
            if self.on_close:
                self.on_close()
            return
        if act in ("up", "down") and n:
            # sin coger: la navegacion no da la vuelta para no confundir
            self.sel = max(0, min(n - 1, self.sel + (1 if act == "down" else -1)))
            return
        ListDialog.action(self, act)

    def draw_row(self, i, row, x, y, w, h, focused):
        g = self.g
        key, label = row
        if focused:
            col = C.GREEN_BOTTOM if self.grabbed else C.ACCENT
            g.round_rect(x, y + 1, w, h - 2, g.S(6), col)
        num = "#%d" % (i + 1)
        g.text(num, x + g.S(12), y + h // 2, 13, C.TEXT if focused else C.ACCENT_SOFT,
               bold=True, valign="middle")
        g.text(label, x + g.S(52), y + h // 2, 13, C.TEXT, bold=focused, valign="middle",
               max_w=w - g.S(96))
        if focused and self.grabbed:
            s = g.S(12)
            g.icon("up", x + w - g.S(34), y + h // 2 - s - 1, s, C.TEXT)
            g.icon("down", x + w - g.S(34), y + h // 2 + 1, s, C.TEXT)
        else:
            # "agarradera" de tres rayas
            for k in range(3):
                g.fill(x + w - g.S(32), y + h // 2 - g.S(5) + k * g.S(4), g.S(14), g.S(2),
                       (255, 255, 255, 90 if focused else 40))

    def hints(self):
        if self.grabbed:
            return [("A", T("h_drop")), ("B", T("h_drop"))]
        return [("A", T("h_grab")), ("B", T("h_done"))]
