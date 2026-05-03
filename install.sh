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
# [3/14] dump1090-fa (the ADS-B receiver) + RTL-SDR udev rule + DVB blacklist
#
# Three things go in this phase, in this order:
#
#   1.  Drop /etc/modprobe.d/blacklist-rtl-sdr.conf so the kernel's
#       DVB-T tuner driver (`dvb_usb_rtl28xxu`) doesn't grab the
#       RTL2832U dongle when it enumerates.  Without this, dump1090-fa
#       on a fresh Bookworm install hits:
#           rtlsdr: error querying device #0: Permission denied
#       in a 30-second restart loop forever.
#
#   2.  Drop /etc/udev/rules.d/60-rtlsdr.rules so when the dongle
#       enumerates the USB device node is created with
#       group=plugdev, mode=0660 -- otherwise it lands as root:root
#       and the unprivileged `dump1090` daemon user can't open it
#       (also "Permission denied", different cause).
#
#   3.  Install dump1090-fa itself.  PiAware's installer is *supposed*
#       to drop equivalents of (1) and (2), but it misses on at least
#       some Bookworm + Pi 4B + 0bda:2832 clone-dongle combinations.
#       Doing them ourselves is idempotent and harmless even when
#       PiAware does the right thing.
#
# After install we attempt `modprobe -r` on the DVB modules.  This
# usually fails (the modules are busy, holding the dongle) and the
# fix is a reboot -- which is already mandatory at the end of the
# installer for the hardware watchdog anyway.
# ---------------------------------------------------------------------------
say "[3/14] Installing RTL-SDR udev rule + DVB blacklist + dump1090-fa receiver..."

# (3a) DVB-T tuner driver blacklist
cat >/etc/modprobe.d/blacklist-rtl-sdr.conf <<'EOF'
# adsb-wifi-manager: keep the in-kernel DVB-T tuner driver away from
# the RTL2832U so dump1090-fa (via librtlsdr) can claim it.
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist rtl2838
EOF
ok "DVB blacklist installed -> /etc/modprobe.d/blacklist-rtl-sdr.conf"

# (3b) udev rule -> hand RTL2832U/RTL2838-class dongles to the
# 'plugdev' group with mode 0660 so the 'dump1090' daemon user
# (which is in plugdev) can rtlsdr_open() the device.
cat >/etc/udev/rules.d/60-rtlsdr.rules <<'EOF'
# adsb-wifi-manager: rtl-sdr USB dongle permissions.
# Without this the device node is root:root 0664 and dump1090-fa
# fails with "rtlsdr: error querying device #0: Permission denied".
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", MODE="0660", GROUP="plugdev", SYMLINK+="rtl_sdr"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE="0660", GROUP="plugdev", SYMLINK+="rtl_sdr"
EOF
udevadm control --reload-rules || warn "udevadm reload-rules failed"
udevadm trigger --action=add 2>/dev/null || true
ok "udev rule installed -> /etc/udev/rules.d/60-rtlsdr.rules"

# (3c) Try to unbind the in-kernel DVB modules now (best-effort -- on
# a fresh install they're usually busy holding the dongle and the
# rmmod fails; the mandatory reboot at the end of the installer will
# guarantee they don't load on next boot).
DVB_STILL_LOADED=0
for m in dvb_usb_rtl28xxu rtl2832_sdr rtl2832 dvb_usb_v2 dvb_core rtl2830 rtl2838; do
    modprobe -r "$m" 2>/dev/null || true
done
if lsmod | grep -qE '^(rtl2832|dvb_usb_rtl28xxu|dvb_usb_v2|dvb_core)\b'; then
    DVB_STILL_LOADED=1
    warn "DVB modules still loaded (will not be on next boot due to blacklist)."
    warn "dump1090-fa may keep restarting until you reboot -- this is expected."
fi

# (3d) FlightAware repo + dump1090-fa
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

# (3e) lighttpd is REQUIRED, not optional.  It serves
# /data/aircraft.json on port 8080 and that endpoint is read by:
#   - adsb_server.py when output_format = json or json_to_sbs1
#     (configurable in config/adsb_server_config.conf -- the default
#     'sbs1' mode does NOT need it, but operator-configurable so we
#     must support it)
#   - SkyAware live map UI at :8080/skyaware/ (nice-to-have)
# So we leave lighttpd alone.  It will bind :80 AND :8080.  Our
# waitress web manager will see :80 already taken and gracefully
# fall back to :5000 -- that fallback path is already coded in
# web_interface/app.py.  Operators reach the web UI via
# http://<host>:5000/.  This was a deliberate architecture choice
# in v2 over fighting lighttpd for :80.
if systemctl is-active lighttpd >/dev/null 2>&1; then
    ok "lighttpd is active (serves :8080/data/aircraft.json -- required by JSON mode)."
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

