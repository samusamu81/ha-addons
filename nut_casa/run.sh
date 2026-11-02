#!/bin/sh
# NUT casa: avvio.
# - nut_casa.py: server NUT sulla porta 3493 (UPS finto "qnapups", risposta per IP
#   dai file /share/nut/<nome>.sol) e un interruttore MQTT per ogni NAS.
# - "ups-vero": l'UPS in USB, solo se real_ups e' attivo. upsd standard sulla
#   porta 3494, solo come sensore per HA: i NAS non lo vedono.
set -e

OPTS=/data/options.json
REAL_UPS=$(jq -r '.real_ups' "$OPTS")

if [ "$REAL_UPS" = "true" ]; then
  mkdir -p /var/run/nut /run/nut
  chmod 0770 /var/run/nut /run/nut
  echo "MODE=netserver" > /etc/nut/nut.conf
  cat > /etc/nut/ups.conf <<EOF
maxretry = 3

[ups-vero]
  driver = $(jq -r '.real_ups_driver' "$OPTS")
  port = $(jq -r '.real_ups_port' "$OPTS")
  desc = "UPS vero in USB"
EOF
  echo "LISTEN 0.0.0.0 3494" > /etc/nut/upsd.conf
  : > /etc/nut/upsd.users
  chmod 0640 /etc/nut/ups.conf /etc/nut/upsd.conf /etc/nut/upsd.users
  if upsdrvctl -u root start ups-vero; then
    upsd -u root
    echo "[nut_casa] UPS vero su porta 3494"
  else
    echo "[nut_casa] ATTENZIONE: UPS vero non avviato, controllare driver e cavo"
  fi
fi

exec python3 -u /nut_casa.py
