# QLog2HA

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
