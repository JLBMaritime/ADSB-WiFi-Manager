# JLBMaritime ADS-B & Wi-Fi Manager

A Raspberry Pi 4B receiver + forwarder for 1090 MHz ADS-B traffic.
Pulls SBS1 frames from `dump1090-fa`, filters them, and forwards to any
number of TCP endpoints. Ships with:

* a self-healing 5 GHz Wi-Fi access point on `wlan1` (USB dongle) so the
  operator can always reach the device — even when `wlan0` has lost its
  upstream
* a Flask + waitress web UI on port 80 (mDNS at `http://ADS-B.local/`)
* a scriptable CLI (`adsb-cli`) with a one-shot `doctor` diagnostic
* hardware + software watchdogs that auto-recover from kernel hangs,
  USB-3 dongle dropouts, and Wi-Fi power-save freezes

The receiver chain is the **primary function** of the device — every
design choice in the AP / web UI / firewall is made to never touch the
ports `dump1090-fa` listens on (see [Receiver port map](#receiver-port-map)).

---

## Receiver port map

| Port | Direction | Bound on | Purpose | Exposed on AP? |
|------|-----------|----------|---------|----------------|
| 1090 MHz | RF in  | antenna | ADS-B radio | n/a |
| 30001 | TCP listen | `0.0.0.0` | dump1090 raw **input** | **NO** (firewalled) |
| 30002 | TCP listen | `0.0.0.0` | dump1090 raw **output** | yes |
| **30003** | TCP listen | `0.0.0.0` | dump1090 **SBS1 output** ← *what `adsb-server` reads* | yes |
| 30004 | TCP listen | `0.0.0.0` | dump1090 Beast **input** | **NO** |
| 30005 | TCP listen | `0.0.0.0` | dump1090 Beast **output** | yes |
| 30104 | TCP listen | `0.0.0.0` | Beast input alt | **NO** |
| **8080** | TCP listen | `0.0.0.0` | dump1090 SkyAware web + `/data/aircraft.json` | yes |
| 30047 | TCP listen | `127.0.0.1` | piaware status JSON (loopback only) | n/a |
| **80**  | TCP listen | `0.0.0.0` | this project's web UI (waitress) | yes |
| 53/67 (UDP) | listen | `wlan1` | per-AP DNS+DHCP (NM-shared dnsmasq) | yes |
| 5353 (UDP) | listen | all | mDNS (`ADS-B.local`) | yes |

Inputs are firewalled off the AP so a malicious phone on
`JLBMaritime-ADSB` can't inject fake aircraft into your feed; outputs
are open so any Mode-S app on the AP (Virtual Radar Server, ADS-B
Helper, etc.) can subscribe directly to dump1090.

---

## Installation (fresh Pi 4B running RPi OS Bookworm 64-bit Lite)

```bash
# 1) prereqs to fetch the repo
sudo apt-get update
sudo apt-get install -y git

# 2) clone
cd ~
git clone https://github.com/JLBMaritime/adsb-wifi-manager.git
cd adsb-wifi-manager

# 3) make the installer executable
#    NB: if you uploaded the project via the GitHub *web UI* (drag-and-drop)
#    the +x bit is stripped; this command is mandatory in that case.
chmod +x install.sh uninstall.sh

# 4) run it
sudo ./install.sh                 # standard
# - or -
sudo ./install.sh --with-tailscale   # also install Tailscale
```

The installer is **idempotent** — re-running it is safe and will
reconcile drift back to the canonical state.  The full transcript is
saved to `/var/log/adsb-install.log` so support requests are easy.

When it finishes you will see a banner like:

```
Web UI (over hotspot):   http://192.168.4.1/
Hotspot SSID:            JLBMaritime-ADSB    (5 GHz, channel 36, WPA2-CCMP)
Hotspot PSK:             g4Hk2eVqp7n9rW3X
Login:                   JLBMaritime / Admin
```

**Reboot once** (`sudo reboot`) so the hardware watchdog
(`bcm2835_wdt`) takes effect.

---

## After install — connecting

### From a phone / laptop (over the hotspot)

1. Connect to Wi-Fi network **`JLBMaritime-ADSB`** (5 GHz).
2. Password: run `sudo adsb-cli show-hotspot` on the Pi over SSH, or
   `cat /opt/adsb-wifi-manager/HOTSPOT_PASSWORD.txt`.
3. Browse to **<http://192.168.4.1/>** or **<http://ADS-B.local/>**.

> **Upgrading from a previous install?**  The hotspot password has been
> randomised for security and the security mode tightened to WPA2-only
> CCMP.  On any device that previously joined `JLBMaritime-ADSB`, open
> Wi-Fi settings, **forget the network**, then rejoin using the new
> password.  This is a one-time inconvenience per device.

### From the LAN (over `wlan0`)

After `adsb-cli` (interactive menu) → "WiFi Manager" you can connect
the Pi to any 2.4 / 5 GHz network.  The web UI is then reachable on
the Pi's wlan0 IP, at port 80 / `http://ADS-B.local/`.

### From anywhere (Tailscale)

```bash
sudo ./install.sh --with-tailscale
sudo tailscale up --ssh                # one-time, prints a URL
```

The Pi is now part of your Tailnet.  Other devices in the tailnet can
hit `http://ads-b/` (Magic DNS) to reach the web UI; `tailscale ssh
ads-b` gives you a shell.

---

## Day-2 ops

### Diagnose anything: `adsb-cli doctor`

```bash
sudo adsb-cli doctor
```

Runs nine pass/fail checks: NM `;`-comment regression, AP activation,
SSID + 5 GHz band, USB-3 dongle stability, listening sockets (30003 /
30005 / 8080 / 80), `/healthz` round-trip, captive-portal DNS pin,
USB-disconnect storm scan, all four units active.  Returns a non-zero
exit code on failure so it can be wired into monitoring.

### Reveal / rotate the hotspot password

```bash
sudo adsb-cli show-hotspot      # SSID, PSK, state
sudo adsb-cli rotate-pw         # generate + apply new 16-char PSK
```

### Live logs

```bash
sudo journalctl -u adsb-server -f             # forwarder
sudo journalctl -u adsb-hotspot-watchdog -f -o cat   # AP supervisor
sudo journalctl -u web-manager -f             # web UI
sudo journalctl -u NetworkManager -f          # network stack
```

### Healthcheck (no auth)

```bash
curl -fsS http://192.168.4.1/healthz | jq
```

Returns 200 only when (a) `dump1090-fa` is bound to 30003 AND
(b) `adsb-server.service` is `active`.

---

## Architecture

```
                +-------------------+
   1090 MHz ─►  | RTL-SDR / DVB-T   |
                +---------┬---------+
                          ▼
                +-------------------+        :8080  SkyAware web
                | dump1090-fa       |◄──────────────────────────►  AP clients
                | :30001 raw IN     |        :30002 raw OUT
                | :30003 SBS1 OUT   |◄───┐   :30005 Beast OUT
                | :30005 Beast OUT  |    │   (read-only on wlan1)
                | :8080 lighttpd    |    │
                +-------------------+    │
                                         │  TCP read
                                         ▼
                              +-----------------------+
                              | adsb_server.py        |
                              | (this project)        |
                              | filter + fan-out      |
                              +----------┬------------+
                                         │
                                         ▼  TCP send
                       ┌─────────────────┴─────────────────┐
                       ▼                 ▼                 ▼
                 endpoint #1       endpoint #2       endpoint #N
                 (e.g. FA)         (e.g. ADSB.lol)   (operator-defined)


   Independent control plane (cannot stop the receiver chain)
   ─────────────────────────────────────────────────────────
   wlan1  ◄─ NetworkManager 'adsb-hotspot' (5 GHz ch 36, WPA2-CCMP)
              │
              ├─ ipv4.method=shared → per-AP private dnsmasq
              │     └─ /etc/NM/dnsmasq-shared.d/00-adsb-upstream.conf
              │           └─ captive-portal probe redirects → 192.168.4.1
              │
              └─ adsb-hotspot-watchdog.service  (5 s poll, exp backoff)

   wlan0  ◄─ NetworkManager 'wifi-…' (operator's home / boat / shore Wi-Fi)
              └─ wifi.powersave=2 (NM drop-in)  +  iw fallback oneshot
```

---

## Troubleshooting

### "Devices can't see / can't join the AP"

Run `sudo adsb-cli doctor` first — it pinpoints 90 % of issues in
under three seconds.  The most common causes, in order:

1. **iPhone / Android 14+ refuses to join** — the previous v1 installer
   used WPA1+WPA2 mixed-mode with TKIP, which Apple/Google deprecated
   in 2023.  v2 is WPA2-only CCMP; if devices still fail, *forget
   the network* on the device and rejoin (cached credentials from
   v1 won't work).
2. **AP is on USB-3 with an mt76x2u dongle** — unstable on Pi 4B.  Move
   the dongle to a **black** (USB-2) port.  See next section.
3. **"No internet, secured" warning** — captive-portal redirects
   missing.  Check `journalctl -u NetworkManager | grep dnsmasq`.
4. **Country code disallows channel 36** — set `REGDOMAIN=GB` in
   `/etc/default/crda` and re-run `sudo ./install.sh`.

### USB Wi-Fi dongle keeps dropping out (mt76x2u + Pi 4B USB-3 bug)

Symptom: AP appears, vanishes, reappears every 10–30 s; `journalctl
-k` shows `mt76x2u: timed out waiting for pending tx` and `usb 2-1:
USB disconnect` in a tight loop; `adsb-cli doctor` flags ≥5 USB
disconnects in 10 minutes.

**Fix**: shut down the Pi and physically move the dongle from a
**blue** (USB-3) port to a **black** (USB-2) port.  No software
change needed — and no, USB-2 is not a bottleneck for an AP that's
only serving a couple of phones over 5 GHz.

The installer detects this combination and prints a loud red banner
at install time.

### Web UI not on port 80, only 5000

This happens when `setcap cap_net_bind_service=+ep` failed against
the venv python (e.g. on filesystems that don't support file
capabilities).  The fallback works — browse to
`http://192.168.4.1:5000/` — but to fix it:

```bash
sudo setcap cap_net_bind_service=+ep /opt/adsb-wifi-manager/.venv/bin/python3
sudo systemctl restart web-manager
```

### `NetworkManager` won't start after editing `/etc/NetworkManager/conf.d/*.conf`

You almost certainly used `;` for a comment.  glib's keyfile parser
on Bookworm only accepts `#`.  Fix:

```bash
sudo sed -i 's/^[[:space:]]*;/#/' /etc/NetworkManager/conf.d/*.conf
sudo systemctl restart NetworkManager
```

The installer pre-flights this and refuses to proceed if any conf.d
file has `;` comments.

### Aircraft count always reads 0

You have an old config with `Dump1090.json_port = 30047`.  v1 wrote
the wrong port (that's piaware's status, not dump1090-fa's data).
The web UI auto-migrates to 8080 on next start, or fix manually:

```bash
sudo sed -i 's/^json_port = 30047/json_port = 8080/' \
    /opt/adsb-wifi-manager/config/adsb_server_config.conf
sudo systemctl restart adsb-server
```

### Tailscale broke my DNS

When Tailscale's installer runs without our pre-flight, it drops
`/etc/NetworkManager/conf.d/tailscale.conf` containing
`dns=systemd-resolved`, which doesn't exist on RPi OS Lite.  Fix:

```bash
sudo rm /etc/NetworkManager/conf.d/tailscale.conf
sudo nmcli general reload
```

Our installer scrubs that file when invoked with `--with-tailscale`.

---

## Uninstall

```bash
sudo ./uninstall.sh
```

Removes:

* `web-manager`, `adsb-server`, `adsb-hotspot-watchdog`,
  `adsb-wifi-powersave-off` units
* the `adsb-hotspot` NM connection
* `/etc/NetworkManager/conf.d/00-wifi-powersave-off.conf`,
  `00-dns.conf`, `dnsmasq-shared.d/00-adsb-upstream.conf`
* `/etc/sudoers.d/adsb-wifi-manager` and `/usr/local/bin/adsb-cli`
* `/opt/adsb-wifi-manager` (after a tarball backup to
  `/root/adsb-wifi-manager-uninstall-backup-*.tar.gz`)
* the `adsb` system user

Leaves alone: `dump1090-fa`, `NetworkManager`, `dnsmasq-base`,
`watchdog`, the journald drop-in, and Tailscale.

---

## Project layout

```
adsb-wifi-manager/
├── install.sh                        ← top-level installer (run once)
├── uninstall.sh                      ← top-level uninstaller
├── README.md                         ← this file
├── adsb_server/
│   ├── adsb_server.py                ← SBS1 → endpoints forwarder
│   └── _hotspot_watchdog.py          ← AP self-healer (its own systemd unit)
├── web_interface/
│   └── app.py                        ← Flask + waitress UI on port 80
├── cli/
│   ├── adsb_cli.py                   ← `adsb-cli` entry (interactive menu)
│   └── _subcommands.py               ← `adsb-cli doctor / show-hotspot / …`
├── wifi_manager/
│   └── wifi_controller.py            ← wlan0 client-mode helper (NM)
├── services/
│   ├── adsb-wifi-powersave-off.service
│   └── adsb-hotspot-watchdog.service
└── config/
    ├── wifi-powersave-off.conf       → /etc/NetworkManager/conf.d/00-…
    └── dnsmasq-shared-adsb.conf      → /etc/NM/dnsmasq-shared.d/00-…
```

---

## License

Internal JLBMaritime project.  See [LICENSE](LICENSE) for terms.
