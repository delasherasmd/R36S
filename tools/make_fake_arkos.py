#!/usr/bin/env python3
"""Crea un ArkOS 'falso' (es_systems.cfg, ROMs vacias, gamelists y caratulas)
para probar Vapor en un PC. Requiere Pillow.

Uso: python3 tools/make_fake_arkos.py /tmp/fakeark
Luego: python3 ports/vapor/main.py --window 640x480 --home /tmp/fakeark/home \
         --es-dir /tmp/fakeark/etc --data /tmp/fakeark/data
"""
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

SYSTEMS = [
    # name, fullname, exts, cover aspect (w/h)
    ("gba", "Nintendo Game Boy Advance", ".gba .zip", 1.0),
    ("snes", "Super Nintendo", ".sfc .smc .zip", 1.38),
    ("megadrive", "Sega Mega Drive", ".md .bin .zip", 0.72),
    ("psx", "Sony PlayStation", ".cue .chd .pbp .m3u", 1.0),
    ("nes", "Nintendo NES", ".nes .zip", 0.72),
    ("gb", "Nintendo Game Boy", ".gb .zip", 1.0),
]

GAMES = {
    "gba": [("Golden Sun", "RPG"), ("Advance Wars", "Strategy"), ("Metroid Fusion", "Action"),
            ("Mario Kart Super Circuit", "Racing"), ("Castlevania Aria of Sorrow", "Action"),
            ("Fire Emblem", "Strategy"), ("Pokemon Edicion Esmeralda", "RPG"),
            ("Kirby Nightmare in Dream Land", "Platform"), ("Minish Cap", "Adventure")],
    "snes": [("Chrono Trigger", "RPG"), ("Super Metroid", "Action"),
             ("Donkey Kong Country", "Platform"), ("Super Mario World", "Platform"),
             ("Final Fantasy VI", "RPG"), ("F-Zero", "Racing"), ("EarthBound", "RPG"),
             ("Street Fighter II Turbo", "Fighting"), ("Secret of Mana", "RPG")],
    "megadrive": [("Sonic the Hedgehog 2", "Platform"), ("Streets of Rage 2", "Beat'em up"),
                  ("Gunstar Heroes", "Action"), ("Phantasy Star IV", "RPG"),
                  ("Shinobi III", "Action")],
    "psx": [("Castlevania Symphony of the Night", "Action"), ("Crash Bandicoot", "Platform"),
            ("Final Fantasy VII", "RPG"), ("Gran Turismo 2", "Racing"), ("Tekken 3", "Fighting"),
            ("Spyro the Dragon", "Platform")],
    "nes": [("Super Mario Bros. 3", "Platform"), ("The Legend of Zelda", "Adventure"),
            ("Mega Man 2", "Action"), ("Contra", "Action"), ("Kirby's Adventure", "Platform")],
    "gb": [("Tetris", "Puzzle"), ("Link's Awakening", "Adventure"), ("Pokemon Red", "RPG"),
           ("Wario Land", "Platform")],
}

DESC = ("Una aventura clasica que marco a toda una generacion de jugadores. Explora un mundo "
        "enorme, descubre secretos y enfrentate a enemigos legendarios en uno de los mejores "
        "juegos de su consola. Incluye multiples finales y una banda sonora inolvidable.")


