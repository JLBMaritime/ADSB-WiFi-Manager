#!/bin/bash
################################################################################
# ADS-B Wi-Fi Manager - Complete Installation Script (Fresh Pi)
# JLBMaritime - Raspberry Pi 4B
#
# This single script installs and configures EVERYTHING:
#   - ADS-B Server (with V1 stability fixes: timeouts, leak prevention, monitoring)
#   - Web Manager (Wi-Fi configuration UI)
#   - Wi-Fi Hotspot (wlan1) + Internet (wlan0)
#   - CLI tool (adsb-cli)
#   - Hardware Watchdog (auto-reboot on freeze)
#   - systemd auto-restart with memory limits
#   - Health monitoring (auto-recovery)
#   - SD card optimizations
#   - Log rotation
#
# Usage:
#   sudo ./install.sh
#   sudo reboot   # REQUIRED for hardware watchdog activation
################################################################################

set -e

echo "=================================================="
echo "ADS-B Wi-Fi Manager - Complete Installation"
echo "JLBMaritime - Raspberry Pi 4B"
echo "=================================================="
echo ""

# ---------------- Pre-flight Checks ----------------
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo ./install.sh)"
    exit 1
fi

ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Please run with sudo, not as root user"
    exit 1
fi

INSTALL_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing for user: $ACTUAL_USER"
echo "Installation directory: $INSTALL_DIR"
echo "Source directory: $SOURCE_DIR"
echo ""

# ---------------- [1/12] Update System ----------------
echo "[1/12] Updating system packages..."
apt-get update
apt-get upgrade -y

# ---------------- [2/12] Install System Packages ----------------
echo "[2/12] Installing required packages..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    hostapd \
    dnsmasq \
    avahi-daemon \
    wireless-tools \
    wpasupplicant \
    git \
    curl \
    dos2unix \
    watchdog \
    logrotate

# ---------------- [3/12] Install dump1090-fa ----------------
echo "[3/12] Installing FlightAware dump1090-fa..."
if ! command -v dump1090-fa &> /dev/null; then
    wget -O /tmp/piaware-repo.deb \
        https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.2_all.deb \
        || true
    if [ -f /tmp/piaware-repo.deb ]; then
        dpkg -i /tmp/piaware-repo.deb || true
        apt-get update
        apt-get install -y dump1090-fa || echo "WARNING: dump1090-fa install failed - install manually"
    else
        echo "WARNING: Could not download dump1090-fa repository"
    fi
else
    echo "      ✓ dump1090-fa already installed"
fi

# ---------------- [4/12] Install Python Packages ----------------
echo "[4/12] Installing Python packages (Flask + psutil for stability)..."
pip3 install flask psutil --break-system-packages 2>/dev/null || pip3 install flask psutil
echo "      ✓ Flask installed (web framework)"
echo "      ✓ psutil installed (resource monitoring)"

# ---------------- [5/12] Copy Application Files ----------------
echo "[5/12] Installing application files..."
if [ -d "$INSTALL_DIR" ]; then
    BACKUP="${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "      Backing up existing installation to $BACKUP"
    mv "$INSTALL_DIR" "$BACKUP"
fi

