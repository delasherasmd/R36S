#!/usr/bin/env python3
"""Genera los iconos PNG (blancos sobre transparente) de ports/vapor/assets/icons.

Solo hace falta para desarrollo (requiere Pillow). Los PNG ya van incluidos.
Uso: python3 tools/make_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "ports", "vapor", "assets", "icons")
SIZE = 64
SS = 4  # supersampling
S = SIZE * SS
WHITE = (255, 255, 255, 255)


def canvas():
    img = Image.new("RGBA", (S, S), (255, 255, 255, 0))
    return img, ImageDraw.Draw(img)


def save(img, name):
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    img.save(os.path.join(OUT, name + ".png"), optimize=True)


def p(x, y):
    return (x * S, y * S)


def star(filled=True):
    img, d = canvas()
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = 0.47 if i % 2 == 0 else 0.19
        pts.append(p(0.5 + r * math.cos(ang), 0.53 + r * math.sin(ang)))
    if filled:
        d.polygon(pts, fill=WHITE)
    else:
        d.line(pts + [pts[0]], fill=WHITE, width=int(0.07 * S), joint="curve")
    return img


def play():
    img, d = canvas()
    d.polygon([p(0.22, 0.12), p(0.86, 0.5), p(0.22, 0.88)], fill=WHITE)
    return img


def check():
    img, d = canvas()
    d.line([p(0.14, 0.52), p(0.4, 0.78), p(0.88, 0.24)], fill=WHITE, width=int(0.14 * S),
           joint="curve")
    return img


def circle():
    img, d = canvas()
    d.ellipse([0, 0, S - 1, S - 1], fill=WHITE)
    return img


def plus():
    img, d = canvas()
    w = 0.12
    d.rectangle([p(0.5 - w / 2, 0.12), p(0.5 + w / 2, 0.88)], fill=WHITE)
    d.rectangle([p(0.12, 0.5 - w / 2), p(0.88, 0.5 + w / 2)], fill=WHITE)
    return img


def search():
    img, d = canvas()
    w = int(0.1 * S)
    d.ellipse([p(0.1, 0.1), p(0.66, 0.66)], outline=WHITE, width=w)
    d.line([p(0.6, 0.6), p(0.9, 0.9)], fill=WHITE, width=int(0.14 * S))
    return img


def tag():
    img, d = canvas()
    d.polygon([p(0.08, 0.12), p(0.5, 0.12), p(0.92, 0.54), p(0.54, 0.92), p(0.08, 0.46)],
              fill=WHITE)
    d.ellipse([p(0.2, 0.24), p(0.34, 0.38)], fill=(0, 0, 0, 0))
    return img


def grid():
    img, d = canvas()
    for gx in (0.1, 0.56):
        for gy in (0.1, 0.56):
            d.rounded_rectangle([p(gx, gy), p(gx + 0.34, gy + 0.34)], radius=int(0.06 * S),
                                fill=WHITE)
    return img


def listicon():
    img, d = canvas()
    for gy in (0.14, 0.44, 0.74):
        d.rounded_rectangle([p(0.08, gy), p(0.24, gy + 0.14)], radius=int(0.03 * S), fill=WHITE)
        d.rounded_rectangle([p(0.32, gy), p(0.92, gy + 0.14)], radius=int(0.03 * S), fill=WHITE)
    return img


def clock():
    img, d = canvas()
    w = int(0.09 * S)
    d.ellipse([p(0.08, 0.08), p(0.92, 0.92)], outline=WHITE, width=w)
    d.line([p(0.5, 0.5), p(0.5, 0.24)], fill=WHITE, width=w)
    d.line([p(0.5, 0.5), p(0.7, 0.6)], fill=WHITE, width=w)
    return img


def gamepad():
    img, d = canvas()
    d.rounded_rectangle([p(0.04, 0.26), p(0.96, 0.78)], radius=int(0.2 * S), fill=WHITE)
    hole = (0, 0, 0, 0)
    d.rectangle([p(0.2, 0.47), p(0.38, 0.55)], fill=hole)
    d.rectangle([p(0.25, 0.42), p(0.33, 0.6)], fill=hole)
    d.ellipse([p(0.62, 0.4), p(0.71, 0.49)], fill=hole)
    d.ellipse([p(0.72, 0.5), p(0.81, 0.59)], fill=hole)
    return img


def home():
    img, d = canvas()
    d.polygon([p(0.5, 0.1), p(0.92, 0.48), p(0.08, 0.48)], fill=WHITE)
    d.rectangle([p(0.2, 0.46), p(0.8, 0.9)], fill=WHITE)
    d.rectangle([p(0.42, 0.62), p(0.58, 0.9)], fill=(0, 0, 0, 0))
    return img


def chip():
    """Icono de 'sistema' (consola)."""
    img, d = canvas()
    d.rounded_rectangle([p(0.08, 0.2), p(0.92, 0.8)], radius=int(0.08 * S), fill=WHITE)
    d.rounded_rectangle([p(0.18, 0.3), p(0.6, 0.7)], radius=int(0.04 * S), fill=(0, 0, 0, 0))
    d.ellipse([p(0.68, 0.32), p(0.82, 0.46)], fill=(0, 0, 0, 0))
    d.ellipse([p(0.68, 0.54), p(0.82, 0.68)], fill=(0, 0, 0, 0))
    return img


def gear():
    img, d = canvas()
    cx = cy = 0.5
    pts = []
    teeth = 8
    for i in range(teeth * 4):
        ang = i * 2 * math.pi / (teeth * 4)
        r = 0.46 if (i % 4) in (0, 1) else 0.34
        pts.append(p(cx + r * math.cos(ang), cy + r * math.sin(ang)))
    d.polygon(pts, fill=WHITE)
    d.ellipse([p(0.36, 0.36), p(0.64, 0.64)], fill=(0, 0, 0, 0))
    return img


def back():
    img, d = canvas()
    d.line([p(0.62, 0.15), p(0.28, 0.5), p(0.62, 0.85)], fill=WHITE, width=int(0.13 * S),
           joint="curve")
    return img


def shadow():
    """Sombra suave circular (se usa como 9-slice para sombras de tarjetas)."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    px = img.load()
    for y in range(S):
        for x in range(S):
            dx = (x + 0.5) / S - 0.5
            dy = (y + 0.5) / S - 0.5
            dist = math.sqrt(dx * dx + dy * dy) * 2  # 0 centro, 1 borde
            a = max(0.0, 1.0 - dist)
            a = a * a * (3 - 2 * a)  # smoothstep
            px[x, y] = (255, 255, 255, int(255 * a))
    return img


