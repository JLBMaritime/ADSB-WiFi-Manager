#!/usr/bin/env bash
################################################################################
# ADS-B Wi-Fi Manager - Installer v2 (NetworkManager-shared AP, 5 GHz)
# JLBMaritime - Raspberry Pi 4B + USB Wi-Fi dongle on wlan1
#
# Major changes vs. v1:
#   * AP stack moved from `hostapd + dnsmasq + /etc/network/interfaces.d`
#     to a single NetworkManager profile (`adsb-hotspot`) with
#     `ipv4.method=shared` -- no more dual-stack races, no more
#     "interface not coming up" because NM and ifupdown both think
#     they own wlan1.  This matches AIS-WiFi-Manager exactly.
#   * 5 GHz channel 36 (UNII-1, non-DFS), WPA2-only CCMP -- iPhones
#     and Android 14+ refused to associate with the old WPA1+WPA2
#     mixed/TKIP config.
#   * Random 16-char alphanumeric PSK at install time (was hard-coded
#     `Admin123` in git).
#   * Captive-portal probe redirects so phones see the AP as a normal
#     "internet OK" Wi-Fi network and don't trap Safari in a captive
#     sheet.
#   * Hotspot self-healer (`adsb-hotspot-watchdog.service`) recovers
#     from mt76x2u USB blips without operator intervention.
#   * MT7612U / MT7610U / RT2870 USB-3 detector with a loud red
#     warning at install time.
#   * Forwarder waits for dump1090's port 30003 to be bound before
#     starting (race fix).
#   * Web UI binds port 80 via `setcap cap_net_bind_service=+ep` on a
#     venv python3 instead of `User=root`.
#   * Python deps installed into a venv at /opt/adsb-wifi-manager/.venv
#     (PEP 668 compliant -- no more `--break-system-packages`).
#   * `set -euo pipefail` + ERR trap for fail-fast diagnostics.
#   * `chmod +x` reminder built in for users who uploaded via the
#     GitHub web UI (which strips the +x bit).
#
# Tested on:
#   * Raspberry Pi OS Bookworm 64-bit Lite, kernel 6.6.x
#   * MT7612U / RT2870 / RT5370 USB Wi-Fi dongles plugged into the
#     BLACK (USB-2) ports of the Pi 4B -- not the BLUE (USB-3) ports;
#     see README troubleshooting if you hit dropouts.
#
# Usage:
#   chmod +x install.sh           # see README "GitHub web upload" note
#   sudo ./install.sh             # standard install
#   sudo ./install.sh --with-tailscale   # bring up Tailscale too
#
# After it finishes:
#   * Connect a phone/laptop to SSID 'JLBMaritime-ADSB'
#     (password: cat /opt/adsb-wifi-manager/HOTSPOT_PASSWORD.txt)
#   * Browse to http://192.168.4.1/  or  http://ADS-B.local/
#   * Login: JLBMaritime / Admin (force-changed on first sign-in)
################################################################################

set -euo pipefail

# ---------------------------------------------------------------------------
# Pretty-printing
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; CYA='\033[0;36m'; RST='\033[0m'
say()   { printf "${CYA}==>${RST} %s\n" "$*"; }
ok()    { printf "${GRN}  [OK]${RST} %s\n" "$*"; }
warn()  { printf "${YLW}  [!!]${RST} %s\n" "$*"; }
fail()  { printf "${RED}  [XX]${RST} %s\n" "$*" >&2; }
banner_red() {
    printf "${RED}"
    printf '%.0s#' {1..72}; printf '\n'
    printf '# %-68s #\n' "$1"
    printf '%.0s#' {1..72}; printf '\n'
    printf "${RST}"
}

LOG=/var/log/adsb-install.log
trap 'fail "install.sh failed at line $LINENO. See $LOG for the full transcript."' ERR
exec > >(tee -a "$LOG") 2>&1

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
say "ADS-B Wi-Fi Manager installer v2 -- Bookworm + NM-shared AP"

