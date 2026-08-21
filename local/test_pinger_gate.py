#!/usr/bin/env python3
"""
Verify the watchdog pinger's heartbeat gate without systemd (Linux only).

Binds a private AF_UNIX datagram socket, points NOTIFY_SOCKET at it, starts
watchdog_pinger_worker with a short interval, and asserts:
  1. READY=1 then WATCHDOG=1 pings arrive while the heartbeat is fresh
  2. pings STOP once the heartbeat goes stale
  3. pings RESUME when the heartbeat freshens again
"""

import os
import socket
import sys
import tempfile
import threading
import time

sock_path = os.path.join(tempfile.mkdtemp(), "notify.sock")
srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
srv.bind(sock_path)
srv.settimeout(0.2)
os.environ["NOTIFY_SOCKET"] = sock_path
os.environ["WATCHDOG_USEC"] = "1000000"  # 1s watchdog -> 0.5s ping interval

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'adsb_server'))
import adsb_server as mod

server = mod.ADSBServer.__new__(mod.ADSBServer)  # skip __init__ (no config I/O)
import logging
server.logger = logging.getLogger("pinger-test")
logging.basicConfig(level=logging.ERROR)
server.last_heartbeat = time.time()
server.heartbeat_stale_after = 2  # stale after 2s for the test

threading.Thread(target=server.watchdog_pinger_worker, daemon=True).start()


def drain(seconds):
    got = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            got.append(srv.recv(64).decode())
        except socket.timeout:
            pass
    return got


def keep_fresh(seconds):
    end = time.time() + seconds
    while time.time() < end:
        server.last_heartbeat = time.time()
        time.sleep(0.1)


failures = []

# Phase 1: fresh heartbeat -> READY + pings
t = threading.Thread(target=keep_fresh, args=(2,)); t.start()
msgs = drain(2); t.join()
if "READY=1" not in msgs:
    failures.append(f"phase1: no READY=1 (got {msgs})")
if msgs.count("WATCHDOG=1") < 2:
    failures.append(f"phase1: expected pings while fresh (got {msgs})")

# Phase 2: let heartbeat go stale -> pings must stop.
# First drain (and discard) pings sent while the heartbeat was still fresh,
# then assert silence once it is definitely stale.
drain(3)
msgs = drain(2)
if "WATCHDOG=1" in msgs:
    failures.append(f"phase2: pings continued while stale (got {msgs})")

# Phase 3: freshen -> pings resume
t = threading.Thread(target=keep_fresh, args=(2,)); t.start()
msgs = drain(2); t.join()
if msgs.count("WATCHDOG=1") < 2:
    failures.append(f"phase3: pings did not resume (got {msgs})")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("PASS: pinger gate (READY, ping-while-fresh, withhold-while-stale, resume)")
