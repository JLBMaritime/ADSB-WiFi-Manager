# Deployment Mode: HTTP-Only (No SSL)

**ADS-B Wi-Fi Manager**  
**Deployment Type:** HTTP-Only Development Mode  
**Last Updated:** January 2026

---

## 🎯 Deployment Decision

This system is deployed in **HTTP-only mode** without SSL/TLS encryption.

### Why HTTP-Only?

**Primary Reasons:**
1. ✅ **Simplified Access** - No browser certificate warnings
2. ✅ **Universal Compatibility** - Works in all browsers (Chrome, Safari, Firefox, Edge)
3. ✅ **Lower Maintenance** - No annual certificate renewals
4. ✅ **Private Network** - System operates on isolated hotspot (192.168.4.x)
5. ✅ **Physical Security** - Raspberry Pi is in controlled environment

### Security Considerations

**Is this secure enough?**

**Yes, for this use case:**

- ✅ **Private Hotspot** - Not connected to public internet
- ✅ **Isolated Network** - 192.168.4.x subnet (hotspot only)
- ✅ **Physical Access Required** - Raspberry Pi in your possession
- ✅ **Authentication Enabled** - Login required (username/password)
- ✅ **Firewall Active** - UFW protecting all network interfaces
- ✅ **Limited Exposure** - Typically only owner connects

**Acceptable Risk:**
- ⚠️ Unencrypted traffic on local network
- ⚠️ Credentials sent in plaintext over WiFi

**Mitigation:**
- WPA2/WPA3 encryption on hotspot encrypts WiFi traffic
- Change default password immediately
- Only trusted devices connect to hotspot

---

## 🌐 Access Information

### URLs
```
Primary: http://ADS-B.local:5000
Direct:  http://192.168.4.1:5000
```

### Default Credentials
```
Username: JLBMaritime
Password: Admin
```

⚠️ **IMPORTANT:** Change the default password after first login!

---

## 🔐 Security Architecture

### Active Protection Layers

1. **WPA2/WPA3 WiFi Encryption**
   - Hotspot: JLBMaritime-ADSB
   - Password protected
   - Encrypts all WiFi traffic

2. **UFW Firewall**
   - Status: Active
   - Default: Deny incoming
   - Allowed ports:
     - 22 (SSH)
     - 5000 (Web Interface)
     - 5353 (mDNS)
     - 8080 (dump1090 SkyAware)
     - 67/68 UDP on wlan1 (DHCP)

3. **Web Authentication**
   - Login required for access
   - Session-based authentication
   - 12-hour session timeout

4. **Network Isolation**
   - Hotspot on dedicated interface (wlan1)
   - Subnet: 192.168.4.0/24
   - No routing to external networks

---

## 📊 Service Architecture

```
┌─────────────┐
│   Browser   │
│  (Any type) │
└──────┬──────┘
       │
       │ HTTP:5000
       │ (Unencrypted)
       │
┌──────▼──────┐
│    Flask    │
│  Web Server │
│  0.0.0.0:   │
│    5000     │
└──────┬──────┘
       │
┌──────▼─────────┐
│  ADS-B Server  │
│  WiFi Manager  │
│  System API    │
└────────────────┘
```

**No nginx** - Direct Flask access  
**No SSL** - HTTP only  
**Firewall** - UFW active  

---

## 🔄 Switching to HTTPS (If Needed)

If you later decide HTTPS is needed:

```bash
cd ~/ADSB-WiFi-Manager
sudo ./deploy_production.sh
```

This will:
- Install nginx
- Generate self-signed SSL certificate
- Configure reverse proxy
- Enable HTTPS access
- Keep firewall active

---

## 🛠️ Maintenance

### Change Password

**Via Web Interface:**
1. Login to http://ADS-B.local:5000
2. Navigate to Settings tab
3. Enter new password
4. Confirm and save

**Never use default password in production!**

### Monitor Firewall

