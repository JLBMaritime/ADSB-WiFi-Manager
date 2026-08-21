#!/usr/bin/env python3
"""
Fake dump1090-fa SBS1 source for local testing of adsb_server.py.

Listens on --port (default 30003) like dump1090-fa's SBS1 output and emits
a synthetic MSG,3 line every --interval seconds to every connected client.

A control listener on --control-port (default 30099) accepts single-line
commands so test scripts can drive failure scenarios:

    wedge    stop emitting but KEEP connections open (silent dump1090)
    resume   start emitting again
    close    close all client connections cleanly (FIN)
    status   report clients/wedged/sent counts
    quit     exit the process

Example:  echo wedge | nc -q1 127.0.0.1 30099
"""

import argparse
import socket
import threading
import time
from datetime import datetime, timezone


class FakeDump1090:
    def __init__(self, port, control_port, interval):
        self.port = port
        self.control_port = control_port
        self.interval = interval
        self.clients = set()
        self.lock = threading.Lock()
        self.wedged = False
        self.running = True
        self.sent = 0

    def log(self, msg):
        print(f"{datetime.now().strftime('%H:%M:%S')} fake_dump1090: {msg}", flush=True)

    def sbs1_line(self):
        now = datetime.now(timezone.utc)
        d, t = now.strftime('%Y/%m/%d'), now.strftime('%H:%M:%S.%f')[:-3]
        return (f"MSG,3,1,1,ABC{self.sent % 1000:03d},1,{d},{t},{d},{t},"
                f"TEST{self.sent % 100:02d},35000,450,90,51.5,-0.1\n")

    def accept_loop(self, srv):
        while self.running:
            try:
                conn, addr = srv.accept()
            except OSError:
                return
            with self.lock:
                self.clients.add(conn)
            self.log(f"client connected from {addr[0]}:{addr[1]} "
                     f"({len(self.clients)} total)")

    def emit_loop(self):
        while self.running:
            time.sleep(self.interval)
            if self.wedged:
                continue
            line = self.sbs1_line().encode()
            with self.lock:
                dead = []
                for c in self.clients:
                    try:
                        c.sendall(line)
                    except OSError:
                        dead.append(c)
                for c in dead:
                    self.clients.discard(c)
                    try:
                        c.close()
                    except OSError:
                        pass
                    self.log("client dropped (send failed)")
                if self.clients:
                    self.sent += 1

    def close_clients(self):
        with self.lock:
            for c in self.clients:
                try:
                    c.close()
                except OSError:
                    pass
            n = len(self.clients)
            self.clients.clear()
        self.log(f"closed {n} client connection(s)")

    def control_loop(self, srv):
        while self.running:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            try:
                cmd = conn.recv(64).decode(errors='ignore').strip().lower()
                if cmd == 'wedge':
                    self.wedged = True
                    self.log("WEDGED: connections stay open, no more data")
                elif cmd == 'resume':
                    self.wedged = False
                    self.log("resumed emitting")
                elif cmd == 'close':
                    self.close_clients()
                elif cmd == 'status':
                    conn.sendall(f"clients={len(self.clients)} wedged={self.wedged} "
                                 f"sent={self.sent}\n".encode())
                elif cmd == 'quit':
                    self.log("quitting")
                    self.running = False
                conn.close()
            except OSError:
                pass

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', self.port))
        srv.listen(5)
        ctl = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ctl.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ctl.bind(('127.0.0.1', self.control_port))
        ctl.listen(5)
        self.log(f"SBS1 on :{self.port}, control on :{self.control_port}, "
                 f"interval {self.interval}s")
        threading.Thread(target=self.accept_loop, args=(srv,), daemon=True).start()
        threading.Thread(target=self.control_loop, args=(ctl,), daemon=True).start()
        try:
            self.emit_loop()
        except KeyboardInterrupt:
            pass
        self.running = False
        srv.close()
        ctl.close()
        self.close_clients()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=30003)
    p.add_argument('--control-port', type=int, default=30099)
    p.add_argument('--interval', type=float, default=1.0)
    a = p.parse_args()
    FakeDump1090(a.port, a.control_port, a.interval).serve()