mkdir -p "$INSTALL_DIR"
cp -r "$SOURCE_DIR"/* "$INSTALL_DIR/"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$INSTALL_DIR"

mkdir -p "$INSTALL_DIR/config" "$INSTALL_DIR/logs"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$INSTALL_DIR/config" "$INSTALL_DIR/logs"

# Convert all Python files to Unix line endings (fixes Windows CRLF issues)
find "$INSTALL_DIR" -name "*.py" -exec dos2unix {} \; 2>/dev/null || true
find "$INSTALL_DIR" -name "*.sh" -exec dos2unix {} \; 2>/dev/null || true

# ---------------- [6/12] Configure Wi-Fi Hotspot (wlan1) ----------------
echo "[6/12] Configuring Wi-Fi hotspot on wlan1..."

mkdir -p /etc/network/interfaces.d/

# hostapd configuration (Hotspot)
cat > /etc/hostapd/hostapd.conf << 'EOF'
# JLBMaritime ADS-B Hotspot Configuration
interface=wlan1
driver=nl80211
ssid=JLBMaritime-ADSB
hw_mode=g
channel=1
ieee80211d=1
country_code=GB
ieee80211n=1
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=3
wpa_passphrase=Admin123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP TKIP
rsn_pairwise=CCMP
beacon_int=100
dtim_period=2
EOF

sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd \
    || echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> /etc/default/hostapd

# dnsmasq configuration (DHCP/DNS for hotspot)
[ -f /etc/dnsmasq.conf ] && mv /etc/dnsmasq.conf /etc/dnsmasq.conf.backup
cat > /etc/dnsmasq.conf << 'EOF'
# JLBMaritime ADS-B DNS/DHCP Configuration
interface=wlan1
bind-interfaces
domain-needed
bogus-priv

dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
dhcp-option=3,192.168.4.1
dhcp-option=6,192.168.4.1
dhcp-authoritative

server=8.8.8.8
server=8.8.4.4
address=/ADS-B.local/192.168.4.1
domain=local
EOF

# wlan1 static IP
cat > /etc/network/interfaces.d/wlan1 << 'EOF'
auto wlan1
iface wlan1 inet static
    address 192.168.4.1
    netmask 255.255.255.0
EOF

# wlan0 DHCP (internet)
cat > /etc/network/interfaces.d/wlan0 << 'EOF'
allow-hotplug wlan0
iface wlan0 inet dhcp
    wpa-conf /etc/wpa_supplicant/wpa_supplicant.conf
EOF

# Prevent wpa_supplicant from managing wlan1
[ -f /etc/wpa_supplicant/wpa_supplicant-wlan1.conf ] && rm -f /etc/wpa_supplicant/wpa_supplicant-wlan1.conf

cat > /etc/wpa_supplicant/wpa_supplicant.conf << 'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB
EOF

systemctl disable wpa_supplicant@wlan1 2>/dev/null || true

# Prevent NetworkManager from managing wlan1
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/unmanage-wlan1.conf << 'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan1
EOF
systemctl is-active NetworkManager &>/dev/null && systemctl restart NetworkManager

# ---------------- [7/12] Configure mDNS & Hostname ----------------
echo "[7/12] Configuring mDNS (ADS-B.local) and hostname..."
systemctl enable avahi-daemon
systemctl start avahi-daemon

hostnamectl set-hostname ADS-B

cat > /etc/hosts << 'EOF'
127.0.0.1       localhost
127.0.1.1       ADS-B
192.168.4.1     ADS-B.local

::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF

# IP forwarding
grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf || echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p > /dev/null

# Firewall rules for hotspot
if command -v ufw &> /dev/null; then
    ufw allow in on wlan1 to any port 67 proto udp comment 'DHCP Server' 2>/dev/null || true
    ufw allow in on wlan1 to any port 68 proto udp comment 'DHCP Client' 2>/dev/null || true
    ufw allow in on wlan1 from 192.168.4.0/24 comment 'Hotspot network' 2>/dev/null || true
    ufw status | grep -q "Status: active" && ufw reload || true
fi

# ---------------- [8/12] Install systemd Services (with Stability Limits) ----------------
echo "[8/12] Installing systemd services with auto-restart and memory limits..."

# wlan1 config service
cp "$INSTALL_DIR/services/wlan1-config.service" /etc/systemd/system/

# ADS-B Server with stability features
cat > /etc/systemd/system/adsb-server.service << EOF
[Unit]
Description=ADS-B Server - Data Receiver and Forwarder
After=network.target dump1090-fa.service
Wants=dump1090-fa.service

[Service]
Type=simple
User=$ACTUAL_USER
Group=$ACTUAL_USER
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 $INSTALL_DIR/adsb_server/adsb_server.py
StandardOutput=journal
StandardError=journal

# Auto-restart on any crash
Restart=always
RestartSec=10s
StartLimitInterval=300s
StartLimitBurst=10

# Resource limits (kill+restart if exceeded - prevents leaks)
MemoryMax=300M
MemoryHigh=200M
CPUQuota=80%
LimitNOFILE=512
TasksMax=50

[Install]
WantedBy=multi-user.target
EOF

# Web Manager with stability features
cat > /etc/systemd/system/web-manager.service << EOF
[Unit]
Description=ADS-B Wi-Fi Manager Web Interface
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/web_interface/app.py
StandardOutput=journal
StandardError=journal

# Auto-restart on any crash
Restart=always
RestartSec=10s
StartLimitInterval=300s
StartLimitBurst=10

# Resource limits
MemoryMax=300M
MemoryHigh=200M
CPUQuota=80%
LimitNOFILE=512
TasksMax=50

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wlan1-config.service
systemctl enable adsb-server.service
systemctl enable web-manager.service

# ---------------- [9/12] Hardware Watchdog (Auto-Recovery from Freeze) ----------------
echo "[9/12] Enabling hardware watchdog (auto-reboots Pi if frozen)..."

# Enable Pi watchdog in firmware config
if ! grep -q "dtparam=watchdog=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=watchdog=on" >> /boot/firmware/config.txt
fi

# Load watchdog kernel module
modprobe bcm2835_wdt 2>/dev/null || true
grep -q "bcm2835_wdt" /etc/modules || echo "bcm2835_wdt" >> /etc/modules

# Configure watchdog daemon
cat > /etc/watchdog.conf << 'EOF'
# ADS-B WiFi Manager Hardware Watchdog
# Pi auto-reboots if system freezes for 15 seconds

watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 5

# Reboot if system load too high (CPU stuck)
max-load-1 = 24
max-load-5 = 18
max-load-15 = 12

# Reboot if memory critically low
min-memory = 1

# Realtime priority for reliable kicks
realtime = yes
priority = 1

log-dir = /var/log/watchdog
verbose = yes

retry-timeout = 60
repair-timeout = 60
EOF

mkdir -p /var/log/watchdog

mkdir -p /etc/systemd/system/watchdog.service.d
cat > /etc/systemd/system/watchdog.service.d/override.conf << 'EOF'
[Service]
Restart=always
RestartSec=10
EOF

systemctl daemon-reload
systemctl enable watchdog

echo "      ✓ Hardware watchdog enabled (15s timeout)"
echo "      ✓ Pi will auto-reboot if frozen - no power cycle needed!"

# ---------------- [10/12] Health Monitor (Auto-Recovery) ----------------
echo "[10/12] Installing system health monitor..."

cat > /usr/local/bin/adsb-health-monitor.sh << 'EOF'
#!/bin/bash
# ADS-B System Health Monitor - runs every 10 minutes
# Logs status and auto-restarts services if down

THROTTLED=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
TEMP=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 | cut -d"'" -f1)
LOAD=$(cat /proc/loadavg | awk '{print $1}')
MEM_FREE=$(free -m | awk '/^Mem:/{print $7}')
DISK_USE=$(df -h / | awk 'NR==2{print $5}')

ADSB_STATUS=$(systemctl is-active adsb-server)
WEB_STATUS=$(systemctl is-active web-manager)

logger -t adsb-health "Throttled=$THROTTLED Temp=${TEMP}C Load=$LOAD MemFree=${MEM_FREE}MB Disk=$DISK_USE ADSB=$ADSB_STATUS Web=$WEB_STATUS"

# Critical: throttling = power supply or thermal issue
if [ "$THROTTLED" != "0x0" ]; then
    logger -t adsb-health "WARNING: System throttled ($THROTTLED) - check power supply or cooling"
fi

# Auto-restart services if down
if [ "$ADSB_STATUS" != "active" ]; then
    logger -t adsb-health "ERROR: ADS-B server inactive, restarting..."
    systemctl restart adsb-server
fi
if [ "$WEB_STATUS" != "active" ]; then
    logger -t adsb-health "ERROR: Web manager inactive, restarting..."
    systemctl restart web-manager
fi

exit 0
EOF
chmod +x /usr/local/bin/adsb-health-monitor.sh

cat > /etc/systemd/system/adsb-health.service << 'EOF'
[Unit]
Description=ADS-B System Health Monitor
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/adsb-health-monitor.sh
EOF

cat > /etc/systemd/system/adsb-health.timer << 'EOF'
[Unit]
Description=Run ADS-B Health Monitor every 10 minutes
Requires=adsb-health.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Unit=adsb-health.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable adsb-health.timer

# ---------------- [11/12] SD Card Protection & Log Rotation ----------------
echo "[11/12] Configuring SD card protection and log rotation..."

# App log rotation
cat > /etc/logrotate.d/adsb-wifi-manager << EOF
$INSTALL_DIR/logs/*.log {
    daily
    rotate 3
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    maxsize 10M
}
EOF

# Limit systemd journal size
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/size-limit.conf << 'EOF'
[Journal]
SystemMaxUse=200M
SystemMaxFileSize=50M
MaxRetentionSec=7day
EOF
systemctl restart systemd-journald

# SD card optimizations - reduce wear
grep -q "noatime" /etc/fstab || sed -i 's|defaults\b|defaults,noatime|' /etc/fstab || true
grep -q "^vm.swappiness" /etc/sysctl.conf || { echo "vm.swappiness=10" >> /etc/sysctl.conf; sysctl -p > /dev/null; }

# Disable unattended upgrades (prevents random reboots)
systemctl stop apt-daily.timer 2>/dev/null || true
systemctl stop apt-daily-upgrade.timer 2>/dev/null || true
systemctl mask apt-daily.timer 2>/dev/null || true
systemctl mask apt-daily-upgrade.timer 2>/dev/null || true

# ---------------- [12/12] Install CLI & Permissions, Start Services ----------------
echo "[12/12] Installing CLI tool and configuring permissions..."

# CLI tool symlink
rm -f /usr/local/bin/adsb-cli
chmod +x "$INSTALL_DIR/cli/adsb_cli.py"
ln -s "$INSTALL_DIR/cli/adsb_cli.py" /usr/local/bin/adsb-cli

# Sudo permissions for web interface
cat > /etc/sudoers.d/adsb-wifi-manager << 'EOF'
# Allow web interface to control services and Wi-Fi
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl start adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl show adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/sbin/iwlist
www-data ALL=(ALL) NOPASSWD: /usr/sbin/iwconfig
www-data ALL=(ALL) NOPASSWD: /usr/sbin/wpa_cli
www-data ALL=(ALL) NOPASSWD: /usr/sbin/dhclient
www-data ALL=(ALL) NOPASSWD: /usr/bin/ip
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl start adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl show adsb-server
EOF
chmod 0440 /etc/sudoers.d/adsb-wifi-manager

# Start hotspot services
echo ""
echo "Starting services..."
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

# Bring up wlan1
ip link set wlan1 down 2>/dev/null || true
sleep 2
ip link set wlan1 up 2>/dev/null || true
sleep 1
ip addr add 192.168.4.1/24 dev wlan1 2>/dev/null || true
iw dev wlan1 set power_save off 2>/dev/null || true
iwconfig wlan1 power off 2>/dev/null || true
sleep 3

systemctl start hostapd 2>/dev/null || true
sleep 2
systemctl start dnsmasq 2>/dev/null || true

# Wait for dump1090-fa
if systemctl is-enabled dump1090-fa &>/dev/null; then
    sleep 5
fi

# Start application services
systemctl start adsb-server.service 2>/dev/null || true
sleep 2
systemctl start web-manager.service 2>/dev/null || true
systemctl start adsb-health.timer 2>/dev/null || true

# ==================== Done ====================
echo ""
echo "=================================================="
echo "✅ Installation Complete!"
echo "=================================================="
echo ""
echo "Setup Summary:"
echo "  Hostname:           ADS-B"
echo "  Hotspot SSID:       JLBMaritime-ADSB"
echo "  Hotspot Password:   Admin123"
echo "  Hotspot IP:         192.168.4.1"
echo "  Web Interface:      http://ADS-B.local or http://192.168.4.1"
echo "  Web Login:          JLBMaritime / Admin"
echo ""
echo "Stability Features:"
echo "  ✓ Hardware Watchdog (auto-reboot if frozen)"
echo "  ✓ Service auto-restart on crash"
echo "  ✓ Memory limits (300MB) - prevents leaks"
echo "  ✓ Health monitor (every 10 min)"
echo "  ✓ Resource leak fixes (sockets, threads)"
echo "  ✓ Log rotation (prevents SD fill)"
echo "  ✓ SD card optimizations (noatime, low swap)"
echo "  ✓ Auto-updates disabled (no random reboots)"
echo ""
echo "Service Status:"
systemctl is-active hostapd     >/dev/null && echo "  ✓ Hotspot:        Running" || echo "  ✗ Hotspot:        Not Running"
systemctl is-active dnsmasq     >/dev/null && echo "  ✓ DNS/DHCP:       Running" || echo "  ✗ DNS/DHCP:       Not Running"
systemctl is-active adsb-server >/dev/null && echo "  ✓ ADS-B Server:   Running" || echo "  ✗ ADS-B Server:   Not Running"
systemctl is-active web-manager >/dev/null && echo "  ✓ Web Manager:    Running" || echo "  ✗ Web Manager:    Not Running"
systemctl is-active dump1090-fa >/dev/null && echo "  ✓ dump1090-fa:    Running" || echo "  ✗ dump1090-fa:    Not Running (install manually)"
systemctl is-enabled watchdog   >/dev/null && echo "  ✓ Watchdog:       Enabled (activates after reboot)" || echo "  ✗ Watchdog:       Not enabled"
systemctl is-enabled adsb-health.timer >/dev/null && echo "  ✓ Health Monitor: Enabled" || echo "  ✗ Health Monitor: Not enabled"
echo ""
echo "Next Steps:"
echo "  1. REBOOT NOW to activate hardware watchdog: sudo reboot"
echo "  2. After reboot, connect to 'JLBMaritime-ADSB' Wi-Fi (password: Admin123)"
echo "  3. Open browser to http://ADS-B.local"
echo "  4. Login: JLBMaritime / Admin"
echo "  5. Configure Wi-Fi for internet (Wi-Fi Manager tab)"
echo "  6. Configure ADS-B endpoints (ADS-B Configuration tab)"
echo "  7. Place logo.png in: $INSTALL_DIR/web_interface/static/"
echo ""
echo "Management:"
echo "  CLI Tool:    adsb-cli"
echo "  SSH:         ssh JLBMaritime@ADS-B.local"
echo "  Logs:        sudo journalctl -u adsb-server -f"
echo "  Health:      sudo journalctl -t adsb-health -f"
echo ""
echo "🔴 IMPORTANT: REBOOT REQUIRED for hardware watchdog!"
echo "   sudo reboot"
echo "=================================================="
