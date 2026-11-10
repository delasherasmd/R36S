#!/bin/bash
#
# Anular stick - deja la consola usable aunque un stick analogico este averiado
# (por ejemplo, trabado marcando "arriba"). Vale para TODA la consola:
# EmulationStation, Vapor, RetroArch y los demas emuladores.
#
# Uso: abrelo desde Ports.
#   - La primera vez lo ACTIVA: instala un servicio que arranca con la consola,
#     antes que EmulationStation, y anula el stick elegido.
#   - Si ya estaba activo, lo QUITA y todo vuelve a como estaba.
#
# Que stick se anula: archivo anularstick/stickfix.conf (desde el PC):
#   izquierdo, derecho o ambos.
# Si algo saliera mal: borra anularstick/stickfix.conf desde el PC y reinicia.

SELF="$(readlink -f "$0")"
BASE="$(dirname "$SELF")"
APP="$BASE/anularstick"
CONF="$APP/stickfix.conf"
UNIT_NAME="anular-stick.service"
UNIT="/etc/systemd/system/$UNIT_NAME"
# copia en el disco del sistema: al encender, EASYROMS se monta tarde
SYS_DIR="/opt/anular-stick"
UNIT_VERSION="# anular-stick v2"
PYTHON="$(command -v python3)"

say() {
  printf "\033c\n\n%b\n" "$1" | sudo tee /dev/tty1 > /dev/null 2>&1
  echo "$1" >> "$APP/stickfix.log"
}

restart_es() {
  # EmulationStation cree que el stick sigue pulsado: se reinicia para que lea
  # el mando de nuevo (esto cierra tambien este script)
  say "$1\n\nReiniciando EmulationStation..."
  sleep 3
  sudo systemctl --no-block restart emulationstation
  exit 0
}

if [ ! -f "$APP/stickfix.py" ] || [ -z "$PYTHON" ]; then
  say "Anular stick: falta $APP/stickfix.py o python3."
  sleep 6
  exit 1
fi

remove_all() {
  sudo systemctl disable --now "$UNIT_NAME" > /dev/null 2>&1
  sudo rm -f "$UNIT"
  sudo rm -rf "$SYS_DIR"
  sudo systemctl daemon-reload
}

# ---- ya activo (version actual): se quita
if [ -f "$UNIT" ] && grep -qF "$UNIT_VERSION" "$UNIT"; then
  remove_all
  sudo "$PYTHON" "$APP/stickfix.py" --restore
  restart_es "Anular stick: DESACTIVADO.\nLos sticks vuelven a funcionar como antes."
fi
# una version anterior (no sobrevivia al reinicio) se reinstala sin preguntar
UPGRADE=0
[ -f "$UNIT" ] && UPGRADE=1

# ---- activar
[ -f "$CONF" ] || printf 'izquierdo\n' > "$CONF"
STICK="$(grep -v '^ *#' "$CONF" | grep -m1 -o '[[:alpha:] ]*[[:alpha:]]')"

sudo mkdir -p "$SYS_DIR"
sudo install -m 644 "$APP/stickfix.py" "$SYS_DIR/stickfix.py"
sudo install -m 644 "$CONF" "$SYS_DIR/stickfix.conf"

cat > /dev/shm/anular-stick.service <<EOF
$UNIT_VERSION
[Unit]
Description=Anular stick analogico averiado
After=systemd-udevd.service systemd-modules-load.service
Before=emulationstation.service
StartLimitIntervalSec=0

[Service]
Type=notify
ExecStartPre=-/sbin/modprobe uinput
ExecStart=$PYTHON $SYS_DIR/stickfix.py --config $SYS_DIR/stickfix.conf --user-config "$CONF" --wait 20
ExecStopPost=$PYTHON $SYS_DIR/stickfix.py --restore
Restart=on-failure
RestartSec=5
TimeoutStartSec=60

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 /dev/shm/anular-stick.service "$UNIT"
rm -f /dev/shm/anular-stick.service
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT_NAME" > /dev/null 2>&1

if ! sudo systemctl restart "$UNIT_NAME"; then
  remove_all
  say "Anular stick: NO se pudo activar.\n\n$(tail -n 4 "$APP/stickfix.log")"
  sleep 10
  exit 1
fi

if [ "$UPGRADE" = 1 ]; then
  restart_es "Anular stick ACTUALIZADO: stick $STICK anulado.\nAhora se mantiene al reiniciar la consola."
fi

# Seguridad: si los botones no responden, se deshace solo
say "Stick $STICK ANULADO en toda la consola.\n\nPulsa cualquier boton en 20 segundos\npara confirmar que el mando funciona.\n\n(Si no pulsas nada, se deshace solo.)"
if sudo "$PYTHON" "$APP/stickfix.py" --confirm 20; then
  restart_es "Listo: stick $STICK anulado.\nSeguira anulado cada vez que enciendas la consola.\n\nPara quitarlo, vuelve a abrir 'Anular stick' desde Ports."
fi

remove_all
restart_es "No se pulso ningun boton: se deshizo.\nLa consola queda como estaba."
