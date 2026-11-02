# FakeNUT

🇮🇹 Italiano (sotto) · 🇬🇧 [English below](#fakenut-english)

> **Avvertenza — solo per uso privato.** Questo software è pubblicato così com'è, per uso personale. Non c'è nessuna garanzia, esplicita o implicita, di funzionamento, prestazioni o idoneità a uno scopo; chi lo usa lo fa a proprio rischio. In particolare FakeNUT può spegnere dispositivi: provalo prima di affidargli qualcosa di importante. Vedi la [licenza MIT](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).

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
force_shutdown: false          # true = chi si riaccende a mano si rispegne (vedi sotto)
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
| `force_shutdown` | cosa succede se riaccendi a mano un dispositivo spento da FakeNUT (sezione sotto). Predefinito `false` |
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
- **Il file `.sol`** sopravvive ai riavvii dell'add-on e di Home Assistant. Quando viene cancellato lo decide `force_shutdown` (sezione sotto).
- **Chi non è nell'elenco** e chiede `qnapups` o `ups` legge sempre "in rete".
- **Nessun comando accettato:** `SET`, `INSTCMD`, `FSD` rispondono `ACCESS-DENIED`. FakeNUT non spegne niente di sua iniziativa: dice solo "a batteria" a chi deve spegnersi.

## Riaccensione a mano e `force_shutdown`
Dopo un OFF, FakeNUT risponde "a batteria" finché esiste il file `<nome>.sol`. Se in quel momento il dispositivo si riaccende senza passare dall'interruttore (pulsante, WOL da un'altra app, ripristino dell'alimentazione), legge "a batteria" e **si rispegne**. `force_shutdown` sceglie se è quello che vuoi.

| | `force_shutdown: false` (predefinito) | `force_shutdown: true` |
|---|---|---|
| Quando si cancella il `.sol` | appena il ping conferma che è **spento** (3 ping falliti) | solo con un **ON** dall'interruttore |
| Lo riaccendi col pulsante | resta acceso; l'interruttore torna su ON da solo | **si rispegne** dopo il ritardo impostato sul dispositivo |
| Per riaccenderlo da HA | interruttore su ON (manda il WOL) | interruttore su ON (cancella il `.sol` e manda il WOL) |
| Adatto a | uso normale: spegni da HA, riaccendi come vuoi | dispositivi che devono restare spenti finché lo decide Home Assistant |

**Con l'UPS vero** (`real_ups: true`) il `.sol` si cancella solo se l'UPS è **in rete** (`OL`). Se è **a batteria**, o se non risponde, il file resta anche con `force_shutdown: false`: durante un blackout il dispositivo è ancora alimentato dalla batteria, e un'accensione lo farebbe ripartire. Il file si cancella da solo quando l'UPS torna in rete.

Un dispositivo spento **non** si riaccende perché il file è stato cancellato: un dispositivo spento non interroga FakeNUT. Lo riaccendono solo il WOL, il pulsante, o il ripristino dell'alimentazione quando la corrente al suo ingresso manca e poi torna.

### Blackout con UPS vero: confronto con un NUT normale
Con un server NUT normale, dopo lo spegnimento dei client il server manda all'UPS il comando "togli corrente" (*killpower*): l'UPS spegne le prese e le riaccende al ritorno della rete, così i dispositivi con il ripristino dell'alimentazione ripartono. Senza quel comando, se la corrente torna prima che la batteria finisca, i dispositivi restano spenti.

FakeNUT non usa *killpower*: per riaccendere usa il **Wake-on-LAN**. Un'automazione tipica:
- UPS vero **a batteria da 3 minuti** → `switch.turn_off` sugli interruttori;
- UPS vero **in rete da 5 minuti** → `switch.turn_on` sugli interruttori dei dispositivi spenti.

Se invece la batteria finisce, al ritorno della corrente i dispositivi con il ripristino dell'alimentazione ripartono da soli; il loro `.sol` è già stato cancellato (UPS in rete), quindi restano accesi.

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
| Si rispegne appena acceso | c'è ancora il suo `.sol`: con `force_shutdown: true` è voluto (interruttore su ON); con `false`, l'UPS vero è a batteria o non risponde |
| Login rifiutato nel registro | client `custom` con utente o password diversi dall'elenco |

---

# FakeNUT (English)

> **Disclaimer — for private use only.** This software is provided "as is", for personal use. There is no warranty of any kind, express or implied, of operation, performance or fitness for a particular purpose; use it at your own risk. FakeNUT can shut devices down: test it before trusting it with anything important. See the [MIT license](https://github.com/samusamu81/ha-addons/blob/main/LICENSE).

A **fake NUT server** that answers each client according to its IP address, plus a **Home Assistant switch** for each device: shut it down cleanly, turn it back on with Wake-on-LAN, and see whether it is on.

## What it is for
Many NAS units and servers can shut themselves down when the UPS goes on battery: they ask a **NUT** (Network UPS Tools) server for the UPS status and, when it reads "on battery, low", they shut down cleanly.

FakeNUT uses this mechanism. It pretends to be a UPS, and Home Assistant decides the answer **device by device**:

```
switch.nas2 OFF ──► FakeNUT creates /share/fakenut/nas2.sol
                          │
nas2 asks the status ─────┴──► "on battery, low" (only to nas2) ──► nas2 shuts down
nas1 asks the status ─────────► "online"                         ──► nas1 stays on

switch.nas2 ON  ──► deletes nas2.sol ──► Wake-on-LAN to nas2's MAC ──► it powers on
ping every 10 s ──► switch state (on = answers the ping)
```

Typical uses:
- shut down a backup NAS when it is done, and power it on when needed;
- during a blackout, shut everything down one by one, with an automation tied to a real UPS;
- power everything back on when the mains return.

## Before you start
- **MQTT broker**: the *Mosquitto broker* add-on with the *MQTT* integration. FakeNUT gets the credentials by itself.
- A device that can act as a **NUT client** ("network UPS slave"): QNAP, Synology, TrueNAS, Unraid, Proxmox, Linux with `upsmon`, WinNUT…
- To power on remotely: **Wake-on-LAN** enabled on the device, and its **MAC**. The packet is a broadcast, so the device must be on the network (VLAN) given in `broadcast`.

## Configuration
The add-on's *Configuration* tab:

```yaml
devices:
  - name: nas1                 # lowercase, digits and _ : becomes switch.nas1
    ip: 192.168.1.10
    mac: "aa:bb:cc:dd:ee:ff"   # optional: without it, no Wake-on-LAN
    type: qnap                 # qnap | synology | custom
  - name: server
    ip: 192.168.1.20
    mac: "aa:bb:cc:dd:ee:00"
    type: custom
    user: monuser              # custom only: the client must use these
    password: a-password
broadcast: 192.168.1.255       # broadcast address of the devices' network (Wake-on-LAN)
ping_interval: 10              # seconds between pings
lock_minutes: 5                # maximum lock time after a command
force_shutdown: false          # true = a device powered on by hand shuts down again (see below)
real_ups: false                # real UPS on USB (see below)
```

| Option | Meaning |
|---|---|
| `name` | name of the switch and of the device in HA. Unique |
| `ip` | fixed IP of the device: this is how FakeNUT recognizes it. Unique |
| `mac` | for Wake-on-LAN. Empty = the switch shuts down but cannot power on |
| `type` | which kind of NUT client it is (table below) |
| `user`, `password` | `custom` only: if set, FakeNUT checks them at login |
| `broadcast` | broadcast address of the devices' network |
| `ping_interval` | how often to check whether devices are on |
| `lock_minutes` | after a command, the longest time the switch stays locked |
| `force_shutdown` | what happens if you power on by hand a device FakeNUT shut down (section below). Default `false` |
| `debug` | (optional) logs every NUT request, with the IP |

### Client types
| `type` | UPS name | User | Password | Notes |
|---|---|---|---|---|
| `qnap` | `qnapups` | `admin` | `123456` | fixed in QTS, cannot be changed |
| `synology` | `ups` | `monuser` | `secret` | fixed in DSM, cannot be changed |
| `custom` | any | `user` | `password` | you choose them and set the same in the client |

FakeNUT answers **any UPS name** according to the client's IP, so the name configured in the client does not matter. For `qnap` and `synology`, user and password are the fixed ones of the system.

## On the device
- **QNAP (QTS):** *Control Panel → System → External Device → UPS*: **Network UPS slave**, server IP = Home Assistant's IP. Also set how long to wait before shutting down once "on battery".
- **Synology (DSM):** *Control Panel → Hardware & Power → UPS*: enable, type **Synology UPS server**, server IP = Home Assistant's IP.
- **Others (custom):** in the NUT client (`upsmon.conf` or equivalent UI): server = Home Assistant's IP, port `3493`, any UPS name, and the same `user`/`password` as in the list.

## Entities in Home Assistant
For each device (via MQTT discovery):

| Entity | What it shows |
|---|---|
| `switch.<name>` | on when the device answers the ping. OFF = shut down, ON = power on |
| `binary_sensor.<name>_in_corso` | on while a command waits for the ping to confirm it ("in corso" = in progress) |

Switch attributes: `ip`, `mac`, `tipo` (type), `spegnimento_richiesto` (shutdown requested: the `.sol` file exists), `comando_in_corso` (command in progress), `bloccato` (locked).

## How it behaves
- **State:** "off" only after 3 failed pings in a row. After OFF the switch stays **on** while the device still answers (usually 2–3 minutes): this is normal.
- **Command lock:** after **ON** the switch ignores further commands until the ping confirms. After **OFF**, during the **first minute** an ON still cancels it; then it is locked. The lock lasts at most `lock_minutes`.
- **The `.sol` file** survives add-on and Home Assistant restarts. When it is deleted depends on `force_shutdown` (section below).
- **Clients not in the list** asking for `qnapups` or `ups` always read "online".
- **No commands accepted:** `SET`, `INSTCMD`, `FSD` answer `ACCESS-DENIED`. FakeNUT never shuts anything down on its own: it only tells "on battery" to the device that must shut down.

## Manual power-on and `force_shutdown`
After an OFF, FakeNUT answers "on battery" as long as the `<name>.sol` file exists. If the device powers on without using the switch (power button, WOL from another app, power recovery), it reads "on battery" and **shuts down again**. `force_shutdown` chooses whether you want that.

| | `force_shutdown: false` (default) | `force_shutdown: true` |
|---|---|---|
| When the `.sol` is deleted | as soon as the ping confirms the device is **off** (3 failed pings) | only by an **ON** from the switch |
| You power it on with the button | it stays on; the switch goes back to ON by itself | it **shuts down again** after the delay set on the device |
| To power it on from HA | switch ON (sends WOL) | switch ON (deletes the `.sol` and sends WOL) |
| Good for | normal use: shut down from HA, power on as you like | devices that must stay off until Home Assistant decides |

**With the real UPS** (`real_ups: true`) the `.sol` is deleted only when the UPS is **online** (`OL`). If it is **on battery**, or does not answer, the file stays even with `force_shutdown: false`: during a blackout the device is still powered by the battery, and powering it on would restart it. The file is deleted by itself once the UPS is back online.

A powered-off device does **not** power on because its file was deleted: a device that is off does not query FakeNUT. Only WOL, the power button, or power recovery (when the power at its input goes away and comes back) turn it on.

### Blackout with a real UPS: compared with a regular NUT
With a regular NUT server, after the clients shut down the server sends the UPS a "kill power" command: the UPS turns its outlets off and back on when the mains return, so devices with power recovery restart. Without that command, if the mains return before the battery runs out, the devices stay off.

FakeNUT does not use kill power: it powers devices on with **Wake-on-LAN**. A typical automation:
- real UPS **on battery for 3 minutes** → `switch.turn_off` on the switches;
- real UPS **online for 5 minutes** → `switch.turn_on` on the switches of the devices that are off.

If the battery does run out, when the mains return the devices with power recovery restart by themselves; their `.sol` has already been deleted (UPS online), so they stay on.

## Real UPS (optional)
With a UPS connected via USB to the Home Assistant machine: `real_ups: true`, `real_ups_driver` (usually `usbhid-ups`) and `real_ups_port` (`auto`). A standard NUT server starts on port **3494**; add it in HA with the **Network UPS Tools** integration. FakeNUT's clients do not see it: to shut them down in a blackout you need an automation, for example "on battery for 3 minutes → turn the switches off".

## Network and security
### Ports
| Port | Protocol | Used by | Direction |
|---|---|---|---|
| **3493** | TCP | the NUT clients in the list | devices → Home Assistant |
| 3494 | TCP | HA's NUT integration, only with `real_ups: true` | HA → add-on |
| 9 | UDP broadcast | Wake-on-LAN | Home Assistant → devices' network |
| 1883 | TCP | MQTT (local broker) | inside Home Assistant |

The add-on uses the **host network**: it must see the clients' real IP and send the Wake-on-LAN broadcast. So port 3493 is open on all of Home Assistant's interfaces. **Never expose it to the internet** (no port forwarding on the router).

If a client is on another VLAN, the firewall must allow it to reach port 3493 on Home Assistant, ideally only from that IP.

### What a "malicious" client can do
- **Give commands:** nothing. FakeNUT accepts no commands (`SET`, `INSTCMD`, `FSD` → `ACCESS-DENIED`) and never shuts anything down by itself. The switches are controlled only from Home Assistant, via MQTT.
- **Read:** anyone on the network can ask for the status. Whoever uses the IP of a listed device reads that device's status ("online" or "on battery"): not very sensitive information. FakeNUT recognizes devices **by IP only**.
- **Deceive a device:** someone who takes Home Assistant's place on the network (same IP, ARP spoofing) can make a NAS believe the UPS is low and shut it down. This is a limit of NUT itself, which encrypts nothing: it applies to any plain-text NUT server.
- **Flood it with requests:** limited. At most **10 connections per IP** and **100 in total**; a connection idle for 5 minutes is closed; lines longer than 64 KB are dropped. Beyond the limits connections are refused, and the log shows "troppe connessioni" (too many connections). A heavy attack from inside the network can still slow the add-on down, like any service: that is why FakeNUT must stay on the home network only.
- **User and password:** checked at login for `custom` clients, but sent in plain text (NUT without TLS). For `qnap` and `synology` they are the fixed, public firmware values, so they protect nothing.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| The device does not shut down | the NUT client is not enabled, or points to another IP; try `debug: true` and check the log |
| It does not power on | Wake-on-LAN disabled on the device, wrong MAC, broadcast of another network, aggregated ports (LAG) |
| It shuts down right after powering on | its `.sol` is still there: with `force_shutdown: true` this is intended (switch to ON); with `false`, the real UPS is on battery or not answering |
| Login refused in the log | `custom` client with a user or password different from the list |
