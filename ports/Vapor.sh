#!/bin/bash
#
# Vapor - biblioteca de juegos estilo Steam para ArkOS (R36S y compatibles)
#
# Instalacion: copia este archivo (Vapor.sh) y la carpeta "vapor" dentro de
# la carpeta "ports" de la tarjeta (particion EASYROMS). Despues reinicia
# EmulationStation y abre Vapor desde el sistema "Ports".
#
# Como funciona: Vapor muestra la biblioteca; al elegir JUGAR escribe el
# comando del emulador (el mismo que usaria EmulationStation) y se cierra.
# Este script ejecuta el juego, apunta el tiempo jugado y vuelve a abrir Vapor.

SELF="$(readlink -f "$0")"
BASE="$(dirname "$SELF")"
APP="$BASE/vapor"
DATA="$APP/data"

if [ -d /dev/shm ] && [ -w /dev/shm ]; then
  LAUNCH="/dev/shm/vapor_launch.cmd"
else
  LAUNCH="$DATA/launch.cmd"
fi

mkdir -p "$DATA"

msg() {
  # Mensaje en pantalla (consola de ArkOS) y en el log
  printf "\033c%s\n" "$1" > /dev/tty1 2>/dev/null
  echo "$1" >> "$DATA/vapor.out"
}

if [ ! -f "$APP/main.py" ]; then
  msg "Vapor: no se encuentra $APP/main.py. Copia la carpeta 'vapor' junto a Vapor.sh."
  sleep 6
  exit 1
fi

PYTHON="$(command -v python3)"
if [ -z "$PYTHON" ]; then
  msg "Vapor: este sistema no tiene python3."
  sleep 6
  exit 1
fi

export VAPOR_SELF="$SELF"
export VAPOR_LAUNCH="$LAUNCH"
export HOME="${HOME:-/home/ark}"
[ -d "$HOME" ] || export HOME=/home/ark

printf "\033c" > /dev/tty1 2>/dev/null

while true; do
  rm -f "$LAUNCH" "$LAUNCH.rom"

  "$PYTHON" "$APP/main.py" > "$DATA/vapor.out" 2>&1
  RC=$?

  if [ ! -s "$LAUNCH" ]; then
    # 0 = salida normal, 3 = error ya mostrado por Vapor en pantalla
    if [ $RC -ne 0 ] && [ $RC -ne 3 ]; then
      msg "Vapor no pudo iniciarse (codigo $RC). Revisa $DATA/vapor.out"
      tail -n 8 "$DATA/vapor.out" > /dev/tty1 2>/dev/null
      sleep 8
    fi
    break
  fi

  ROM="$(head -n 1 "$LAUNCH.rom" 2>/dev/null)"
  START=$(date +%s)

  # Igual que EmulationStation: el comando se ejecuta con /bin/sh
  /bin/sh "$LAUNCH"

  END=$(date +%s)
  printf '%s\t%s\t%s\n' "$START" "$((END - START))" "$ROM" >> "$DATA/history.log"
  printf "\033c" > /dev/tty1 2>/dev/null
done

rm -f "$LAUNCH" "$LAUNCH.rom"
printf "\033c" > /dev/tty1 2>/dev/null
exit 0
