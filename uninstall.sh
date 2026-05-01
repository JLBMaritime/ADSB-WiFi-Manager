#!/usr/bin/env bash
################################################################################
# ADS-B Wi-Fi Manager - uninstaller
# Idempotent: safe to run multiple times.  Removes everything install.sh
# v2 created (NM profile, drop-ins, units, sudoers, /opt tree) but leaves
# dump1090-fa, NetworkManager and the OS alone.
################################################################################
set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; CYA='\033[0;36m'; RST='\033[0m'
say(){ printf "${CYA}==>${RST} %s\n" "$*"; }
ok() { printf "${GRN}  [OK]${RST} %s\n" "$*"; }
warn(){ printf "${YLW}  [!!]${RST} %s\n" "$*"; }

[[ $EUID -eq 0 ]] || { printf "${RED}run as root${RST}\n"; exit 1; }

INSTALL_DIR="/opt/adsb-wifi-manager"

say "Stopping + disabling units..."
for svc in web-manager adsb-server adsb-hotspot-watchdog adsb-wifi-powersave-off; do
    systemctl disable --now "$svc.service" 2>/dev/null && ok "$svc disabled" || warn "$svc not present"
done

say "Removing systemd units..."
rm -f /etc/systemd/system/{web-manager,adsb-server,adsb-hotspot-watchdog,adsb-wifi-powersave-off}.service
systemctl daemon-reload
ok "Units removed"

say "Removing NetworkManager profile + drop-ins..."
nmcli connection delete adsb-hotspot 2>/dev/null && ok "adsb-hotspot connection deleted" \
    || warn "adsb-hotspot connection not present"
rm -f /etc/NetworkManager/conf.d/00-wifi-powersave-off.conf
rm -f /etc/NetworkManager/conf.d/00-dns.conf
rm -f /etc/NetworkManager/dnsmasq-shared.d/00-adsb-upstream.conf
nmcli general reload 2>/dev/null || systemctl restart NetworkManager
ok "NM drop-ins removed and reloaded"

say "Removing sudoers + CLI shim..."
rm -f /etc/sudoers.d/adsb-wifi-manager
rm -f /usr/local/bin/adsb-cli
ok "sudoers + adsb-cli removed"

say "Backing up config + removing $INSTALL_DIR..."
if [[ -d "$INSTALL_DIR" ]]; then
    bk="/root/adsb-wifi-manager-uninstall-backup-$(date +%Y%m%d_%H%M%S).tar.gz"
    tar -czf "$bk" -C /opt adsb-wifi-manager 2>/dev/null && ok "Backup -> $bk" \
        || warn "Backup tarball failed (continuing)"
    rm -rf "$INSTALL_DIR"
    ok "$INSTALL_DIR removed"
fi

# Optional user
if id -u adsb >/dev/null 2>&1; then
    userdel adsb 2>/dev/null && ok "user 'adsb' removed" || warn "could not remove user 'adsb'"
fi

say "Done.  Kept: dump1090-fa, NetworkManager, dnsmasq-base, watchdog, journald drop-in."
say "If you want a fully clean Pi: 'sudo apt-get purge dump1090-fa watchdog avahi-daemon dnsmasq-base'"