# Note: we deliberately do NOT setcap CAP_NET_BIND_SERVICE on the venv
# python any more.  lighttpd owns port 80 (it serves
# :8080/data/aircraft.json which adsb_server.py needs in JSON mode),
# so the web manager binds :5000 instead.  Removing setcap also means
# the web manager process has no elevated capabilities at all -- a
# small but real hardening win.

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

# web-manager.service: waitress on port 5000, non-root, watchdog ping.
#
# CRITICAL: do NOT set NoNewPrivileges=true on this unit.
# ----------------------------------------------------------------
# The web manager NEEDS to be able to run sudo at runtime so the
# unprivileged 'adsb' daemon user can:
#   - call `nmcli` (scan / connect / disconnect / forget)
#   - call `systemctl start|stop|restart adsb-server.service`
# Sudo is a setuid binary; its whole job is to fork+setuid(0).
# `NoNewPrivileges=true` is a kernel flag that PERMANENTLY (for the
# lifetime of the process tree) forbids any execve() from raising
# privileges via setuid.  Setting it here causes EVERY sudo call to
# fail at the kernel level with the journal line:
#   "sudo: The 'no new privileges' flag is set, which prevents sudo
#    from running as root."
# Symptoms in the UI when this flag is on:
#   * Wi-Fi scan returns 0 networks (sudo nmcli ... silently rc!=0)
#   * Saved Networks list is empty
#   * Dashboard shows "Not Connected" even when wlan0 is associated
#   * Start/Stop/Restart buttons throw "Failed to <action> ADS-B server"
#   * Saving any config in the UI does not actually restart the
#     forwarder
# All other hardening directives below (ProtectSystem, ProtectHome,
# ReadWritePaths, PrivateTmp) are kept ON because they don't
# interfere with sudo's setuid path.
# ----------------------------------------------------------------
cat >/etc/systemd/system/web-manager.service <<EOF
[Unit]
Description=ADS-B Wi-Fi Manager Web UI (waitress @ :5000)
After=network-online.target lighttpd.service
Wants=network-online.target

[Service]
Type=simple
User=$ADSB_USER
Group=$ADSB_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/web_interface/app.py
Restart=always
RestartSec=10s

# Hardening -- but NOT NoNewPrivileges (see fat comment above).
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/config $INSTALL_DIR/logs
PrivateTmp=true

# Resource caps
MemoryMax=300M
MemoryHigh=200M
CPUQuota=60%
LimitNOFILE=512
TasksMax=64

# Web manager listens on 5000 because lighttpd owns 80 (lighttpd is
# required -- see [3e] above).  app.py also has a 80->5000 fallback,
# so even if a future change tries to bind 80 it will gracefully
# downgrade rather than crash-loop.
Environment=PYTHONUNBUFFERED=1
Environment=ADSB_HTTP_PORT=5000

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Drop the AmbientCapabilities/CapabilityBoundingSet for CAP_NET_BIND_SERVICE
# from web-manager.service since we no longer try to bind :80.
sed -i '/^AmbientCapabilities=CAP_NET_BIND_SERVICE$/d' /etc/systemd/system/web-manager.service
sed -i '/^CapabilityBoundingSet=CAP_NET_BIND_SERVICE$/d' /etc/systemd/system/web-manager.service

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
# Sudoers drop-in for the web UI.
#
# IMPORTANT: sudo does *exact-string* matching on every argv element.
# A rule for 'systemctl restart adsb-server.service' will NOT match
# the call 'systemctl restart adsb-server' (no '.service' suffix), and
# vice-versa.  We therefore install BOTH forms for every action -- so
# that any code in app.py / adsb_cli.py / future contributions that
# uses either form will be permitted.  This was the root cause of the
# v1 'Failed to stop ADS-B server' alert in the web UI.
cat >/etc/sudoers.d/adsb-wifi-manager <<EOF
# adsb-wifi-manager -- least-privilege command list for the web UI.
# Reload with 'sudo visudo -c -f /etc/sudoers.d/adsb-wifi-manager'.
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/nmcli
$ADSB_USER ALL=(root) NOPASSWD: /usr/sbin/iw
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/ip

