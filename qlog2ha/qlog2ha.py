#!/usr/bin/env python3
"""QLog2HA: gli eventi dei NAS QNAP (syslog di QuLog Center) in Home Assistant.

- Ascolto syslog RFC 3164 su UDP e TCP, solo dagli IP dell'elenco.
- Per ogni NAS: sensore "Ultimo evento" ed entita' evento (info/avviso/errore), via
  MQTT discovery; una riga nel Registro di HA; storico su file, un file al giorno.
- Accessi ai file ("conn log"): solo nel file, non in HA.
"""
import asyncio
import json
import logging
import logging.handlers
import os
import queue
import re
import socket
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

VERSION = "1.0.1"
OPTIONS_FILE = os.environ.get("QLOG2HA_OPTIONS", "/data/options.json")
LOG_DIR = os.environ.get("QLOG2HA_DIR", "/share/qlog2ha")
DEVICES_FILE = os.environ.get("QLOG2HA_DEVICES", "/data/devices.json")
TOPIC = "qlog2ha"

OPTS = json.load(open(OPTIONS_FILE))
PORT = int(os.environ.get("QLOG2HA_PORT", OPTS.get("port", 1514)))
DAYS = int(OPTS.get("days", 90))


def log(msg):
    print(f"[qlog2ha] {msg}", flush=True)


class Nas:
    def __init__(self, d):
        self.name = d["name"]
        self.ip = d["ip"]


NAS = [Nas(d) for d in OPTS.get("devices", [])]
BY_NAME = {n.name: n for n in NAS}
BY_IP = {n.ip: n for n in NAS}
if len(BY_NAME) != len(NAS) or len(BY_IP) != len(NAS):
    log("ATTENZIONE: nomi o IP ripetuti nell'elenco: vale l'ultimo")


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


# Tetto agli eventi mandati in HA: un NAS impazzito (o qualcuno che falsifica il
# suo IP in UDP) non deve riempire il Registro e il database. Oltre il tetto gli
# eventi vanno solo nel file.
MAX_PER_MINUTE = 30
rate = {}  # nome -> [inizio del minuto, eventi, avvisato]


def within_rate(nas):
    now = time.monotonic()
    r = rate.setdefault(nas.name, [now, 0, False])
    if now - r[0] >= 60:
        r[:] = [now, 0, False]
    r[1] += 1
    if r[1] <= MAX_PER_MINUTE:
        return True
    if not r[2]:
        r[2] = True
        log(f"{nas.name}: piu' di {MAX_PER_MINUTE} eventi al minuto, i successivi solo nel file")
    return False


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
    to_ha = ev.get("tipo_log") != "conn log" and within_rate(nas)
    if to_ha:
        log(f"{nas.name} {text}")
        publish_event(nas, ev)
    history.put((nas, ev, text, to_ha))


# Storico: una riga nel Registro di HA (logbook.log) e nel file del giorno
# <LOG_DIR>/<nome>.log, tenuto DAYS giorni. In un thread a parte: le chiamate
# HTTP non devono fermare la ricezione.
history = queue.Queue()


