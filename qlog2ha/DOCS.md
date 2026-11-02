# QLog2HA

🇮🇹 Italiano (sotto) · 🇬🇧 [English below](#qlog2ha-english)

> **Avvertenza — solo per uso privato.** Questo software è pubblicato così com'è, per uso personale. Non c'è nessuna garanzia, esplicita o implicita, di funzionamento, prestazioni o idoneità a uno scopo; chi lo usa lo fa a proprio rischio. Vedi la [licenza MIT](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).

Gli **eventi dei NAS QNAP** in Home Assistant: errori dei dischi, snapshot, backup, aggiornamenti, accessi… Arrivano dal syslog di **QuLog Center** e diventano sensori, eventi per le automazioni, righe nel Registro e uno storico su file.

## Come funziona
```
NAS QNAP ── QuLog Center → Mittente log ── syslog (UDP/TCP 1514) ──► QLog2HA
                                                                      ├─► sensor.<nome>_ultimo_evento
                                                                      ├─► event.<nome>_evento (info / avviso / errore)
                                                                      ├─► Registro di HA ("NAS <nome>")
                                                                      └─► /share/qlog2ha/<nome>.log
```
Niente email, niente account QTS in Home Assistant: è il NAS che manda i suoi eventi.

## Prima di iniziare
- **Broker MQTT**: l'add-on *Mosquitto broker* con l'integrazione *MQTT*. QLog2HA prende le credenziali da solo.
- NAS QNAP con **QTS** e **QuLog Center** (preinstallato su QTS 5).
- IP fisso per ogni NAS: è come QLog2HA lo riconosce.

## Configurazione
```yaml
devices:
  - name: nas1            # minuscole, cifre e _ : diventa sensor.nas1_ultimo_evento
    ip: 192.168.1.10
port: 1514                # porta syslog (UDP e TCP)
days: 90                  # giorni di storico su file
```
I messaggi da IP non in elenco vengono ignorati (una riga nel registro dell'add-on, una volta sola per IP).

Se usi anche **FakeNUT**, dai ai NAS **gli stessi nomi** in tutti e due: in Home Assistant le entità finiscono sotto lo stesso dispositivo.

## Sul NAS
*QuLog Center → Mittente log* (in inglese *Log Sender*):
1. **Invia al server Syslog** (non "Invia a QuLog Center", che usa il protocollo QNAP).
2. Server: IP di Home Assistant. Porta: `1514`. Protocollo: UDP o TCP. Formato: **RFC 3164**.
3. Registri da inviare: **Registro eventi**. Il *Registro connessioni* è meglio lasciarlo spento: scrive una riga per ogni file aperto o caricato, migliaia al giorno.

Per fare una prova: un evento qualsiasi, per esempio il test SMART rapido di un disco, deve comparire in pochi secondi in `sensor.<nome>_ultimo_evento`.

## Entità in Home Assistant
| Entità | Cosa mostra |
|---|---|
| `sensor.<nome>_ultimo_evento` | testo dell'ultimo evento. Negli attributi: `livello`, `severita`, `application`, `category`, `users`, `source_ip`, `ricevuto`, `raw`… |
| `event.<nome>_evento` | scatta a ogni evento. Tipo `info`, `avviso` o `errore`, con gli stessi campi negli attributi |

Il livello viene dalla priorità syslog: da emergenza a errore → `errore`; avviso → `avviso`; il resto → `info`.

### Esempio: notifica sul telefono per gli errori
```yaml
automation:
  - alias: "NAS: errore"
    triggers:
      - trigger: state
        entity_id: event.nas1_evento
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type == 'errore' }}"
    actions:
      - action: notify.mobile_app_telefono
        data:
          title: "NAS nas1"
          message: "{{ trigger.to_state.attributes.content }}"
```

## Storico
- **Registro di HA:** una riga per evento, con il nome "NAS &lt;nome&gt;". Resta quanto il recorder di HA (10 giorni, se non l'hai cambiato).
- **File:** `/share/qlog2ha/<nome>.log` (cartella `share` di Home Assistant, anche via Samba), un file al giorno per `days` giorni. Ogni riga ha l'ora di ricezione (fuso di HA), il testo e il messaggio originale.
- **Accessi ai file** ("conn log"), se il NAS li manda: solo nel file, non nel sensore né nel Registro.

## Rete e sicurezza
### Porte
| Porta | Protocollo | Chi la usa | Direzione |
|---|---|---|---|
| **1514** (o `port`) | UDP e TCP | i NAS dell'elenco | NAS → Home Assistant |
| 1883 | TCP | MQTT (broker locale) | interno a Home Assistant |

L'add-on usa la **rete dell'host**, perché deve vedere il vero IP dei NAS. Quindi la porta è aperta su tutte le interfacce di Home Assistant. **Non va mai esposta su internet.** Si usa la 1514 e non la 514 standard, perché sotto la 1024 servono privilegi e spesso la 514 è già occupata.

### Cosa può fare un mittente "cattivo"
- **Falsificare eventi:** in **UDP** l'IP del mittente si può falsificare. Da dentro la rete, qualcuno può mandare finti eventi "a nome" di un NAS, per esempio un finto errore che fa scattare una notifica. In **TCP** l'IP non si falsifica, e chi non è in elenco viene rifiutato già alla connessione: **se il NAS lo permette, usa TCP**.
- **Annegarlo di messaggi:** limitato.
  - **In HA:** al massimo **30 eventi al minuto per NAS**; gli altri vanno solo nel file, e nel registro dell'add-on compare un avviso. Così Registro e database di HA non si riempiono.
  - **In TCP:** massimo 5 connessioni per IP; quelle ferme da un'ora si chiudono; righe oltre 64 KB vengono scartate.
  - **In UDP:** i messaggi da IP non in elenco vengono buttati subito, ma un flusso enorme occupa comunque rete e CPU.
  - **Spazio su disco:** i file dello storico crescono con i messaggi, anche con quelli in eccesso. Il limite è `days`, i giorni tenuti.
- **Leggere:** il syslog viaggia **in chiaro**: chi intercetta il traffico in rete legge gli eventi. Va bene in casa, non attraverso internet: per un NAS fuori sede serve una VPN o un tunnel.
- **Privacy:** gli eventi contengono nomi utente, IP e, con il Registro connessioni, nomi di file. Finiscono nel Registro di HA e nella cartella `share`, quindi li vede chi ha accesso a Home Assistant.

## Da dove viene
L'idea è dell'articolo [Getting QNAP notifications into Home Assistant with a syslog-to-MQTT relay](https://rutg3r.com/getting-qnap-notifications-into-home-assistant-with-a-syslog-to-mqtt-relay/) di rutg3r.com, che abbiamo studiato prima di scrivere QLog2HA. Lì il syslog dei QNAP arriva a un piccolo programma separato, che lo inoltra a MQTT.

QLog2HA fa la stessa cosa dentro un add-on, con in più:
- entità create da sole (MQTT discovery);
- riconoscimento del NAS dall'IP;
- lettura dei campi di QuLog Center (applicazione, categoria, utenti, contenuto) e del livello;
- Registro di HA e storico su file;
- filtro degli accessi e limiti contro gli abusi.

## Problemi frequenti
| Sintomo | Causa probabile |
|---|---|
| Non arriva niente | Mittente log non attivo, IP o porta sbagliati, "Invia a QuLog Center" invece di "Server Syslog" |
| Nel registro "syslog da … ignorato" | l'IP del NAS non è nell'elenco (o il NAS manda da un'altra scheda di rete) |
| Migliaia di righe di accessi | è attivo il Registro connessioni nel Mittente log |

---

# QLog2HA (English)

> **Disclaimer — for private use only.** This software is provided "as is", for personal use. There is no warranty of any kind, express or implied, of operation, performance or fitness for a particular purpose; use it at your own risk. See the [MIT license](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).

**QNAP NAS events** in Home Assistant: disk errors, snapshots, backups, updates, logins… They come from the **QuLog Center** syslog and become sensors, events for automations, Logbook entries and a history on file.

## How it works
```
QNAP NAS ── QuLog Center → Log Sender ── syslog (UDP/TCP 1514) ──► QLog2HA
                                                                    ├─► sensor.<name>_ultimo_evento
                                                                    ├─► event.<name>_evento (info / avviso / errore)
                                                                    ├─► HA Logbook ("NAS <name>")
                                                                    └─► /share/qlog2ha/<name>.log
```
No email, no QTS account in Home Assistant: the NAS sends its own events.

## Before you start
- **MQTT broker**: the *Mosquitto broker* add-on with the *MQTT* integration. QLog2HA gets the credentials by itself.
- QNAP NAS with **QTS** and **QuLog Center** (preinstalled on QTS 5).
- A fixed IP for each NAS: this is how QLog2HA recognizes it.

## Configuration
```yaml
devices:
  - name: nas1            # lowercase, digits and _ : becomes sensor.nas1_ultimo_evento
    ip: 192.168.1.10
port: 1514                # syslog port (UDP and TCP)
days: 90                  # days of history on file
```
Messages from IPs not in the list are ignored (one line in the add-on log, once per IP).

If you also use **FakeNUT**, give the NAS units **the same names** in both: in Home Assistant their entities end up under the same device.

## On the NAS
*QuLog Center → Log Sender*:
1. **Send to Syslog server** (not "Send to QuLog Center", which uses QNAP's own protocol).
2. Server: Home Assistant's IP. Port: `1514`. Protocol: UDP or TCP. Format: **RFC 3164**.
3. Logs to send: **Event log**. Better leave the *Connection log* off: it writes one line for every file opened or uploaded, thousands a day.

To test: any event, for example a quick SMART test of a disk, should show up within seconds in `sensor.<name>_ultimo_evento`.

## Entities in Home Assistant
Entity names are in Italian (`ultimo_evento` = last event, `evento` = event).

| Entity | What it shows |
|---|---|
| `sensor.<name>_ultimo_evento` | text of the last event. Attributes: `livello` (level), `severita` (severity), `application`, `category`, `users`, `source_ip`, `ricevuto` (received), `raw`… |
| `event.<name>_evento` | fires on every event. Type `info`, `avviso` (warning) or `errore` (error), with the same fields as attributes |

The level comes from the syslog priority: emergency to error → `errore`; warning → `avviso`; everything else → `info`.

### Example: phone notification for errors
```yaml
automation:
  - alias: "NAS: error"
    triggers:
      - trigger: state
        entity_id: event.nas1_evento
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type == 'errore' }}"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "NAS nas1"
          message: "{{ trigger.to_state.attributes.content }}"
```

## History
- **HA Logbook:** one line per event, named "NAS &lt;name&gt;". Kept as long as HA's recorder keeps data (10 days unless you changed it).
- **File:** `/share/qlog2ha/<name>.log` (Home Assistant's `share` folder, also via Samba), one file per day for `days` days. Each line has the time received (HA's time zone), the text and the original message.
- **File accesses** ("conn log"), if the NAS sends them: only in the file, not in the sensor or the Logbook.

## Network and security
### Ports
| Port | Protocol | Used by | Direction |
|---|---|---|---|
| **1514** (or `port`) | UDP and TCP | the NAS units in the list | NAS → Home Assistant |
| 1883 | TCP | MQTT (local broker) | inside Home Assistant |

The add-on uses the **host network**, because it must see the NAS units' real IP. So the port is open on all of Home Assistant's interfaces. **Never expose it to the internet.** Port 1514 is used instead of the standard 514 because ports below 1024 need privileges, and 514 is often already taken.

### What a "malicious" sender can do
- **Forge events:** over **UDP** the sender's IP can be spoofed. From inside the network, someone can send fake events "on behalf of" a NAS, for example a fake error that triggers a notification. Over **TCP** the IP cannot be spoofed, and senders not in the list are refused at connection time: **use TCP if the NAS allows it**.
- **Flood it with messages:** limited.
  - **Into HA:** at most **30 events per minute per NAS**; the rest go only to the file, and the add-on log shows a warning. This way HA's Logbook and database do not fill up.
  - **Over TCP:** at most 5 connections per IP; connections idle for an hour are closed; lines over 64 KB are dropped.
  - **Over UDP:** messages from IPs not in the list are dropped immediately, but a huge stream still uses network and CPU.
  - **Disk space:** history files grow with the messages, including the excess ones. The limit is `days`, the number of days kept.
- **Read:** syslog travels **in plain text**: anyone sniffing network traffic can read the events. Fine at home, not across the internet: for an off-site NAS use a VPN or a tunnel.
- **Privacy:** events contain user names, IPs and, with the Connection log, file names. They end up in HA's Logbook and in the `share` folder, so anyone with access to Home Assistant can see them.

## Where it comes from
The idea comes from the article [Getting QNAP notifications into Home Assistant with a syslog-to-MQTT relay](https://rutg3r.com/getting-qnap-notifications-into-home-assistant-with-a-syslog-to-mqtt-relay/) on rutg3r.com, which we studied before writing QLog2HA. There, QNAP's syslog goes to a small separate program that relays it to MQTT.

QLog2HA does the same inside an add-on, plus:
- entities created automatically (MQTT discovery);
- NAS recognized by IP;
- parsing of QuLog Center fields (application, category, users, content) and of the level;
- HA Logbook and history on file;
- file-access filter and limits against abuse.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Nothing arrives | Log Sender not enabled, wrong IP or port, "Send to QuLog Center" instead of "Syslog server" |
| Log shows "syslog da … ignorato" (ignored) | the NAS's IP is not in the list (or the NAS sends from another network card) |
| Thousands of access lines | the Connection log is enabled in the Log Sender |
