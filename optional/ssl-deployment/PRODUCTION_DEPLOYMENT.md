# Production Deployment Guide

**ADS-B Wi-Fi Manager - HTTPS with Self-Signed SSL Certificate**

This guide covers deploying the ADS-B Wi-Fi Manager in production mode with HTTPS encryption using nginx as a reverse proxy and self-signed SSL certificates.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [What Changes](#what-changes)
- [Deployment Steps](#deployment-steps)
- [Accessing the Application](#accessing-the-application)
- [Security Features](#security-features)
- [Troubleshooting](#troubleshooting)
- [Rollback](#rollback)
- [Maintenance](#maintenance)

---

## 🎯 Overview

### Production vs Development Mode

**Development Mode (Default):**
```
Browser → HTTP (port 5000) → Flask App
- No encryption
- Direct Flask access
- Port 5000 exposed
```

**Production Mode (After Deployment):**
```
Browser → HTTPS (port 443) → Nginx → Flask (localhost:5000)
- Full encryption (TLS 1.2/1.3)
- Reverse proxy security
- Security headers
- Flask internal only
- Firewall protection
```

### Key Benefits

✅ **Encrypted Traffic** - All data encrypted with TLS  
✅ **Security Headers** - HSTS, CSP, X-Frame-Options, etc.  
✅ **Reverse Proxy** - nginx handles SSL, compression, static files  
✅ **Secure Cookies** - HTTPS-only session cookies  
✅ **Firewall Rules** - UFW configured properly  
✅ **Production Hardening** - Flask secured behind localhost  

---

## 🔧 Prerequisites

### Already Installed

If you ran the standard installation (`install.sh`), you already have:
- ✅ Raspberry Pi OS (Bookworm)
- ✅ Python3 and Flask
- ✅ WiFi hotspot configured
- ✅ ADS-B server installed
- ✅ Web interface running on port 5000

### New Requirements

The deployment script will install:
- nginx (reverse proxy)
- openssl (SSL certificates)
- ufw (firewall)

---

## 🔄 What Changes

### Files Created/Modified

**New Files:**
```
/etc/ssl/adsb-manager/
├── adsb-manager.crt     # SSL certificate
└── adsb-manager.key     # Private key

/etc/nginx/
└── sites-available/
    └── adsb-manager.conf  # nginx config

~/ADSB-WiFi-Manager/
├── .production_mode      # Flag file
└── ssl/
    ├── adsb-manager.crt  # Certificate copy
    └── adsb-manager.key  # Key copy
```

**Modified Files:**
```
/etc/systemd/system/web-manager.service
- Changed: --host 0.0.0.0 → --host 127.0.0.1
- Flask now binds to localhost only (security)
```

### Services Modified

1. **nginx** - Installed, enabled, started
2. **web-manager** - Reloaded with new binding
3. **ufw** - Configured with firewall rules

### Network Changes

**Firewall Rules (UFW):**
```
Port 22  (SSH)   - ALLOW
Port 80  (HTTP)  - ALLOW (redirects to HTTPS)
Port 443 (HTTPS) - ALLOW
Port 5000 (Flask) - BLOCKED externally
Port 5353 (mDNS) - ALLOW
```

---

## 🚀 Deployment Steps

### Step 1: Prepare for Deployment

1. **Connect to Raspberry Pi**:
   ```bash
   ssh JLBMaritime@ADS-B.local
   ```

2. **Navigate to installation directory**:
   ```bash
   cd ~/ADSB-WiFi-Manager
   ```

3. **Ensure latest code** (if using git):
   ```bash
   git pull origin main
   ```

4. **Make scripts executable**:
   ```bash
   chmod +x deploy_production.sh
   chmod +x rollback_production.sh
   chmod +x ssl/generate_self_signed.sh
   ```

### Step 2: Run Production Deployment

```bash
sudo ./deploy_production.sh
```

**What the script does:**

```
[1/10] Creating backup
[2/10] Installing nginx
[3/10] Generating SSL certificate (10 years)
[4/10] Installing certificate
[5/10] Configuring nginx
[6/10] Updating Flask for production
[7/10] Configuring firewall (UFW)
[8/10] Starting services
[9/10] Verifying services
[10/10] Setting production mode flag
```

**Deployment Time:** ~2-3 minutes

### Step 3: Verify Deployment

The script automatically verifies:
- ✓ Web Manager service running
- ✓ Nginx service running
- ✓ Firewall active

Check manually:
```bash
sudo systemctl status nginx
sudo systemctl status web-manager
sudo ufw status
```

Expected output:
```
nginx: active (running)
web-manager: active (running)
ufw: Status: active
```

---

## 🌐 Accessing the Application

### HTTPS Access

**Primary URL (mDNS):**
```
https://ADS-B.local
```

**Direct IP:**
```
https://192.168.4.1
```

### First-Time Certificate Warning

**This is NORMAL and EXPECTED for self-signed certificates!**

#### Chrome/Edge

1. You'll see: **"Your connection is not private"**
2. Click **"Advanced"**
3. Click **"Proceed to ADS-B.local (unsafe)"**
4. Browser remembers exception - no more warnings

#### Firefox

1. You'll see: **"Warning: Potential Security Risk"**
2. Click **"Advanced"**
3. Click **"Accept the Risk and Continue"**
4. Browser remembers exception

#### Safari (iOS/macOS)

1. Tap **"Show Details"**
2. Tap **"visit this website"**
3. Confirm again

**Important:** The connection IS encrypted despite the warning. The warning appears because the certificate isn't from a trusted Certificate Authority (CA).

### Why Self-Signed?

**Advantages:**
- ✅ Free
- ✅ Works offline/no internet
- ✅ No domain required
- ✅ Full encryption (same as Let's Encrypt)
- ✅ Perfect for local network

**Trade-off:**
- ⚠️ Browser warning on first access (one-time, browser remembers)

---

## 🔐 Security Features

### SSL/TLS Configuration

```nginx
Protocols: TLS 1.2, TLS 1.3
Key Size: 4096-bit RSA
Cipher Suites: Modern, secure only
Certificate Validity: 365 days (1 year)
```

**Note:** Certificate validity is limited to 365 days to comply with modern browser security requirements. You'll need to renew annually (see [Maintenance](#maintenance) section).

### HTTP Security Headers

Automatically added by nginx:

```nginx
Strict-Transport-Security: max-age=31536000
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### Flask Security Enhancements

**Production Mode Features:**
- ProxyFix middleware (trusts reverse proxy)
- Secure cookies (HTTPS only)
- HttpOnly cookies
- SameSite: Lax
- 12-hour session lifetime

### Firewall Protection

```bash
# View firewall status
sudo ufw status verbose

# Expected output:
To                         Action      From
--                         ------      ----
22/tcp                     ALLOW IN    Anywhere
80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
5353/udp                   ALLOW IN    Anywhere
```

---

## 🔍 Troubleshooting

### Issue: Cannot Access HTTPS URL

**Symptoms:** Browser times out or connection refused

**Solutions:**

1. **Check nginx is running:**
   ```bash
   sudo systemctl status nginx
   ```
   
   If not running:
   ```bash
   sudo systemctl start nginx
   ```

2. **Check firewall:**
   ```bash
   sudo ufw status
   ```
   
   Ensure port 443 is allowed.

3. **Try direct IP:**
   ```
   https://192.168.4.1
   ```

4. **Check nginx logs:**
   ```bash
   sudo tail -f /var/log/nginx/adsb-manager-error.log
   ```

### Issue: Certificate Error Persists

**Symptoms:** Browser won't accept certificate even after "proceed"

**Solutions:**

1. **Clear browser cache and certificates**
   - Chrome: Settings → Privacy → Clear browsing data → Cached images and files
   - Firefox: Settings → Privacy → Clear Data

2. **Regenerate certificate:**
   ```bash
   cd ~/ADSB-WiFi-Manager/ssl
   sudo ./generate_self_signed.sh
   sudo cp adsb-manager.* /etc/ssl/adsb-manager/
   sudo systemctl restart nginx
   ```

### Issue: HTTP Redirect Not Working

**Symptoms:** HTTP doesn't redirect to HTTPS

**Solution:**

Check nginx config:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Issue: Flask Not Accessible

**Symptoms:** nginx running but getting 502 Bad Gateway

**Solutions:**

1. **Check Flask is running:**
   ```bash
   sudo systemctl status web-manager
   ```

2. **Ensure Flask binds to localhost:**
   ```bash
   sudo systemctl cat web-manager | grep ExecStart
   ```
   
   Should show: `--host 127.0.0.1`

3. **Restart both services:**
   ```bash
   sudo systemctl restart web-manager
   sudo systemctl restart nginx
   ```

### Issue: Firewall Blocking Access

**Symptoms:** Can access sometimes but not always

**Solutions:**

1. **Check UFW status:**
   ```bash
   sudo ufw status numbered
   ```

2. **Ensure HTTPS allowed:**
   ```bash
   sudo ufw allow 443/tcp
   sudo ufw reload
   ```

### Issue: Want to Test Without HTTPS

**Solution:** Temporarily disable nginx:
```bash
sudo systemctl stop nginx
sudo ufw allow 5000/tcp
```

Access at: `http://192.168.4.1:5000`

Re-enable:
```bash
sudo systemctl start nginx
sudo ufw delete allow 5000/tcp
```

---

## 🔙 Rollback

### Quick Rollback to Development Mode

If you need to revert to HTTP-only mode:

```bash
cd ~/ADSB-WiFi-Manager
sudo ./rollback_production.sh
```

**What rollback does:**
- Stops and disables nginx
- Removes nginx configuration
- Updates Flask to bind to 0.0.0.0 (all interfaces)
- Removes production mode flag
- Allows port 5000 through firewall

**After rollback:**
- Access: `http://ADS-B.local:5000`
- No HTTPS
- Direct Flask access

### Re-Deploy Production

To switch back to production mode:
```bash
sudo ./deploy_production.sh
```

---

## 🛠️ Maintenance

### View nginx Access Logs

```bash
sudo tail -f /var/log/nginx/adsb-manager-access.log
```

### View nginx Error Logs

```bash
sudo tail -f /var/log/nginx/adsb-manager-error.log
```

### Test nginx Configuration

After manual changes:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Renew SSL Certificate

**Certificate Validity:** 365 days (1 year)

Browsers will start showing warnings a few weeks before the certificate expires. You'll need to regenerate the certificate annually.

#### Method 1: Automated Script (Recommended)

Use the provided renewal script:

```bash
cd ~/ADSB-WiFi-Manager
sudo ./fix_ssl_certificate.sh
```

**What the script does:**
- Backs up old certificate
- Generates new 365-day certificate
- Installs to system location
- Restarts nginx
- Verifies everything works

**Time Required:** ~30 seconds

#### Method 2: Manual Renewal

If you prefer manual control:

```bash
# Generate new certificate
cd ~/ADSB-WiFi-Manager/ssl
sudo ./generate_self_signed.sh

# Install to system
sudo cp adsb-manager.crt /etc/ssl/adsb-manager/
sudo cp adsb-manager.key /etc/ssl/adsb-manager/
sudo chmod 600 /etc/ssl/adsb-manager/adsb-manager.key
sudo chmod 644 /etc/ssl/adsb-manager/adsb-manager.crt

# Restart nginx
sudo systemctl restart nginx
```

#### After Renewal

**Important:** After renewing the certificate, each device will see the certificate warning ONE more time (just like the first time). Simply accept the new certificate and you're good for another year.

#### Set a Reminder

Set a calendar reminder for **11 months from deployment** to renew the certificate before it expires.

**Why 365 days?** Modern browsers (Chrome, Safari, Firefox) require SSL certificates to have a maximum validity of 398 days for security reasons.

### Update nginx Configuration

1. Edit config:
   ```bash
   sudo nano /etc/nginx/sites-available/adsb-manager.conf
   ```

2. Test configuration:
   ```bash
   sudo nginx -t
   ```

3. Reload if OK:
   ```bash
   sudo systemctl reload nginx
   ```

### Backup Configuration

```bash
cd ~/ADSB-WiFi-Manager
tar -czf production-backup-$(date +%Y%m%d).tar.gz \
    ssl/ \
    nginx/ \
    /etc/nginx/sites-available/adsb-manager.conf \
    /etc/ssl/adsb-manager/
```

### Monitor Services

```bash
# All services status
sudo systemctl status nginx web-manager adsb-server

# Live logs
sudo journalctl -u nginx -u web-manager -f
```

---

## 📊 Performance Optimization

### nginx Caching (Optional)

Add to nginx config for better static file performance:

```nginx
location /static/ {
    alias /home/JLBMaritime/ADSB-WiFi-Manager/web_interface/static/;
    expires 1y;
    add_header Cache-Control "public, immutable";
    
    # Optional: Enable gzip for static files
    gzip_static on;
}
```

### Connection Limits (Optional)

To prevent abuse:

```nginx
# Add to http block
limit_conn_zone $binary_remote_addr zone=addr:10m;

# Add to server block
limit_conn addr 10;
```

---

## 🔒 Additional Security Recommendations

### 1. Change Default Passwords

**Web Interface:**
- Login to https://ADS-B.local
- Go to Settings tab
- Change password from "Admin"

**SSH:**
```bash
passwd JLBMaritime
```

**Hotspot:**
```bash
sudo nano /etc/hostapd/hostapd.conf
# Change wpa_passphrase
sudo systemctl restart hostapd
```

### 2. Disable SSH Password Authentication (Advanced)

Use SSH keys instead:
```bash
# On your computer, generate key
ssh-keygen -t ed25519

# Copy to Raspberry Pi  
ssh-copy-id JLBMaritime@ADS-B.local

# Disable password auth
sudo nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
sudo systemctl restart sshd
```

### 3. Enable Fail2ban (Optional)

Protect against brute force:
```bash
sudo apt-get install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 📞 Support

### Health Check

Test if application is responding:
```bash
curl -k https://192.168.4.1/health
```

Expected response:
```json
{
  "status": "healthy",
  "production_mode": true,
  "timestamp": "2026-01-04T19:30:00"
}
```

### Diagnostic Commands

```bash
# System status
systemctl status nginx web-manager adsb-server

# Network connections
sudo netstat -tlnp | grep -E '443|5000'

# Certificate info
openssl x509 -in /etc/ssl/adsb-manager/adsb-manager.crt -text -noout

# nginx test
sudo nginx -t

# Firewall status
sudo ufw status verbose
```

---

## 📝 Production Checklist

Before going live:

- [ ] Deployment completed successfully
- [ ] Can access https://ADS-B.local
- [ ] Accepted certificate warning (one-time)
- [ ] Can login with credentials
- [ ] WiFi manager working
- [ ] ADS-B configuration accessible
- [ ] Changed default web password
- [ ] Changed default SSH password
- [ ] Firewall active and configured
- [ ] nginx logs look normal
- [ ] Health check responds

---

## 🎯 Quick Reference

**Access URLs:**
```
HTTPS: https://ADS-B.local
HTTP:  http://ADS-B.local (redirects to HTTPS)
```

**Default Credentials:**
```
Username: JLBMaritime
Password: Admin (CHANGE THIS!)
```

**Important Commands:**
```bash
# Deploy production
sudo ./deploy_production.sh

# Rollback to development
sudo ./rollback_production.sh

# Restart services
sudo systemctl restart nginx web-manager

# View logs
sudo tail -f /var/log/nginx/adsb-manager-error.log
sudo journalctl -u web-manager -f

# Test configuration
sudo nginx -t

# Firewall status
sudo ufw status
```

**Certificate Location:**
```
/etc/ssl/adsb-manager/adsb-manager.crt
/etc/ssl/adsb-manager/adsb-manager.key
```

---

**Version:** 1.0  
**Last Updated:** January 2026  
**Author:** JLBMaritime Development Team
