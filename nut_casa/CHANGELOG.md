# Changelog

## 2.4.2
- Anche per amd64 (PC Intel/AMD, macchine virtuali).
- Licenza MIT.

## 2.4.1
- Comandi MQTT memorizzati (retain) ignorati e cancellati.

## 2.4.0
- Orari dello storico nel fuso orario di Home Assistant.
- Accessi ai file ("conn log") solo nel file di storico, non in HA.

## 2.3.0
- Storico syslog nel Registro di HA e in `/share/nut/syslog/<nome>.log`.

## 2.2.0
- Syslog dei NAS (porta 1514, UDP e TCP): sensore "Ultimo evento" ed entità evento.

## 2.0.x – 2.1.x
- Un interruttore MQTT per ogni NAS dell'elenco, server NUT con risposta per IP.
- Blocco dei comandi dopo ON/OFF finché il ping non conferma.
