# -*- coding: utf-8 -*-
"""Colores y medidas (diseno base 640x480, se escala a otras pantallas).

Los colores son variables del modulo: apply() las cambia en caliente y toda la
interfaz las lee al dibujar, asi que un cambio de tema se ve al instante."""
import colorsys
import zlib

# Temas. Cada uno: fondo arriba/abajo, barras, acento y, opcionalmente, acento
# secundario, color del foco, colores del boton JUGAR e imagen de fondo.
# "vapor" es el tema principal (colores del logo: morado, rosa neon, cian y el sol).
PRESETS = [
    ("vapor", {"es": "Vapor", "en": "Vapor"},
     dict(top=(40, 10, 66), bottom=(14, 3, 32), bar=(20, 4, 44), accent=(236, 72, 168),
          soft=(0, 214, 232), focus=(120, 236, 255),
          play=((250, 190, 70), (236, 78, 128)), bg="bg_vapor.jpg")),
    ("steam", {"es": "Steam", "en": "Steam"},
     dict(top=(33, 47, 66), bottom=(12, 17, 23), bar=(16, 21, 28), accent=(26, 159, 255))),
    ("midnight", {"es": "Medianoche", "en": "Midnight"},
     dict(top=(30, 31, 36), bottom=(6, 6, 8), bar=(13, 13, 16), accent=(122, 162, 255))),
    ("purple", {"es": "Morado", "en": "Purple"},
     dict(top=(50, 30, 76), bottom=(14, 8, 22), bar=(22, 13, 33), accent=(178, 102, 255))),
    ("ocean", {"es": "Océano", "en": "Ocean"},
     dict(top=(14, 54, 68), bottom=(4, 16, 22), bar=(8, 24, 31), accent=(0, 200, 220))),
    ("emerald", {"es": "Esmeralda", "en": "Emerald"},
     dict(top=(18, 60, 48), bottom=(5, 18, 14), bar=(9, 26, 21), accent=(46, 204, 113))),
    ("crimson", {"es": "Carmesí", "en": "Crimson"},
     dict(top=(72, 22, 32), bottom=(20, 6, 9), bar=(30, 10, 14), accent=(255, 72, 92))),
    ("amber", {"es": "Ámbar", "en": "Amber"},
     dict(top=(68, 42, 16), bottom=(20, 12, 5), bar=(28, 17, 8), accent=(255, 152, 0))),
    ("pink", {"es": "Rosa", "en": "Pink"},
     dict(top=(74, 28, 60), bottom=(22, 8, 18), bar=(32, 12, 26), accent=(255, 105, 180))),
    ("gameboy", {"es": "Game Boy", "en": "Game Boy"},
     dict(top=(48, 64, 24), bottom=(14, 20, 7), bar=(22, 30, 11), accent=(155, 188, 15))),
    ("graphite", {"es": "Grafito", "en": "Graphite"},
     dict(top=(54, 56, 61), bottom=(17, 18, 20), bar=(25, 26, 29), accent=(190, 198, 208))),
]
DEFAULT_THEME = "vapor"

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
ACCENT = ACCENT_SOFT = FOCUS = PLAY_TOP = PLAY_BOTTOM = None
BG_IMAGE = None
TILE_MIN = 108

BAR_LINE = (255, 255, 255, 18)
DIM = (0, 0, 0, 150)

TEXT = (236, 240, 244, 255)
TEXT2 = (165, 177, 190, 255)
TEXT3 = (112, 125, 140, 255)
DARK_TEXT = (18, 22, 28, 255)

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


def preset(key):
    return _find(PRESETS, key)[2]


def apply(theme=DEFAULT_THEME, accent="auto", tile_size="normal"):
    """Activa un tema. Se puede llamar en cualquier momento."""
    global BG_TOP, BG_BOTTOM, BAR, PANEL, PANEL_HI, DIALOG, SEL, ACCENT, ACCENT_SOFT, TILE_MIN
    global FOCUS, PLAY_TOP, PLAY_BOTTOM, BG_IMAGE
    p = preset(theme)
    top, bottom, bar, acc = p["top"], p["bottom"], p["bar"], p["accent"]
    soft = p.get("soft")
    acc_row = _find(ACCENTS, accent)
    if acc_row[2] is not None:
        acc = acc_row[2]
        soft = None  # con un acento propio, el secundario sale de el
    white = (255, 255, 255, 255)
    BG_TOP = _rgba(top)
    BG_BOTTOM = _rgba(bottom)
    BAR = _rgba(bar)
    DIALOG = mix(mix(_rgba(top), _rgba(bottom), 0.45), white, 0.02)
    PANEL = mix(_rgba(top), _rgba(bottom), 0.15)
    PANEL_HI = mix(_rgba(top), white, 0.10)
    SEL = mix(_rgba(top), white, 0.20)
    ACCENT = _rgba(acc)
    ACCENT_SOFT = _rgba(soft) if soft else mix(_rgba(acc), white, 0.35)
    FOCUS = _rgba(p.get("focus", (255, 255, 255)))
    play = p.get("play", ((112, 180, 30), (74, 128, 18)))
    PLAY_TOP, PLAY_BOTTOM = _rgba(play[0]), _rgba(play[1])
    BG_IMAGE = p.get("bg")
    TILE_MIN = _find(TILE_SIZES, tile_size)[2]


def system_color(name, light=0.30, sat=0.42):
    h = (zlib.crc32(name.encode("utf-8")) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, light, sat)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


apply()
