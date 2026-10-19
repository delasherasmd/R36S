#!/usr/bin/env python3
"""Crea dist/Vapor-R36S.zip: el paquete listo para copiar a la tarjeta.

Dentro del ZIP la carpeta 'ports' ya tiene la estructura final, asi que basta con
copiarla a la raiz de la particion de los juegos (al lado de gba, snes, psx...).
Uso: python3 tools/make_dist.py
"""
import os
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "dist", "Vapor-R36S.zip")
DATE = (2026, 1, 1, 0, 0, 0)  # fecha fija: el ZIP solo cambia si cambia el contenido

GAMELIST_ENTRY = """\t<game>
\t\t<path>./Vapor.sh</path>
\t\t<name>Vapor - Biblioteca estilo Steam</name>
\t\t<desc>Tus juegos como en Steam: caratulas, fichas, favoritos, tiempo de juego y listas ordenadas por prioridad.</desc>
\t\t<image>./vapor/assets/vapor-port.png</image>
\t\t<thumbnail>./vapor/assets/vapor-port.png</thumbnail>
\t</game>
"""

GAMELIST = '<?xml version="1.0"?>\n<gameList>\n' + GAMELIST_ENTRY + "</gameList>\n"

LEEME = """VAPOR - Biblioteca estilo Steam para ArkOS (R36S)
=================================================

INSTALACION
-----------
1. Saca la tarjeta micro SD donde estan tus JUEGOS y abrela en el PC.
   Es la particion que tiene las carpetas de los juegos: gba, snes, psx, nes...
   (suele llamarse EASYROMS).

   - Si la consola tiene DOS tarjetas: los juegos suelen estar en la segunda
     (ranura de la izquierda / TF2). Si no sabes cual usa, copia Vapor en las dos:
     no pasa nada.

2. Copia la carpeta "ports" de este ZIP en la RAIZ de esa particion, al lado de
   gba, snes, psx... Si Windows pregunta si quieres combinar la carpeta "ports"
   que ya existe, di que SI.

   Tiene que quedar exactamente asi:

       EASYROMS\\ports\\Vapor.sh
       EASYROMS\\ports\\vapor\\main.py

   OJO: no debe quedar dentro de otra carpeta (por ejemplo
   EASYROMS\\ports\\ports\\Vapor.sh o EASYROMS\\ports\\Vapor-R36S\\Vapor.sh).
   EmulationStation NO mira las subcarpetas de "ports".

3. Pon la tarjeta en la consola y enciendela. Si ya estaba encendida, reinicia
   EmulationStation: START > QUIT > RESTART EMULATIONSTATION.

4. Entra en el sistema PORTS y abre "Vapor".


SI NO APARECE
-------------
A) El sistema PORTS no sale en el menu principal:
   START > UI SETTINGS > VISIBLE SYSTEMS (sistemas visibles) > activa "Ports".
   Luego reinicia EmulationStation.

B) PORTS sale, pero Vapor no esta en la lista:
   tu EmulationStation solo lee los juegos que estan apuntados en gamelist.xml.
   Tienes dos opciones (con una basta):

   1. En la consola: START > ADVANCED SETTINGS > PARSE GAMESLISTS ONLY > OFF,
      y reinicia EmulationStation.

   2. En el PC, mira si existe el archivo  ports\\gamelist.xml
      - Si NO existe: copia "extra\\gamelist.xml" de este ZIP a la carpeta ports.
      - Si SI existe: abrelo con el Bloc de notas y pega el contenido de
        "extra\\entrada-gamelist.txt" justo ANTES de la ultima linea </gameList>.
        Guarda y reinicia EmulationStation.

C) Aparece pero se cierra enseguida:
   mira el archivo ports\\vapor\\data\\vapor.out (se abre con el Bloc de notas).


PERSONALIZAR (START > Personalizar...)
--------------------------------------
- Tema y color de acento, tamano de caratulas (con vista previa en vivo).
- Brillo: funciona aunque el brillo de EmulationStation no haga nada en tu consola.
- Musica de fondo: copia tus canciones (.mp3 .ogg .wav...) en ports\\vapor\\music
  y sonaran en orden aleatorio.
- Abrir Vapor al encender: activalo desde la consola. Para ir a EmulationStation:
  START > Salir a EmulationStation (o SELECT+START).
  Para desactivarlo desde el PC: borra el archivo ports\\vapor\\data\\autostart
  Si alguna vez Vapor no llegara a abrirse al arrancar, el siguiente encendido va
  directo a EmulationStation y la opcion se desactiva sola.


SILENCIO, VIDEOS Y ARRANQUE
---------------------------
- Silenciar toda la consola (tambien los juegos): START > Silenciar consola.
  Se quita igual, o subiendo el volumen con los botones.
- Si sale un video/imagen al abrir o cerrar juegos: en EmulationStation
  START > UI SETTINGS > GAME LOADING IMAGE MODE > NONE
  (o renombra la carpeta EASYROMS\\launchimages).
- Si Vapor no se abre al encender: abre Vapor una vez desde Ports (se actualiza
  solo) y APAGA LA CONSOLA DEL TODO (START > QUIT > SHUTDOWN SYSTEM). Pulsar el
  boton de encendido un momento solo la pone en reposo, eso no es un arranque.
  Si sigue sin abrirse, abre Vapor desde Ports y envia el archivo
  ports\\vapor\\data\\diagnostico.txt


USO RAPIDO
----------
L1/R1 pestanas - A ficha/JUGAR - B atras - X listas - Y favorito
L2/R2 cambiar prioridad (en listas y favoritos) - SELECT vista - START menu
SELECT+START salir

Tus listas se guardan en ports\\vapor\\data\\library.json (con copia .bak).
Para desinstalar: borra ports\\Vapor.sh y la carpeta ports\\vapor.
"""


def crlf(text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def add_file(z, src, arc):
    info = zipfile.ZipInfo(arc, DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if arc.endswith(".sh") or arc.endswith("main.py") else 0o644
    info.external_attr = (0o100000 | mode) << 16
    with open(src, "rb") as f:
        z.writestr(info, f.read())


def add_text(z, arc, text):
    info = zipfile.ZipInfo(arc, DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100644) << 16
    z.writestr(info, text.encode("utf-8"))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    files = [(os.path.join(ROOT, "ports", "Vapor.sh"), "ports/Vapor.sh")]
    app = os.path.join(ROOT, "ports", "vapor")
    for d, dirs, names in os.walk(app):
        dirs[:] = sorted(x for x in dirs if x not in ("data", "__pycache__"))
        for n in sorted(names):
            if n.endswith(".pyc"):
                continue
            full = os.path.join(d, n)
            files.append((full, "ports/vapor/" + os.path.relpath(full, app).replace(os.sep, "/")))
    with zipfile.ZipFile(OUT, "w") as z:
        add_text(z, "LEEME.txt", crlf(LEEME))
        for src, arc in files:
            add_file(z, src, arc)
        add_text(z, "extra/gamelist.xml", crlf(GAMELIST))
        add_text(z, "extra/entrada-gamelist.txt", crlf(GAMELIST_ENTRY))
    print("Creado", OUT, "(%d archivos)" % (len(files) + 3))


if __name__ == "__main__":
    main()
