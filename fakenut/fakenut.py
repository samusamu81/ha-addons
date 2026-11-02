#!/usr/bin/env python3
"""FakeNUT: un finto server NUT che risponde a ogni client in base al suo IP,
e un interruttore in Home Assistant per ogni dispositivo dell'elenco.

- Stato dell'interruttore = il dispositivo risponde al ping.
- Spegnere = creare /share/fakenut/<nome>.sol ("stop over lan"): da quel momento
  il server NUT risponde "a batteria e scarica" a quel dispositivo, che si spegne.
- Accendere = cancellare <nome>.sol, poi Wake-on-LAN.

Ogni client chiede l'UPS con il nome che ha configurato (QNAP "qnapups",
Synology "ups", ...): la risposta dipende solo dall'IP. Nessun comando accettato.
Interruttori: MQTT discovery, credenziali prese dal Supervisor.
"""
import asyncio
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

VERSION = "3.0.1"
OPTIONS_FILE = os.environ.get("FAKENUT_OPTIONS", "/data/options.json")
SOL_DIR = os.environ.get("FAKENUT_SOL_DIR", "/share/fakenut")
DEVICES_FILE = os.environ.get("FAKENUT_DEVICES", "/data/devices.json")
NUT_PORT = int(os.environ.get("FAKENUT_PORT", "3493"))
TOPIC = "fakenut"
OFF_AFTER = 3  # ping falliti di fila prima di dire "spento"
OFF_CANCEL = 60  # secondi dopo un OFF in cui un ON lo annulla ancora
# Client con nome dell'UPS, utente e password fissi (non si cambiano dal client).
TYPES = {
    "qnap": {"ups": "qnapups", "user": "admin", "password": "123456"},
    "synology": {"ups": "ups", "user": "monuser", "password": "secret"},
}

OPTS = json.load(open(OPTIONS_FILE))
DEBUG = bool(OPTS.get("debug", False))
LOCK = int(OPTS.get("lock_minutes", 5)) * 60
STATE = threading.Lock()  # ping e MQTT girano in thread diversi


def log(msg):
    print(f"[fakenut] {msg}", flush=True)


class Host:
    def __init__(self, d):
        self.name = d["name"]
        self.ip = d["ip"]
        self.mac = (d.get("mac") or "").strip()
        self.type = d.get("type") or "custom"
        known = TYPES.get(self.type, {})
        self.ups = known.get("ups")
        self.user = known.get("user", d.get("user") or "")
        self.password = known.get("password", d.get("password") or "")
        self.online = None
        self.fails = 0
        self.pending = None  # "ON"/"OFF": comando in corso, finche' il ping non lo conferma
        self.pending_since = 0.0

    @property
    def sol(self):
        return os.path.join(SOL_DIR, f"{self.name}.sol")

    def stop_requested(self):
        return os.path.exists(self.sol)

    def update_pending(self):
        """Chiude il comando in corso se il ping lo conferma o se e' scaduto. True = cambiato."""
        if self.pending is None:
            return False
        done = (self.pending == "ON" and self.online) or (self.pending == "OFF" and self.online is False)
        if done or time.time() - self.pending_since > LOCK:
            if not done:
                log(f"{self.name}: nessuna conferma dal ping dopo {LOCK // 60} minuti, sblocco")
            self.pending = None
            return True
        return False

    def locked(self):
        """Comandi bloccati: subito dopo un ON, dopo il primo minuto da un OFF."""
        self.update_pending()
        if self.pending == "OFF":
            return time.time() - self.pending_since >= OFF_CANCEL
        return self.pending == "ON"


HOSTS = [Host(d) for d in OPTS.get("devices", [])]
BY_NAME = {h.name: h for h in HOSTS}
BY_IP = {h.ip: h for h in HOSTS}
if len(BY_NAME) != len(HOSTS) or len(BY_IP) != len(HOSTS):
    log("ATTENZIONE: nomi o IP ripetuti nell'elenco: vale l'ultimo")
