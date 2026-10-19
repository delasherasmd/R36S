# -*- coding: utf-8 -*-
"""Capa grafica: fuentes, cache de textos, carga de caratulas en segundo plano,
rectangulos redondeados, degradados e iconos. Todo sobre SDL_Renderer."""
import ctypes
import os
import threading
from collections import OrderedDict

import sdl
import theme as C

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
WHITE = (255, 255, 255, 255)


def _enc(s):
    return s.encode("utf-8", "replace")


class Font(object):
    def __init__(self, path, size):
        self.ptr = sdl.TTF_OpenFont(_enc(path), size)
        if not self.ptr:
            raise RuntimeError("No se pudo abrir la fuente %s: %s" % (path, sdl.error()))
        self.size = size
        self.height = sdl.TTF_FontHeight(self.ptr)
        self.ascent = sdl.TTF_FontAscent(self.ptr)
        self._widths = {}

    def width(self, text):
        if not text:
            return 0
        w = self._widths.get(text)
        if w is None:
            cw = ctypes.c_int()
            ch = ctypes.c_int()
            sdl.TTF_SizeUTF8(self.ptr, _enc(text), ctypes.byref(cw), ctypes.byref(ch))
            w = cw.value
            if len(self._widths) > 4000:
                self._widths.clear()
            self._widths[text] = w
        return w

    def close(self):
        if self.ptr:
            sdl.TTF_CloseFont(self.ptr)
            self.ptr = None


class ImageLoader(object):
    """Carga imagenes (IMG_Load) en un hilo aparte. ctypes libera el GIL durante
    las llamadas a C, asi que la interfaz sigue fluida mientras se decodifica."""

    MAX_SOFT = 1024  # imagenes mas grandes se reducen primero por software

    def __init__(self):
        self.lock = threading.Condition()
        self.pending = {}  # key -> (path, max_w, max_h, frame)
        self.done = []  # (key, surface_ptr or None)
        self.frame = 0
        self.alive = True
        self.thread = None
        if sdl.IMG_Load is not None:
            self.thread = threading.Thread(target=self._run, name="vapor-img")
            self.thread.daemon = True
            self.thread.start()

    def request(self, key, path, max_w, max_h):
        with self.lock:
            if key in self.pending:
                p = self.pending[key]
                self.pending[key] = (p[0], p[1], p[2], self.frame)
            else:
                self.pending[key] = (path, max_w, max_h, self.frame)
                self.lock.notify()

    def tick(self):
        with self.lock:
            self.frame += 1
            # descartar peticiones que ya no se ven (el usuario se desplazo)
            stale = [k for k, v in self.pending.items() if self.frame - v[3] > 20]
            for k in stale:
                del self.pending[k]

    def take_done(self, limit):
        with self.lock:
            out = self.done[:limit]
            del self.done[:limit]
            return out

    def stop(self):
        with self.lock:
            self.alive = False
            self.lock.notify_all()
        if self.thread is not None:
            self.thread.join(1.0)
        for _k, surf in self.take_done(10000):
            if surf:
                sdl.SDL_FreeSurface(surf)

    def _run(self):
        while True:
            with self.lock:
                while self.alive and not self.pending:
                    self.lock.wait()
                if not self.alive:
                    return
                # lo pedido mas recientemente primero
                key = max(self.pending, key=lambda k: self.pending[k][3])
                path, mw, mh, _f = self.pending.pop(key)
            surf = self._load(path, mw, mh)
            with self.lock:
                if not self.alive:
                    if surf:
                        sdl.SDL_FreeSurface(surf)
                    return
                self.done.append((key, surf))

    def _load(self, path, mw, mh):
        try:
            if not path or not os.path.isfile(path):
                return None
            raw = sdl.IMG_Load(_enc(path))
            if not raw:
                return None
            surf = sdl.SDL_ConvertSurfaceFormat(raw, sdl.SDL_PIXELFORMAT_ARGB8888, 0)
            sdl.SDL_FreeSurface(raw)
            if not surf:
                return None
            w, h = surf.contents.w, surf.contents.h
            # Reduccion previa (vecino mas cercano) solo para imagenes enormes;
            # el ajuste fino se hace luego en GPU con filtrado lineal.
            limit = max(self.MAX_SOFT, 2 * max(mw, mh))
            if w > limit or h > limit:
                f = float(limit) / max(w, h)
                nw, nh = max(1, int(w * f)), max(1, int(h * f))
                small = sdl.SDL_CreateRGBSurfaceWithFormat(0, nw, nh, 32,
                                                           sdl.SDL_PIXELFORMAT_ARGB8888)
                if small:
                    sdl.SDL_SetSurfaceBlendMode(surf, sdl.SDL_BLENDMODE_NONE)
                    dst = sdl.rect(0, 0, nw, nh)
                    sdl.SDL_UpperBlitScaled(surf, None, small, ctypes.byref(dst))
                    sdl.SDL_FreeSurface(surf)
                    surf = small
            return surf
        except Exception:
            return None


