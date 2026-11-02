# FakeNUT

> **Avvertenza — solo per uso privato.** Questo software è pubblicato così com'è, per uso personale. Non c'è nessuna garanzia, esplicita o implicita, di funzionamento, prestazioni o idoneità a uno scopo; chi lo usa lo fa a proprio rischio. In particolare FakeNUT può spegnere dispositivi: provalo prima di affidargli qualcosa di importante. Vedi la [licenza MIT](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).
>
> *Disclaimer — for private use only. Provided "as is", without any express or implied warranty of operation, performance or fitness for a particular purpose. Use at your own risk.*

Un **finto server NUT** che risponde a ogni client in base al suo indirizzo IP, e un **interruttore in Home Assistant** per ogni dispositivo: lo spegni in modo pulito, lo riaccendi col Wake-on-LAN, e vedi se è acceso.

## A cosa serve
Molti NAS e server sanno spegnersi da soli quando l'UPS va a batteria: chiedono lo stato a un server **NUT** (Network UPS Tools) e, se legge "a batteria e scarica", si spengono in modo pulito.

FakeNUT sfrutta questo meccanismo. Fa finta di essere un UPS, e la risposta la decide Home Assistant, **dispositivo per dispositivo**:

```
switch.nas2 OFF ──► FakeNUT crea /share/fakenut/nas2.sol
                          │
nas2 chiede lo stato ─────┴──► "a batteria, scarica" (solo a nas2) ──► nas2 si spegne
nas1 chiede lo stato ─────────► "in rete"                           ──► nas1 resta acceso

switch.nas2 ON  ──► cancella nas2.sol ──► Wake-on-LAN al MAC di nas2 ──► si riaccende
ping ogni 10 s  ──► stato dell'interruttore (acceso = risponde al ping)
```

Usi tipici:
- spegnere un NAS di backup quando ha finito e riaccenderlo quando serve;
- spegnere tutto, uno per uno, in un blackout, con un'automazione legata a un UPS vero;
- riaccendere tutto al ritorno della corrente.

## Prima di iniziare
- **Broker MQTT**: l'add-on *Mosquitto broker* con l'integrazione *MQTT*. FakeNUT prende le credenziali da solo.
- Un dispositivo che sappia fare da **client NUT** ("slave di rete UPS"): QNAP, Synology, TrueNAS, Unraid, Proxmox, Linux con `upsmon`, WinNUT…
- Per accendere da remoto: **Wake-on-LAN** abilitato sul dispositivo e il suo **MAC**. Il pacchetto parte in broadcast, quindi il dispositivo deve stare nella stessa rete (VLAN) indicata in `broadcast`.

## Configurazione
Scheda *Configurazione* dell'add-on:

```yaml
devices:
  - name: nas1                 # minuscole, cifre e _ : diventa switch.nas1
    ip: 192.168.1.10
    mac: "aa:bb:cc:dd:ee:ff"   # facoltativo: senza, niente Wake-on-LAN
    type: qnap                 # qnap | synology | custom
  - name: server
    ip: 192.168.1.20
    mac: "aa:bb:cc:dd:ee:00"
    type: custom
    user: monuser              # solo per custom: il client deve usare questi
    password: una-password
broadcast: 192.168.1.255       # broadcast della rete dei dispositivi (Wake-on-LAN)
ping_interval: 10              # secondi tra un ping e l'altro
lock_minutes: 5                # durata massima del blocco dopo un comando
real_ups: false                # UPS vero collegato in USB (vedi sotto)
```

| Voce | Cosa vuol dire |
|---|---|
| `name` | nome dell'interruttore e del dispositivo in HA. Unico |
| `ip` | IP fisso del dispositivo: è come FakeNUT lo riconosce. Unico |
| `mac` | per il Wake-on-LAN. Vuoto = l'interruttore spegne ma non riaccende |
| `type` | che client NUT è (tabella sotto) |
| `user`, `password` | solo per `custom`: se compilati, FakeNUT li controlla al login |
| `broadcast` | indirizzo di broadcast della rete dei dispositivi |
| `ping_interval` | ogni quanto controllare se sono accesi |
| `lock_minutes` | dopo un comando, per quanto al massimo l'interruttore resta bloccato |
| `debug` | (facoltativo) scrive nel registro ogni domanda NUT, con l'IP |

### Tipi di client
| `type` | Nome UPS | Utente | Password | Note |
|---|---|---|---|---|
| `qnap` | `qnapups` | `admin` | `123456` | fissi in QTS, non si cambiano |
| `synology` | `ups` | `monuser` | `secret` | fissi in DSM, non si cambiano |
| `custom` | qualsiasi | `user` | `password` | li scegli tu e li scrivi uguali nel client |

FakeNUT risponde a **qualsiasi nome di UPS** in base all'IP di chi chiede, quindi il nome configurato nel client non conta. Per i tipi `qnap` e `synology` utente e password sono quelli fissi del sistema.

## Sul dispositivo
- **QNAP (QTS):** *Pannello di controllo → Sistema → Alimentazione esterna → UPS*: **Slave di rete UPS**, IP del server = IP di Home Assistant. Imposta anche dopo quanto spegnersi una volta "a batteria".
- **Synology (DSM):** *Pannello di controllo → Hardware e alimentazione → UPS*: abilita, tipo **Server UPS Synology**, IP del server = IP di Home Assistant.
- **Altri (custom):** nel client NUT (`upsmon.conf` o interfaccia equivalente): server = IP di Home Assistant, porta `3493`, un nome UPS qualsiasi, e `user`/`password` uguali a quelli dell'elenco.

