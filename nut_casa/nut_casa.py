#!/usr/bin/env python3
"""NUT casa: un interruttore in Home Assistant per ogni NAS dell'elenco.

- Stato dell'interruttore = il NAS risponde al ping.
- Spegnere = creare /share/nut/<nome>.sol ("stop over lan"): da quel momento il
  server NUT risponde "a batteria e scarica" a quel NAS, che si spegne.
- Accendere = cancellare <nome>.sol, poi Wake-on-LAN.

Server NUT: i NAS QNAP chiedono sempre l'UPS "qnapups" (nome fisso in QTS).
La risposta dipende dall'IP di chi chiede. Nessun comando e' accettato.
Interruttori: MQTT discovery, credenziali prese dal Supervisor.

Syslog (porta 1514, UDP e TCP): i NAS mandano i loro eventi (QuLog Center ->
Mittente log -> Syslog). Accettati solo dagli IP dell'elenco; per ogni NAS un
sensore "Ultimo evento" e un'entita' evento in HA, e una riga nel registro.
"""
import asyncio
import json
import logging
import logging.handlers
import os
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

VERSION = "2.4.2"
OPTIONS_FILE = os.environ.get("NUT_CASA_OPTIONS", "/data/options.json")
SOL_DIR = os.environ.get("NUT_CASA_SOL_DIR", "/share/nut")
DEVICES_FILE = os.environ.get("NUT_CASA_DEVICES", "/data/devices.json")
NUT_PORT = int(os.environ.get("NUT_CASA_PORT", "3493"))
SYSLOG_PORT = int(os.environ.get("NUT_CASA_SYSLOG_PORT", "1514"))
QNAP_UPS = "qnapups"
TOPIC = "nut_casa"
OFF_AFTER = 3  # ping falliti di fila prima di dire "spento"
OFF_CANCEL = 60  # secondi dopo un OFF in cui un ON lo annulla ancora

OPTS = json.load(open(OPTIONS_FILE))
DEBUG = bool(OPTS.get("debug", False))
LOCK = int(OPTS.get("lock_minutes", 5)) * 60
STATE = threading.Lock()  # ping e MQTT girano in thread diversi


def log(msg):
    print(f"[nut_casa] {msg}", flush=True)


class Nas:
    def __init__(self, d):
        self.name = d["name"]
        self.ip = d["ip"]
        self.mac = (d.get("mac") or "").strip()
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


NAS = [Nas(d) for d in OPTS.get("devices", [])]
BY_NAME = {n.name: n for n in NAS}
BY_IP = {n.ip: n for n in NAS}
if len(BY_NAME) != len(NAS) or len(BY_IP) != len(NAS):
    log("ATTENZIONE: nomi o IP ripetuti nell'elenco: vale l'ultimo")


# ---------------------------------------------------------------- server NUT

def ups_vars(nas):
    """Variabili dell'UPS finto. nas=None (chi chiede non e' nell'elenco) = in rete."""
    stop = nas is not None and nas.stop_requested()
    return {
        "device.mfr": "Casa",
        "device.model": "UPS finto (Home Assistant)",
        "device.type": "ups",
        "driver.name": "nut_casa",
        "driver.version": VERSION,
        "ups.mfr": "Casa",
        "ups.model": "UPS finto (Home Assistant)",
        "ups.status": "OB LB" if stop else "OL",
        "battery.charge": "5" if stop else "100",
        "battery.runtime": "60" if stop else "3600",
    }


def resolve(ups, peer):
    """(trovato, nas). "qnapups" dipende dall'IP; il nome di un NAS vale da ovunque (prove)."""
    if ups == QNAP_UPS:
        return True, BY_IP.get(peer)
    if ups in BY_NAME:
        return True, BY_NAME[ups]
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


def answer(args, peer):
    """Risposta (lista di righe) a un comando NUT. None = chiudere la connessione."""
    if not args:
        return ["ERR UNKNOWN-COMMAND"]
    cmd = args[0].upper()
    sub = args[1].upper() if len(args) > 1 else ""

    if cmd == "VER":
        return [f"Network UPS Tools upsd 2.8.2 - nut_casa {VERSION}"]
    if cmd == "NETVER":
        return ["1.3"]
    if cmd == "HELP":
        return ["Commands: HELP VER GET LIST SET INSTCMD LOGIN LOGOUT USERNAME PASSWORD STARTTLS"]
    if cmd in ("USERNAME", "PASSWORD", "LOGIN"):
        return ["OK"]  # chiunque puo' solo leggere: il login non cambia niente
    if cmd == "LOGOUT":
        return None
    if cmd == "STARTTLS":
        return ["ERR FEATURE-NOT-CONFIGURED"]
    if cmd in ("SET", "INSTCMD", "FSD", "PRIMARY", "MASTER"):
        return ["ERR ACCESS-DENIED"]

    if cmd == "LIST" and sub == "UPS":
        rows = [f'UPS {QNAP_UPS} "UPS finto per i NAS (risposta per IP)"']
        rows += [f'UPS {n.name} "UPS finto di {n.name} ({n.ip})"' for n in NAS]
        return ["BEGIN LIST UPS", *rows, "END LIST UPS"]

    if cmd in ("LIST", "GET") and len(args) >= 3:
        ups = args[2]
        found, nas = resolve(ups, peer)
        if not found:
            return ["ERR UNKNOWN-UPS"]
        values = ups_vars(nas)
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


