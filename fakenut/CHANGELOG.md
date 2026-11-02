# Changelog

## 3.1.0
- 🇮🇹 Nuova opzione `force_shutdown` (predefinita `false`): il file `.sol` si cancella appena il dispositivo risulta spento, così riaccenderlo a mano non lo fa rispegnere. Con l'UPS vero il file resta finché l'UPS è a batteria. Con `true`, comportamento di prima: il file resta fino all'ON.
- 🇬🇧 New option `force_shutdown` (default `false`): the `.sol` file is deleted as soon as the device is off, so powering it on by hand does not shut it down again. With the real UPS the file stays while the UPS is on battery. With `true`, previous behavior: the file stays until ON.

## 3.0.1
- 🇮🇹 Nuovo logo. Documentazione e opzioni anche in inglese.
- 🇬🇧 New logo. Documentation and options also in English.

## 3.0.0
- 🇮🇹 Nuovo nome: **FakeNUT** (prima "NUT casa"); il syslog è diventato un add-on a parte, **QLog2HA**. Tipo di client per ogni dispositivo (`qnap`, `synology`, `custom`). Risposta per IP a **qualsiasi nome di UPS**. Login controllato per i `custom`. Limiti alle connessioni. File `.sol` in `/share/fakenut/`.
- 🇬🇧 New name: **FakeNUT** (formerly "NUT casa"); syslog moved to a separate add-on, **QLog2HA**. Client type per device (`qnap`, `synology`, `custom`). Answers **any UPS name** by IP. Login checked for `custom`. Connection limits. `.sol` files in `/share/fakenut/`.

## 2.4.2
- 🇮🇹 Anche per amd64. Licenza MIT. · 🇬🇧 amd64 support. MIT license.

## 2.4.1
- 🇮🇹 Comandi MQTT memorizzati (retain) ignorati e cancellati. · 🇬🇧 Retained MQTT commands are ignored and cleared.

## 2.4.0
- 🇮🇹 Orari nel fuso orario di Home Assistant. · 🇬🇧 Times in Home Assistant's time zone.

## 2.0 – 2.3
- 🇮🇹 Un interruttore MQTT per dispositivo, server NUT con risposta per IP, blocco dei comandi, syslog.
- 🇬🇧 One MQTT switch per device, NUT server answering by IP, command lock, syslog.