# adsb-server (forwarder) -- both bare and fully-qualified unit names
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl is-active adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl show adsb-server
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl stop adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl is-active adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl status adsb-server.service
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl show adsb-server.service

# adsb-hotspot-watchdog -- restart only, both forms
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-hotspot-watchdog
$ADSB_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart adsb-hotspot-watchdog.service
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
# NB: previous version used `try-restart X || start X`.  systemctl
# `try-restart` is documented as a NO-OP that returns 0 when the unit
# is stopped -- so the `||` arm never fires `start`, the service
# never comes up, and the post-flight check below reports it as
# inactive.  Plain `restart` does the right thing in both states
# (start if stopped, restart if running).
systemctl restart adsb-wifi-powersave-off.service || warn "adsb-wifi-powersave-off start failed"
systemctl restart adsb-hotspot-watchdog.service   || warn "adsb-hotspot-watchdog start failed"
systemctl restart adsb-server.service             || warn "adsb-server start failed"
systemctl restart web-manager.service             || warn "web-manager start failed"

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

# Live healthz -- web manager runs on :5000 by default (lighttpd has :80).
if curl -fsS --max-time 3 "http://127.0.0.1:5000/healthz" >/dev/null 2>&1; then
    ok "GET :5000/healthz returned 200"
elif curl -fsS --max-time 3 "http://127.0.0.1/healthz" >/dev/null 2>&1; then
    warn "Web UI ended up on :80 (lighttpd missing or stopped?)"
else
    warn "Could not reach /healthz on :5000 or :80 yet -- service may still be warming up"
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
  Web UI (over hotspot):   http://192.168.4.1:5000/
  Web UI (over LAN):       http://ADS-B.local:5000/   or   http://<pi-ip>:5000/
  Login:                   JLBMaritime / Admin   (forced change on first login)

  Note on port 5000 (not 80):
    Port 80 is served by lighttpd, which dump1090-fa pulls in as a
    dependency and uses for SkyAware UI + /data/aircraft.json.  The
    forwarder (adsb_server.py) uses that JSON endpoint when its
    output_format is 'json' or 'json_to_sbs1' -- so lighttpd is
    REQUIRED, not optional, and our web manager runs on :5000.

  Hotspot SSID:            JLBMaritime-ADSB    (5 GHz, channel 36, WPA2-CCMP)
  Hotspot PSK:             $(cat "$PSK_FILE")
                           ^^ also stored at: $PSK_FILE
                           reveal at any time:  sudo adsb-cli show-hotspot
                           rotate:               sudo adsb-cli rotate-pw

  Receiver port map:
    :5000   web manager (waitress) -- you log in here
    :80     lighttpd / SkyAware UI (http://<host>/)
    :8080   lighttpd / SkyAware data: /data/aircraft.json + /skyaware/
            (read by adsb_server.py in 'json' / 'json_to_sbs1' modes)
    :30002  dump1090-fa raw OUT     } AP clients on JLBMaritime-ADSB
    :30003  dump1090-fa SBS1 OUT    } can connect to any of these
    :30005  dump1090-fa Beast OUT   } directly
    :30004/:30104   dump1090-fa raw IN (network feeders)

  Diagnose anytime:        sudo adsb-cli doctor
  Live forwarder logs:     sudo journalctl -u adsb-server -f
  Live AP supervisor:      sudo journalctl -u adsb-hotspot-watchdog -f -o cat

  *** REBOOT NOW -- THIS IS REQUIRED, NOT OPTIONAL ***   sudo reboot

  The hardware watchdog only arms after a reboot, and on a FIRST
  install the kernel's DVB-T tuner driver is still resident in
  memory holding the RTL-SDR dongle (the blacklist we just dropped
  only takes effect at next boot).  Without the reboot dump1090-fa
  will keep crashing with "rtlsdr: error querying device #0:
  Permission denied".
EOF

if [[ $DVB_STILL_LOADED -eq 1 ]]; then
    banner_red "REBOOT REQUIRED -- DVB modules still resident in kernel"
    warn "dump1090-fa will fail until you 'sudo reboot' -- this is normal on a first install."
fi

# IMPORTANT: see README troubleshooting "USB Wi-Fi dongle keeps dropping out
# (mt76x2u + Pi 4B USB-3 bug)" if the AP is intermittent.
exit 0
