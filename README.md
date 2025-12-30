# ADS-B Wi-Fi Manager

**JLBMaritime - Integrated ADS-B Data Management System**

A comprehensive solution for Raspberry Pi 4B that combines ADS-B aircraft tracking with powerful web-based and command-line WiFi management interfaces.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Quick Start Guide](#quick-start-guide)
- [Web Interface](#web-interface)
- [Interactive CLI](#interactive-cli)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Advanced Topics](#advanced-topics)

---

## 🎯 Overview

This system provides a complete ADS-B (Automatic Dependent Surveillance-Broadcast) data reception, filtering, and forwarding solution with integrated WiFi management via both web and command-line interfaces. Perfect for maritime or aviation tracking applications requiring reliable data forwarding and flexible network configuration.

### What it Does

1. **Receives ADS-B Data**: Captures aircraft tracking data via FlightAware SDR USB dongle
2. **Multiple Output Formats**: SBS1 streaming, JSON objects, or JSON→SBS1 conversion
3. **Filters Aircraft**: By specific ICAO IDs and/or maximum altitude
4. **Forwards Data**: Sends filtered data to multiple TCP endpoints
5. **Manages WiFi**: Hotspot + web/CLI interfaces for network management
6. **Dual Interface**: Web browser OR interactive terminal control
7. **Remote Access**: Full SSH management with color-coded CLI

---

## ✨ Features

### ADS-B Server
- ✅ **Three Output Modes**:
  - **SBS1 Streaming** - Real-time BaseStation format from dump1090
  - **JSON Objects** - Individual aircraft as JSON (polled every second)
  - **JSON→SBS1** - JSON data converted to SBS1 format
- ✅ **Dual Filtering**:
  - ICAO aircraft ID filter (specific IDs or all aircraft)
  - Altitude filter (configurable maximum altitude)
- ✅ Multiple TCP endpoint forwarding with auto-reconnect
- ✅ 72-hour automatic log rotation
- ✅ Runs as systemd service (auto-start on boot)
- ✅ Live configuration reload (no restart needed)

### WiFi Manager
- ✅ Built-in hotspot (wlan1) for configuration access
- ✅ Scan and connect to WiFi networks (wlan0)
- ✅ Save and manage network profiles
- ✅ Network diagnostics and ping tests
- ✅ mDNS support (ADS-B.local domain)
- ✅ Signal strength indicators

### Web Interface
- ✅ **Dashboard**: Real-time system status
- ✅ **WiFi Manager**: Scan, connect, forget networks
- ✅ **ADS-B Configuration**: Output formats, filters, endpoints
- ✅ **Logs & Troubleshooting**: Live viewer with filtering
- ✅ **Settings**: Password management, backups
- ✅ Responsive design (desktop and mobile)
- ✅ Secure authentication

### Interactive CLI ⭐ **NEW**
- ✅ **Global Command**: Type `adsb-cli` from anywhere
- ✅ **Full Feature Parity**: Everything the web UI can do
- ✅ **Color-Coded Interface**: Green/Red/Yellow status indicators
- ✅ **Menu-Driven**: Easy number-based navigation
- ✅ **SSH Friendly**: Perfect for remote terminal access
- ✅ **No Authentication**: Relies on SSH security
- ✅ **Real-Time Status**: Live system information display

---

## 🖥️ System Requirements

### Hardware
- **Raspberry Pi 4B** (2GB RAM minimum, 4GB recommended)
- **Two WiFi interfaces**: wlan0 and wlan1 (built-in + USB adapter)
- **FlightAware SDR USB stick** with antenna
- **MicroSD card** (16GB minimum, Class 10)
- **Power supply**: Official Raspberry Pi 5V/3A adapter

### Software
- **OS**: Raspberry Pi OS 64-bit (Bookworm) - Lite or Desktop
- **Python**: 3.9 or higher (included in OS)
- **Internet connection**: For initial setup

---

## 📦 Installation

### Automated Installation

1. **Clone the repository** to your Raspberry Pi:
   ```bash
   cd ~
   git clone <repository-url> ADSB-WiFi-Manager
   cd ADSB-WiFi-Manager
   ```

2. **Run the installation script**:
   ```bash
   sudo ./install.sh
   ```

3. **Reboot** when installation completes:
   ```bash
   sudo reboot
   ```

### What Gets Installed

The automated installer handles everything:
- ✅ System package updates
- ✅ Python3 and Flask web framework
- ✅ dump1090-fa for ADS-B reception
- ✅ hostapd and dnsmasq for WiFi hotspot
- ✅ Avahi daemon for mDNS (ADS-B.local)
- ✅ dos2unix for line ending conversion
- ✅ Systemd services for auto-start
- ✅ wlan1 hotspot configuration (192.168.4.1)
- ✅ Interactive CLI with global `adsb-cli` command
- ✅ Hostname set to "ADS-B"

**Installation Time**: 15-30 minutes (depending on internet speed)

---

## 🚀 Quick Start Guide

### Step 1: Connect to Hotspot
- **WiFi Network**: `JLBMaritime-ADSB`
- **Password**: `Admin123`

### Step 2: Access Web Interface
- **URL**: `http://ADS-B.local:5000` or `http://192.168.4.1:5000`
- **Username**: `JLBMaritime`
- **Password**: `Admin`

### Step 3: Configure Internet WiFi
1. Click "WiFi Manager" tab
2. Click "Scan Networks"
3. Select your WiFi network
4. Enter password and connect

### Step 4: Configure ADS-B

1. Go to "ADS-B Configuration" tab
2. **Select Output Format**:
   - SBS1 (for most applications)
   - JSON (for custom processing)
   - JSON→SBS1 (JSON source, SBS1 output)
3. **Set Filter**:
   - All Aircraft OR Specific ICAOs
   - Optional: Enable altitude filter
4. **Add Endpoints**:
   - Click "Add Endpoint"
   - Enter IP address and port
   - Test connection
5. Click "Save Configuration"

### Step 5: Access via SSH (Optional)
```bash
ssh JLBMaritime@ADS-B.local
adsb-cli  # Launch interactive menu
```

---

## 🌐 Web Interface

### Dashboard Tab
**Real-time monitoring:**
- ADS-B server status (Running/Stopped, uptime)
- WiFi connection (SSID, IP, signal strength)
- System hostname and basic metrics

### WiFi Manager Tab
**Network management:**
- **Current Connection**: Shows active network with IP
- **Scan Networks**: Displays available WiFi with signal bars
- **Saved Networks**: Manage saved profiles (connect/forget)
- **Diagnostics**: View interface info
- **Ping Test**: Test internet connectivity

### ADS-B Configuration Tab
**Server configuration:**

**Service Control**:
- Start/Stop/Restart server
- View current status

**Output Format**:
- **SBS1 Streaming**: Real-time data from dump1090 port 30003
- **JSON Objects**: Poll dump1090 JSON API, send individual aircraft
- **JSON→SBS1**: Poll JSON, convert to SBS1 format

**Aircraft Filters**:
- **Mode**: All Aircraft or Specific ICAOs
- **ICAO List**: Comma-separated codes (e.g., A92F2D,A932E4,A9369B,A93A52)
- **Altitude Filter**: Enable/disable with maximum altitude setting

**TCP Endpoints**:
- Add multiple IP:Port destinations
- Test connection to each endpoint
- Remove endpoints

### Logs & Troubleshooting Tab
**Monitoring and diagnostics:**
- View logs with filtering (All/Errors/Warnings/Info)
- Manual refresh
- Download or clear logs
- System diagnostics

### Settings Tab
**System management:**
- Change web interface password
- View system information (hostname, OS, uptime)
- Backup/restore configuration files

---

## 🖥️ Interactive CLI

### Overview

The interactive CLI provides **full feature parity** with the web interface, perfect for SSH remote access. Color-coded, menu-driven interface makes management intuitive without memorizing commands.

### Launching the CLI

**From anywhere on the system:**
```bash
adsb-cli
```

**Via SSH:**
```bash
ssh JLBMaritime@ADS-B.local
adsb-cli
```

### Main Menu

```
═══════════════════════════════════════════════════════
   JLBMaritime ADS-B & WiFi Manager - Remote CLI
═══════════════════════════════════════════════════════

System Status:
  ADS-B Server: ● RUNNING (Uptime: 2h 15m)
  WiFi: Connected to "MyNetwork" (192.168.1.50)
  Hostname: ADS-B

───────────────────────────────────────────────────────

[1] Dashboard & Status
[2] WiFi Manager
[3] ADS-B Configuration
[4] Service Control
[5] Logs & Troubleshooting
[6] Settings
[7] Exit

Enter choice [1-7]:
```

### [1] Dashboard & Status

Displays detailed system information:
- ADS-B server status and uptime
- WiFi connection details
- System hostname
- System uptime and load average

### [2] WiFi Manager

**Full WiFi management:**

```
━━━ WiFi Manager ━━━

Current Network: MyNetwork (192.168.1.50) ✓

[1] Scan for Networks
[2] View Saved Networks
[3] Connect to Network
[4] Forget Network
[5] Run Ping Test
[6] Network Diagnostics
[7] Back to Main Menu
```

**Features:**
- **Scan Networks**: Shows SSIDs with signal strength bars (▮▮▮▮)
- **Saved Networks**: List with current network highlighted
- **Connect**: Secure password prompt (hidden input)
- **Forget**: Remove saved network (protects active connection)
- **Ping Test**: Custom host or default to 8.8.8.8
- **Diagnostics**: Interface, IP, gateway, DNS info

### [3] ADS-B Configuration

**Complete server configuration:**

```
━━━ ADS-B Configuration ━━━

Current Settings:
  Output Format: JSON→SBS1
  Filter Mode: SPECIFIC
  Altitude Filter: OFF
  Endpoints: 2 configured

[1] Set Output Format
[2] Configure Filters
[3] Manage Endpoints
[4] View Full Configuration
[5] Save & Restart Server
[6] Back to Main Menu
```

**Submenus:**

**Set Output Format:**
- [1] SBS1 Streaming
- [2] JSON Objects
- [3] JSON→SBS1

**Configure Filters:**
- Set filter mode (All/Specific)
- Manage ICAO list (add/remove/clear)
- Configure altitude filter (enable/disable, set max)

**Manage Endpoints:**
- Add endpoint (with name, IP, port)
- Remove endpoint
- Test endpoint connection

### [4] Service Control

**Manage ADS-B server:**
- Start server
- Stop server  
- Restart server
- View detailed status

### [5] Logs & Troubleshooting

**Log management:**
- View recent logs (last 5 lines)
- Filter by level (ERROR/WARNING/INFO)
- Live tail mode (Ctrl+C to exit)
- Clear logs

### [6] Settings

**System settings:**
- System information (hostname, OS, uptime, IP)
- Backup configuration (creates timestamped zip file)

### CLI Features

**User Experience:**
- ✅ **Color-Coded**: Green (success), Red (error), Yellow (warning), Cyan (info)
- ✅ **Status Indicators**: ● GREEN/RED for running/stopped
- ✅ **Signal Strength**: Visual bars for WiFi strength
- ✅ **Confirmation Prompts**: Prevents accidental destructive operations
- ✅ **Table Formatting**: Clean data presentation
- ✅ **Navigation**: Number selection, back buttons at every level
- ✅ **Error Handling**: Clear, helpful error messages

---

## ⚙️ Configuration

### Default Credentials

**Hotspot WiFi**:
- SSID: `JLBMaritime-ADSB`
- Password: `Admin123`
- IP Range: 192.168.4.10-50

**Web/SSH Login**:
- Username: `JLBMaritime`
- Password: `Admin`

⚠️ **Important**: Change default passwords after installation!

### Configuration Files

**ADS-B Server Config**  
Location: `/home/JLBMaritime/ADSB-WiFi-Manager/config/adsb_server_config.conf`

```ini
[Dump1090]
host = 127.0.0.1
sbs1_port = 30003
json_port = 8080

[Output]
format = sbs1  # Options: sbs1, json, json_to_sbs1

[Filter]
mode = specific  # Options: all, specific
icao_list = A92F2D,A932E4,A9369B,A93A52
altitude_filter_enabled = false
max_altitude = 10000

[Endpoints]
count = 2
endpoint_0_name = Main Server
endpoint_0_ip = 192.168.1.100
endpoint_0_port = 30003
endpoint_1_name = Backup Server
endpoint_1_ip = 10.0.0.50
endpoint_1_port = 30003
```

**Web Interface Config**  
Location: `/home/JLBMaritime/ADSB-WiFi-Manager/config/web_config.conf`

```ini
[Auth]
username = JLBMaritime
password = Admin
```

### Output Format Details

**1. SBS1 Streaming** (Default)
- Connects to dump1090-fa port 30003
- Real-time SBS1 (BaseStation) format
- Best for: Most tracking software, VirtualRadar, etc.
- Lowest latency

**2. JSON Objects**
- Polls dump1090-fa JSON API (port 8080) every second
- Sends individual aircraft as JSON objects
- Best for: Custom processing, databases, web apps
- More detailed data fields

**3. JSON→SBS1**
- Polls JSON API, converts to SBS1 format
- Best for: When JSON is only source but need SBS1 output
- Slightly higher latency than direct SBS1

### Altitude Filter

When enabled, filters aircraft by barometric altitude:
- Works with both "All" and "Specific" ICAO modes
- Altitude in feet
- Uses `alt_baro` or `alt_geom` from aircraft data
- Example: Set to 10000 to only track aircraft below 10,000 feet

---

## 🔍 Troubleshooting

### Common Issues

#### 1. WiFi Hotspot Not Visible

**Symptoms**: Cannot see "JLBMaritime-ADSB" network

**Solutions**:
```bash
# Check if hostapd is running
sudo systemctl status hostapd

# Check wlan1 interface
iwconfig wlan1

# Should show "Mode:Master" for AP mode
iw dev wlan1 info

# Restart hotspot
sudo systemctl restart hostapd dnsmasq

# Verify IP address
ip addr show wlan1  # Should be 192.168.4.1
```

#### 2. NetworkManager Interfering with wlan1

**Problem**: Hotspot disappears, wlan1 connects to WiFi networks

**Solution**: Already handled by installer, but if needed:
```bash
# Unmanage wlan1 from NetworkManager
sudo tee /etc/NetworkManager/conf.d/unmanage-wlan1.conf > /dev/null <<EOF
[keyfile]
unmanaged-devices=interface-name:wlan1
EOF

sudo systemctl restart NetworkManager
```

#### 3. Cannot Access Web Interface

**Problem**: Browser can't reach ADS-B.local

**Solutions**:
1. Try direct IP: `http://192.168.4.1:5000`
2. Ensure connected to JLBMaritime-ADSB hotspot
3. Check web service:
   ```bash
   sudo systemctl status web-manager
   sudo systemctl restart web-manager
   ```

#### 4. ADS-B Server Not Receiving Data

**Problem**: No aircraft data appears

**Check dump1090-fa**:
```bash
# Verify dump1090-fa is running
sudo systemctl status dump1090-fa

# Check for SDR dongle
lsusb | grep -i rtl

# Test SBS1 connection
telnet 127.0.0.1 30003

# Test JSON endpoint
curl http://127.0.0.1:8080/data/aircraft.json
```

#### 5. CLI Line Ending Error

**Problem**: `python3\r: No such file or directory`

**Solution**: Already handled by installer's dos2unix conversion, but if needed:
```bash
dos2unix ~/ADSB-WiFi-Manager/cli/*.py
```

#### 6. CLI Module Not Found

**Problem**: `ModuleNotFoundError: No module named 'cli'`

**Solution**: Fixed in latest version with `os.path.realpath()`, ensure you have the latest code

### Performance Optimization

**Reduce CPU Usage**:
```bash
# Check CPU usage
htop

# Reduce dump1090 gain if needed
sudo nano /etc/default/dump1090-fa
# Add: --gain 40
```

**Free Disk Space**:
```bash
# Check disk space
df -h

# Clear old logs
sudo truncate -s 0 ~/ADSB-WiFi-Manager/logs/adsb_server.log
```

---

## 🏗️ Architecture

### System Overview

```
┌────────────────────────────────────────────────────────┐
│           Raspberry Pi 4B (ADS-B)                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│  ┌──────────────┐                                     │
│  │ FlightAware  │ USB                                 │
│  │  SDR Stick   ├──────┐                              │
│  └──────────────┘      │                              │
│                        ▼                               │
│                 ┌─────────────────┐                   │
│                 │  dump1090-fa    │                   │
│                 │   (Decoder)     │                   │
│                 │                 │                   │
│                 │ Port 30003:SBS1 │                   │
│                 │ Port 8080: JSON │                   │
│                 └────────┬────────┘                   │
│                          │                             │
│                          ▼                             │
│                 ┌────────────────────┐                │
│                 │   ADS-B Server     │                │
│                 │    (Python 3)      │                │
│                 │                    │                │
│                 │ 3 Output Modes:    │                │
│                 │ • SBS1 Stream      │                │
│                 │ • JSON Objects     │                │
│                 │ • JSON→SBS1        │                │
│                 │                    │                │
│                 │ Dual Filters:      │                │
│                 │ • ICAO IDs         │                │
│                 │ • Altitude         │                │
│                 └─────────┬──────────┘                │
│                           │                            │
│                           ▼                            │
│                   TCP Endpoints                        │
│                   (Multiple IPs)                       │
│                                                        │
│  ┌───────────────────────────────────────────┐        │
│  │        Web Interface (Flask)              │        │
│  │  http://ADS-B.local:5000                  │        │
│  │                                           │        │
│  │  • Dashboard                              │        │
│  │  • WiFi Manager                           │        │
│  │  • ADS-B Configuration                    │        │
│  │  • Logs & Troubleshooting                 │        │
│  │  • Settings                               │        │
│  └───────────────────────────────────────────┘        │
│                                                        │
│  ┌───────────────────────────────────────────┐        │
│  │     Interactive CLI (Python 3)            │        │
│  │     Command: adsb-cli                     │        │
│  │                                           │        │
│  │  • Color-coded menus                      │        │
│  │  • WiFi management                        │        │
│  │  • ADS-B configuration                    │        │
│  │  • Service control                        │        │
│  │  • Logs viewing                           │        │
│  │  • Settings & backup                      │        │
│  └───────────────────────────────────────────┘        │
│                                                        │
│  ┌────────────────────────────────────┐               │
│  │   WiFi Hotspot (wlan1)             │               │
│  │   - hostapd + dnsmasq              │               │
│  │   - SSID: JLBMaritime-ADSB         │               │
│  │   - IP: 192.168.4.1                │               │
│  │   - mDNS: ADS-B.local              │               │
│  └────────────────────────────────────┘               │
│                                                        │
│  ┌────────────────────────────────────┐               │
│  │   Internet WiFi (wlan0)            │               │
│  │   - wpa_supplicant                 │               │
│  │   - DHCP client                    │               │
│  └────────────────────────────────────┘               │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### File Structure

```
/home/JLBMaritime/ADSB-WiFi-Manager/
├── adsb_server/
│   ├── adsb_server.py          # Main ADS-B server
│   └── adsb_cli.py              # Legacy CLI (basic commands)
├── cli/
│   ├── __init__.py              # Package initialization
│   ├── adsb_cli.py              # Interactive CLI entry point
│   ├── utils.py                 # Colors, tables, formatting
│   ├── wifi_menu.py             # WiFi management menu
│   ├── adsb_menu.py             # ADS-B configuration menu
│   ├── service_menu.py          # Service control menu
│   ├── logs_menu.py             # Log viewing menu
│   └── settings_menu.py         # Settings menu
├── wifi_manager/
│   └── wifi_controller.py       # WiFi backend
├── web_interface/
│   ├── app.py                   # Flask application
│   ├── templates/
│   │   ├── index.html           # Main dashboard
│   │   └── login.html           # Login page
│   └── static/
│       ├── css/style.css        # Stylesheet
│       ├── js/main.js           # Frontend JavaScript
│       └── logo.png             # JLBMaritime logo
├── config/
│   ├── adsb_server_config.conf  # ADS-B configuration
│   └── web_config.conf          # Web auth config
├── services/
│   ├── adsb-server.service      # Systemd service
│   ├── web-manager.service      # Web service
│   └── wlan1-config.service     # wlan1 setup service
├── logs/
│   └── adsb_server.log          # Application logs
├── install.sh                   # Installation script
└── README.md                    # This file
```

### Network Flow

**Data Reception**: SDR → dump1090-fa → ADS-B Server → Filter → TCP Endpoints

**Management**:
- **Web**: Browser → wlan1 hotspot → Flask app (port 5000)
- **CLI**: SSH → wlan0/wlan1 → adsb-cli → Interactive menus

**Internet**: Raspberry Pi → wlan0 → Your WiFi → Internet

---

## 🔒 Security Considerations

1. **Change Default Passwords**: 
   - Hotspot password
   - Web interface password
   - SSH password for JLBMaritime user

2. **Network Isolation**: 
   - wlan1 (hotspot) is isolated from wlan0 (internet) by default
   - No routing between interfaces unless explicitly enabled

3. **Firewall** (Optional):
   ```bash
   sudo apt-get install ufw
   sudo ufw allow 5000/tcp  # Web interface
   sudo ufw allow 30003/tcp # ADS-B endpoints
   sudo ufw enable
   ```

4. **HTTPS** (Production):
   - Consider adding SSL/TLS certificates
   - Use nginx as reverse proxy

5. **SSH Security**:
   - Change default SSH port
   - Use key-based authentication
   - Disable password authentication

---

## 📚 Advanced Topics

### Custom Output Processing

**SBS1 Format Fields**:
```
MSG,3,1,1,ICAO,1,DATE,TIME,DATE,TIME,CALLSIGN,ALTITUDE,SPEED,TRACK,LAT,LON,...
```

**JSON Format Fields**:
```json
{
  "hex": "abc123",
  "flight": "BAW123",
  "alt_baro": 35000,
  "gs": 450,
  "track": 180,
  "lat": 51.5,
  "lon": -0.1
}
```

### Systemd Service Management

**View live logs**:
```bash
sudo journalctl -u adsb-server -f
sudo journalctl -u web-manager -f
```

**Enable/disable services**:
```bash
sudo systemctl enable adsb-server
sudo systemctl disable adsb-server
```

**Service dependencies**:
- `adsb-server` depends on: `dump1090-fa`, `network-online.target`
- `web-manager` depends on: `network.target`

### Backup and Restore

**Manual backup**:
```bash
cd ~/ADSB-WiFi-Manager
tar -czf adsb-backup-$(date +%Y%m%d).tar.gz config/ logs/
```

**Restore**:
```bash
cd ~/ADSB-WiFi-Manager
tar -xzf adsb-backup-YYYYMMDD.tar.gz
sudo systemctl restart adsb-server web-manager
```

---

## 🤝 Support

### Getting Help

1. **Check Troubleshooting Section**: Common issues solved
2. **View Logs**: 
   - Web: Logs & Troubleshooting tab
   - CLI: Option [5] → View logs
   - Terminal: `sudo journalctl -u adsb-server -f`
3. **Test Components**: Use CLI diagnostics and endpoint testing

### Reporting Issues

Include the following:
- Raspberry Pi model and OS version (`uname -a`)
- Service status (`systemctl status adsb-server`)
- Recent logs (last 50 lines)
- Steps to reproduce

---

## 📄 License

This project is developed for JLBMaritime. All rights reserved.

---

## 🙏 Acknowledgments

- **FlightAware** - dump1090-fa ADS-B decoder
- **Raspberry Pi Foundation** - Hardware platform
- **Flask** - Web framework
- **Python Community** - Libraries and tools

---

**Version**: 2.0.0  
**Last Updated**: December 2025  
**Author**: JLBMaritime Development Team

---

## 📞 Quick Reference

**Access Points**:
- Web: `http://ADS-B.local:5000`
- SSH: `ssh JLBMaritime@ADS-B.local`
- CLI: `adsb-cli`

**Default Credentials**:
- Hotspot: JLBMaritime-ADSB / Admin123
- Web/SSH: JLBMaritime / Admin

**Service Commands**:
```bash
sudo systemctl status adsb-server
sudo systemctl restart adsb-server
adsb-cli  # Interactive management
```

**Important Paths**:
- Config: `~/ADSB-WiFi-Manager/config/`
- Logs: `~/ADSB-WiFi-Manager/logs/`
- Web: `http://192.168.4.1:5000`
