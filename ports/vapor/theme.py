# -*- coding: utf-8 -*-
"""Colores y medidas (diseno base 640x480, se escala a otras pantallas).

Los colores son variables del modulo: apply() las cambia en caliente y toda la
interfaz las lee al dibujar, asi que un cambio de tema se ve al instante."""
import colorsys
import zlib

# Temas: fondo arriba, fondo abajo, barras y color de acento.
PRESETS = [
    ("steam", {"es": "Steam", "en": "Steam"},
     (33, 47, 66), (12, 17, 23), (16, 21, 28), (26, 159, 255)),
    ("midnight", {"es": "Medianoche", "en": "Midnight"},
     (30, 31, 36), (6, 6, 8), (13, 13, 16), (122, 162, 255)),
    ("purple", {"es": "Morado", "en": "Purple"},
     (50, 30, 76), (14, 8, 22), (22, 13, 33), (178, 102, 255)),
    ("ocean", {"es": "Océano", "en": "Ocean"},
     (14, 54, 68), (4, 16, 22), (8, 24, 31), (0, 200, 220)),
    ("emerald", {"es": "Esmeralda", "en": "Emerald"},
     (18, 60, 48), (5, 18, 14), (9, 26, 21), (46, 204, 113)),
    ("crimson", {"es": "Carmesí", "en": "Crimson"},
     (72, 22, 32), (20, 6, 9), (30, 10, 14), (255, 72, 92)),
    ("amber", {"es": "Ámbar", "en": "Amber"},
     (68, 42, 16), (20, 12, 5), (28, 17, 8), (255, 152, 0)),
    ("pink", {"es": "Rosa", "en": "Pink"},
     (74, 28, 60), (22, 8, 18), (32, 12, 26), (255, 105, 180)),
    ("gameboy", {"es": "Game Boy", "en": "Game Boy"},
     (48, 64, 24), (14, 20, 7), (22, 30, 11), (155, 188, 15)),
    ("graphite", {"es": "Grafito", "en": "Graphite"},
     (54, 56, 61), (17, 18, 20), (25, 26, 29), (190, 198, 208)),
]

ACCENTS = [
    ("auto", {"es": "Del tema", "en": "Theme"}, None),
    ("blue", {"es": "Azul", "en": "Blue"}, (26, 159, 255)),
    ("sky", {"es": "Celeste", "en": "Sky"}, (102, 192, 244)),
    ("cyan", {"es": "Turquesa", "en": "Cyan"}, (0, 200, 220)),
    ("green", {"es": "Verde", "en": "Green"}, (46, 204, 113)),
    ("lime", {"es": "Lima", "en": "Lime"}, (155, 200, 20)),
    ("yellow", {"es": "Amarillo", "en": "Yellow"}, (255, 200, 0)),
    ("orange", {"es": "Naranja", "en": "Orange"}, (255, 140, 0)),
    ("red", {"es": "Rojo", "en": "Red"}, (255, 72, 92)),
    ("pink", {"es": "Rosa", "en": "Pink"}, (255, 105, 180)),
    ("purple", {"es": "Violeta", "en": "Violet"}, (178, 102, 255)),
    ("white", {"es": "Blanco", "en": "White"}, (232, 236, 242)),
]

TILE_SIZES = [
    ("small", {"es": "Pequeñas", "en": "Small"}, 84),
    ("normal", {"es": "Normales", "en": "Normal"}, 108),
    ("large", {"es": "Grandes", "en": "Large"}, 140),
]

# Valores del tema activo (los rellena apply)
BG_TOP = BG_BOTTOM = BAR = PANEL = PANEL_HI = DIALOG = SEL = None
ACCENT = ACCENT_SOFT = None
TILE_MIN = 108

BAR_LINE = (255, 255, 255, 18)
DIM = (0, 0, 0, 150)

TEXT = (236, 240, 244, 255)
TEXT2 = (165, 177, 190, 255)
TEXT3 = (112, 125, 140, 255)
DARK_TEXT = (18, 22, 28, 255)

FOCUS = (255, 255, 255, 255)

GREEN_TOP = (112, 180, 30, 255)
GREEN_BOTTOM = (74, 128, 18, 255)
GOLD = (255, 196, 56, 255)
RED = (214, 72, 72, 255)

GLYPH_BG = (205, 211, 218, 255)

TOPBAR_H = 34
HEADER_H = 28
HINTBAR_H = 26
MARGIN = 16
GAP = 10
RADIUS = 5


def _rgba(c):
    return (int(c[0]), int(c[1]), int(c[2]), 255)


def mix(a, b, t):
    a = a if len(a) == 4 else tuple(a) + (255,)
    b = b if len(b) == 4 else tuple(b) + (255,)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _find(table, key):
    for row in table:
        if row[0] == key:
            return row
    return table[0]


def label(table, key, lang="es"):
    names = _find(table, key)[1]
    return names.get(lang, names["es"])


def cycle(table, key, d):
    keys = [row[0] for row in table]
    i = keys.index(key) if key in keys else 0
    return keys[(i + d) % len(keys)]


def apply(theme="steam", accent="auto", tile_size="normal"):
    """Activa un tema. Se puede llamar en cualquier momento."""
    global BG_TOP, BG_BOTTOM, BAR, PANEL, PANEL_HI, DIALOG, SEL, ACCENT, ACCENT_SOFT, TILE_MIN
    row = _find(PRESETS, theme)
    top, bottom, bar, acc = row[2], row[3], row[4], row[5]
    acc_row = _find(ACCENTS, accent)
    if acc_row[2] is not None:
        acc = acc_row[2]
    white = (255, 255, 255, 255)
    BG_TOP = _rgba(top)
    BG_BOTTOM = _rgba(bottom)
    BAR = _rgba(bar)
    DIALOG = mix(mix(_rgba(top), _rgba(bottom), 0.45), white, 0.02)
    PANEL = mix(_rgba(top), _rgba(bottom), 0.15)
    PANEL_HI = mix(_rgba(top), white, 0.10)
    SEL = mix(_rgba(top), white, 0.20)
    ACCENT = _rgba(acc)
    ACCENT_SOFT = mix(_rgba(acc), white, 0.35)
    TILE_MIN = _find(TILE_SIZES, tile_size)[2]


def system_color(name, light=0.30, sat=0.42):
    h = (zlib.crc32(name.encode("utf-8")) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, light, sat)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


apply()