def cover(path, title, system, aspect, seed):
    rnd = random.Random(seed)
    h = 360
    w = int(h * aspect)
    hue = rnd.random()
    import colorsys
    c1 = tuple(int(v * 255) for v in colorsys.hls_to_rgb(hue, 0.45, 0.7))
    c2 = tuple(int(v * 255) for v in colorsys.hls_to_rgb((hue + 0.15) % 1, 0.18, 0.6))
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / float(h)
        d.line([(0, y), (w, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    for _ in range(6):
        r = rnd.randint(20, 90)
        x0, y0 = rnd.randint(-20, w), rnd.randint(-20, h)
        d.ellipse([x0, y0, x0 + r, y0 + r], outline=(255, 255, 255), width=3)
    d.rectangle([0, 0, w, 34], fill=(20, 20, 20))
    f = ImageFont.truetype(FONT, 18)
    d.text((10, 7), system.upper(), font=f, fill=(255, 255, 255))
    f2 = ImageFont.truetype(FONT, 30)
    words = title.split()
    lines, cur = [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if d.textlength(cand, font=f2) > w - 30 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    lines.append(cur)
    y = h - 30 - 36 * len(lines)
    for l in lines:
        d.text((16, y), l, font=f2, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        y += 36
    img.save(path)


def screenshot(path, title, seed):
    rnd = random.Random(seed + 99)
    w, h = 320, 240
    img = Image.new("RGB", (w, h), (rnd.randint(0, 80), rnd.randint(40, 120), rnd.randint(80, 160)))
    d = ImageDraw.Draw(img)
    for _ in range(25):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        s = rnd.randint(8, 40)
        d.rectangle([x, y, x + s, y + s], fill=(rnd.randint(0, 255), rnd.randint(0, 255),
                                               rnd.randint(0, 255)))
    d.rectangle([0, h - 40, w, h], fill=(30, 90, 30))
    img.save(path)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(root):
    etc = os.path.join(root, "etc")
    home = os.path.join(root, "home")
    roms = os.path.join(root, "roms")
    for d in (etc, os.path.join(home, ".emulationstation", "collections"), roms):
        os.makedirs(d, exist_ok=True)
    sysxml = ['<?xml version="1.0"?>', "<systemList>"]
    for i, (name, full, exts, aspect) in enumerate(SYSTEMS):
        sp = os.path.join(roms, name)
        os.makedirs(os.path.join(sp, "images"), exist_ok=True)
        sysxml.append("""  <system>
    <name>%s</name>
    <fullname>%s</fullname>
    <path>%s/</path>
    <extension>%s %s</extension>
    <command>sudo perfmax %%GOVERNOR%% %%ROM%%; nice -n -19 /usr/local/bin/%%EMULATOR%% -L /home/ark/.config/%%EMULATOR%%/cores/%%CORE%%_libretro.so %%ROM%%; sudo perfnorm</command>
    <emulators>
      <emulator name="retroarch">
        <cores><core>%s_core</core><core>alt_core</core></cores>
      </emulator>
    </emulators>
    <platform>%s</platform>
    <theme>%s</theme>
  </system>""" % (name, full, sp, exts, exts.upper(), name, name, name))
        gl = ['<?xml version="1.0"?>', "<gameList>"]
        ext = exts.split()[0]
        for j, (title, genre) in enumerate(GAMES[name]):
            fn = title + " (USA)" + ext
            open(os.path.join(sp, fn), "w").close()
            seed = i * 100 + j
            has_art = (i + j) % 5 != 4  # algunos sin caratula
            entry = ["  <game>", "    <path>./%s</path>" % esc(fn),
                     "    <name>%s</name>" % esc(title)]
            if has_art:
                cover(os.path.join(sp, "images", title + "-thumb.png"), title, name, aspect, seed)
                screenshot(os.path.join(sp, "images", title + "-image.png"), title, seed)
                entry.append("    <thumbnail>./images/%s-thumb.png</thumbnail>" % esc(title))
                entry.append("    <image>./images/%s-image.png</image>" % esc(title))
            entry.append("    <desc>%s</desc>" % esc(DESC))
            entry.append("    <genre>%s</genre>" % esc(genre))
            entry.append("    <releasedate>19%02d0101T000000</releasedate>" % (88 + j % 10))
            entry.append("    <developer>Estudio %d</developer>" % (j + 1))
            entry.append("    <rating>0.%d</rating>" % (5 + j % 5))
            if j == 0:
                entry.append("    <favorite>true</favorite>")
            if j == 1:
                entry.append("    <lastplayed>20240310T201500</lastplayed>")
                entry.append("    <playcount>3</playcount>")
            entry.append("  </game>")
            gl.extend(entry)
        gl.append("</gameList>")
        with open(os.path.join(sp, "gamelist.xml"), "w") as f:
            f.write("\n".join(gl))
    # un sistema sin gamelist (solo ficheros) y el menu de opciones de ArkOS
    sp = os.path.join(roms, "ports")
    os.makedirs(sp, exist_ok=True)
    for n in ("Cave Story.sh", "Doom.sh", "Vapor.sh"):
        open(os.path.join(sp, n), "w").close()
    sysxml.append("""  <system>
    <name>ports</name><fullname>Ports</fullname><path>%s/</path>
    <extension>.sh .SH</extension><command>sudo perfmax %%GOVERNOR%% %%ROM%%; %%ROM%%; sudo perfnorm</command>
    <platform>pc</platform><theme>ports</theme>
  </system>
  <system>
    <name>retropie</name><fullname>Options</fullname><path>/opt/system/</path>
    <extension>.sh</extension>
    <command>sudo chmod 666 /dev/tty1; %%ROM%% 2>&1 > /dev/tty1; printf "\\033c" >> /dev/tty1</command>
    <platform>cmds</platform>
  </system>""" % sp)
    sysxml.append("</systemList>")
    with open(os.path.join(etc, "es_systems.cfg"), "w") as f:
        f.write("\n".join(sysxml))
    with open(os.path.join(etc, "es_input.cfg"), "w") as f:
        f.write("""<?xml version="1.0"?>
<inputList>
  <inputConfig type="keyboard" deviceName="Keyboard" deviceGUID="-1">
    <input name="a" type="key" id="13" value="1"/>
  </inputConfig>
  <inputConfig type="joystick" deviceName="GO-Super Gamepad" deviceGUID="190000004b4800000011000000010000">
    <input name="a" type="button" id="1" value="1"/>
    <input name="b" type="button" id="0" value="1"/>
    <input name="x" type="button" id="2" value="1"/>
    <input name="y" type="button" id="3" value="1"/>
    <input name="hotkeyenable" type="button" id="12" value="1"/>
    <input name="select" type="button" id="12" value="1"/>
    <input name="start" type="button" id="13" value="1"/>
    <input name="up" type="button" id="8" value="1"/>
    <input name="down" type="button" id="9" value="1"/>
    <input name="left" type="button" id="10" value="1"/>
    <input name="right" type="button" id="11" value="1"/>
    <input name="leftshoulder" type="button" id="4" value="1"/>
    <input name="rightshoulder" type="button" id="5" value="1"/>
    <input name="lefttrigger" type="button" id="6" value="1"/>
    <input name="righttrigger" type="button" id="7" value="1"/>
  </inputConfig>
</inputList>
""")
    with open(os.path.join(home, ".emulationstation", "es_settings.cfg"), "w") as f:
        f.write('<?xml version="1.0"?>\n<config>\n<string name="snes.core" value="alt_core" />\n'
                '<string name="GlobalPerformanceGovernor" value="performance" />\n</config>\n')
    with open(os.path.join(home, ".emulationstation", "collections", "custom-RPG favoritos.cfg"),
              "w") as f:
        f.write(os.path.join(roms, "snes", "Chrono Trigger (USA).sfc") + "\n")
        f.write(os.path.join(roms, "psx", "Final Fantasy VII (USA).cue") + "\n")
        f.write(os.path.join(roms, "gba", "Golden Sun (USA).gba") + "\n")
        f.write(os.path.join(roms, "gba", "Pokemon Edicion Esmeralda (USA).gba") + "\n")
    print("ArkOS falso creado en", root)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fakeark")