def pin():
    """Chincheta: la lista se muestra como pestana."""
    img, d = canvas()
    d.polygon([p(0.3, 0.08), p(0.7, 0.08), p(0.64, 0.18), p(0.64, 0.46), p(0.82, 0.62),
               p(0.18, 0.62), p(0.36, 0.46), p(0.36, 0.18)], fill=WHITE)
    d.polygon([p(0.46, 0.62), p(0.54, 0.62), p(0.5, 0.94)], fill=WHITE)
    return img


def arrow(up=True):
    img, d = canvas()
    w = int(0.13 * S)
    if up:
        d.line([p(0.5, 0.88), p(0.5, 0.18)], fill=WHITE, width=w)
        d.line([p(0.2, 0.46), p(0.5, 0.16), p(0.8, 0.46)], fill=WHITE, width=w, joint="curve")
    else:
        d.line([p(0.5, 0.12), p(0.5, 0.82)], fill=WHITE, width=w)
        d.line([p(0.2, 0.54), p(0.5, 0.84), p(0.8, 0.54)], fill=WHITE, width=w, joint="curve")
    return img


def trash():
    img, d = canvas()
    d.rectangle([p(0.16, 0.18), p(0.84, 0.28)], fill=WHITE)
    d.rectangle([p(0.38, 0.08), p(0.62, 0.2)], fill=WHITE)
    d.polygon([p(0.22, 0.32), p(0.78, 0.32), p(0.72, 0.92), p(0.28, 0.92)], fill=WHITE)
    hole = (0, 0, 0, 0)
    for x in (0.38, 0.5, 0.62):
        d.rectangle([p(x - 0.03, 0.42), p(x + 0.03, 0.82)], fill=hole)
    return img


def tray(out=True):
    img, d = canvas()
    w = int(0.11 * S)
    d.line([p(0.12, 0.6), p(0.12, 0.88), p(0.88, 0.88), p(0.88, 0.6)], fill=WHITE, width=w,
           joint="curve")
    if out:
        d.line([p(0.5, 0.7), p(0.5, 0.1)], fill=WHITE, width=w)
        d.line([p(0.26, 0.34), p(0.5, 0.1), p(0.74, 0.34)], fill=WHITE, width=w, joint="curve")
    else:
        d.line([p(0.5, 0.08), p(0.5, 0.66)], fill=WHITE, width=w)
        d.line([p(0.26, 0.42), p(0.5, 0.66), p(0.74, 0.42)], fill=WHITE, width=w, joint="curve")
    return img


