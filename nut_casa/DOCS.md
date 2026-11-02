# NUT casa

Un interruttore in Home Assistant per ogni NAS QNAP dell'elenco.

- **Stato:** acceso se il NAS risponde al ping (spento dopo 3 ping falliti di fila).
- **Spegnere:** l'add-on crea `/share/nut/<nome>.sol` ("stop over lan"). Da quel momento il server NUT risponde a quel NAS "a batteria e scarica", e QTS si spegne in modo pulito.
- **Accendere:** cancella `<nome>.sol` e manda il Wake-on-LAN al MAC del NAS.
- **Blocco:** dopo un comando l'interruttore non accetta altri comandi finché il ping non conferma (al massimo `lock_minutes`). Un ON annulla ancora un OFF nel primo minuto.

## Come funziona il server NUT
QTS chiede sempre l'UPS con il nome fisso `qnapups`. L'add-on risponde in base all'**IP** di chi chiede, quindi ogni NAS legge solo il proprio stato. Non accetta comandi (`SET`, `INSTCMD`, `FSD`).

## Configurazione
```yaml
devices:
  - name: nas1          # minuscole, cifre, _ : diventa switch.nas1
    ip: 192.168.1.10
    mac: "aa:bb:cc:dd:ee:ff"   # vuoto = niente Wake-on-LAN
broadcast: 192.168.1.255       # broadcast della rete dei NAS, per il Wake-on-LAN
ping_interval: 10              # secondi
lock_minutes: 5
syslog_days: 90                # giorni di storico syslog su file
real_ups: false                # UPS vero in USB, esposto su porta 3494
```
Nomi e IP devono essere unici. Il Wake-on-LAN usa un solo broadcast, quindi funziona per i NAS di quella rete.

## Su ogni NAS (QTS)
- *Pannello di controllo → Alimentazione esterna → UPS*: **Slave di rete UPS**, IP del server = IP di Home Assistant.
- Syslog (facoltativo): *QuLog Center → Mittente log → Invia al server Syslog*, IP di Home Assistant, porta `1514`, UDP o TCP, formato RFC 3164, **solo Registro eventi** (il registro delle connessioni scrive una riga per ogni file aperto).

## Entità (MQTT discovery)
Per ogni NAS: `switch.<nome>`, `binary_sensor.<nome>_in_corso`, `sensor.<nome>_ultimo_evento`, `event.<nome>_evento` (tipi `info`, `avviso`, `errore`).

## Storico syslog
Ogni evento va nel **Registro** di HA (nome "NAS &lt;nome&gt;") e nel file `/share/nut/syslog/<nome>.log`, un file al giorno, tenuto `syslog_days` giorni. Gli accessi ai file ("conn log") vanno solo nel file.

## Requisiti
Broker MQTT (add-on Mosquitto), integrazione MQTT. Architetture: aarch64 (Raspberry Pi 4/5 e simili) e amd64 (PC, macchine virtuali). Provato su Raspberry Pi 5 con QTS 5.2.