def history_loop():
    os.makedirs(LOG_DIR, exist_ok=True)
    files = {}
    for nas in NAS:
        h = logging.handlers.TimedRotatingFileHandler(
            os.path.join(LOG_DIR, f"{nas.name}.log"), when="midnight", backupCount=DAYS, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%d/%m/%Y %H:%M:%S"))
        files[nas.name] = logging.getLogger(f"qlog2ha.{nas.name}")
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


MAX_CONN_PER_IP = 5  # QTS ne usa una sola
IDLE_TIMEOUT = 3600  # secondi senza messaggi
connections = {}


async def syslog_tcp_client(reader, writer):
    peer = writer.get_extra_info("peername")[0]
    if peer.startswith("::ffff:"):
        peer = peer[7:]
    if peer not in BY_IP or connections.get(peer, 0) >= MAX_CONN_PER_IP:
        # in TCP l'IP non si falsifica: chi non e' in elenco non entra proprio
        if peer not in unknown_senders:
            unknown_senders.add(peer)
            log(f"syslog TCP da {peer} rifiutato")
        writer.close()
        return
    connections[peer] = connections.get(peer, 0) + 1
    try:
        while True:
            raw = await asyncio.wait_for(reader.readline(), IDLE_TIMEOUT)
            if not raw:
                break
            on_syslog(raw.decode(errors="replace"), peer)
    except (ConnectionError, asyncio.LimitOverrunError, ValueError, asyncio.TimeoutError):
        pass
    finally:
        connections[peer] -= 1
        if not connections[peer]:
            del connections[peer]
        writer.close()


# ---------------------------------------------------------------- MQTT

client = None


def device(nas):
    # Stesso identificativo in FakeNUT: in HA un solo dispositivo per nome.
    return {
        "identifiers": [f"host_{nas.name}"],
        "name": nas.name,
    }


def discovery_sensor(nas):
    # Ultimo messaggio syslog del NAS; tutti i campi negli attributi.
    return json.dumps({
        "name": "Ultimo evento",
        "unique_id": f"qlog2ha_{nas.name}_ultimo_evento",
        "state_topic": f"{TOPIC}/{nas.name}/ultimo",
        "value_template": "{{ value_json.content[:255] }}",
        "json_attributes_topic": f"{TOPIC}/{nas.name}/ultimo",
        "availability_topic": f"{TOPIC}/status",
        "icon": "mdi:text-box-outline",
        "device": device(nas),
    })


def discovery_event(nas):
    # Un evento per ogni messaggio, per le automazioni (tipo = livello).
    return json.dumps({
        "name": "Evento",
        "unique_id": f"qlog2ha_{nas.name}_evento",
        "state_topic": f"{TOPIC}/{nas.name}/evento",
        "availability_topic": f"{TOPIC}/status",
        "event_types": ["info", "avviso", "errore"],
        "icon": "mdi:bell-outline",
        "device": device(nas),
    })


def publish_event(nas, ev):
    if client is None:
        return
    client.publish(f"{TOPIC}/{nas.name}/ultimo", json.dumps(ev), retain=True)
    client.publish(f"{TOPIC}/{nas.name}/evento", json.dumps({"event_type": ev["livello"], **ev}))


def remove_old():
    """Toglie da HA le entita' dei nomi tolti dall'elenco."""
    try:
        old = set(json.load(open(DEVICES_FILE)))
    except (OSError, ValueError):
        old = set()
    for name in old - set(BY_NAME):
        client.publish(f"homeassistant/sensor/qlog2ha_{name}_ultimo_evento/config", "", retain=True)
        client.publish(f"homeassistant/event/qlog2ha_{name}_evento/config", "", retain=True)
        client.publish(f"{TOPIC}/{name}/ultimo", "", retain=True)
        log(f"{name}: tolto dall'elenco, entita' rimosse")
    with open(DEVICES_FILE, "w") as f:
        json.dump(sorted(BY_NAME), f)


def announce():
    for nas in NAS:
        client.publish(f"homeassistant/sensor/qlog2ha_{nas.name}_ultimo_evento/config",
                       discovery_sensor(nas), retain=True)
        client.publish(f"homeassistant/event/qlog2ha_{nas.name}_evento/config",
                       discovery_event(nas), retain=True)
    client.publish(f"{TOPIC}/status", "online", retain=True)


def on_connect(c, userdata, flags, rc, *rest):
    if getattr(rc, "is_failure", rc != 0):
        log(f"MQTT: connessione rifiutata ({rc})")
        return
    log("MQTT connesso")
    c.subscribe("homeassistant/status")
    remove_old()
    announce()


def on_message(c, userdata, msg):
    if msg.topic == "homeassistant/status" and msg.payload.decode(errors="replace").strip() == "online":
        announce()  # HA riavviato: ripubblicare


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
        log("MQTT: niente SUPERVISOR_TOKEN, entita' non disponibili")
        return
    try:
        req = urllib.request.Request("http://supervisor/services/mqtt",
                                     headers={"Authorization": f"Bearer {token}"})
        cfg = json.load(urllib.request.urlopen(req, timeout=10))["data"]
    except Exception as e:  # noqa: BLE001
        log(f"MQTT: broker non trovato dal Supervisor ({e}), entita' non disponibili")
        return
    host = cfg["host"]
    try:
        socket.gethostbyname(host)
    except OSError:
        log(f"MQTT: {host} non si risolve, uso 127.0.0.1")
        host = "127.0.0.1"
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="qlog2ha")
    except AttributeError:
        c = mqtt.Client(client_id="qlog2ha")
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], cfg.get("password"))
    c.will_set(f"{TOPIC}/status", "offline", retain=True)
    c.on_connect = on_connect
    c.on_message = on_message
    client = c
    c.connect_async(host, int(cfg.get("port", 1883)))
    c.loop_start()


# ---------------------------------------------------------------- avvio

async def main():
    set_timezone()
    for nas in NAS:
        log(f"{nas.name}: {nas.ip}")
    mqtt_start()
    threading.Thread(target=history_loop, daemon=True).start()
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(SyslogUDP, local_addr=("0.0.0.0", PORT))
    tcp = await asyncio.start_server(syslog_tcp_client, "0.0.0.0", PORT)
    log(f"syslog sulla porta {PORT} (UDP e TCP), solo dai NAS dell'elenco; storico in {LOG_DIR}")
    async with tcp:
        await tcp.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
