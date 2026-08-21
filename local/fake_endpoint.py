#!/usr/bin/env python3
"""
Fake forwarding endpoint (FlightAware/ADSB.lol stand-in) for local testing.

TCP sink on --port that counts received lines and logs connection events
plus a stats line every --stats-interval seconds, so test scripts can
assert that data is (or is not) flowing.
"""

import argparse
import socket
import threading
import time
from datetime import datetime


class FakeEndpoint:
    def __init__(self, port, stats_interval):
        self.port = port
        self.stats_interval = stats_interval
        self.lines = 0
        self.connections = 0

    def log(self, msg):
        print(f"{datetime.now().strftime('%H:%M:%S')} endpoint:{self.port}: {msg}",
              flush=True)

    def client_loop(self, conn, addr):
        buf = b''
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    _, buf = buf.split(b'\n', 1)
                    self.lines += 1
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            self.log(f"client {addr[0]}:{addr[1]} disconnected")

    def stats_loop(self):
        prev = 0
        while True:
            time.sleep(self.stats_interval)
            self.log(f"stats: lines={self.lines} (+{self.lines - prev}) "
                     f"connections={self.connections}")
            prev = self.lines

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', self.port))
        srv.listen(5)
        self.log("listening")
        threading.Thread(target=self.stats_loop, daemon=True).start()
        try:
            while True:
                conn, addr = srv.accept()
                self.connections += 1
                self.log(f"client connected from {addr[0]}:{addr[1]}")
                threading.Thread(target=self.client_loop, args=(conn, addr),
                                 daemon=True).start()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=40001)
    p.add_argument('--stats-interval', type=float, default=5.0)
    a = p.parse_args()
    FakeEndpoint(a.port, a.stats_interval).serve()
