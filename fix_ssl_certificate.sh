#!/bin/bash
################################################################################
# Fix SSL Certificate Validity Issue
# Regenerates certificate with 365-day validity (browser-compliant)
################################################################################

echo "==========================================="
echo "SSL Certificate Fix"
echo "Regenerating with 365-day validity"
echo "==========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo ./fix_ssl_certificate.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Please run with sudo, not as root user"
    exit 1
fi

INSTALL_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager"
SSL_DIR="$INSTALL_DIR/ssl"

echo "User: $ACTUAL_USER"
echo "SSL Directory: $SSL_DIR"
echo ""

# Check if SSL directory exists
if [ ! -d "$SSL_DIR" ]; then
    echo "ERROR: SSL directory not found: $SSL_DIR"
    exit 1
fi

echo "[1/5] Backing up old certificate..."
cd "$SSL_DIR"
if [ -f "adsb-manager.crt" ]; then
    cp adsb-manager.crt adsb-manager.crt.backup.$(date +%Y%m%d_%H%M%S)
    cp adsb-manager.key adsb-manager.key.backup.$(date +%Y%m%d_%H%M%S)
    echo "✓ Old certificates backed up"
else
    echo "No existing certificates found - will create new ones"
fi

echo ""
echo "[2/5] Generating new SSL certificate (365 days)..."
chmod +x "$SSL_DIR/generate_self_signed.sh"
cd "$SSL_DIR"
./generate_self_signed.sh

echo ""
echo "[3/5] Installing new certificate to system..."
mkdir -p /etc/ssl/adsb-manager
cp "$SSL_DIR/adsb-manager.crt" /etc/ssl/adsb-manager/
cp "$SSL_DIR/adsb-manager.key" /etc/ssl/adsb-manager/
chmod 600 /etc/ssl/adsb-manager/adsb-manager.key
chmod 644 /etc/ssl/adsb-manager/adsb-manager.crt
echo "✓ Certificate installed to /etc/ssl/adsb-manager/"

echo ""
echo "[4/5] Restarting nginx..."
systemctl restart nginx

echo ""
echo "[5/5] Verifying certificate..."
sleep 2

# Check nginx status
if systemctl is-active --quiet nginx; then
    echo "✓ nginx is running"
else
    echo "✗ nginx failed to start - check logs: sudo journalctl -u nginx -n 50"
    exit 1
fi

# Display certificate details
echo ""
echo "New Certificate Details:"
openssl x509 -in /etc/ssl/adsb-manager/adsb-manager.crt -noout -subject -dates

echo ""
echo "==========================================="
echo "SSL Certificate Fix Complete!"
echo "==========================================="
echo ""
echo "Changes Made:"
echo "  ✓ Certificate validity: 365 days (1 year)"
echo "  ✓ Old certificates backed up"
echo "  ✓ New certificate installed"
echo "  ✓ nginx restarted"
echo ""
echo "Next Steps:"
echo "  1. On iPhone: Close all browser tabs"
echo "  2. Clear iPhone Safari cache (optional)"
echo "  3. Navigate to: https://ADS-B.local"
echo "  4. Accept the certificate warning (one-time)"
echo "  5. You should now access the web interface!"
echo ""
echo "Note: You may still see a warning because it's self-signed,"
echo "but 'NET::ERR_CERT_VALIDITY_TOO_LONG' should be gone."
echo ""
echo "For iOS:"
echo "  Safari: Tap 'Show Details' → 'visit this website'"
echo "  Chrome: May still be strict - use Safari instead"
echo "==========================================="
