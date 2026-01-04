#!/bin/bash
################################################################################
# Generate Self-Signed SSL Certificate for ADS-B Manager
# 10-year validity, 4096-bit RSA key
################################################################################

echo "Generating self-signed SSL certificate..."

# Certificate details
CERT_COUNTRY="GB"
CERT_STATE="England"
CERT_CITY="London"
CERT_ORG="JLBMaritime"
CERT_OU="ADS-B Manager"
CERT_CN="ADS-B.local"
CERT_DAYS=3650  # 10 years

# File names
KEY_FILE="adsb-manager.key"
CERT_FILE="adsb-manager.crt"

# Generate private key (4096-bit RSA)
echo "Generating 4096-bit RSA private key..."
openssl genrsa -out "$KEY_FILE" 4096

# Create certificate configuration file
cat > cert_config.txt << EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
C = $CERT_COUNTRY
ST = $CERT_STATE
L = $CERT_CITY
O = $CERT_ORG
OU = $CERT_OU
CN = $CERT_CN

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = $CERT_CN
DNS.2 = ADS-B
DNS.3 = localhost
IP.1 = 192.168.4.1
IP.2 = 127.0.0.1
EOF

# Generate self-signed certificate
echo "Generating self-signed certificate..."
openssl req -new -x509 -key "$KEY_FILE" -out "$CERT_FILE" -days "$CERT_DAYS" -config cert_config.txt

# Set proper permissions
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

# Clean up config file
rm cert_config.txt

# Display certificate info
echo ""
echo "✓ Certificate generated successfully!"
echo ""
echo "Files created:"
echo "  Private Key: $KEY_FILE"
echo "  Certificate: $CERT_FILE"
echo ""
echo "Certificate Details:"
openssl x509 -in "$CERT_FILE" -noout -subject -dates -issuer

echo ""
echo "Certificate is valid for:"
echo "  - ADS-B.local"
echo "  - ADS-B"
echo "  - 192.168.4.1"
echo "  - 127.0.0.1"
echo ""
echo "Validity: $CERT_DAYS days (10 years)"
