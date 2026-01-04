#!/bin/bash
################################################################################
# ADS-B Wi-Fi Manager - Rollback Production Deployment
# Reverts to development mode (HTTP without nginx)
################################################################################

set -e  # Exit on error

echo "=========================================="
echo "ADS-B Wi-Fi Manager - Rollback Production"
echo "Reverting to Development Mode"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo ./rollback_production.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Please run with sudo, not as root user"
    exit 1
fi

INSTALL_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager"

echo "User: $ACTUAL_USER"
echo "Installation Directory: $INSTALL_DIR"
echo ""

# Confirm rollback
read -p "This will rollback to development mode (HTTP only). Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

echo "[1/7] Stopping nginx..."
systemctl stop nginx || true
systemctl disable nginx || true

echo "[2/7] Removing nginx configuration..."
rm -f /etc/nginx/sites-enabled/adsb-manager.conf
rm -f /etc/nginx/sites-available/adsb-manager.conf

echo "[2.5/7] Reverting lighttpd to port 80..."
if [ -f /etc/lighttpd/lighttpd.conf ]; then
    sed -i 's/server.port = 8080/server.port = 80/' /etc/lighttpd/lighttpd.conf
    systemctl restart lighttpd || true
    echo "✓ lighttpd reverted to port 80"
fi

echo "[3/7] Updating Flask to bind to all interfaces..."
sed -i 's/--host 127.0.0.1/--host 0.0.0.0/g' /etc/systemd/system/web-manager.service || true
systemctl daemon-reload

echo "[4/7] Removing production mode flag..."
rm -f "$INSTALL_DIR/.production_mode"

echo "[5/7] Restarting web-manager service..."
systemctl restart web-manager

echo "[6/7] Disabling strict firewall rules..."
# Reset firewall to allow direct access to port 5000
ufw allow 5000/tcp comment 'Flask Development'

echo "[7/7] Verifying services..."
sleep 2

if systemctl is-active --quiet web-manager; then
    echo "✓ Web Manager service: Running"
else
    echo "✗ Web Manager service: Failed"
fi

echo ""
echo "=========================================="
echo "Rollback Complete!"
echo "=========================================="
echo ""
echo "Access URLs:"
echo "  HTTP: http://ADS-B.local:5000"
echo "  HTTP: http://192.168.4.1:5000"
echo ""
echo "Note: nginx has been stopped and disabled"
echo "Note: HTTPS is no longer available"
echo "Note: Flask is accessible on port 5000"
echo ""
echo "To re-deploy production mode:"
echo "  sudo ./deploy_production.sh"
echo "=========================================="
