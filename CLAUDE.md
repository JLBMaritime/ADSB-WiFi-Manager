# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

ADSB-WiFi-Manager is a headless Raspberry Pi 4B appliance (JLBMaritime) for receiving and forwarding **1090 MHz ADS-B**: it pulls SBS1 frames from `dump1090-fa` (TCP :30003, or `/data/aircraft.json` on :8080 in json modes), filters, and fans out to TCP endpoints (FlightAware, ADSB.lol). It is the aviation sibling of `AIS-WiFi-Manager` in `C:\dev` — same architecture, but ADS-B/SBS1 instead of AIS/NMEA, and an external dump1090-fa process instead of a serial HAT.

## Running

Web UI: `web_interface/app.py` (Flask + waitress) on **port 5000** (mDNS `ADS-B.local:5000`) — lighttpd/dump1090 own :80/:8080, so don't move it. Forwarder: `adsb_server/adsb_server.py`. CLI: `adsb-cli` → `cli/adsb_cli.py` (interactive menus in `cli/*_menu.py`; note a second, separate `adsb_server/adsb_cli.py` also exists). No test suite. `install.sh` deploys with systemd units in `services/`: adsb-server, web-manager, adsb-hotspot-watchdog, wlan1-config, adsb-wifi-powersave-off. `optional/ssl-deployment/` holds nginx/SSL docs.

## Architecture

`adsb_server/` (SBS1 forwarder + `_hotspot_watchdog.py`), `web_interface/` (Flask UI), `wifi_manager/wifi_controller.py` (nmcli), `cli/` (menu-driven), `config/`. The control plane (web UI + hotspot on wlan1 5 GHz) is deliberately independent of the receiver chain so a UI failure can't stop forwarding.

Dependencies are minimal — Flask + psutil (`requirements.txt`); everything else is stdlib (socket/subprocess/configparser) plus system packages (dump1090-fa, hostapd, dnsmasq, avahi, waitress). Auth defaults `JLBMaritime`/`Admin`, forced change on first login; always-on AP on wlan1; Wi-Fi power-save disabled (brcmfmac freeze workaround).

This runs on remote Pi hardware — dump1090/nmcli/systemd behavior can't be tested locally on Windows. The hotspot/watchdog/powersave patterns are copy-pasted (not shared) across the sibling repos; a fix here may need porting to `AIS-WiFi-Manager` and vice versa.
