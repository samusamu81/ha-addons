# Changelog

## 3.0.0
- Nuovo nome: **FakeNUT** (prima "NUT casa"). Il syslog è diventato un add-on a parte, **QLog2HA**.
- Tipo di client per ogni dispositivo: `qnap`, `synology`, `custom`.
- Risposta in base all'IP per **qualsiasi nome di UPS**, non solo `qnapups`.
- Client `custom`: utente e password controllati al login.
- File `.sol` in `/share/fakenut/`; entità con identificativi nuovi (`fakenut_…`), stesso nome in HA.

## 2.4.2
- Anche per amd64. Licenza MIT.

## 2.4.1
- Comandi MQTT memorizzati (retain) ignorati e cancellati.

## 2.4.0
- Orari nel fuso orario di Home Assistant.

## 2.0 – 2.3
- Un interruttore MQTT per dispositivo, server NUT con risposta per IP, blocco dei comandi, syslog.
