# Add-on per Home Assistant

> **Avvertenza — solo per uso privato.** Questo software è pubblicato così com'è, per uso personale. Non c'è nessuna garanzia, esplicita o implicita, di funzionamento, prestazioni o idoneità a uno scopo; chi lo usa lo fa a proprio rischio. In particolare FakeNUT può spegnere dispositivi: provalo prima di affidargli qualcosa di importante. Vedi la [licenza MIT](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).
>
> *Disclaimer — for private use only. Provided "as is", without any express or implied warranty of operation, performance or fitness for a particular purpose. Use at your own risk.*

Due add-on indipendenti per gestire NAS e server di casa da Home Assistant. Si possono installare uno o tutti e due.

| Add-on | A cosa serve | Per chi |
|---|---|---|
| [**FakeNUT**](fakenut/DOCS.md) | Finto server NUT che risponde a ogni client in base al suo IP: un interruttore per dispositivo, per spegnerlo in modo pulito e riaccenderlo col Wake-on-LAN | qualsiasi client NUT: QNAP, Synology, TrueNAS, Unraid, Proxmox, Linux… |
| [**QLog2HA**](qlog2ha/DOCS.md) | Gli eventi dei NAS QNAP (syslog di QuLog Center) come sensori, eventi per le automazioni, Registro e storico | chi ha un QNAP |

Se usi tutti e due con **gli stessi nomi**, in Home Assistant le entità di ogni NAS stanno sotto un solo dispositivo.

*Two independent Home Assistant add-ons: **FakeNUT**, a fake NUT server answering each client by IP (one switch per device: clean shutdown, Wake-on-LAN, ping status); **QLog2HA**, QNAP syslog events as MQTT entities. Documentation in Italian.*

## Installazione
1. In Home Assistant: *Impostazioni → Componenti aggiuntivi → Negozio dei componenti aggiuntivi → ⋮ → Repository*.
2. Aggiungi `https://github.com/samusamu81/ha-addons`.
3. Installa FakeNUT e/o QLog2HA, compila la scheda *Configurazione* e avvia.

L'immagine viene costruita sul tuo Home Assistant al momento dell'installazione (un paio di minuti).

## Requisiti
- Home Assistant OS o Supervised (servono gli add-on).
- Add-on **Mosquitto broker** e integrazione **MQTT**.
- Architetture: `aarch64` (Raspberry Pi 4/5 e simili) e `amd64` (PC, macchine virtuali). Provati su Raspberry Pi 5 con QNAP QTS 5.2.

## Licenza
[MIT](LICENSE).