def refresh():
    img, d = canvas()
    w = int(0.11 * S)
    d.arc([p(0.14, 0.14), p(0.86, 0.86)], start=-60, end=230, fill=WHITE, width=w)
    d.polygon([p(0.62, 0.02), p(0.92, 0.2), p(0.6, 0.34)], fill=WHITE)
    return img


def info():
    img, d = canvas()
    d.ellipse([p(0.06, 0.06), p(0.94, 0.94)], fill=WHITE)
    hole = (0, 0, 0, 0)
    d.ellipse([p(0.43, 0.2), p(0.57, 0.34)], fill=hole)
    d.rectangle([p(0.43, 0.42), p(0.57, 0.8)], fill=hole)
    return img


def globe():
    img, d = canvas()
    w = int(0.08 * S)
    d.ellipse([p(0.08, 0.08), p(0.92, 0.92)], outline=WHITE, width=w)
    d.ellipse([p(0.32, 0.08), p(0.68, 0.92)], outline=WHITE, width=w)
    d.line([p(0.1, 0.5), p(0.9, 0.5)], fill=WHITE, width=w)
    d.line([p(0.18, 0.3), p(0.82, 0.3)], fill=WHITE, width=w)
    d.line([p(0.18, 0.7), p(0.82, 0.7)], fill=WHITE, width=w)
    return img


def exit_icon():
    img, d = canvas()
    w = int(0.11 * S)
    d.line([p(0.5, 0.12), p(0.14, 0.12), p(0.14, 0.88), p(0.5, 0.88)], fill=WHITE, width=w,
           joint="curve")
    d.line([p(0.36, 0.5), p(0.9, 0.5)], fill=WHITE, width=w)
    d.line([p(0.68, 0.28), p(0.9, 0.5), p(0.68, 0.72)], fill=WHITE, width=w, joint="curve")
    return img


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    icons = {
        "star": star(True),
        "star_outline": star(False),
        "play": play(),
        "check": check(),
        "circle": circle(),
        "plus": plus(),
        "search": search(),
        "tag": tag(),
        "grid": grid(),
        "list": listicon(),
        "clock": clock(),
        "gamepad": gamepad(),
        "home": home(),
        "system": chip(),
        "gear": gear(),
        "back": back(),
        "shadow": shadow(),
        "pin": pin(),
        "up": arrow(True),
        "down": arrow(False),
        "trash": trash(),
        "export": tray(True),
        "import": tray(False),
        "refresh": refresh(),
        "info": info(),
        "globe": globe(),
        "exit": exit_icon(),
    }
    for name, img in icons.items():
        save(img, name)
    port_image()
    print("Iconos generados en", os.path.abspath(OUT))


def port_image():
    """Imagen de Vapor para la lista de Ports de EmulationStation (gamelist.xml)."""
    from PIL import ImageFont
    fonts = os.path.join(OUT, "..", "fonts")
    w, h = 480, 360
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    top, bottom = (33, 47, 66), (12, 17, 23)
    for y in range(h):
        t = y / float(h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t)
                                            for i in range(3)) + (255,))
    # tarjetas de fondo, como una biblioteca
    for i, x in enumerate(range(-30, w, 92)):
        col = [(58, 76, 98), (44, 56, 72), (70, 92, 120)][i % 3]
        d.rounded_rectangle([x, 244, x + 80, 352], radius=8, fill=col + (255,))
    cx, cy, r = w // 2, 96, 50
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(26, 159, 255, 255))
    d.polygon([(cx - 16, cy - 26), (cx + 28, cy), (cx - 16, cy + 26)], fill=(255, 255, 255, 255))
    fb = ImageFont.truetype(os.path.join(fonts, "Inter-Bold.otf"), 54)
    fr = ImageFont.truetype(os.path.join(fonts, "Inter-Regular.otf"), 20)
    d.text((cx, 190), "VAPOR", font=fb, fill=(255, 255, 255, 255), anchor="ms")
    d.text((cx, 220), "Biblioteca estilo Steam", font=fr, fill=(165, 177, 190, 255),
           anchor="ms")
    img.save(os.path.join(OUT, "..", "vapor-port.png"), optimize=True)


if __name__ == "__main__":
    main()
