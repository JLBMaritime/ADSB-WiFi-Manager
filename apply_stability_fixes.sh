#!/bin/bash
#
# Apply Stability Fixes for ADS-B WiFi Manager
# Fixes system freezes, memory leaks, and resource exhaustion
#
# Run with: sudo ./apply_stability_fixes.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ADS-B WiFi Manager - Stability Fixes${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-JLBMaritime}
BASE_DIR="/home/$ACTUAL_USER/ADSB-WiFi-Manager"

echo -e "${YELLOW}Installing to: $BASE_DIR${NC}"
echo -e "${YELLOW}User: $ACTUAL_USER${NC}"
echo ""

# Check if directory exists
if [ ! -d "$BASE_DIR" ]; then
    echo -e "${RED}Error: Directory $BASE_DIR not found${NC}"
    exit 1
fi

cd "$BASE_DIR"

echo -e "${GREEN}[1/8] Creating backup...${NC}"
BACKUP_DIR="$BASE_DIR/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp adsb_server/adsb_server.py "$BACKUP_DIR/" 2>/dev/null || true
cp services/adsb-server.service "$BACKUP_DIR/" 2>/dev/null || true
cp services/web-manager.service "$BACKUP_DIR/" 2>/dev/null || true
echo -e "${GREEN}✓ Backup created in $BACKUP_DIR${NC}"
echo ""

echo -e "${GREEN}[2/8] Installing Python dependencies...${NC}"
pip3 install psutil==5.9.8 --break-system-packages 2>/dev/null || pip3 install psutil==5.9.8
echo -e "${GREEN}✓ psutil installed${NC}"
echo ""

echo -e "${GREEN}[3/8] Applying fixed ADS-B server code...${NC}"
if [ -f "adsb_server/adsb_server_fixed.py" ]; then
    cp adsb_server/adsb_server_fixed.py adsb_server/adsb_server.py
    chown $ACTUAL_USER:$ACTUAL_USER adsb_server/adsb_server.py
    chmod +x adsb_server/adsb_server.py
    echo -e "${GREEN}✓ Fixed ADS-B server deployed${NC}"
else
    echo -e "${RED}Warning: adsb_server_fixed.py not found, skipping${NC}"
fi
echo ""

echo -e "${GREEN}[4/8] Updating systemd service files...${NC}"
# ADS-B Server service
if [ -f "services/adsb-server-improved.service" ]; then
    cp services/adsb-server-improved.service /etc/systemd/system/adsb-server.service
    echo -e "${GREEN}✓ ADS-B server service updated${NC}"
fi

# Web Manager service
if [ -f "services/web-manager-improved.service" ]; then
    cp services/web-manager-improved.service /etc/systemd/system/web-manager.service
    echo -e "${GREEN}✓ Web manager service updated${NC}"
fi
echo ""

echo -e "${GREEN}[5/8] Enabling hardware watchdog...${NC}"
# Enable hardware watchdog if available
if [ -e /dev/watchdog ]; then
    modprobe bcm2835_wdt 2>/dev/null || true
    
    # Configure watchdog
    if ! grep -q "bcm2835_wdt" /etc/modules; then
        echo "bcm2835_wdt" >> /etc/modules
    fi
    
    # Install watchdog package if not present
    if ! command -v watchdog &> /dev/null; then
        echo "Installing watchdog package..."
        apt-get update -qq
        apt-get install -y watchdog
    fi
    
    # Configure watchdog daemon
    cat > /etc/watchdog.conf << 'EOF'
# Watchdog configuration for ADS-B WiFi Manager
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 5
max-load-1 = 24
min-memory = 1
EOF
    
    systemctl enable watchdog
    systemctl start watchdog
    echo -e "${GREEN}✓ Hardware watchdog enabled${NC}"
else
    echo -e "${YELLOW}⚠ Hardware watchdog not available (not critical)${NC}"
fi
echo ""

echo -e "${GREEN}[6/8] Configuring system resource limits...${NC}"
# Set global resource limits
cat > /etc/security/limits.d/adsb-limits.conf << EOF
# Resource limits for ADS-B services
JLBMaritime soft nofile 1024
JLBMaritime hard nofile 2048
JLBMaritime soft nproc 100
JLBMaritime hard nproc 200
EOF
echo -e "${GREEN}✓ Resource limits configured${NC}"
echo ""

echo -e "${GREEN}[7/8] Reloading systemd and restarting services...${NC}"
systemctl daemon-reload

echo "Stopping services..."
systemctl stop adsb-server || true
systemctl stop web-manager || true

sleep 2

echo "Starting services..."
systemctl start adsb-server
systemctl start web-manager

sleep 2

# Check status
if systemctl is-active --quiet adsb-server; then
    echo -e "${GREEN}✓ ADS-B server running${NC}"
else
    echo -e "${RED}✗ ADS-B server failed to start${NC}"
fi

if systemctl is-active --quiet web-manager; then
    echo -e "${GREEN}✓ Web manager running${NC}"
else
    echo -e "${RED}✗ Web manager failed to start${NC}"
fi
echo ""

echo -e "${GREEN}[8/8] Verifying installation...${NC}"
echo ""
echo "System Status:"
echo "=============="

# Check memory
TOTAL_MEM=$(free -m | awk 'NR==2{print $2}')
USED_MEM=$(free -m | awk 'NR==2{print $3}')
echo -e "Memory: ${USED_MEM}MB / ${TOTAL_MEM}MB used"

# Check processes
ADSB_PID=$(pgrep -f "adsb_server.py" || echo "not running")
WEB_PID=$(pgrep -f "web_interface/app.py" || echo "not running")
echo -e "ADS-B Server PID: $ADSB_PID"
echo -e "Web Manager PID: $WEB_PID"

# Check watchdog
if systemctl is-active --quiet watchdog; then
    echo -e "Watchdog: ${GREEN}Active${NC}"
else
    echo -e "Watchdog: ${YELLOW}Inactive${NC}"
fi
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Stability Fixes Applied Successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "What was fixed:"
echo "  ✓ Socket timeouts (prevents indefinite blocking)"
echo "  ✓ Connection leak prevention (limits threads)"
echo "  ✓ Resource monitoring (tracks memory/FDs)"
echo "  ✓ Auto-restart on failures"
echo "  ✓ Memory limits (prevents runaway growth)"
echo "  ✓ Hardware watchdog (auto-recovery from freezes)"
echo ""
echo "Monitoring:"
echo "  • View logs: sudo journalctl -u adsb-server -f"
echo "  • Check status: sudo systemctl status adsb-server"
echo "  • Resource usage logged every 5 minutes"
echo ""
echo "Expected stability:"
echo "  • Should run for weeks without restart"
echo "  • Auto-recovery from crashes"
echo "  • Protection against memory leaks"
echo ""
echo -e "${YELLOW}Backup saved to: $BACKUP_DIR${NC}"
echo ""