class Gfx(object):
    def __init__(self, ren, width, height):
        self.ren = ren
        self.w = width
        self.h = height
        # escala respecto al diseno base de 640x480 (pantalla del R36S)
        self.s = min(width / 640.0, height / 480.0)
        self.fonts = {}
        self.text_cache = OrderedDict()
        self.text_cache_max = 700
        self.icons = {}
        self.images = OrderedDict()  # key -> (tex, w, h) o None si fallo
        self.images_max = 90
        self.loader = ImageLoader()
        self.target_ok = bool(sdl.SDL_RenderTargetSupported(ren))
        self._grad = None
        self._clip_stack = []
        self.statics = {}  # imagenes fijas de assets (fondos, logo)
        self._load_icons()

    # ------------------------------------------------------------------ util
    def S(self, v):
        return int(round(v * self.s))

    def font(self, size, bold=False):
        px = max(8, self.S(size))
        key = (px, bold)
        f = self.fonts.get(key)
        if f is None:
            name = "Inter-Bold.otf" if bold else "Inter-Regular.otf"
            f = Font(os.path.join(ASSETS, "fonts", name), px)
            self.fonts[key] = f
        return f

    def _load_icons(self):
        d = os.path.join(ASSETS, "icons")
        if sdl.IMG_Load is None or not os.path.isdir(d):
            return
        for fn in os.listdir(d):
            if not fn.endswith(".png"):
                continue
            surf = sdl.IMG_Load(_enc(os.path.join(d, fn)))
            if not surf:
                continue
            tex = sdl.SDL_CreateTextureFromSurface(self.ren, surf)
            sdl.SDL_FreeSurface(surf)
            if tex:
                sdl.SDL_SetTextureBlendMode(tex, sdl.SDL_BLENDMODE_BLEND)
                self.icons[fn[:-4]] = tex
        # degradado vertical: blanco opaco arriba -> transparente abajo
        n = 128
        data = bytearray()
        for i in range(n):
            data += bytes((255, 255, 255, 255 - (i * 255) // (n - 1)))
        self._grad = self._texture_from_bytes(data, 1, n)

    def _texture_from_bytes(self, data, w, h):
        tex = sdl.SDL_CreateTexture(self.ren, sdl.SDL_PIXELFORMAT_ABGR8888,
                                    sdl.SDL_TEXTUREACCESS_STATIC, w, h)
        if not tex:
            return None
        buf = (ctypes.c_ubyte * len(data)).from_buffer(data)
        sdl.SDL_UpdateTexture(tex, None, buf, w * 4)
        sdl.SDL_SetTextureBlendMode(tex, sdl.SDL_BLENDMODE_BLEND)
        return tex

    # ------------------------------------------------------------ primitivas
    def set_color(self, c):
        a = c[3] if len(c) > 3 else 255
        sdl.SDL_SetRenderDrawColor(self.ren, c[0], c[1], c[2], a)
        sdl.SDL_SetRenderDrawBlendMode(self.ren, sdl.SDL_BLENDMODE_BLEND if a < 255
                                       else sdl.SDL_BLENDMODE_NONE)

    def clear(self, c):
        self.set_color(c)
        sdl.SDL_RenderClear(self.ren)

    def fill(self, x, y, w, h, c):
        if w <= 0 or h <= 0:
            return
        self.set_color(c)
        r = sdl.rect(x, y, w, h)
        sdl.SDL_RenderFillRect(self.ren, ctypes.byref(r))

    def outline(self, x, y, w, h, c, t=1):
        for i in range(t):
            self.set_color(c)
            r = sdl.rect(x + i, y + i, w - 2 * i, h - 2 * i)
            sdl.SDL_RenderDrawRect(self.ren, ctypes.byref(r))

    def line(self, x1, y1, x2, y2, c):
        self.set_color(c)
        sdl.SDL_RenderDrawLine(self.ren, int(x1), int(y1), int(x2), int(y2))

    def _copy(self, tex, src, dst):
        sdl.SDL_RenderCopy(self.ren, tex, ctypes.byref(src) if src else None,
                           ctypes.byref(dst) if dst else None)

    def _tint(self, tex, c):
        sdl.SDL_SetTextureColorMod(tex, c[0], c[1], c[2])
        sdl.SDL_SetTextureAlphaMod(tex, c[3] if len(c) > 3 else 255)

    def round_rect(self, x, y, w, h, r, c):
        """Rectangulo con esquinas redondeadas (anti-aliasing via textura circular)."""
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w <= 0 or h <= 0:
            return
        r = int(min(r, w // 2, h // 2))
        circ = self.icons.get("circle")
        if r <= 1 or circ is None:
            self.fill(x, y, w, h, c)
            return
        self.fill(x + r, y, w - 2 * r, h, c)
        self.fill(x, y + r, r, h - 2 * r, c)
        self.fill(x + w - r, y + r, r, h - 2 * r, c)
        self._tint(circ, c)
        half = 32  # la textura del circulo mide 64x64
        for (sx, sy, dx, dy) in ((0, 0, x, y), (half, 0, x + w - r, y),
                                 (0, half, x, y + h - r), (half, half, x + w - r, y + h - r)):
            self._copy(circ, sdl.rect(sx, sy, half, half), sdl.rect(dx, dy, r, r))

    def round_frame(self, x, y, w, h, r, c, t, inner=None):
        """Marco redondeado de grosor t. Si 'inner' es None el interior no se
        pinta (para dibujar luego una imagen encima)."""
        self.round_rect(x, y, w, h, r, c)
        if inner is not None:
            self.round_rect(x + t, y + t, w - 2 * t, h - 2 * t, max(0, r - t), inner)

    def vgradient(self, x, y, w, h, top, bottom):
        """Degradado vertical de 'top' a 'bottom'."""
        self.fill(x, y, w, h, bottom)
        if self._grad is None:
            return
        self._tint(self._grad, top)
        self._copy(self._grad, None, sdl.rect(x, y, w, h))

    def fade(self, x, y, w, h, c, opaque_at="top"):
        """Capa de color que se desvanece (opaca arriba o abajo)."""
        if self._grad is None:
            return
        self._tint(self._grad, c)
        dst = sdl.rect(x, y, w, h)
        if opaque_at == "top":
            self._copy(self._grad, None, dst)
        else:
            sdl.SDL_RenderCopyEx(self.ren, self._grad, None, ctypes.byref(dst), 0.0, None,
                                 sdl.SDL_FLIP_VERTICAL)

    def shadow(self, x, y, w, h, spread, alpha=150):
        """Sombra difusa alrededor de un rectangulo (9-slice de 'shadow')."""
        tex = self.icons.get("shadow")
        if tex is None or spread <= 0:
            return
        self._tint(tex, (0, 0, 0, alpha))
        sp = int(spread)
        x0, y0, x1, y1 = int(x) - sp, int(y) - sp, int(x + w) + sp, int(y + h) + sp
        half = 32
        # esquinas
        self._copy(tex, sdl.rect(0, 0, half, half), sdl.rect(x0, y0, 2 * sp, 2 * sp))
        self._copy(tex, sdl.rect(half, 0, half, half), sdl.rect(x1 - 2 * sp, y0, 2 * sp, 2 * sp))
        self._copy(tex, sdl.rect(0, half, half, half), sdl.rect(x0, y1 - 2 * sp, 2 * sp, 2 * sp))
        self._copy(tex, sdl.rect(half, half, half, half),
                   sdl.rect(x1 - 2 * sp, y1 - 2 * sp, 2 * sp, 2 * sp))
        mw = (x1 - x0) - 4 * sp
        mh = (y1 - y0) - 4 * sp
        if mw > 0:
            self._copy(tex, sdl.rect(half - 1, 0, 2, half), sdl.rect(x0 + 2 * sp, y0, mw, 2 * sp))
            self._copy(tex, sdl.rect(half - 1, half, 2, half),
                       sdl.rect(x0 + 2 * sp, y1 - 2 * sp, mw, 2 * sp))
        if mh > 0:
            self._copy(tex, sdl.rect(0, half - 1, half, 2), sdl.rect(x0, y0 + 2 * sp, 2 * sp, mh))
            self._copy(tex, sdl.rect(half, half - 1, half, 2),
                       sdl.rect(x1 - 2 * sp, y0 + 2 * sp, 2 * sp, mh))
        if mw > 0 and mh > 0:
            self.fill(x0 + 2 * sp, y0 + 2 * sp, mw, mh, (0, 0, 0, alpha))

    def static(self, name):
        """Textura de una imagen de assets/ (fondos, logo). None si no se puede."""
        if name in self.statics:
            return self.statics[name]
        ent = None
        path = os.path.join(ASSETS, name)
        if sdl.IMG_Load is not None and os.path.isfile(path):
            surf = sdl.IMG_Load(_enc(path))
            if surf:
                tex = sdl.SDL_CreateTextureFromSurface(self.ren, surf)
                if tex:
                    ent = (tex, surf.contents.w, surf.contents.h)
                sdl.SDL_FreeSurface(surf)
        self.statics[name] = ent
        return ent

    def draw_static(self, name, x, y, w, h, alpha=255):
        ent = self.static(name)
        if not ent:
            return False
        self.draw_image(ent, x, y, w, h, mode="cover", alpha=alpha)
        return True

    def background(self):
        """Fondo del tema: imagen (tema Vapor) o degradado."""
        if C.BG_IMAGE and self.draw_static(C.BG_IMAGE, 0, 0, self.w, self.h):
            return
        self.vgradient(0, 0, self.w, self.h, C.BG_TOP, C.BG_BOTTOM)

    def text_spaced(self, text, cx, y, size, c=WHITE, bold=False, spacing=6):
        """Texto centrado con letras separadas (como el 'CARGANDO' del logo)."""
        sp = self.S(spacing)
        widths = [self.text_w(ch, size, bold) for ch in text]
        total = sum(widths) + sp * (len(text) - 1)
        x = cx - total // 2
        for ch, w in zip(text, widths):
            if ch != " ":
                self.text(ch, x, y, size, c, bold=bold)
            x += w + sp

    def icon(self, name, x, y, size, c=WHITE):
        tex = self.icons.get(name)
        if tex is None:
            return False
        self._tint(tex, c)
        self._copy(tex, None, sdl.rect(x, y, size, size))
        return True

    def push_clip(self, x, y, w, h):
        r = sdl.rect(x, y, max(0, w), max(0, h))
        self._clip_stack.append(r)
        sdl.SDL_RenderSetClipRect(self.ren, ctypes.byref(r))

    def pop_clip(self):
        if self._clip_stack:
            self._clip_stack.pop()
        if self._clip_stack:
            sdl.SDL_RenderSetClipRect(self.ren, ctypes.byref(self._clip_stack[-1]))
        else:
            sdl.SDL_RenderSetClipRect(self.ren, None)

    # ----------------------------------------------------------------- texto
    def _text_tex(self, text, size, bold):
        key = (text, size, bold)
        ent = self.text_cache.get(key)
        if ent is not None:
            self.text_cache.move_to_end(key)
            return ent
        f = self.font(size, bold)
        surf = sdl.TTF_RenderUTF8_Blended(f.ptr, _enc(text), sdl.SDL_Color(255, 255, 255, 255))
        if not surf:
            ent = (None, 0, 0)
        else:
            tex = sdl.SDL_CreateTextureFromSurface(self.ren, surf)
            ent = (tex, surf.contents.w, surf.contents.h)
            sdl.SDL_FreeSurface(surf)
            if tex:
                sdl.SDL_SetTextureBlendMode(tex, sdl.SDL_BLENDMODE_BLEND)
        self.text_cache[key] = ent
        while len(self.text_cache) > self.text_cache_max:
            _k, old = self.text_cache.popitem(last=False)
            if old[0]:
                sdl.SDL_DestroyTexture(old[0])
        return ent

    def text_w(self, text, size, bold=False):
        return self.font(size, bold).width(text)

    def line_h(self, size, bold=False):
        return self.font(size, bold).height

    def ellipsize(self, text, size, bold, max_w):
        f = self.font(size, bold)
        if max_w is None or f.width(text) <= max_w:
            return text
        ell = u"…"
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if f.width(text[:mid].rstrip() + ell) <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + ell if lo > 0 else ell

    def text(self, text, x, y, size, c=WHITE, bold=False, align="left", max_w=None,
             valign="top"):
        """Dibuja texto. Devuelve el ancho dibujado."""
        if not text:
            return 0
        text = self.ellipsize(text, size, bold, max_w)
        tex, w, h = self._text_tex(text, size, bold)
        if not tex:
            return 0
        if align == "center":
            x = x - w // 2
        elif align == "right":
            x = x - w
        if valign == "middle":
            y = y - h // 2
        self._tint(tex, c)
        self._copy(tex, None, sdl.rect(x, y, w, h))
        return w

    def wrap(self, text, size, max_w, max_lines=None, bold=False):
        f = self.font(size, bold)
        lines = []
        for para in (text or "").replace("\r", "").split("\n"):
            words = para.split()
            if not words:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            cur = ""
            for wd in words:
                cand = wd if not cur else cur + " " + wd
                if f.width(cand) <= max_w:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    # palabra mas larga que la linea: se corta
                    while f.width(wd) > max_w and len(wd) > 1:
                        cut = len(wd)
                        while cut > 1 and f.width(wd[:cut]) > max_w:
                            cut -= 1
                        lines.append(wd[:cut])
                        wd = wd[cut:]
                    cur = wd
            if cur:
                lines.append(cur)
        while lines and lines[-1] == "":
            lines.pop()
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.ellipsize(lines[-1] + u" …", size, bold, max_w)
        return lines

    # -------------------------------------------------------------- imagenes
    def image(self, path, max_w, max_h):
        """Devuelve (tex, w, h) si la imagen ya esta lista, None si no hay o
        si todavia se esta cargando (se pide al hilo de carga)."""
        if not path:
            return None
        key = (path, int(max_w), int(max_h))
        if key in self.images:
            ent = self.images[key]
            self.images.move_to_end(key)
            return ent
        self.loader.request(key, path, int(max_w), int(max_h))
        return None

    def image_state(self, path, max_w, max_h):
        """'ok', 'missing' o 'loading'."""
        key = (path, int(max_w), int(max_h))
        if key in self.images:
            return "ok" if self.images[key] else "missing"
        return "loading"

    def pump_images(self, limit=3):
        """Convierte en texturas las imagenes ya decodificadas. Devuelve True si
        hubo alguna nueva (para redibujar)."""
        self.loader.tick()
        done = self.loader.take_done(limit)
        for key, surf in done:
            ent = None
            if surf:
                ent = self._make_thumb(surf, key[1], key[2])
                sdl.SDL_FreeSurface(surf)
            self.images[key] = ent
            while len(self.images) > self.images_max:
                _k, old = self.images.popitem(last=False)
                if old and old[0]:
                    sdl.SDL_DestroyTexture(old[0])
        return bool(done)

    def _make_thumb(self, surf, max_w, max_h):
        sw, sh = surf.contents.w, surf.contents.h
        if sw <= 0 or sh <= 0:
            return None
        f = min(float(max_w) / sw, float(max_h) / sh, 1.0)
        fw, fh = max(1, int(round(sw * f))), max(1, int(round(sh * f)))
        tex = sdl.SDL_CreateTextureFromSurface(self.ren, surf)
        if not tex:
            return None
        cw, ch = sw, sh
        if self.target_ok and (cw > fw or ch > fh):
            # reducciones a la mitad en GPU (filtrado lineal) => buena calidad
            while True:
                nw, nh = cw // 2, ch // 2
                if nw < fw or nh < fh:
                    nw, nh = fw, fh
                t2 = sdl.SDL_CreateTexture(self.ren, sdl.SDL_PIXELFORMAT_ARGB8888,
                                           sdl.SDL_TEXTUREACCESS_TARGET, nw, nh)
                if not t2:
                    break
                sdl.SDL_SetRenderTarget(self.ren, t2)
                sdl.SDL_SetRenderDrawColor(self.ren, 0, 0, 0, 0)
                sdl.SDL_RenderClear(self.ren)
                sdl.SDL_SetTextureBlendMode(tex, sdl.SDL_BLENDMODE_NONE)
                sdl.SDL_RenderCopy(self.ren, tex, None, None)
                sdl.SDL_SetRenderTarget(self.ren, None)
                sdl.SDL_DestroyTexture(tex)
                tex = t2
                cw, ch = nw, nh
                if (cw, ch) == (fw, fh):
                    break
        sdl.SDL_SetTextureBlendMode(tex, sdl.SDL_BLENDMODE_BLEND)
        return (tex, cw, ch)

    def fit_rect(self, ent, x, y, w, h, align="center"):
        """Rectangulo donde quedaria la imagen ajustada (modo 'contain')."""
        _tex, iw, ih = ent
        f = min(float(w) / iw, float(h) / ih)
        dw, dh = int(iw * f), int(ih * f)
        if align == "bottom":
            return x + (w - dw) // 2, y + h - dh, dw, dh
        return x + (w - dw) // 2, y + (h - dh) // 2, dw, dh

    def draw_image(self, ent, x, y, w, h, mode="contain", alpha=255, align="center"):
        """Dibuja una imagen ya cargada dentro de la caja (x,y,w,h)."""
        if not ent or not ent[0]:
            return None
        tex, iw, ih = ent
        if mode == "cover":
            f = max(float(w) / iw, float(h) / ih)
            # recortamos la fuente para que llene la caja sin deformar
            sw, sh = int(w / f), int(h / f)
            sx, sy = (iw - sw) // 2, (ih - sh) // 4 if ih > sh else 0
            sdl.SDL_SetTextureAlphaMod(tex, alpha)
            sdl.SDL_SetTextureColorMod(tex, 255, 255, 255)
            self._copy(tex, sdl.rect(sx, sy, sw, sh), sdl.rect(x, y, w, h))
            return (x, y, w, h)
        f = min(float(w) / iw, float(h) / ih)
        dw, dh = int(iw * f), int(ih * f)
        if align == "bottom":
            dx, dy = x + (w - dw) // 2, y + h - dh
        else:
            dx, dy = x + (w - dw) // 2, y + (h - dh) // 2
        sdl.SDL_SetTextureAlphaMod(tex, alpha)
        sdl.SDL_SetTextureColorMod(tex, 255, 255, 255)
        self._copy(tex, None, sdl.rect(dx, dy, dw, dh))
        return (dx, dy, dw, dh)

    def destroy(self):
        self.loader.stop()
        for ent in self.text_cache.values():
            if ent[0]:
                sdl.SDL_DestroyTexture(ent[0])
        for ent in self.images.values():
            if ent and ent[0]:
                sdl.SDL_DestroyTexture(ent[0])
        for tex in self.icons.values():
            sdl.SDL_DestroyTexture(tex)
        for ent in self.statics.values():
            if ent and ent[0]:
                sdl.SDL_DestroyTexture(ent[0])
        if self._grad:
            sdl.SDL_DestroyTexture(self._grad)
        for f in self.fonts.values():
            f.close()