KNOWN_UPS = {t["ups"] for t in TYPES.values()}


# ---------------------------------------------------------------- server NUT

def ups_vars(host):
    """Variabili dell'UPS finto. host=None (chi chiede non e' nell'elenco) = in rete."""
    stop = host is not None and host.stop_requested()
    return {
        "device.mfr": "FakeNUT",
        "device.model": "UPS finto (Home Assistant)",
        "device.type": "ups",
        "driver.name": "fakenut",
        "driver.version": VERSION,
        "ups.mfr": "FakeNUT",
        "ups.model": "UPS finto (Home Assistant)",
        "ups.status": "OB LB" if stop else "OL",
        "battery.charge": "5" if stop else "100",
        "battery.runtime": "60" if stop else "3600",
    }


def resolve(ups, peer):
    """(trovato, dispositivo). Dagli IP dell'elenco vale qualsiasi nome di UPS; da altri IP
    i nomi dell'elenco (per le prove) e quelli dei tipi noti (sempre "in rete")."""
    if peer in BY_IP:
        return True, BY_IP[peer]
    if ups in BY_NAME:
        return True, BY_NAME[ups]
    if ups in KNOWN_UPS:
        return True, None
    return False, None


def split_args(line):
    """Argomenti NUT: separati da spazi, tra virgolette se contengono spazi."""
    args, cur, quoted, esc, started = [], "", False, False, False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            quoted = not quoted
            started = True
        elif ch.isspace() and not quoted:
            if started or cur:
                args.append(cur)
            cur, started = "", False
        else:
            cur += ch
    if started or cur:
        args.append(cur)
    return args


def answer(args, peer, session):
    """Risposta (lista di righe) a un comando NUT. None = chiudere la connessione.
    session: utente e password dati su questa connessione."""
    if not args:
        return ["ERR UNKNOWN-COMMAND"]
    cmd = args[0].upper()
    sub = args[1].upper() if len(args) > 1 else ""

    if cmd == "VER":
        return [f"Network UPS Tools upsd 2.8.2 - fakenut {VERSION}"]
    if cmd == "NETVER":
        return ["1.3"]
    if cmd == "HELP":
        return ["Commands: HELP VER GET LIST SET INSTCMD LOGIN LOGOUT USERNAME PASSWORD STARTTLS"]
    if cmd in ("USERNAME", "PASSWORD") and len(args) >= 2:
        session[cmd] = args[1]
        return ["OK"]
    if cmd == "LOGIN":
        # Si legge anche senza login: il login serve a upsmon per registrarsi come
        # client. Per i custom con utente e password si controllano davvero.
        host = BY_IP.get(peer)
        if host and host.type == "custom" and host.user and (
                session.get("USERNAME") != host.user or session.get("PASSWORD") != host.password):
            log(f"{host.name}: login rifiutato, utente o password diversi da quelli dell'elenco")
            return ["ERR ACCESS-DENIED"]
        return ["OK"]
    if cmd == "LOGOUT":
        return None
    if cmd == "STARTTLS":
        return ["ERR FEATURE-NOT-CONFIGURED"]
    if cmd in ("SET", "INSTCMD", "FSD", "PRIMARY", "MASTER"):
        return ["ERR ACCESS-DENIED"]

    if cmd == "LIST" and sub == "UPS":
        rows = [f'UPS {u} "UPS finto (risposta per IP)"' for u in sorted({h.ups for h in HOSTS if h.ups})]
        rows += [f'UPS {h.name} "UPS finto di {h.name} ({h.ip})"' for h in HOSTS]
        return ["BEGIN LIST UPS", *rows, "END LIST UPS"]

    if cmd in ("LIST", "GET") and len(args) >= 3:
        ups = args[2]
        found, host = resolve(ups, peer)
        if not found:
            return ["ERR UNKNOWN-UPS"]
        values = ups_vars(host)
        if cmd == "LIST" and sub == "VAR":
            rows = [f'VAR {ups} {k} "{v}"' for k, v in values.items()]
            return [f"BEGIN LIST VAR {ups}", *rows, f"END LIST VAR {ups}"]
        if cmd == "LIST" and sub in ("RW", "CMD", "CLIENT"):
            return [f"BEGIN LIST {sub} {ups}", f"END LIST {sub} {ups}"]
        if cmd == "LIST" and sub in ("ENUM", "RANGE") and len(args) >= 4:
            return [f"BEGIN LIST {sub} {ups} {args[3]}", f"END LIST {sub} {ups} {args[3]}"]
        if cmd == "GET" and sub == "UPSDESC":
            return [f'UPSDESC {ups} "UPS finto (Home Assistant)"']
        if cmd == "GET" and sub == "NUMLOGINS":
            return [f"NUMLOGINS {ups} 0"]
        if cmd == "GET" and sub in ("VAR", "TYPE", "DESC") and len(args) >= 4:
            var = args[3]
            if var not in values:
                return ["ERR VAR-NOT-SUPPORTED"]
            if sub == "VAR":
                return [f'VAR {ups} {var} "{values[var]}"']
            if sub == "TYPE":
                return [f"TYPE {ups} {var} NUMBER" if values[var].isdigit() else f"TYPE {ups} {var} STRING:64"]
            return [f'DESC {ups} {var} "Unavailable"']
        if cmd == "GET" and sub == "CMDDESC":
            return ["ERR CMD-NOT-SUPPORTED"]

    if cmd in ("LIST", "GET"):
        return ["ERR INVALID-ARGUMENT"]
    return ["ERR UNKNOWN-COMMAND"]


