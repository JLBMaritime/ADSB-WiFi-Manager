#!/usr/bin/env python3
"""
adsb-cli non-interactive subcommands
====================================

Loaded by ``cli/adsb_cli.py`` when the user invokes ``adsb-cli`` with
arguments (i.e. ``adsb-cli show-hotspot``, ``adsb-cli doctor`` etc.).
With NO arguments, the original interactive menu is shown -- this
module is purely additive.

Subcommands:
    show-hotspot   Print the live hotspot SSID + PSK (read from NM)
    rotate-pw      Generate a new 16-char PSK, write to NM and restart AP
    health         Hit /healthz and print JSON
    doctor         End-to-end diagnostics for the AP + receiver chain
    update         git pull && re-run install.sh

Design notes:
* The PSK source-of-truth is the NetworkManager profile, NOT the seed
  file at /opt/adsb-wifi-manager/HOTSPOT_PASSWORD.txt.  ``show-hotspot``
  reads from NM via ``nmcli --show-secrets`` and ``rotate-pw`` writes
  back to NM (and re-syncs the seed file for convenience).
* ``doctor`` is the operator's go-to command when something looks
  wrong -- it doesn't change anything, just prints a colour-coded
  pass/fail per check.  Mirrors AIS-WiFi-Manager's doctor exactly.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

CONNECTION_NAME = "adsb-hotspot"
INSTALL_DIR = Path(os.environ.get("ADSB_INSTALL_DIR", "/opt/adsb-wifi-manager"))
PSK_SEED_FILE = INSTALL_DIR / "HOTSPOT_PASSWORD.txt"

# Pretty-printing.  Falls back to plain text when stdout isn't a TTY
# (so journalctl + log capture stay readable).
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s
def ok(s: str)   -> str: return _c("32", "[OK]   ") + s
def warn(s: str) -> str: return _c("33", "[WARN] ") + s
def fail(s: str) -> str: return _c("31", "[FAIL] ") + s
def info(s: str) -> str: return _c("36", "[INFO] ") + s


# ---------------------------------------------------------------------------
# nmcli wrapper (shell=False)
# ---------------------------------------------------------------------------
def _nmcli(*args: str, sudo: bool = False, timeout: float = 10.0) -> tuple[int, str, str]:
    cmd = []
    if sudo and os.geteuid() != 0:
        cmd.append("sudo")
    cmd.append(shutil.which("nmcli") or "/usr/bin/nmcli")
    cmd.extend(args)
    try:
        cp = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout, check=False,
            encoding="utf-8", errors="replace",
        )
        return cp.returncode, cp.stdout.strip(), cp.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"nmcli timed out after {timeout}s"
    except FileNotFoundError:
        return 127, "", "nmcli not installed"


def _read_psk_from_nm() -> str | None:
    """Authoritative PSK lookup: ask NM, not the seed file.  Requires
    root because secrets are gated behind PolicyKit."""
    rc, out, err = _nmcli(
        "--show-secrets", "-t", "-f", "802-11-wireless-security.psk",
        "connection", "show", CONNECTION_NAME, sudo=True,
    )
    if rc != 0:
        return None
    # Output format: "802-11-wireless-security.psk:thePassword"
    for line in out.splitlines():
        if line.startswith("802-11-wireless-security.psk:"):
            return line.split(":", 1)[1]
    return None


def _read_ssid_from_nm() -> str | None:
    rc, out, _ = _nmcli("-t", "-f", "802-11-wireless.ssid",
                        "connection", "show", CONNECTION_NAME)
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("802-11-wireless.ssid:"):
            return line.split(":", 1)[1]
    return None


# ---------------------------------------------------------------------------
# Subcommand: show-hotspot
# ---------------------------------------------------------------------------
def cmd_show_hotspot(_args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        print(fail("Run as root: sudo adsb-cli show-hotspot"))
        return 1
    ssid = _read_ssid_from_nm()
    psk  = _read_psk_from_nm()
    state_rc, state_out, _ = _nmcli("-t", "-f", "GENERAL.STATE",
                                    "connection", "show", CONNECTION_NAME)
    state = state_out.split(":", 1)[1] if (state_rc == 0 and ":" in state_out) else "<unknown>"

    print(info(f"Connection : {CONNECTION_NAME}"))
    print(info(f"SSID       : {ssid or '<not configured>'}"))
    print(info(f"PSK        : {psk or '<not configured>'}"))
    print(info(f"State      : {state}"))
    print(info(f"Seed file  : {PSK_SEED_FILE} "
               f"(install-time only -- NM is the source of truth)"))
    return 0 if (ssid and psk) else 2


# ---------------------------------------------------------------------------
# Subcommand: rotate-pw
# ---------------------------------------------------------------------------
def _gen_psk(n: int = 16) -> str:
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def cmd_rotate_pw(_args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        print(fail("Run as root: sudo adsb-cli rotate-pw"))
        return 1
    new_psk = _gen_psk(16)
    rc, _, err = _nmcli("connection", "modify", CONNECTION_NAME,
                        "802-11-wireless-security.psk", new_psk,
                        sudo=True, timeout=15.0)
    if rc != 0:
        print(fail(f"nmcli modify failed: {err}"))
        return 2
    rc2, _, err2 = _nmcli("connection", "up", CONNECTION_NAME,
                          sudo=True, timeout=30.0)
    if rc2 != 0:
        print(warn(f"PSK saved but bring-up failed: {err2}"))
    # Re-sync the seed file for operator convenience.
    try:
        PSK_SEED_FILE.write_text(new_psk + "\n")
        os.chmod(PSK_SEED_FILE, 0o600)
    except OSError as e:
        print(warn(f"Couldn't update seed file {PSK_SEED_FILE}: {e}"))
    print(ok(f"New PSK active: {new_psk}"))
    print(info("All previously paired devices must FORGET the network and rejoin."))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: health
# ---------------------------------------------------------------------------
def cmd_health(_args: argparse.Namespace) -> int:
    for url in ("http://127.0.0.1/healthz", "http://127.0.0.1:5000/healthz"):
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                print(info(f"{url} -> {resp.status}"))
                try:
                    print(json.dumps(json.loads(body), indent=2))
                except ValueError:
                    print(body)
                return 0 if resp.status == 200 else 3
        except Exception:
            continue
    print(fail("Could not reach /healthz on :80 or :5000"))
    return 4


# ---------------------------------------------------------------------------
# Subcommand: doctor
# ---------------------------------------------------------------------------
def cmd_doctor(_args: argparse.Namespace) -> int:
    """
    End-to-end diagnostics.  Each check prints a one-line PASS/WARN/FAIL.
    The script returns 0 only when every check passes; non-zero exit on
    any FAIL so this can be wired into monitoring.
    """
    failed = 0
    warned = 0

    def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str]:
        try:
            cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout, check=False)
            return cp.returncode, cp.stdout
        except Exception as e:
            return 255, str(e)

    print(_c("1;36", "=== adsb-cli doctor ==="))

    # 1. NM conf.d ';' regression
    bad = []
    try:
        for f in Path("/etc/NetworkManager/conf.d").glob("*.conf"):
            for line in f.read_text(errors="replace").splitlines():
                if line.lstrip().startswith(";"):
                    bad.append(str(f)); break
    except FileNotFoundError:
        pass
    if bad:
        print(fail(f"NM conf.d has ';' comments (will brick NM): {bad}"))
        failed += 1
    else:
        print(ok("NM conf.d files have no ';' comments"))

    # 2. adsb-hotspot connection state
    rc, out, _ = _nmcli("-t", "-f", "GENERAL.STATE", "connection", "show",
                        CONNECTION_NAME)
    state = out.split(":", 1)[1] if rc == 0 and ":" in out else ""
    if state == "activated":
        print(ok(f"NM connection '{CONNECTION_NAME}' is activated"))
    else:
        print(fail(f"NM connection '{CONNECTION_NAME}' state={state!r}"))
        failed += 1

    # 3. SSID + 5 GHz band check
    ssid = _read_ssid_from_nm() or ""
    rc, out, _ = _nmcli("-t", "-f", "802-11-wireless.band", "connection",
                        "show", CONNECTION_NAME)
    band = out.split(":", 1)[1] if rc == 0 and ":" in out else "?"
    if ssid and band == "a":
        print(ok(f"AP profile: SSID='{ssid}', band=5 GHz"))
    elif ssid:
        print(warn(f"AP profile: SSID='{ssid}', band={band} (expected 'a' for 5 GHz)"))
        warned += 1
    else:
        print(fail("AP profile has no SSID configured"))
        failed += 1

    # 4. wlan1 USB-3 / mt76x2u stability
    try:
        drv_link = Path("/sys/class/net/wlan1/device/driver")
        drv = drv_link.resolve().name if drv_link.exists() else ""
        speed_path = Path("/sys/class/net/wlan1/device/../speed")
        speed = speed_path.read_text().strip() if speed_path.exists() else ""
    except Exception:
        drv, speed = "", ""
    risky = drv in {"mt76x2u", "mt76x0u", "mt76xxu", "rt2800usb"}
    if risky and speed == "5000":
        print(fail(f"wlan1 driver={drv} on USB-3 (5 Gbps) -- move to USB-2 port!"))
        failed += 1
    elif risky:
        print(ok(f"wlan1 driver={drv} on USB-2 (known-good)"))
    elif drv:
        print(info(f"wlan1 driver={drv} (not on the risky list)"))
    else:
        print(warn("wlan1 not detected"))
        warned += 1

    # 5. Listening sockets we expect
    rc, out = _run(["ss", "-ltn"])
    needed = {"30003": "dump1090 SBS1", "30005": "dump1090 Beast",
              "8080": "dump1090 SkyAware", "80": "web UI"}
    for port, label in needed.items():
        if f":{port} " in out or f":{port}\n" in out:
            print(ok(f"port {port} bound ({label})"))
        elif port == "80":
            # Acceptable: fell back to 5000.
            if ":5000 " in out:
                print(warn("web UI fell back to :5000 (port 80 not bound)"))
                warned += 1
            else:
                print(fail(f"port {port} NOT bound ({label})"))
                failed += 1
        else:
            print(warn(f"port {port} NOT bound ({label}) -- is dump1090-fa running?"))
            warned += 1

    # 6. /healthz round-trip
    try:
        with urllib.request.urlopen("http://127.0.0.1/healthz", timeout=2) as r:
            body = json.loads(r.read())
            if r.status == 200 and body.get("status") == "ok":
                print(ok("GET /healthz -> 200 ok"))
            else:
                print(warn(f"GET /healthz -> {r.status} {body}"))
                warned += 1
    except Exception:
        try:
            urllib.request.urlopen("http://127.0.0.1:5000/healthz", timeout=2)
            print(warn("/healthz only on :5000 (web UI not on :80)"))
            warned += 1
        except Exception as e:
            print(fail(f"/healthz unreachable: {e}"))
            failed += 1

    # 7. Captive-portal probe redirect verification
    try:
        rc, out = _run(["dig", "+short", "+time=2", "+tries=1",
                        "@192.168.4.1", "captive.apple.com"])
        if "192.168.4.1" in out:
            print(ok("dnsmasq redirects captive.apple.com -> 192.168.4.1"))
        else:
            print(warn(f"captive.apple.com via 192.168.4.1 didn't return our IP "
                       f"(got: {out.strip()!r}) -- AP DNS may be misconfigured"))
            warned += 1
    except FileNotFoundError:
        print(info("`dig` not installed -- skipping captive-portal DNS check"))

    # 8. USB-disconnect rate scan (kernel log)
    rc, out = _run(["journalctl", "-k", "--since", "10 min ago", "--no-pager"], timeout=8)
    drops = sum(1 for l in out.splitlines() if "USB disconnect" in l)
    if drops >= 5:
        print(fail(f"{drops} kernel 'USB disconnect' events in last 10 min "
                   f"-- check dongle / cable / USB-3 port"))
        failed += 1
    elif drops >= 1:
        print(warn(f"{drops} USB disconnects in last 10 min (one is normal at boot)"))
        warned += 1
    else:
        print(ok("No USB disconnect storms in last 10 min"))

    # 9. Services
    for svc in ("NetworkManager", "adsb-hotspot-watchdog",
                "adsb-server", "web-manager"):
        rc, out = _run(["systemctl", "is-active", svc])
        if out.strip() == "active":
            print(ok(f"service {svc} active"))
        else:
            print(fail(f"service {svc} = {out.strip()!r}"))
            failed += 1

    # ----- Summary -----
    print()
    if failed == 0 and warned == 0:
        print(_c("32", "All checks passed."))
        return 0
    if failed == 0:
        print(_c("33", f"{warned} warning(s); no hard failures."))
        return 0
    print(_c("31", f"{failed} failure(s), {warned} warning(s)."))
    return 1


# ---------------------------------------------------------------------------
# Subcommand: update
# ---------------------------------------------------------------------------
def cmd_update(_args: argparse.Namespace) -> int:
    if os.geteuid() != 0:
        print(fail("Run as root: sudo adsb-cli update"))
        return 1
    repo = INSTALL_DIR
    print(info(f"Pulling latest in {repo}..."))
    rc1 = subprocess.call(["git", "-C", str(repo), "pull", "--ff-only"])
    if rc1 != 0:
        print(fail("git pull failed.  Check repo state manually."))
        return 2
    print(info("Re-running install.sh..."))
    return subprocess.call(["bash", str(repo / "install.sh")])


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="adsb-cli",
                                description="ADS-B Wi-Fi Manager admin CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show-hotspot", help="show hotspot SSID + PSK")
    sub.add_parser("rotate-pw",    help="generate a new 16-char hotspot PSK")
    sub.add_parser("health",       help="hit /healthz and print result")
    sub.add_parser("doctor",       help="end-to-end diagnostics")
    sub.add_parser("update",       help="git pull && re-run install.sh")

    args = p.parse_args(argv)
    handlers = {
        "show-hotspot": cmd_show_hotspot,
        "rotate-pw":    cmd_rotate_pw,
        "health":       cmd_health,
        "doctor":       cmd_doctor,
        "update":       cmd_update,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