async def nut_client(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    if peer.startswith("::ffff:"):
        peer = peer[7:]
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            line = raw.decode(errors="replace").strip()
            reply = answer(split_args(line), peer)
            if DEBUG:
                log(f"NUT {peer}: {line} -> {reply[0] if reply else 'chiusa'}")
            if reply is None:
                writer.write(b"OK Goodbye\n")
                await writer.drain()
                break
            writer.write(("\n".join(reply) + "\n").encode())
            await writer.drain()
    except (ConnectionError, asyncio.LimitOverrunError, ValueError):
        pass
    finally:
        writer.close()


# ---------------------------------------------------------------- syslog

SEVERITY = ["emergenza", "allarme", "critico", "errore", "avviso", "nota", "info", "debug"]
PRI = re.compile(r"^(?:\d+ )?<(\d{1,3})>")  # anche col conteggio dei byte del TCP
QNAP_LOG = re.compile(r"(conn log|event log): (.+)", re.I)
FIELD = re.compile(r"^([A-Za-z][A-Za-z ]{0,29}): (.*)$", re.S)
unknown_senders = set()


def parse_syslog(line):
    """Messaggio syslog RFC 3164 di QTS -> dizionario. I campi QNAP sono "Chiave: valore, ..."."""
    m = PRI.match(line)
    sev = int(m.group(1)) % 8 if m else 6
    body = line[m.end():] if m else line
    ev = {
        "livello": "errore" if sev <= 3 else "avviso" if sev == 4 else "info",
        "severita": SEVERITY[sev],
        "ricevuto": time.strftime("%d/%m/%Y %H:%M:%S"),
    }
    q = QNAP_LOG.search(body)
    if q:
        ev["tipo_log"] = q.group(1).lower()
        last = None
        for part in q.group(2).split(", "):
            f = FIELD.match(part)
            if f and last != "content":  # il contenuto e' l'ultimo campo: dopo, tutto e' contenuto
                last = f.group(1).strip().lower().replace(" ", "_")
                ev[last] = f.group(2).strip()
            elif last:  # una virgola dentro il valore
                ev[last] += ", " + part
        ev.setdefault("content", q.group(2).strip())  # conn log: niente campo Content
    ev.setdefault("content", body.strip())
    ev["raw"] = line[:1000]
    return ev


def on_syslog(line, peer):
    line = line.strip()
    if not line:
        return
    nas = BY_IP.get(peer)
    if nas is None:
        if peer not in unknown_senders:
            unknown_senders.add(peer)
            log(f"syslog da {peer} ignorato: non e' nell'elenco dei NAS")
        return
    ev = parse_syslog(line)
    where = " / ".join(x for x in (ev.get("application"), ev.get("category")) if x)
    text = f"[{ev['livello']}] {where + ': ' if where else ''}{ev['content']}"
    # Accessi ai file ("conn log"): uno per file, migliaia al giorno. Solo nel file
    # dello storico, non in HA, dove coprirebbero gli eventi veri.
    to_ha = ev.get("tipo_log") != "conn log"
    if to_ha:
        log(f"{nas.name} {text}")
        publish_syslog(nas, ev)
    history.put((nas, ev, text, to_ha))


# Storico: una riga nel Registro di HA (logbook.log) e nel file del giorno
# /share/nut/syslog/<nome>.log, tenuto SYSLOG_DAYS giorni. In un thread a parte:
# le chiamate HTTP non devono fermare il server NUT.
SYSLOG_DIR = os.path.join(SOL_DIR, "syslog")
SYSLOG_DAYS = int(OPTS.get("syslog_days", 90))
history = queue.Queue()


def history_loop():
    os.makedirs(SYSLOG_DIR, exist_ok=True)
    files = {}
    for nas in NAS:
        h = logging.handlers.TimedRotatingFileHandler(
            os.path.join(SYSLOG_DIR, f"{nas.name}.log"), when="midnight", backupCount=SYSLOG_DAYS,
            encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%d/%m/%Y %H:%M:%S"))
        files[nas.name] = logging.getLogger(f"syslog.{nas.name}")
        files[nas.name].propagate = False
        files[nas.name].addHandler(h)
        files[nas.name].setLevel(logging.INFO)
    while True:
        nas, ev, text, to_ha = history.get()
        files[nas.name].info(f"{text} | {ev['raw']}")
        token = supervisor_token()
        if not to_ha or not token:
            continue
        try:
            req = urllib.request.Request(
                "http://supervisor/core/api/services/logbook/log",
                data=json.dumps({"name": f"NAS {nas.name}", "message": text[:500]}).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as e:  # noqa: BLE001
            log(f"registro di HA non scritto ({e})")


class SyslogUDP(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        for line in data.decode(errors="replace").splitlines():
            on_syslog(line, addr[0])


async def syslog_tcp_client(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    try:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            on_syslog(raw.decode(errors="replace"), peer)
    except (ConnectionError, asyncio.LimitOverrunError, ValueError):
        pass
    finally:
        writer.close()


# ---------------------------------------------------------------- comandi

def wake(nas):
    if not nas.mac:
        log(f"{nas.name}: MAC mancante, niente Wake-on-LAN")
        return
    mac = bytes.fromhex(nas.mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(3):
            s.sendto(packet, (OPTS.get("broadcast", "255.255.255.255"), 9))
    log(f"{nas.name}: Wake-on-LAN inviato a {nas.mac}")


def switch_off(nas):
    with open(nas.sol, "w") as f:
        f.write(f"spegnimento richiesto da Home Assistant il {time.strftime('%d/%m/%Y %H:%M:%S')}\n")
    log(f"{nas.name}: creato {nas.sol}, il NAS ora legge 'a batteria' e si spegne")


def switch_on(nas):
    # Prima si toglie il .sol: un NAS che si accende e legge "a batteria" si rispegne.
    if nas.stop_requested():
        os.remove(nas.sol)
        log(f"{nas.name}: cancellato {nas.sol}, il NAS ora legge 'in rete'")
    wake(nas)


# ---------------------------------------------------------------- MQTT

client = None


def publish_state(nas):
    if client is None:
        return
    if nas.online is not None:
        client.publish(f"{TOPIC}/{nas.name}/state", "ON" if nas.online else "OFF", retain=True)
    client.publish(f"{TOPIC}/{nas.name}/in_corso", "ON" if nas.pending else "OFF", retain=True)
    client.publish(f"{TOPIC}/{nas.name}/attributes", json.dumps({
        "ip": nas.ip,
        "mac": nas.mac,
        "spegnimento_richiesto": nas.stop_requested(),
        "comando_in_corso": nas.pending,
        "bloccato": nas.locked(),
    }), retain=True)


def device(nas):
    return {
        "identifiers": [f"nut_casa_{nas.name}"],
        "name": nas.name,
        "manufacturer": "Casa",
        "model": f"NAS {nas.ip} (NUT casa)",
        "sw_version": VERSION,
    }


def discovery(nas):
    return json.dumps({
        "name": None,
        "unique_id": f"nut_casa_{nas.name}",
        "command_topic": f"{TOPIC}/{nas.name}/set",
        "state_topic": f"{TOPIC}/{nas.name}/state",
        "json_attributes_topic": f"{TOPIC}/{nas.name}/attributes",
        "availability_topic": f"{TOPIC}/status",
        "icon": "mdi:nas",
        "device": device(nas),
    })


def discovery_in_corso(nas):
    # Acceso = comando in esecuzione, in attesa che il ping lo confermi.
    return json.dumps({
        "name": "In corso",
        "unique_id": f"nut_casa_{nas.name}_in_corso",
        "state_topic": f"{TOPIC}/{nas.name}/in_corso",
        "availability_topic": f"{TOPIC}/status",
        "device_class": "running",
        "icon": "mdi:timer-sand",
        "device": device(nas),
    })


def discovery_syslog(nas):
    # Ultimo messaggio syslog del NAS; tutti i campi negli attributi.
    return json.dumps({
        "name": "Ultimo evento",
        "unique_id": f"nut_casa_{nas.name}_syslog",
        "state_topic": f"{TOPIC}/{nas.name}/syslog",
        "value_template": "{{ value_json.content[:255] }}",
        "json_attributes_topic": f"{TOPIC}/{nas.name}/syslog",
        "icon": "mdi:text-box-outline",
        "device": device(nas),
    })


def discovery_syslog_event(nas):
    # Un evento per ogni messaggio, per le automazioni (tipo = livello).
    return json.dumps({
        "name": "Evento",
        "unique_id": f"nut_casa_{nas.name}_syslog_evento",
        "state_topic": f"{TOPIC}/{nas.name}/syslog_evento",
        "event_types": ["info", "avviso", "errore"],
        "icon": "mdi:bell-outline",
        "device": device(nas),
    })


def publish_syslog(nas, ev):
    if client is None:
        return
    client.publish(f"{TOPIC}/{nas.name}/syslog", json.dumps(ev), retain=True)
    client.publish(f"{TOPIC}/{nas.name}/syslog_evento", json.dumps({"event_type": ev["livello"], **ev}))


def remove_old_switches():
    """Toglie da HA gli interruttori dei nomi tolti dall'elenco."""
    try:
        old = set(json.load(open(DEVICES_FILE)))
    except (OSError, ValueError):
        old = set()
    for name in old - set(BY_NAME):
        client.publish(f"homeassistant/switch/nut_casa_{name}/config", "", retain=True)
        client.publish(f"homeassistant/binary_sensor/nut_casa_{name}_in_corso/config", "", retain=True)
        client.publish(f"homeassistant/sensor/nut_casa_{name}_syslog/config", "", retain=True)
        client.publish(f"homeassistant/event/nut_casa_{name}_syslog/config", "", retain=True)
        for t in ("state", "in_corso", "attributes", "syslog"):
            client.publish(f"{TOPIC}/{name}/{t}", "", retain=True)
        log(f"{name}: tolto dall'elenco, interruttore rimosso")
    with open(DEVICES_FILE, "w") as f:
        json.dump(sorted(BY_NAME), f)


def announce():
    for nas in NAS:
        client.publish(f"homeassistant/switch/nut_casa_{nas.name}/config", discovery(nas), retain=True)
        client.publish(f"homeassistant/binary_sensor/nut_casa_{nas.name}_in_corso/config",
                       discovery_in_corso(nas), retain=True)
        client.publish(f"homeassistant/sensor/nut_casa_{nas.name}_syslog/config",
                       discovery_syslog(nas), retain=True)
        client.publish(f"homeassistant/event/nut_casa_{nas.name}_syslog/config",
                       discovery_syslog_event(nas), retain=True)
    client.publish(f"{TOPIC}/status", "online", retain=True)
    for nas in NAS:
        publish_state(nas)


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
    name = msg.topic.split("/")[1]
    nas = BY_NAME.get(name)
    if nas is None or payload not in ("ON", "OFF"):
        return
    with STATE:
        if nas.locked():
            log(f"{nas.name}: comando {payload} ignorato, {nas.pending} in corso")
        elif payload == nas.pending:
            log(f"{nas.name}: comando {payload} ignorato, gia' in corso")
        else:
            if payload == "OFF":
                switch_off(nas)
            else:
                switch_on(nas)
            nas.pending, nas.pending_since = payload, time.time()
            nas.update_pending()  # gia' nello stato giusto: niente blocco
        publish_state(nas)


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
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="nut_casa")
    except AttributeError:
        c = mqtt.Client(client_id="nut_casa")
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
        for nas in NAS:
            up = ping(nas.ip)
            with STATE:
                if up:
                    nas.fails = 0
                    new = True
                else:
                    nas.fails += 1
                    new = nas.online if nas.fails < OFF_AFTER and nas.online is not None else False
                changed = new != nas.online
                if changed:
                    nas.online = new
                    log(f"{nas.name} ({nas.ip}): {'acceso' if new else 'spento'}")
                busy = nas.pending is not None
                if nas.update_pending() or changed or busy:
                    publish_state(nas)
        time.sleep(interval)


# ---------------------------------------------------------------- avvio

async def main():
    set_timezone()
    os.makedirs(SOL_DIR, exist_ok=True)
    for nas in NAS:
        log(f"{nas.name}: {nas.ip}, MAC {nas.mac or '-'}, "
            f"{'SPEGNIMENTO RICHIESTO (' + nas.sol + ')' if nas.stop_requested() else 'in rete'}")
    mqtt_start()
    threading.Thread(target=ping_loop, daemon=True).start()
    threading.Thread(target=history_loop, daemon=True).start()
    server = await asyncio.start_server(nut_client, "0.0.0.0", NUT_PORT)
    log(f"server NUT sulla porta {NUT_PORT}, UPS '{QNAP_UPS}' risponde in base all'IP")
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(SyslogUDP, local_addr=("0.0.0.0", SYSLOG_PORT))
    syslog_tcp = await asyncio.start_server(syslog_tcp_client, "0.0.0.0", SYSLOG_PORT)
    log(f"syslog sulla porta {SYSLOG_PORT} (UDP e TCP), solo dai NAS dell'elenco")
    async with server, syslog_tcp:
        await asyncio.gather(server.serve_forever(), syslog_tcp.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