# Contro chi apre troppe connessioni o le lascia ferme. Un client vero (upsmon)
# ne tiene aperta una e chiede lo stato ogni pochi secondi.
MAX_CONN_PER_IP = 10
MAX_CONN = 100
IDLE_TIMEOUT = 300  # secondi senza comandi
connections = {}


async def nut_client(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    if peer.startswith("::ffff:"):
        peer = peer[7:]
    if connections.get(peer, 0) >= MAX_CONN_PER_IP or sum(connections.values()) >= MAX_CONN:
        log(f"NUT {peer}: troppe connessioni, rifiutata")
        writer.close()
        return
    connections[peer] = connections.get(peer, 0) + 1
    session = {}
    try:
        while True:
            raw = await asyncio.wait_for(reader.readline(), IDLE_TIMEOUT)
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            reply = answer(split_args(line), peer, session)
            if DEBUG:
                shown = "PASSWORD ***" if line.upper().startswith("PASSWORD") else line
                log(f"NUT {peer}: {shown} -> {reply[0] if reply else 'chiusa'}")
            if reply is None:
                writer.write(b"OK Goodbye\n")
                await writer.drain()
                break
            writer.write(("\n".join(reply) + "\n").encode())
            await writer.drain()
    except (ConnectionError, asyncio.LimitOverrunError, ValueError, asyncio.TimeoutError):
        pass
    finally:
        connections[peer] -= 1
        if not connections[peer]:
            del connections[peer]
        writer.close()


# ---------------------------------------------------------------- comandi

def wake(host):
    if not host.mac:
        log(f"{host.name}: MAC mancante, niente Wake-on-LAN")
        return
    mac = bytes.fromhex(host.mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(3):
            s.sendto(packet, (OPTS.get("broadcast", "255.255.255.255"), 9))
    log(f"{host.name}: Wake-on-LAN inviato a {host.mac}")


def switch_off(host):
    with open(host.sol, "w") as f:
        f.write(f"spegnimento richiesto da Home Assistant il {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
    log(f"{host.name}: creato {host.sol}, ora legge 'a batteria' e si spegne")


def switch_on(host):
    # Prima si toglie il .sol: chi si accende e legge "a batteria" si rispegne.
    if host.stop_requested():
        os.remove(host.sol)
        log(f"{host.name}: cancellato {host.sol}, ora legge 'in rete'")
    wake(host)


# ---------------------------------------------------------------- MQTT

client = None


def publish_state(host):
    if client is None:
        return
    if host.online is not None:
        client.publish(f"{TOPIC}/{host.name}/state", "ON" if host.online else "OFF", retain=True)
    client.publish(f"{TOPIC}/{host.name}/in_corso", "ON" if host.pending else "OFF", retain=True)
    client.publish(f"{TOPIC}/{host.name}/attributes", json.dumps({
        "ip": host.ip,
        "mac": host.mac,
        "tipo": host.type,
        "spegnimento_richiesto": host.stop_requested(),
        "comando_in_corso": host.pending,
        "bloccato": host.locked(),
    }), retain=True)


def device(host):
    # Stesso identificativo in QLog2HA: in HA un solo dispositivo per nome.
    return {
        "identifiers": [f"host_{host.name}"],
        "name": host.name,
        "model": f"{host.type} {host.ip}",
    }


def discovery(host):
    return json.dumps({
        "name": None,
        "unique_id": f"fakenut_{host.name}",
        "command_topic": f"{TOPIC}/{host.name}/set",
        "state_topic": f"{TOPIC}/{host.name}/state",
        "json_attributes_topic": f"{TOPIC}/{host.name}/attributes",
        "availability_topic": f"{TOPIC}/status",
        "icon": "mdi:nas",
        "device": device(host),
    })


def discovery_in_corso(host):
    # Acceso = comando in esecuzione, in attesa che il ping lo confermi.
    return json.dumps({
        "name": "In corso",
        "unique_id": f"fakenut_{host.name}_in_corso",
        "state_topic": f"{TOPIC}/{host.name}/in_corso",
        "availability_topic": f"{TOPIC}/status",
        "device_class": "running",
        "icon": "mdi:timer-sand",
        "device": device(host),
    })


def remove_old_switches():
    """Toglie da HA gli interruttori dei nomi tolti dall'elenco."""
    try:
        old = set(json.load(open(DEVICES_FILE)))
    except (OSError, ValueError):
        old = set()
    for name in old - set(BY_NAME):
        client.publish(f"homeassistant/switch/fakenut_{name}/config", "", retain=True)
        client.publish(f"homeassistant/binary_sensor/fakenut_{name}_in_corso/config", "", retain=True)
        for t in ("state", "in_corso", "attributes"):
            client.publish(f"{TOPIC}/{name}/{t}", "", retain=True)
        log(f"{name}: tolto dall'elenco, interruttore rimosso")
    with open(DEVICES_FILE, "w") as f:
        json.dump(sorted(BY_NAME), f)


def announce():
    for host in HOSTS:
        client.publish(f"homeassistant/switch/fakenut_{host.name}/config", discovery(host), retain=True)
        client.publish(f"homeassistant/binary_sensor/fakenut_{host.name}_in_corso/config",
                       discovery_in_corso(host), retain=True)
    client.publish(f"{TOPIC}/status", "online", retain=True)
    for host in HOSTS:
        publish_state(host)


def on_connect(c, userdata, flags, rc, *rest):
    if getattr(rc, "is_failure", rc != 0):
        log(f"MQTT: connessione rifiutata ({rc})")
        return
    log("MQTT connesso")
    c.subscribe(f"{TOPIC}/+/set")
    c.subscribe("homeassistant/status")
    remove_old_switches()
    announce()


def on_message(c, userdata, msg):
    payload = msg.payload.decode(errors="replace").strip()
    if msg.topic == "homeassistant/status":
        if payload == "online":
            announce()  # HA riavviato: ripubblicare
        return
    if msg.retain:
        # Comando rimasto nel broker (pubblicato con retain da qualcun altro): a ogni
        # riconnessione rifarebbe WOL o spegnimento. Si ignora e si cancella.
        if payload:
            log(f"{msg.topic}: comando memorizzato '{payload}' ignorato e cancellato")
            c.publish(msg.topic, "", retain=True)
        return
    host = BY_NAME.get(msg.topic.split("/")[1])
    if host is None or payload not in ("ON", "OFF"):
        return
    with STATE:
        if host.locked():
            log(f"{host.name}: comando {payload} ignorato, {host.pending} in corso")
        elif payload == host.pending:
            log(f"{host.name}: comando {payload} ignorato, gia' in corso")
        else:
            if payload == "OFF":
                switch_off(host)
            else:
                switch_on(host)
            host.pending, host.pending_since = payload, time.time()
            host.update_pending()  # gia' nello stato giusto: niente blocco
        publish_state(host)


def container_env(name):
    value = os.environ.get(name)
    if not value:  # sotto s6 l'ambiente del container sta in un file
        try:
            value = open(f"/run/s6/container_environment/{name}").read().strip()
        except OSError:
            pass
    return value


def supervisor_token():
    return container_env("SUPERVISOR_TOKEN")


def set_timezone():
    """Fuso orario di HA (es. Europe/Rome): senza, il container scrive gli orari in UTC."""
    tz = container_env("TZ")
    if not tz and supervisor_token():
        try:
            req = urllib.request.Request("http://supervisor/info",
                                         headers={"Authorization": f"Bearer {supervisor_token()}"})
            tz = json.load(urllib.request.urlopen(req, timeout=10))["data"]["timezone"]
        except Exception as e:  # noqa: BLE001
            log(f"fuso orario non letto dal Supervisor ({e}), orari in UTC")
    if tz:
        os.environ["TZ"] = tz
        time.tzset()
        log(f"fuso orario {tz}")


def mqtt_start():
    global client
    token = supervisor_token()
    if not token:
        log("MQTT: niente SUPERVISOR_TOKEN, interruttori non disponibili")
        return
    try:
        req = urllib.request.Request("http://supervisor/services/mqtt",
                                     headers={"Authorization": f"Bearer {token}"})
        cfg = json.load(urllib.request.urlopen(req, timeout=10))["data"]
    except Exception as e:  # noqa: BLE001
        log(f"MQTT: broker non trovato dal Supervisor ({e}), interruttori non disponibili")
        return
    host = cfg["host"]
    try:
        socket.gethostbyname(host)
    except OSError:
        log(f"MQTT: {host} non si risolve, uso 127.0.0.1")
        host = "127.0.0.1"
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fakenut")
    except AttributeError:
        c = mqtt.Client(client_id="fakenut")
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], cfg.get("password"))
    c.will_set(f"{TOPIC}/status", "offline", retain=True)
    c.on_connect = on_connect
    c.on_message = on_message
    client = c
    c.connect_async(host, int(cfg.get("port", 1883)))
    c.loop_start()


# ---------------------------------------------------------------- ping

def ping(ip):
    return subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def ping_loop():
    interval = int(OPTS.get("ping_interval", 10))
    while True:
        for host in HOSTS:
            up = ping(host.ip)
            with STATE:
                if up:
                    host.fails = 0
                    new = True
                else:
                    host.fails += 1
                    new = host.online if host.fails < OFF_AFTER and host.online is not None else False
                changed = new != host.online
                if changed:
                    host.online = new
                    log(f"{host.name} ({host.ip}): {'acceso' if new else 'spento'}")
                busy = host.pending is not None
                if host.update_pending() or changed or busy:
                    publish_state(host)
        time.sleep(interval)


# ---------------------------------------------------------------- avvio

async def main():
    set_timezone()
    os.makedirs(SOL_DIR, exist_ok=True)
    for host in HOSTS:
        kind = host.type + (f", UPS {host.ups}" if host.ups else "")
        log(f"{host.name}: {host.ip} ({kind}), MAC {host.mac or '-'}, "
            f"{'SPEGNIMENTO RICHIESTO (' + host.sol + ')' if host.stop_requested() else 'in rete'}")
    mqtt_start()
    threading.Thread(target=ping_loop, daemon=True).start()
    server = await asyncio.start_server(nut_client, "0.0.0.0", NUT_PORT)
    log(f"server NUT sulla porta {NUT_PORT}: qualsiasi nome di UPS, risposta in base all'IP")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