```bash
# Check firewall status
sudo ufw status verbose

# View recent blocks
sudo tail -f /var/log/ufw.log
```

### Monitor Web Access

```bash
# View Flask logs
sudo journalctl -u web-manager -f

# Check active connections
sudo netstat -tlnp | grep :5000
```

---

## ✅ Security Best Practices

Even in HTTP-only mode:

1. ✅ **Change default passwords**
   - Web interface password
   - SSH password
   - Hotspot password

2. ✅ **Keep firewall active**
   - Never disable UFW
   - Review rules periodically

3. ✅ **Limit physical access**
   - Keep Raspberry Pi secure
   - Only trusted individuals access hotspot

4. ✅ **Monitor logs**
   - Check for unusual access
   - Review firewall blocks

5. ✅ **Update regularly**
   - Keep system packages updated
   - Apply security patches

---

## 🎯 Threat Model

### What This Protects Against

✅ **Unauthorized network access** - Firewall blocks unwanted connections  
✅ **Service exposure** - Only essential ports open  
✅ **Brute force SSH** - Firewall + strong passwords  
✅ **Hotspot abuse** - WPA2 encryption + password  

### What This Doesn't Protect Against

⚠️ **Local network sniffing** - Traffic unencrypted on local network  
⚠️ **MITM on WiFi** - WPA2 provides some protection but not SSL level  
⚠️ **Compromised device** - If laptop/phone is hacked, credentials visible  

**Risk Assessment:** **LOW** for private hotspot use  
**Acceptable:** Yes, for controlled environment with physical security  

---

## 📝 Deployment Checklist

Before using in production:

- [ ] Rolled back from HTTPS (if previously deployed)
- [ ] Can access http://ADS-B.local:5000
- [ ] Changed web interface password from "Admin"
- [ ] Changed SSH password from default
- [ ] Changed hotspot password from "Admin123"
- [ ] Verified firewall active (`sudo ufw status`)
- [ ] Tested from all devices (phone, tablet, laptop)
- [ ] Verified login works on all devices
- [ ] WiFi Manager functional
- [ ] ADS-B configuration accessible
- [ ] Logs show no errors

---

## 🆘 Support

### Can't Access Web Interface

**Check:**
1. Connected to JLBMaritime-ADSB hotspot
2. Using http:// not https://
3. Including :5000 port number
4. Flask service running: `sudo systemctl status web-manager`
5. Firewall allows port 5000: `sudo ufw status`

### Hotspot Not Working

**Check:**
1. Firewall DHCP rules: `sudo ufw status | grep -E "67|68|wlan1"`
2. dnsmasq running: `sudo systemctl status dnsmasq`
3. hostapd running: `sudo systemctl status hostapd`

### Performance Issues

HTTP-only mode is generally faster than HTTPS because:
- No SSL encryption overhead
- No reverse proxy (direct Flask access)
- Fewer services running

If you experience slow performance, check:
- System load: `top`
- Memory usage: `free -h`
- Network latency: `ping 192.168.4.1`

---

## 📞 Quick Reference

**Access URL:** `http://ADS-B.local:5000`  
**Hotspot:** JLBMaritime-ADSB  
**Username:** JLBMaritime  
**Password:** Admin (CHANGE THIS!)  

**Services:**
```bash
# Web Interface
sudo systemctl status web-manager

# Hotspot
sudo systemctl status hostapd

# DHCP
sudo systemctl status dnsmasq

# ADS-B Server
sudo systemctl status adsb-server

# Firewall
sudo ufw status
```

**Emergency Restart:**
```bash
sudo systemctl restart web-manager
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
```

---

**Deployment Mode:** HTTP-Only  
**Security Level:** Moderate (Suitable for private hotspot)  
**Maintenance:** Low (No certificate renewals)  
**Compatibility:** Excellent (All browsers)  

---

*This deployment mode prioritizes simplicity and compatibility over maximum encryption. Suitable for private, physically-secured environments.*
