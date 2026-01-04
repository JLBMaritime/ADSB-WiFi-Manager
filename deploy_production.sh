#!/bin/bash
################################################################################
# ADS-B Wi-Fi Manager - Production Deployment Script
# Deploys with HTTPS (Self-Signed SSL) and Nginx Reverse Proxy
################################################################################

set -e  # Exit on error

echo "=========================================="
echo "ADS-B Wi-Fi Manager - Production Deployment"
echo "HTTPS with Self-Signed SSL Certificate"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "ERROR: Please run as root (sudo ./deploy_production.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-$USER}
if [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Please run with sudo, not as root user"
    exit 1
fi

INSTALL_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager"
BACKUP_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager-backup-$(date +%Y%m%d_%H%M%S)"

echo "User: $ACTUAL_USER"
echo "Installation Directory: $INSTALL_DIR"
echo "Backup Directory: $BACKUP_DIR"
echo ""

# Confirm deployment
read -p "This will deploy HTTPS with self-signed SSL. Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

# Create backup
echo "[1/10] Creating backup of current installation..."
if [ -d "$INSTALL_DIR" ]; then
    cp -r "$INSTALL_DIR" "$BACKUP_DIR"
    echo "Backup created at: $BACKUP_DIR"
else
    echo "No existing installation found. Skipping backup."
fi

# Install nginx
echo "[2/10] Installing nginx..."
apt-get update
apt-get install -y nginx

# Reconfigure lighttpd to use port 8080 (not port 80)
echo "[2.5/10] Reconfiguring lighttpd for port 8080..."
if systemctl is-active --quiet lighttpd; then
    systemctl stop lighttpd
fi
if [ -f /etc/lighttpd/lighttpd.conf ]; then
    sed -i 's/server.port = 80/server.port = 8080/' /etc/lighttpd/lighttpd.conf
    echo "✓ lighttpd reconfigured for port 8080"
fi

# Stop nginx for configuration
systemctl stop nginx

# Generate SSL certificate
echo "[3/10] Generating self-signed SSL certificate..."
mkdir -p "$INSTALL_DIR/ssl"
cd "$INSTALL_DIR/ssl"

# Run the SSL generation script
chmod +x "$INSTALL_DIR/ssl/generate_self_signed.sh"
"$INSTALL_DIR/ssl/generate_self_signed.sh"

# Install certificate
echo "[4/10] Installing SSL certificate..."
mkdir -p /etc/ssl/adsb-manager
cp "$INSTALL_DIR/ssl/adsb-manager.crt" /etc/ssl/adsb-manager/
cp "$INSTALL_DIR/ssl/adsb-manager.key" /etc/ssl/adsb-manager/
chmod 600 /etc/ssl/adsb-manager/adsb-manager.key
chmod 644 /etc/ssl/adsb-manager/adsb-manager.crt

# Configure nginx
echo "[5/10] Configuring nginx..."

# Remove default nginx site
rm -f /etc/nginx/sites-enabled/default

# Copy our nginx configuration
cp "$INSTALL_DIR/nginx/adsb-manager.conf" /etc/nginx/sites-available/
ln -sf /etc/nginx/sites-available/adsb-manager.conf /etc/nginx/sites-enabled/

# Test nginx configuration
nginx -t

# Update Flask to bind to localhost only (security)
echo "[6/10] Updating Flask for production mode..."

# Update the web-manager service to bind to localhost
sed -i 's/--host 0.0.0.0/--host 127.0.0.1/g' /etc/systemd/system/web-manager.service || true

# Reload systemd
systemctl daemon-reload

# Set directory permissions for nginx access
echo "[6.5/10] Setting directory permissions..."
chmod 755 /home/$ACTUAL_USER
chmod 755 "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR/web_interface"
chmod 755 "$INSTALL_DIR/web_interface/static"
echo "✓ Directory permissions set"

# Configure firewall
echo "[7/10] Configuring firewall (UFW)..."

# Install UFW if not present
apt-get install -y ufw

# Configure firewall rules
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# Allow SSH
ufw allow 22/tcp comment 'SSH'

# Allow HTTP (will redirect to HTTPS)
ufw allow 80/tcp comment 'HTTP'

# Allow HTTPS
ufw allow 443/tcp comment 'HTTPS'

# Allow dump1090 SkyAware (lighttpd JSON endpoint)
ufw allow 8080/tcp comment 'dump1090 SkyAware'

# Allow mDNS
ufw allow 5353/udp comment 'mDNS'

# Enable firewall
echo "y" | ufw enable

# Start services
echo "[8/10] Starting services..."

# Start lighttpd on port 8080
if [ -f /etc/lighttpd/lighttpd.conf ]; then
    systemctl enable lighttpd
    systemctl start lighttpd
    echo "✓ lighttpd started on port 8080"
fi

# Restart web-manager service
systemctl restart web-manager

# Start nginx
systemctl enable nginx
systemctl start nginx

# Verify services
echo "[9/10] Verifying services..."

sleep 2

# Check web-manager
if systemctl is-active --quiet web-manager; then
    echo "✓ Web Manager service: Running"
else
    echo "✗ Web Manager service: Failed"
fi

# Check nginx
if systemctl is-active --quiet nginx; then
    echo "✓ Nginx service: Running"
else
    echo "✗ Nginx service: Failed"
fi

# Check UFW
if ufw status | grep -q "Status: active"; then
    echo "✓ Firewall: Active"
else
    echo "✗ Firewall: Inactive"
fi

# Create production mode flag
echo "[10/10] Setting production mode flag..."
touch "$INSTALL_DIR/.production_mode"
echo "$(date)" > "$INSTALL_DIR/.production_mode"

echo ""
echo "=========================================="
echo "Production Deployment Complete!"
echo "=========================================="
echo ""
echo "Access URLs:"
echo "  HTTPS: https://ADS-B.local"
echo "  HTTPS: https://192.168.4.1"
echo "  HTTP:  http://ADS-B.local (redirects to HTTPS)"
echo ""
echo "Login Credentials:"
echo "  Username: JLBMaritime"
echo "  Password: Admin"
echo ""
echo "Certificate Information:"
echo "  Type: Self-Signed"
echo "  Location: /etc/ssl/adsb-manager/"
echo "  Validity: 10 years"
echo ""
echo "⚠️  IMPORTANT - First Access:"
echo "  1. Navigate to https://ADS-B.local"
echo "  2. Browser will show security warning (expected)"
echo "  3. Click 'Advanced' → 'Accept Risk and Continue'"
echo "  4. Browser will remember this (one-time only)"
echo ""
echo "Security Status:"
echo "  ✓ HTTPS enabled (TLS 1.2/1.3)"
echo "  ✓ HTTP → HTTPS redirect active"
echo "  ✓ Flask bound to localhost only"
echo "  ✓ Firewall configured and active"
echo "  ✓ Security headers enabled"
echo ""
echo "Services:"
systemctl is-active web-manager && echo "  ✓ Web Manager: Running" || echo "  ✗ Web Manager: Not Running"
systemctl is-active nginx && echo "  ✓ Nginx: Running" || echo "  ✗ Nginx: Not Running"
systemctl is-active adsb-server && echo "  ✓ ADS-B Server: Running" || echo "  ✗ ADS-B Server: Not Running"
echo ""
echo "Backup Location:"
echo "  $BACKUP_DIR"
echo ""
echo "To rollback:"
echo "  sudo ./rollback_production.sh"
echo ""
echo "For troubleshooting:"
echo "  sudo nginx -t                    # Test nginx config"
echo "  sudo systemctl status nginx      # Check nginx status"
echo "  sudo systemctl status web-manager # Check Flask status"
echo "  sudo tail -f /var/log/nginx/error.log  # View nginx errors"
echo "=========================================="
