# -*- coding: utf-8 -*-
"""Colores y medidas (diseno base 640x480, se escala a otras pantallas)."""
import colorsys
import zlib

BG_TOP = (33, 47, 66, 255)
BG_BOTTOM = (12, 17, 23, 255)
BAR = (16, 21, 28, 255)
BAR_LINE = (255, 255, 255, 18)
PANEL = (30, 39, 51, 255)
PANEL_HI = (44, 56, 72, 255)
DIALOG = (27, 34, 44, 255)
DIM = (0, 0, 0, 150)

TEXT = (236, 240, 244, 255)
TEXT2 = (165, 177, 190, 255)
TEXT3 = (112, 125, 140, 255)
DARK_TEXT = (18, 22, 28, 255)

ACCENT = (26, 159, 255, 255)
ACCENT_SOFT = (102, 192, 244, 255)
SEL = (58, 76, 98, 255)
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


def system_color(name, light=0.30, sat=0.42):
    h = (zlib.crc32(name.encode("utf-8")) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(h, light, sat)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))
