# Add-on per Home Assistant · Home Assistant add-ons

🇮🇹 [Italiano](#italiano) · 🇬🇧 [English](#english)

| | |
|---|---|
| <img src="fakenut/logo.png" width="120" alt="FakeNUT"> | <img src="qlog2ha/logo.png" width="120" alt="QLog2HA"> |
| [**FakeNUT**](fakenut/DOCS.md) | [**QLog2HA**](qlog2ha/DOCS.md) |

## Italiano

> **Avvertenza — solo per uso privato.** Questo software è pubblicato così com'è, per uso personale. Non c'è nessuna garanzia, esplicita o implicita, di funzionamento, prestazioni o idoneità a uno scopo; chi lo usa lo fa a proprio rischio. In particolare FakeNUT può spegnere dispositivi: provalo prima di affidargli qualcosa di importante. Vedi la [licenza MIT](LICENSE).

Due add-on indipendenti per gestire NAS e server di casa da Home Assistant. Si possono installare uno o tutti e due.

| Add-on | A cosa serve | Per chi |
|---|---|---|
| [**FakeNUT**](fakenut/DOCS.md) | Finto server NUT che risponde a ogni client in base al suo IP: un interruttore per dispositivo, per spegnerlo in modo pulito e riaccenderlo col Wake-on-LAN | qualsiasi client NUT: QNAP, Synology, TrueNAS, Unraid, Proxmox, Linux… |
| [**QLog2HA**](qlog2ha/DOCS.md) | Gli eventi dei NAS QNAP (syslog di QuLog Center) come sensori, eventi per le automazioni, Registro e storico | chi ha un QNAP |

Se usi tutti e due con **gli stessi nomi**, in Home Assistant le entità di ogni NAS stanno sotto un solo dispositivo.

### Installazione
1. In Home Assistant: *Impostazioni → Componenti aggiuntivi → Negozio dei componenti aggiuntivi → ⋮ → Repository*.
2. Aggiungi `https://github.com/samusamu81/ha-addons`.
3. Installa FakeNUT e/o QLog2HA, compila la scheda *Configurazione* e avvia.

L'immagine viene costruita sul tuo Home Assistant al momento dell'installazione (un paio di minuti).

### Requisiti
- Home Assistant OS o Supervised (servono gli add-on).
- Add-on **Mosquitto broker** e integrazione **MQTT**.
- Architetture: `aarch64` (Raspberry Pi 4/5 e simili) e `amd64` (PC, macchine virtuali). Provati su Raspberry Pi 5 con QNAP QTS 5.2.

### Licenza
[MIT](LICENSE).

## English

> **Disclaimer — for private use only.** This software is provided "as is", for personal use. There is no warranty of any kind, express or implied, of operation, performance or fitness for a particular purpose; use it at your own risk. FakeNUT can shut devices down: test it before trusting it with anything important. See the [MIT license](LICENSE).

Two independent add-ons to manage home NAS units and servers from Home Assistant. Install one or both.

| Add-on | What it does | For |
|---|---|---|
| [**FakeNUT**](fakenut/DOCS.md) | Fake NUT server answering each client by its IP: one switch per device, to shut it down cleanly and power it on with Wake-on-LAN | any NUT client: QNAP, Synology, TrueNAS, Unraid, Proxmox, Linux… |
| [**QLog2HA**](qlog2ha/DOCS.md) | QNAP NAS events (QuLog Center syslog) as sensors, events for automations, Logbook entries and history | QNAP owners |

If you use both with **the same names**, each NAS's entities are grouped under a single device in Home Assistant.

### Installation
1. In Home Assistant: *Settings → Add-ons → Add-on store → ⋮ → Repositories*.
2. Add `https://github.com/samusamu81/ha-addons`.
3. Install FakeNUT and/or QLog2HA, fill in the *Configuration* tab and start.

The image is built on your Home Assistant at install time (a couple of minutes).

### Requirements
- Home Assistant OS or Supervised (add-ons are required).
- **Mosquitto broker** add-on and **MQTT** integration.
- Architectures: `aarch64` (Raspberry Pi 4/5 and similar) and `amd64` (PCs, virtual machines). Tested on a Raspberry Pi 5 with QNAP QTS 5.2.

The documentation is in Italian first, then English. Entity and attribute names are in Italian.

### License
[MIT](LICENSE).

---
#ha-addons