## Entità in Home Assistant
Per ogni dispositivo (via MQTT discovery):

| Entità | Cosa mostra |
|---|---|
| `switch.<nome>` | acceso se risponde al ping. OFF = spegnimento, ON = riaccensione |
| `binary_sensor.<nome>_in_corso` | acceso mentre un comando aspetta la conferma del ping |

Attributi dell'interruttore: `ip`, `mac`, `tipo`, `spegnimento_richiesto` (c'è il file `.sol`), `comando_in_corso`, `bloccato`.

## Come si comporta
- **Stato:** "spento" solo dopo 3 ping falliti di fila. Dopo un OFF l'interruttore resta su **on** finché il dispositivo risponde ancora (di solito 2–3 minuti): è normale.
- **Blocco dei comandi:** dopo un **ON** l'interruttore ignora altri comandi finché il ping non conferma. Dopo un **OFF**, nel **primo minuto** un ON lo annulla ancora; poi resta bloccato. Il blocco dura al massimo `lock_minutes`.
- **Il file `.sol` resta** anche se l'add-on o Home Assistant si riavviano. Attenzione: un dispositivo che si riaccende da solo (per esempio al ritorno della corrente) con il suo `.sol` presente **si rispegne**. Si riaccende con l'interruttore.
- **Chi non è nell'elenco** e chiede `qnapups` o `ups` legge sempre "in rete".
- **Nessun comando accettato:** `SET`, `INSTCMD`, `FSD` rispondono `ACCESS-DENIED`. FakeNUT non spegne niente di sua iniziativa: dice solo "a batteria" a chi deve spegnersi.

## UPS vero (facoltativo)
Con un UPS collegato in USB al dispositivo di Home Assistant: `real_ups: true`, `real_ups_driver` (di solito `usbhid-ups`) e `real_ups_port` (`auto`). Parte un server NUT standard sulla porta **3494**, da aggiungere in HA con l'integrazione **Network UPS Tools**. I client di FakeNUT non lo vedono: per spegnerli in un blackout serve un'automazione, per esempio "a batteria da 3 minuti → spegni gli interruttori".

## Rete e sicurezza
### Porte
| Porta | Protocollo | Chi la usa | Direzione |
|---|---|---|---|
| **3493** | TCP | i client NUT dell'elenco | dispositivi → Home Assistant |
| 3494 | TCP | integrazione NUT di HA, solo con `real_ups: true` | HA → add-on |
| 9 | UDP broadcast | Wake-on-LAN | Home Assistant → rete dei dispositivi |
| 1883 | TCP | MQTT (broker locale) | interno a Home Assistant |

L'add-on usa la **rete dell'host**: deve vedere il vero IP dei client e mandare il broadcast del Wake-on-LAN. Quindi la 3493 è aperta su tutte le interfacce di Home Assistant. **Non va mai esposta su internet** (niente port forwarding sul router).

Se un client è in un'altra VLAN, il firewall deve permettergli la 3493 verso Home Assistant. Meglio solo da quell'IP.

### Cosa può fare un client "cattivo"
- **Comandare:** niente. FakeNUT non accetta comandi (`SET`, `INSTCMD`, `FSD` → `ACCESS-DENIED`) e non spegne niente di sua iniziativa. Gli interruttori si comandano solo da Home Assistant, via MQTT.
- **Leggere:** chi è in rete può chiedere lo stato. Chi ha l'IP di un dispositivo dell'elenco legge il suo stato ("in rete" o "a batteria"): è un'informazione poco sensibile. FakeNUT riconosce i dispositivi **solo dall'IP**.
- **Ingannare un dispositivo:** chi riesce a prendere il posto di Home Assistant in rete (stesso IP, ARP spoofing) può far credere a un NAS che l'UPS è scarico e farlo spegnere. È il limite di NUT stesso, che non cifra niente: vale per qualsiasi server NUT in chiaro.
- **Annegarlo di richieste:** limitato. Massimo **10 connessioni per IP** e **100 in totale**; una connessione ferma da 5 minuti si chiude; righe lunghe oltre 64 KB vengono scartate. Oltre i limiti le connessioni vengono rifiutate, e nel registro compare "troppe connessioni". Un attacco forte da dentro la rete può comunque rallentare l'add-on, come ogni servizio: per questo FakeNUT va tenuto solo sulla rete di casa.
- **Utente e password:** per i client `custom` vengono controllati al login, ma viaggiano in chiaro (NUT senza TLS). Per `qnap` e `synology` sono quelli fissi e pubblici del firmware, quindi non proteggono niente.

## Problemi frequenti
| Sintomo | Causa probabile |
|---|---|
| Il dispositivo non si spegne | il client NUT non è attivo, o punta a un altro IP; prova con `debug: true` e guarda il registro |
| Non si riaccende | Wake-on-LAN spento sul dispositivo, MAC sbagliato, broadcast di un'altra rete, porte aggregate (LAG) |
| Si rispegne appena acceso | c'è ancora il suo `.sol`: interruttore su ON |
| Login rifiutato nel registro | client `custom` con utente o password diversi dall'elenco |
