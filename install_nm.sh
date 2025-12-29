#!/bin/bash
################################################################################
# ADS-B Wi-Fi Manager Installation Script (NetworkManager Version)
# JLBMaritime - Raspberry Pi 4B Installation
################################################################################

set -e  # Exit on error

echo "=========================================="
echo "ADS-B Wi-Fi Manager Installation"
echo "JLBMaritime - NetworkManager Edition"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo ./install_nm.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Please run with sudo, not as root user"
    exit 1
fi

INSTALL_DIR="/home/$ACTUAL_USER/adsb-wifi-manager"

echo "Installing for user: $ACTUAL_USER"
echo "Installation directory: $INSTALL_DIR"
echo ""

# Update system
echo "[1/8] Updating system packages..."
apt-get update
apt-get upgrade -y

# Install required packages
echo "[2/8] Installing required packages..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    network-manager \
    avahi-daemon \
    git \
    curl \
    dnsmasq-base

# Install FlightAware dump1090-fa
echo "[3/8] Installing dump1090-fa..."
if ! command -v dump1090-fa &> /dev/null; then
    wget -O - https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.2_all.deb > /tmp/piaware-repo.deb || true
    if [ -f /tmp/piaware-repo.deb ]; then
        dpkg -i /tmp/piaware-repo.deb || true
        apt-get update
        apt-get install -y dump1090-fa
    else
        echo "WARNING: Could not install dump1090-fa automatically. Please install manually."
    fi
else
    echo "dump1090-fa already installed"
fi

# Install Python packages
echo "[4/8] Installing Python packages..."
pip3 install flask --break-system-packages || pip3 install flask

# Copy application files
echo "[5/8] Copying application files..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Backing up existing installation..."
    mv "$INSTALL_DIR" "${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$INSTALL_DIR"
cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
chown -R $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR"

# Create config directory if it doesn't exist
mkdir -p "$INSTALL_DIR/config"
mkdir -p "$INSTALL_DIR/logs"
chown -R $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR/config"
chown -R $ACTUAL_USER:$ACTUAL_USER "$INSTALL_DIR/logs"

# Configure NetworkManager
echo "[6/8] Configuring NetworkManager..."

# Ensure NetworkManager is enabled and running
systemctl enable NetworkManager
systemctl start NetworkManager

# Set regulatory domain
echo "Setting wireless regulatory domain to GB..."
iw reg set GB

# Create NetworkManager hotspot connection for wlan1
echo "Creating NetworkManager hotspot profile..."
nmcli connection delete JLBMaritime-Hotspot 2>/dev/null || true

nmcli connection add type wifi ifname wlan1 con-name JLBMaritime-Hotspot \
    autoconnect yes \
    ssid JLBMaritime-ADSB

nmcli connection modify JLBMaritime-Hotspot \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    802-11-wireless.channel 1 \
    ipv4.method shared \
    ipv4.addresses 192.168.4.1/24 \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "Admin123" \
    wifi-sec.proto rsn \
    wifi-sec.group ccmp \
    wifi-sec.pairwise ccmp

# Ensure wlan0 uses automatic DHCP for client connections
if ! nmcli connection show preconfigured &>/dev/null; then
    echo "Creating wlan0 client connection profile..."
    nmcli connection add type wifi ifname wlan0 con-name preconfigured \
        autoconnect yes
fi

# Configure mDNS (Avahi)
echo "[7/8] Configuring mDNS for ADS-B.local resolution..."
systemctl enable avahi-daemon
systemctl start avahi-daemon

# Set hostname
hostnamectl set-hostname ADS-B

# Update hosts file
cat > /etc/hosts << EOF
127.0.0.1       localhost
127.0.1.1       ADS-B
192.168.4.1     ADS-B.local

::1             localhost ip6-localhost ip6-loopback
ff02::1         ip6-allnodes
ff02::2         ip6-allrouters
EOF

# Enable IP forwarding (for hotspot internet sharing)
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p

# Install systemd services
echo "[8/8] Installing systemd services..."

# Install ADS-B Server service
cp "$INSTALL_DIR/services/adsb-server.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable adsb-server.service

# Install Web Manager service
cp "$INSTALL_DIR/services/web-manager.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable web-manager.service

# Configure sudo permissions for web interface
cat > /etc/sudoers.d/adsb-wifi-manager << EOF
# Allow web interface to control services and NetworkManager
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl start adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl show adsb-server
www-data ALL=(ALL) NOPASSWD: /usr/bin/nmcli
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl start adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/systemctl show adsb-server
root ALL=(ALL) NOPASSWD: /usr/bin/nmcli
$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli
EOF
chmod 0440 /etc/sudoers.d/adsb-wifi-manager

# Start services
echo ""
echo "Starting services..."

# Activate the hotspot
echo "Activating hotspot on wlan1..."
nmcli connection up JLBMaritime-Hotspot

# Start application services
systemctl start adsb-server.service
sleep 2
systemctl start web-manager.service

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Setup Summary:"
echo "  - Hostname: ADS-B"
echo "  - Hotspot SSID: JLBMaritime-ADSB"
echo "  - Hotspot Password: Admin123"
echo "  - Hotspot IP: 192.168.4.1"
echo "  - Web Interface: http://ADS-B.local:5000 or http://192.168.4.1:5000"
echo "  - Web Login: JLBMaritime / Admin"
echo ""
echo "Services Status:"
nmcli connection show JLBMaritime-Hotspot | grep -q GENERAL.STATE && echo "  ✓ Hotspot: Running" || echo "  ✗ Hotspot: Not Running"
systemctl is-active adsb-server && echo "  ✓ ADS-B Server: Running" || echo "  ✗ ADS-B Server: Not Running"
systemctl is-active web-manager && echo "  ✓ Web Manager: Running" || echo "  ✗ Web Manager: Not Running"
systemctl is-active dump1090-fa && echo "  ✓ dump1090-fa: Running" || echo "  ✗ dump1090-fa: Not Running (install manually if needed)"
echo ""
echo "Next Steps:"
echo "  1. Connect to Wi-Fi hotspot 'JLBMaritime-ADSB' (password: Admin123)"
echo "  2. Open browser to http://ADS-B.local:5000"
echo "  3. Login with JLBMaritime / Admin"
echo "  4. Configure your internet Wi-Fi in the Wi-Fi Manager tab"
echo "  5. Configure ADS-B endpoints in the ADS-B Configuration tab"
echo "  6. Place logo.png file in: $INSTALL_DIR/web_interface/static/"
echo ""
echo "NetworkManager Hotspot Commands:"
echo "  - Check status: nmcli connection show JLBMaritime-Hotspot"
echo "  - Start hotspot: nmcli connection up JLBMaritime-Hotspot"
echo "  - Stop hotspot: nmcli connection down JLBMaritime-Hotspot"
echo "  - List all connections: nmcli connection show"
echo ""
echo "Reboot recommended: sudo reboot"
echo "=========================================="