if [[ $EUID -ne 0 ]]; then
    fail "Please run as root: sudo ./install.sh"; exit 1
fi
ACTUAL_USER="${SUDO_USER:-${USER:-pi}}"
if [[ "$ACTUAL_USER" == "root" ]]; then
    fail "Run with sudo from your login user, not directly as root."; exit 1
fi
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/adsb-wifi-manager"
ADSB_USER="adsb"

WITH_TAILSCALE=0
for arg in "$@"; do
    case "$arg" in
        --with-tailscale) WITH_TAILSCALE=1 ;;
        *) warn "Unknown arg: $arg" ;;
    esac
done

ok  "Source : $SOURCE_DIR"
ok  "Install: $INSTALL_DIR"
ok  "Operator user: $ACTUAL_USER (web UI service runs as $ADSB_USER)"
[[ $WITH_TAILSCALE -eq 1 ]] && ok "Tailscale: will install"

# ---------------------------------------------------------------------------
# [1/14] Validate NM drop-ins (the ';'-comment trap)
# ---------------------------------------------------------------------------
say "[1/14] Validating /etc/NetworkManager/conf.d/*.conf for the ';'-comment trap..."
shopt -s nullglob
bad=0
for f in /etc/NetworkManager/conf.d/*.conf; do
    if grep -Pq '^[[:space:]]*;' "$f"; then
        fail "  $f contains ';'-style comments -- glib's keyfile parser on"
        fail "  Bookworm rejects them and NetworkManager will refuse to start."
        fail "  Fix:  sudo sed -i 's/^[[:space:]]*;/#/' $f"
        bad=1
    fi
done
shopt -u nullglob
if [[ $bad -eq 1 ]]; then
    fail "Aborting before we make things worse.  Fix the file(s) above and re-run."
    exit 2
fi
ok "No ';' comments found"

# ---------------------------------------------------------------------------
# [2/14] System packages (no apt upgrade -- explicit deps only)
# ---------------------------------------------------------------------------
say "[2/14] Installing system packages..."
apt-get update -qq
# NB: dnsmasq-base (binary only, NO unit) NOT dnsmasq -- the full
# dnsmasq package's unit grabs :53/:67 on 0.0.0.0 and steals them
# from NetworkManager's per-AP private dnsmasq.  The remove below
# is belt-and-braces for upgrades from v1.
apt-get install -y \
    python3 python3-venv python3-pip \
    network-manager dnsmasq-base \
    iw wireless-tools \
    libcap2-bin curl wget git dos2unix \
    avahi-daemon \
    watchdog logrotate \
    rfkill usbutils
apt-get remove -y dnsmasq hostapd 2>/dev/null || true
systemctl disable --now dnsmasq hostapd 2>/dev/null || true
ok "Packages installed; full dnsmasq + hostapd removed (NM owns the AP now)"

# ---------------------------------------------------------------------------
# [3/14] dump1090-fa (the ADS-B receiver)
# ---------------------------------------------------------------------------
say "[3/14] Installing FlightAware dump1090-fa receiver..."
if ! command -v dump1090-fa >/dev/null 2>&1; then
    tmp=/tmp/piaware-repo.deb
    if wget -q -O "$tmp" \
        "https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.2_all.deb"
    then
        dpkg -i "$tmp" || true
        rm -f "$tmp"
        apt-get update -qq
        apt-get install -y dump1090-fa || warn "dump1090-fa install failed -- install manually later"
    else
        warn "Could not download dump1090-fa repo; install manually if you need it"
    fi
else
    ok "dump1090-fa already installed"
fi

# ---------------------------------------------------------------------------
# [4/14] mt76x2u / rt2800usb USB-3 stability detector
# ---------------------------------------------------------------------------
say "[4/14] Checking the wlan1 USB dongle for the USB-3 stability bug..."
RISKY_DRIVERS=(mt76x2u mt76x0u mt76xxu rt2800usb)
risky=""
if [[ -e /sys/class/net/wlan1/device ]]; then
    drv=$(basename "$(readlink -f /sys/class/net/wlan1/device/driver 2>/dev/null)" 2>/dev/null || true)

    # ----------------------------------------------------------------
    # Find the *USB device* node for wlan1.
    #
    # Previous logic tried two things and got both wrong:
    #   (a) `cat /sys/class/net/wlan1/device/../speed` -- this resolves
    #       to the USB *interface* node (e.g. .../1-1.4:1.0/) which has
    #       NO 'speed' file.  Always returns empty.
    #   (b) `lsusb -t | grep -q '5000M'` -- this matches if ANY device
    #       on the system enumerates at 5000M, including the Pi 4B's
    #       OWN empty USB-3 root hub.  False positive guaranteed.
    #
    # Correct method: walk up from the netdev's `device` link until we
    # find an ancestor that has a `speed` file.  That ancestor IS the
    # USB device node.  Its `speed` field is the real link speed:
    #   480  = USB-2 high-speed   (good)
    #   5000 = USB-3 SuperSpeed   (the bug zone for mt76x2u on Pi 4B)
    # ----------------------------------------------------------------
    usb_node=$(readlink -f /sys/class/net/wlan1/device 2>/dev/null || true)
    while [[ -n "$usb_node" && "$usb_node" != "/" && ! -f "$usb_node/speed" ]]; do
        usb_node=$(dirname "$usb_node")
    done
    speed=""
    [[ -n "$usb_node" && -f "$usb_node/speed" ]] && speed=$(cat "$usb_node/speed" 2>/dev/null || echo "")

    for r in "${RISKY_DRIVERS[@]}"; do
        if [[ "$drv" == "$r" ]]; then risky="$r"; break; fi
    done
    if [[ -n "$risky" ]]; then
        # Detect USB-3 SuperSpeed enumeration (5000 Mbps) on the dongle
        # specifically -- not on any other USB-3 hub on the system.
        if [[ "$speed" == "5000" ]]; then
            banner_red "WARNING: ${risky} dongle on a USB-3 (SuperSpeed) port"
            warn "The MediaTek MT76xx / Ralink RT2870 driver + Pi 4B xhci_hcd is a"
            warn "known unstable combination on USB-3.  Symptoms: AP appears, vanishes,"
            warn "reappears every 10-30 s, journalctl shows 'mt76x2u: timed out waiting"
            warn "for pending tx' and 'usb 2-1: USB disconnect' in a loop."
            warn ""
            warn "FIX: shut down, move the dongle from a BLUE (USB-3) port to a BLACK"
            warn "     (USB-2) port on the Pi 4B.  No software change required."
            warn ""
            warn "The installer will continue, but 'adsb-cli doctor' will continue"
            warn "to flag this until the dongle is on USB-2."
            sleep 5
        else
            ok "wlan1 driver=$drv on USB-2 (link speed=${speed:-unknown} Mbps) -- known good"
        fi
    else
        ok "wlan1 driver=$drv -- not on the risky-driver list"
    fi
else
    warn "/sys/class/net/wlan1 not present yet -- plug the dongle in or check 'iw dev'"
fi

# ---------------------------------------------------------------------------
# [5/14] Persistent journal (so we keep watchdog logs across reboots)
# ---------------------------------------------------------------------------
say "[5/14] Enabling persistent journald..."
mkdir -p /var/log/journal
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/00-adsb-persistent.conf <<'EOF'
[Journal]
Storage=persistent
SystemMaxUse=200M
SystemMaxFileSize=50M
MaxRetentionSec=14day
EOF
systemctl restart systemd-journald
ok "Journal is persistent (200M cap)"

# ---------------------------------------------------------------------------
# [6/14] Materialise project at /opt + venv
# ---------------------------------------------------------------------------
say "[6/14] Copying project to $INSTALL_DIR + creating venv..."
id -u "$ADSB_USER" >/dev/null 2>&1 || useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$ADSB_USER"
mkdir -p "$INSTALL_DIR"
# Backup any previous install
if [[ -e "$INSTALL_DIR/web_interface" ]]; then
    bk="$INSTALL_DIR.backup.$(date +%Y%m%d_%H%M%S)"
    say "  Existing install detected -- backing up to $bk"
    cp -a "$INSTALL_DIR" "$bk"
fi
# Copy fresh.
# IMPORTANT: the exclude list names *runtime* files only -- we used to
# do `--exclude='config/*.conf'` which also stripped the project's
# *shipped* NM drop-ins (config/wifi-powersave-off.conf,
# config/dnsmasq-shared-adsb.conf), which then caused step [7/14] to
# fail with "cannot stat /opt/.../config/wifi-powersave-off.conf".
# Whitelist the operator-edited files by exact name instead.
rsync -a --delete --exclude='.venv' \
      --exclude='config/adsb_server_config.conf' \
      --exclude='config/web_config.conf' \
      --exclude='HOTSPOT_PASSWORD.txt' \
      --exclude='secret_key' --exclude='logs/*' \
      "$SOURCE_DIR"/ "$INSTALL_DIR"/
mkdir -p "$INSTALL_DIR"/{config,logs}
# CRLF -> LF (Windows-edited files are common)
find "$INSTALL_DIR" \( -name '*.py' -o -name '*.sh' -o -name '*.conf' \) \
    -exec dos2unix -q {} \; 2>/dev/null || true

# Venv (PEP 668-friendly).
# `--copies` (NOT a symlink) is REQUIRED because we will run
# `setcap cap_net_bind_service=+ep` on the venv python below.
# setcap(8) refuses to operate on symlinks (it would otherwise be
# applying the capability to the SYSTEM /usr/bin/python3.11, which is
# both a security hole and not what we want).  If the venv already
# exists as a symlink-style venv from a previous v2 install, blow it
# away and recreate so setcap can succeed.
if [[ -L "$INSTALL_DIR/.venv/bin/python3" || ! -e "$INSTALL_DIR/.venv/bin/python3" ]]; then
    rm -rf "$INSTALL_DIR/.venv"
    python3 -m venv --copies "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip wheel
"$INSTALL_DIR/.venv/bin/pip" install --quiet \
    flask waitress flask-login bcrypt sdnotify psutil
ok "Venv ready at $INSTALL_DIR/.venv"

chown -R "$ADSB_USER":"$ADSB_USER" "$INSTALL_DIR"
chmod 0750 "$INSTALL_DIR"

# Web service binds port 80 without root via setcap on the venv python.
setcap 'cap_net_bind_service=+ep' "$INSTALL_DIR/.venv/bin/python3" \
    && ok "setcap cap_net_bind_service on venv python3 (so we can drop User=root)" \
    || warn "setcap failed -- web UI will fall back to port 5000"

# ---------------------------------------------------------------------------
# [7/14] NetworkManager drop-ins (powersave-off + DNS sanity)
# ---------------------------------------------------------------------------
say "[7/14] Installing NetworkManager drop-ins..."
mkdir -p /etc/NetworkManager/conf.d
# Read the NM drop-ins from the SOURCE checkout, not the /opt/ copy.
# They are static, source-controlled files -- no need to round-trip
# them through $INSTALL_DIR, and not doing so means we no longer care
# whether the rsync exclude list happens to skip them.
install -m 0644 "$SOURCE_DIR/config/wifi-powersave-off.conf" \
    /etc/NetworkManager/conf.d/00-wifi-powersave-off.conf
# Pre-empt the "Tailscale broke my DNS" trap: declare dns=default
# BEFORE Tailscale's installer drops dns=systemd-resolved.
cat >/etc/NetworkManager/conf.d/00-dns.conf <<'EOF'
[main]
# RPi OS Lite does not ship systemd-resolved enabled, so we MUST stay
# on dns=default.  Tailscale's installer will try to set this to
# systemd-resolved -- the post-flight check at the end of install.sh
# scrubs that file if it appears.
dns=default
rc-manager=file
EOF
# dnsmasq drop-in for the per-AP private dnsmasq spawned by ipv4.method=shared
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
install -m 0644 "$SOURCE_DIR/config/dnsmasq-shared-adsb.conf" \
    /etc/NetworkManager/dnsmasq-shared.d/00-adsb-upstream.conf

# Final ';'-comment regression check (we just installed two files)
if grep -lP '^[[:space:]]*;' /etc/NetworkManager/conf.d/*.conf >/dev/null 2>&1; then
    fail "Just-installed NM conf.d files contain ';' comments.  This is a bug in the project."
    exit 3
fi
systemctl is-active NetworkManager >/dev/null && nmcli general reload || systemctl restart NetworkManager
ok "NetworkManager reloaded"

# ---------------------------------------------------------------------------
# [8/14] Materialise the AP profile on wlan1 (5 GHz, WPA2-CCMP)
# ---------------------------------------------------------------------------
say "[8/14] Creating NetworkManager profile 'adsb-hotspot' on wlan1 (5 GHz, ch 36)..."

# Generate a fresh random PSK on every install.  This file is the
# install-time SEED only; the source of truth for the live PSK is the
# NetworkManager profile (read it back via `adsb-cli show-hotspot`).
PSK_FILE="$INSTALL_DIR/HOTSPOT_PASSWORD.txt"
if [[ ! -s "$PSK_FILE" ]]; then
    # NB: previous version was `tr -dc '...' </dev/urandom | head -c 16`,
    # which trips `set -o pipefail`: head closes the pipe after 16 bytes,
    # tr writes one more chunk and is killed by SIGPIPE (exit 141), the
    # pipeline as a whole returns 141, and the ERR trap aborts the
    # installer at this line.  Use python3 + `secrets` instead -- no
    # pipe, no SIGPIPE, and CSPRNG-strength randomness.
    HOTSPOT_PSK="$(python3 -c '
import secrets, string
alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(16)))
')"
    if [[ -z "$HOTSPOT_PSK" || ${#HOTSPOT_PSK} -ne 16 ]]; then
        fail "PSK generation failed (got ${#HOTSPOT_PSK} chars)"
        exit 5
    fi
    umask 077
    printf '%s\n' "$HOTSPOT_PSK" > "$PSK_FILE"
    chown "$ADSB_USER":"$ADSB_USER" "$PSK_FILE"
    chmod 0600 "$PSK_FILE"
    ok "Generated new 16-char PSK -> $PSK_FILE (mode 600)"
else
    HOTSPOT_PSK="$(<"$PSK_FILE")"
    ok "Re-using existing PSK from $PSK_FILE"
fi

SSID="JLBMaritime-ADSB"
# Country code: pull from /etc/default/crda or default to GB.
COUNTRY=$(awk -F= '/^REGDOMAIN=/{gsub(/"/,"",$2); print $2}' /etc/default/crda 2>/dev/null || true)
COUNTRY=${COUNTRY:-GB}
iw reg set "$COUNTRY" 2>/dev/null || true

# Recreate the profile from scratch so re-installs are idempotent.
nmcli connection delete adsb-hotspot 2>/dev/null || true
nmcli connection add type wifi ifname wlan1 con-name adsb-hotspot \
    autoconnect yes \
    ssid "$SSID"
# REQUIRED properties: failure here MUST abort -- without them the
# AP would either fail to start or accept clients in an insecure mode.
nmcli connection modify adsb-hotspot \
    802-11-wireless.mode ap \
    802-11-wireless.band a \
    802-11-wireless.channel 36 \
    802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.proto rsn \
    802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.group ccmp \
    802-11-wireless-security.psk "$HOTSPOT_PSK" \
    ipv4.method shared \
    ipv4.addresses 192.168.4.1/24 \
    ipv6.method disabled \
    connection.autoconnect-priority 100

# OPTIONAL properties: best-effort, log on failure.
# - 802-11-wireless.powersave    : silently ignored on older NM
# - 802-11-wireless-security.pmf : NM 1.42 accepts the string forms
#                                  (disable|optional|required) reliably;
#                                  the integer alias `1` was rejected
#                                  on at least one Bookworm build.
# - ipv4.shared-dhcp-lease-time  : optional, NM picks a sane default
# - connection.zone              : firewalld zone name -- RPi OS Lite
#                                  does NOT install firewalld, so any
#                                  value other than '' is rejected.
#                                  We deliberately don't set this; per-
#                                  AP isolation is already provided by
#                                  ipv4.method=shared.
nmcli connection modify adsb-hotspot 802-11-wireless.powersave 2 2>/dev/null \
    || warn "could not set 802-11-wireless.powersave=2 (NM too old?)"
nmcli connection modify adsb-hotspot 802-11-wireless-security.pmf disable 2>/dev/null \
    || warn "could not set 802-11-wireless-security.pmf=disable (NM too old?)"
nmcli connection modify adsb-hotspot ipv4.shared-dhcp-lease-time 3600 2>/dev/null \
    || true

# Bring it up and verify activation (poll up to 20 s).
nmcli connection up adsb-hotspot >/dev/null || true
for i in $(seq 1 20); do
    state=$(nmcli -t -f GENERAL.STATE connection show adsb-hotspot 2>/dev/null | cut -d: -f2 || true)
    [[ "$state" == "activated" ]] && break
    sleep 1
done
if [[ "$state" != "activated" ]]; then
    fail "adsb-hotspot did not reach 'activated' after 20 s (state=$state)"
    fail "Check 'journalctl -u NetworkManager --since \"1 min ago\"' for clues."
    fail "Common causes:"
    fail "  * wlan1 doesn't exist (USB dongle not detected) -- check 'iw dev'"
    fail "  * Dongle on USB-3 with mt76x2u driver -- move to USB-2 (see [4/14])"
    fail "  * Country code (\$COUNTRY=$COUNTRY) doesn't permit channel 36 outdoors"
    journalctl -u NetworkManager --no-pager -n 30 || true
    exit 4
fi
ok "AP 'JLBMaritime-ADSB' is up on wlan1, 5 GHz channel 36, WPA2-CCMP"

# ---------------------------------------------------------------------------
# [9/14] Hostname + mDNS
# ---------------------------------------------------------------------------
say "[9/14] Configuring hostname (ADS-B) and mDNS..."
hostnamectl set-hostname ADS-B
cat >/etc/hosts <<'EOF'
127.0.0.1       localhost
127.0.1.1       ADS-B
192.168.4.1     ADS-B.local

::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF
systemctl enable --now avahi-daemon
ok "Hostname=ADS-B; mDNS enabled"

# ---------------------------------------------------------------------------
# [10/14] systemd units
# ---------------------------------------------------------------------------
say "[10/14] Installing systemd units..."

install -m 0644 "$INSTALL_DIR/services/adsb-wifi-powersave-off.service" \
    /etc/systemd/system/adsb-wifi-powersave-off.service
install -m 0644 "$INSTALL_DIR/services/adsb-hotspot-watchdog.service" \
    /etc/systemd/system/adsb-hotspot-watchdog.service

# adsb-server.service: Type=simple, persistent TCP forwarder, waits for
# dump1090-fa's port 30003 to be bound before starting.  Uses the venv
# python3 so 'flask', 'sdnotify', 'psutil' all resolve.
cat >/etc/systemd/system/adsb-server.service <<EOF
[Unit]
Description=ADS-B Forwarder (SBS1 from dump1090 -> configured endpoints)
Documentation=file://$INSTALL_DIR/README.md
# Wait for dump1090-fa to actually bind 30003 before we connect to it.
# Without this the forwarder races dump1090 on boot and spews
# "Connection refused" until the receiver finishes warming up.
After=network-online.target dump1090-fa.service
Wants=dump1090-fa.service network-online.target

[Service]
Type=simple
User=$ADSB_USER
Group=$ADSB_USER
WorkingDirectory=$INSTALL_DIR
# Wait up to 60 s for SBS1 (30003) to be bound.  '|| true' lets us
# proceed even on a Pi without dump1090-fa (rare) -- the forwarder
# will simply log "Failed to connect" and retry on its own loop.
ExecStartPre=/bin/sh -c 'for i in \$(seq 1 60); do ss -ltn | grep -q ":30003" && exit 0; sleep 1; done; exit 0'
ExecStart=$INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/adsb_server/adsb_server.py
Restart=always
RestartSec=10s

# Stability / leak guards
MemoryMax=300M
MemoryHigh=200M
CPUQuota=80%
LimitNOFILE=512
TasksMax=64

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/logs $INSTALL_DIR/config
PrivateTmp=true

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# web-manager.service: waitress on port 80, non-root, watchdog ping.
cat >/etc/systemd/system/web-manager.service <<EOF
[Unit]
Description=ADS-B Wi-Fi Manager Web UI (waitress @ :80)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ADSB_USER
Group=$ADSB_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/web_interface/app.py
Restart=always
RestartSec=10s

# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/config $INSTALL_DIR/logs
PrivateTmp=true
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

# Resource caps
MemoryMax=300M
MemoryHigh=200M
CPUQuota=60%
LimitNOFILE=512
TasksMax=64

Environment=PYTHONUNBUFFERED=1
Environment=ADSB_HTTP_PORT=80

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable adsb-wifi-powersave-off.service
systemctl enable adsb-hotspot-watchdog.service
systemctl enable adsb-server.service
systemctl enable web-manager.service
ok "Units installed and enabled"

# ---------------------------------------------------------------------------
# [11/14] Hardware watchdog (auto-reboot on freeze)
# ---------------------------------------------------------------------------
say "[11/14] Configuring hardware watchdog..."
if [[ -f /boot/firmware/config.txt ]]; then
    grep -q '^dtparam=watchdog=on' /boot/firmware/config.txt \
        || echo 'dtparam=watchdog=on' >> /boot/firmware/config.txt
fi
modprobe bcm2835_wdt 2>/dev/null || true
grep -q '^bcm2835_wdt' /etc/modules || echo 'bcm2835_wdt' >> /etc/modules
cat >/etc/watchdog.conf <<'EOF'
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 5
max-load-1 = 24
max-load-5 = 18
max-load-15 = 12
min-memory = 1
realtime = yes
priority = 1
log-dir = /var/log/watchdog
verbose = yes
retry-timeout = 60
repair-timeout = 60
EOF
mkdir -p /var/log/watchdog
mkdir -p /etc/systemd/system/watchdog.service.d
cat >/etc/systemd/system/watchdog.service.d/override.conf <<'EOF'
[Service]
Restart=always
RestartSec=10
EOF
systemctl daemon-reload
systemctl enable watchdog
ok "Hardware watchdog enabled (15 s timeout, activates after reboot)"

# ---------------------------------------------------------------------------
# [12/14] Sudoers (so the web UI can call nmcli, systemctl, iw)
# ---------------------------------------------------------------------------
say "[12/14] Installing sudoers drop-in for $ADSB_USER..."
cat >/etc/sudoers.d/adsb-wifi-manager <<EOF
# adsb-wifi-manager -- least-privilege command list for the web UI.
# Reload with 'sudo visudo -c -f /etc/sudoers.d/adsb-wifi-manager'.
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/nmcli
$ADSB_USER ALL=(root) NOPASSWD: /usr/sbin/iw
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/ip
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-hotspot-watchdog.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl is-active adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl show adsb-server.service
EOF
chmod 0440 /etc/sudoers.d/adsb-wifi-manager
visudo -cf /etc/sudoers.d/adsb-wifi-manager >/dev/null && ok "Sudoers OK"

# ---------------------------------------------------------------------------
# [13/14] CLI shim (`adsb-cli`)
# ---------------------------------------------------------------------------
say "[13/14] Installing adsb-cli shim..."
chmod +x "$INSTALL_DIR/cli/adsb_cli.py"
cat >/usr/local/bin/adsb-cli <<EOF
#!/bin/sh
exec $INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/cli/adsb_cli.py "\$@"
EOF
chmod +x /usr/local/bin/adsb-cli
ok "adsb-cli installed (try: sudo adsb-cli show-hotspot)"

# ---------------------------------------------------------------------------
# [14/14] Optional: Tailscale + start everything + post-flight
# ---------------------------------------------------------------------------
if [[ $WITH_TAILSCALE -eq 1 ]]; then
    say "[14a/14] Installing Tailscale..."
    if ! command -v tailscale >/dev/null 2>&1; then
        curl -fsSL https://tailscale.com/install.sh | sh
    fi
    # Scrub the dns=systemd-resolved trap if present.
    rm -f /etc/NetworkManager/conf.d/tailscale.conf
    systemctl is-active NetworkManager >/dev/null && nmcli general reload
    systemctl enable --now tailscaled
    ok "Tailscale installed.  Run 'sudo tailscale up --ssh' when ready."
fi

say "[14/14] Starting services + post-flight..."
systemctl try-restart adsb-wifi-powersave-off.service || systemctl start adsb-wifi-powersave-off.service
systemctl try-restart adsb-hotspot-watchdog.service   || systemctl start adsb-hotspot-watchdog.service
systemctl try-restart adsb-server.service             || systemctl start adsb-server.service
systemctl try-restart web-manager.service             || systemctl start web-manager.service

sleep 3
post_ok=1
for svc in NetworkManager adsb-hotspot-watchdog adsb-server web-manager; do
    if systemctl is-active "$svc" >/dev/null 2>&1; then
        ok "$svc active"
    else
        fail "$svc NOT active -- journalctl -u $svc -n 50 --no-pager"
        post_ok=0
    fi
done

# Live healthz
if curl -fsS --max-time 3 "http://127.0.0.1/healthz" >/dev/null 2>&1; then
    ok "GET /healthz returned 200"
elif curl -fsS --max-time 3 "http://127.0.0.1:5000/healthz" >/dev/null 2>&1; then
    warn "Web UI fell back to :5000 (port 80 not bound -- check setcap)"
else
    warn "Could not reach /healthz on :80 or :5000 yet -- service may still be warming up"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "=========================================================================="
if [[ $post_ok -eq 1 ]]; then
    printf "${GRN}Installation complete.${RST}\n"
else
    printf "${YLW}Installation finished with warnings -- review above.${RST}\n"
fi
echo "=========================================================================="
cat <<EOF
  Web UI (over hotspot):   http://192.168.4.1/
  Web UI (over LAN):       http://ADS-B.local/   or   http://<pi-ip>/
  Login:                   JLBMaritime / Admin   (forced change on first login)

  Hotspot SSID:            JLBMaritime-ADSB    (5 GHz, channel 36, WPA2-CCMP)
  Hotspot PSK:             $(cat "$PSK_FILE")
                           ^^ also stored at: $PSK_FILE
                           reveal at any time:  sudo adsb-cli show-hotspot
                           rotate:               sudo adsb-cli rotate-pw

  Receiver port map:
    1090 MHz radio  -> dump1090-fa
                       :30002  raw OUT (open)         } readable by AP
                       :30003  SBS1 OUT (open)        } clients on
                       :30005  Beast OUT (open)       } JLBMaritime-ADSB
                       :8080   SkyAware web (open)    }
                       :30001/4/30104 raw IN (firewalled OFF on wlan1)

  Diagnose anytime:        sudo adsb-cli doctor
  Live forwarder logs:     sudo journalctl -u adsb-server -f
  Live AP supervisor:      sudo journalctl -u adsb-hotspot-watchdog -f -o cat

  REBOOT now to activate the hardware watchdog:  sudo reboot
EOF

# IMPORTANT: see README troubleshooting "USB Wi-Fi dongle keeps dropping out
# (mt76x2u + Pi 4B USB-3 bug)" if the AP is intermittent.
exit 0
