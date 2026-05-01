#!/usr/bin/env python3
"""
ADS-B Hotspot Watchdog
======================

A tiny, stdlib-only supervisor that keeps the `adsb-hotspot`
NetworkManager connection on wlan1 in the `activated` state.

Why this is its own process (not a thread inside the main web service):
-----------------------------------------------------------------------
* If the web service crashes / OOMs / gets stuck in a Python GC pause,
  the AP must KEEP RUNNING -- the AP is the *only* in-the-field
  recovery channel for the operator.  Decoupling the supervisor into
  its own systemd unit means the AP is independent of the web UI's
  liveness.
* No third-party deps (no `requests`, no `pyroute2`, no `gi`),
  precisely so PEP 668 ("externally-managed-environment" on RPi OS
  Bookworm) can't ever break this loop.

Algorithm
---------
* Every WATCH_PERIOD seconds, poll the connection state via
  `nmcli -t -f GENERAL.STATE,GENERAL.DEVICES connection show adsb-hotspot`
  (and a `--active` short-circuit for liveness).
* When the state is anything other than 'activated' for FAIL_THRESHOLD
  seconds, escalate: run `nmcli connection up adsb-hotspot` and
  back off 5 -> 10 -> 20 -> 40 -> 80 -> 160 -> 300 s on repeated
  failure.  On success, reset the backoff.
* Tag every event with a structured journal field (HOTSPOT_DOWN /
  RECOVERED / BACKOFF) so `journalctl -t adsb-hotspot-watchdog -o cat`
  is a clean operator timeline.

The watchdog is intentionally noisy on first boot (every state-change
goes to the journal) so the operator can correlate "AP went away" with
USB disconnects / kernel events.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import syslog
import time

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
CONNECTION_NAME = "adsb-hotspot"
WATCH_PERIOD    = 5      # seconds between polls
FAIL_THRESHOLD  = 15     # seconds of "down" before we intervene
BACKOFFS        = (5, 10, 20, 40, 80, 160, 300)  # capped at 300 s

# Where the install.sh placed the project; only used for nice journal
# context, never for executing anything.
INSTALL_DIR = "/opt/adsb-wifi-manager"

# ---------------------------------------------------------------------------
# Logging helpers (journald via syslog -- no python-systemd dep needed)
# ---------------------------------------------------------------------------
syslog.openlog(ident="adsb-hotspot-watchdog",
               logoption=syslog.LOG_PID,
               facility=syslog.LOG_DAEMON)


def log(level: int, tag: str, msg: str) -> None:
    """Emit a structured-ish log line.  `tag` is an upper-case event
    label so journal queries like `journalctl -t adsb-hotspot-watchdog
    | grep HOTSPOT_DOWN` are easy."""
    syslog.syslog(level, f"{tag}: {msg}")


# ---------------------------------------------------------------------------
# nmcli wrapper -- stdlib subprocess, shell=False for safety
# ---------------------------------------------------------------------------
def _nmcli(*args: str, timeout: float = 10.0) -> tuple[int, str, str]:
    nmcli = shutil.which("nmcli") or "/usr/bin/nmcli"
    try:
        cp = subprocess.run(
            [nmcli, "-t", *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
            text=True, encoding="utf-8", errors="replace",
        )
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"nmcli timed out after {timeout}s"
    except FileNotFoundError:
        return 127, "", "nmcli not installed"


def get_state() -> str:
    """Return the activation state of `adsb-hotspot`, e.g. 'activated',
    'activating', 'deactivated', or '' if NM doesn't know about it."""
    rc, out, _ = _nmcli("-f", "GENERAL.STATE",
                        "connection", "show", CONNECTION_NAME)
    if rc != 0:
        # Connection profile is missing entirely -- catastrophic but
        # nothing the watchdog can fix; log and let RestartSec handle
        # the noise rate-limit.
        return ""
    # Output: "GENERAL.STATE:activated"
    for line in out.splitlines():
        if line.startswith("GENERAL.STATE:"):
            return line.split(":", 1)[1].strip()
    return ""


def bring_up() -> bool:
    rc, _, err = _nmcli("connection", "up", CONNECTION_NAME, timeout=30.0)
    if rc == 0:
        return True
    log(syslog.LOG_WARNING, "BRING_UP_FAILED",
        f"nmcli rc={rc} stderr={err!r}")
    return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> int:
    log(syslog.LOG_INFO, "STARTED",
        f"watching '{CONNECTION_NAME}' every {WATCH_PERIOD}s "
        f"(install_dir={INSTALL_DIR})")

    # Graceful shutdown on SIGTERM (systemctl stop)
    stopping = {"flag": False}

    def _on_sig(_signum, _frame):
        stopping["flag"] = True
    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    last_state = "unknown"
    down_since: float | None = None
    backoff_idx = 0

    while not stopping["flag"]:
        state = get_state()
        now = time.monotonic()

        # State-change accounting + journal noise
        if state != last_state:
            log(syslog.LOG_INFO, "STATE_CHANGE",
                f"{last_state} -> {state or '<unknown>'}")
            last_state = state

        if state == "activated":
            if down_since is not None:
                elapsed = now - down_since
                log(syslog.LOG_NOTICE, "RECOVERED",
                    f"hotspot back up after {elapsed:.0f}s")
                down_since = None
                backoff_idx = 0
            time.sleep(WATCH_PERIOD)
            continue

        # Not activated.
        if down_since is None:
            down_since = now
            log(syslog.LOG_WARNING, "HOTSPOT_DOWN",
                f"state={state!r} (will intervene after {FAIL_THRESHOLD}s)")

        elapsed = now - down_since
        if elapsed < FAIL_THRESHOLD:
            time.sleep(WATCH_PERIOD)
            continue

        # Time to intervene.
        wait = BACKOFFS[min(backoff_idx, len(BACKOFFS) - 1)]
        log(syslog.LOG_WARNING, "BACKOFF",
            f"attempt {backoff_idx + 1}: nmcli c up {CONNECTION_NAME} "
            f"(then sleep {wait}s on failure)")
        if bring_up():
            # Don't optimistically reset the counters -- the next poll
            # tick will see 'activated' and emit RECOVERED.  This avoids
            # double-counting if NM reports activated then drops it
            # 100 ms later (which we have observed on the mt76x2u
            # USB-3 bug path).
            time.sleep(WATCH_PERIOD)
        else:
            backoff_idx += 1
            time.sleep(wait)

    log(syslog.LOG_INFO, "STOPPED", "received SIGTERM, exiting cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
