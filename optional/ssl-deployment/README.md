# HTTPS/SSL Deployment (Optional)

**Advanced Feature - HTTPS with Self-Signed SSL Certificate**

---

## ⚠️ Important

**This is an OPTIONAL advanced deployment feature.**

The **standard installation** uses HTTP-only (port 5000) which:
- ✅ Works perfectly for private hotspot use
- ✅ No browser warnings
- ✅ Simpler to maintain
- ✅ Works in all browsers

**Only use this HTTPS deployment if:**
- You specifically need SSL encryption
- You understand the trade-offs (browser warnings)
- You're comfortable with certificate management

---

## 🎯 What This Does

Converts your HTTP-only installation to HTTPS with:
- ✅ nginx reverse proxy
- ✅ Self-signed SSL certificate (365-day validity)
- ✅ TLS 1.2/1.3 encryption
- ✅ Security headers
- ✅ HTTP → HTTPS redirect

**Access changes from:**
- `http://ADS-B.local:5000` 

**To:**
- `https://ADS-B.local`

---

## 📋 Prerequisites

**You MUST have already run:**
```bash
sudo ./install.sh
```
(The main installation script in the root directory)

---

## 🚀 Deploy HTTPS

### Step 1: Navigate to This Directory

```bash
cd ~/ADSB-WiFi-Manager/optional/ssl-deployment
```

### Step 2: Make Scripts Executable

```bash
chmod +x deploy_production.sh
chmod +x rollback_production.sh
chmod +x fix_ssl_certificate.sh
chmod +x ssl/generate_self_signed.sh
```

### Step 3: Run Deployment

```bash
sudo ./deploy_production.sh
```

**Deployment takes:** ~2-3 minutes

**What happens:**
1. Installs nginx
2. Generates SSL certificate (365 days)
3. Configures reverse proxy
4. Updates firewall rules
5. Starts HTTPS service

---

## 🌐 Accessing After Deployment

### New URLs

**HTTPS (Primary):**
```
https://ADS-B.local
```

**HTTP (Redirects to HTTPS):**
```
http://ADS-B.local
```

**Direct IP:**
```
https://192.168.4.1
```

### Browser Certificate Warning

**You WILL see a warning** - this is normal for self-signed certificates!

**Safari:**
1. Tap "Show Details"
2. Tap "visit this website"
3. Done ✅

**Chrome (Desktop):**
1. Click "Advanced"
2. Click "Proceed to ADS-B.local (unsafe)"
3. Done ✅

**Chrome (iOS):**
- May be very strict - consider using Safari instead
- Try typing `thisisunsafe` on the warning page

**The warning is expected** - your connection IS encrypted, the browser just doesn't trust the certificate because you created it yourself.

---

## 🔄 Return to HTTP (Rollback)

If you want to return to HTTP-only:

```bash
cd ~/ADSB-WiFi-Manager/optional/ssl-deployment
sudo ./rollback_production.sh
```

This will:
- Stop and remove nginx
- Return to HTTP on port 5000
- Keep all your data and configuration
- Keep firewall and hotspot working

**After rollback, access:**
```
http://ADS-B.local:5000
```

---

## 🔧 Certificate Renewal

**Certificates expire after 365 days** (browser requirement)

### Renew Before Expiration:

```bash
cd ~/ADSB-WiFi-Manager/optional/ssl-deployment
sudo ./fix_ssl_certificate.sh
```

**Takes:** ~30 seconds  
**Set reminder:** 11 months after deployment

**After renewal:**
- Each device will see certificate warning one more time
- Just accept it again like the first time
- Good for another year

---

## 📁 Files in This Directory

```
ssl-deployment/
├── README.md                    # This file
├── deploy_production.sh         # Deploy HTTPS
├── rollback_production.sh       # Return to HTTP
├── fix_ssl_certificate.sh       # Renew certificate
├── PRODUCTION_DEPLOYMENT.md     # Detailed HTTPS guide
├── ssl/
│   └── generate_self_signed.sh  # Certificate generator
└── nginx/
    └── adsb-manager.conf        # nginx configuration
```

---

## 🔐 Security Notes

**HTTPS Provides:**
- ✅ Encrypted traffic (TLS)
- ✅ Credential protection
- ✅ Data integrity

**Trade-offs:**
- ⚠️ Browser warnings (self-signed cert)
- ⚠️ Annual certificate renewal
- ⚠️ More complex troubleshooting
- ⚠️ Extra service (nginx) to maintain

**For Private Hotspot:**
- HTTP-only is usually sufficient
- WPA2 encryption protects WiFi traffic
- Physical access required anyway
- HTTPS adds hassle for minimal benefit

---

## 🆘 Troubleshooting

### Can't Access After Deployment

1. **Check nginx:**
   ```bash
   sudo systemctl status nginx
   ```

2. **Check Flask:**
   ```bash
   sudo systemctl status web-manager
   ```

3. **Try direct IP:**
   ```
   https://192.168.4.1
   ```

4. **Check nginx logs:**
   ```bash
   sudo tail -f /var/log/nginx/adsb-manager-error.log
   ```

### Certificate Issues

**Error: NET::ERR_CERT_VALIDITY_TOO_LONG**
- Already fixed! Certificate uses 365 days
- Regenerate if needed: `sudo ./fix_ssl_certificate.sh`

**Can't Bypass Warning**
- Try different browser (Safari usually easiest)
- Type `thisisunsafe` on Chrome warning page
- Or rollback to HTTP: `sudo ./rollback_production.sh`

### Want HTTP Back

Just run rollback:
```bash
sudo ./rollback_production.sh
```

Everything goes back to normal HTTP-only mode.

---

## 📚 Detailed Documentation

For complete HTTPS deployment documentation, see:
```
PRODUCTION_DEPLOYMENT.md
```

Includes:
- Detailed security architecture
- Complete troubleshooting guide
- Performance optimization tips
- Certificate management details

---

## 💡 Recommendation

**For most users: Skip this and use HTTP-only**

HTTPS is overkill for a private hotspot unless you have specific security requirements.

**HTTP-only benefits:**
- ✅ No browser warnings
- ✅ Works in all browsers
- ✅ No certificate renewals
- ✅ Simpler troubleshooting
- ✅ Faster (no SSL overhead)

**The standard install.sh gives you everything you need!**

---

## ✅ Quick Decision Matrix

| Your Situation | Use HTTPS? |
|----------------|-----------|
| Private hotspot, you're the only user | ❌ No |
| Shared with trusted people | ❌ No |
| Want maximum simplicity | ❌ No |
| Security compliance requirement | ✅ Yes |
| Public facing (not typical for this app) | ✅ Yes |
| You really like SSL certificates | ✅ Sure! |

---

**Version:** 1.0  
**Last Updated:** January 2026  

For questions or issues, refer to main repository README.md
