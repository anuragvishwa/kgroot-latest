#!/bin/bash

# ============================================================================
# KG RCA Mini Server - SSL/TLS Certificate Setup
# ============================================================================
# This script generates SSL certificates for Kafka
# Run this script from the mini-server-prod directory
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}KG RCA Mini Server - SSL Certificate Setup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# ============================================================================
# Configuration
# ============================================================================
SSL_DIR="./ssl"
VALIDITY_DAYS=3650  # 10 years
KEY_SIZE=2048

# Default passwords (will prompt for custom)
KEYSTORE_PASSWORD="changeit"
TRUSTSTORE_PASSWORD="changeit"
KEY_PASSWORD="changeit"

# Certificate details
COUNTRY="US"
STATE="California"
CITY="San Francisco"
ORG="Lumniverse"
ORG_UNIT="Engineering"

# ============================================================================
# Get server hostname
# ============================================================================
echo -e "${YELLOW}[1/6] Server Configuration${NC}"
echo ""

# Try to detect public IP or hostname
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo "Detected IP/Hostname: $PUBLIC_IP"
read -p "Enter your server's public hostname or IP [$PUBLIC_IP]: " KAFKA_HOST
KAFKA_HOST=${KAFKA_HOST:-$PUBLIC_IP}

echo -e "${GREEN}✓ Using hostname: $KAFKA_HOST${NC}"

# ============================================================================
# Get passwords
# ============================================================================
echo ""
echo -e "${YELLOW}[2/6] SSL Password Configuration${NC}"
echo ""

read -sp "Enter keystore password [$KEYSTORE_PASSWORD]: " INPUT_KEYSTORE_PASSWORD
echo
KEYSTORE_PASSWORD=${INPUT_KEYSTORE_PASSWORD:-$KEYSTORE_PASSWORD}

read -sp "Enter truststore password [$TRUSTSTORE_PASSWORD]: " INPUT_TRUSTSTORE_PASSWORD
echo
TRUSTSTORE_PASSWORD=${INPUT_TRUSTSTORE_PASSWORD:-$TRUSTSTORE_PASSWORD}

read -sp "Enter key password [$KEY_PASSWORD]: " INPUT_KEY_PASSWORD
echo
KEY_PASSWORD=${INPUT_KEY_PASSWORD:-$KEY_PASSWORD}

echo -e "${GREEN}✓ Passwords configured${NC}"

# ============================================================================
# Create SSL directory
# ============================================================================
echo ""
echo -e "${YELLOW}[3/6] Creating SSL directory structure...${NC}"

mkdir -p "$SSL_DIR"
cd "$SSL_DIR"

echo -e "${GREEN}✓ SSL directory created${NC}"

# ============================================================================
# Generate CA (Certificate Authority)
# ============================================================================
echo ""
echo -e "${YELLOW}[4/6] Generating Certificate Authority (CA)...${NC}"

# Generate CA private key
openssl req -new -x509 \
    -keyout ca-key \
    -out ca-cert \
    -days $VALIDITY_DAYS \
    -passout pass:$KEY_PASSWORD \
    -subj "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORG/OU=$ORG_UNIT/CN=KG-RCA-CA"

echo -e "${GREEN}✓ CA certificate generated${NC}"

# ============================================================================
# Generate Kafka broker certificate
# ============================================================================
echo ""
echo -e "${YELLOW}[5/6] Generating Kafka broker certificates...${NC}"

# Create keystore and generate key pair
keytool -genkey -noprompt \
    -alias kafka-broker \
    -keyalg RSA \
    -keysize $KEY_SIZE \
    -keystore kafka.keystore.jks \
    -storepass $KEYSTORE_PASSWORD \
    -keypass $KEY_PASSWORD \
    -dname "CN=$KAFKA_HOST,OU=$ORG_UNIT,O=$ORG,L=$CITY,ST=$STATE,C=$COUNTRY" \
    -ext SAN=DNS:$KAFKA_HOST,DNS:localhost,DNS:kafka,IP:127.0.0.1

# Create certificate signing request (CSR)
keytool -certreq -noprompt \
    -alias kafka-broker \
    -keystore kafka.keystore.jks \
    -storepass $KEYSTORE_PASSWORD \
    -keypass $KEY_PASSWORD \
    -file kafka-broker.csr

# Sign the certificate with CA
openssl x509 -req \
    -CA ca-cert \
    -CAkey ca-key \
    -in kafka-broker.csr \
    -out kafka-broker-signed.crt \
    -days $VALIDITY_DAYS \
    -CAcreateserial \
    -passin pass:$KEY_PASSWORD \
    -extensions v3_req \
    -extfile <(cat <<EOF
[v3_req]
subjectAltName = DNS:$KAFKA_HOST,DNS:localhost,DNS:kafka,IP:127.0.0.1
EOF
)

# Import CA certificate into keystore
keytool -import -noprompt \
    -alias ca-cert \
    -file ca-cert \
    -keystore kafka.keystore.jks \
    -storepass $KEYSTORE_PASSWORD

# Import signed certificate into keystore
keytool -import -noprompt \
    -alias kafka-broker \
    -file kafka-broker-signed.crt \
    -keystore kafka.keystore.jks \
    -storepass $KEYSTORE_PASSWORD \
    -keypass $KEY_PASSWORD

echo -e "${GREEN}✓ Kafka broker certificate generated${NC}"

# ============================================================================
# Create truststore
# ============================================================================
echo ""
echo -e "${YELLOW}[6/6] Creating truststore...${NC}"

keytool -import -noprompt \
    -alias ca-cert \
    -file ca-cert \
    -keystore kafka.truststore.jks \
    -storepass $TRUSTSTORE_PASSWORD

echo -e "${GREEN}✓ Truststore created${NC}"

# ============================================================================
# Generate client certificate (optional, for mutual TLS)
# ============================================================================
echo ""
read -p "Generate client certificate for mutual TLS? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Generating client certificate...${NC}"

    # Create client keystore
    keytool -genkey -noprompt \
        -alias kafka-client \
        -keyalg RSA \
        -keysize $KEY_SIZE \
        -keystore kafka-client.keystore.jks \
        -storepass $KEYSTORE_PASSWORD \
        -keypass $KEY_PASSWORD \
        -dname "CN=kg-rca-client,OU=$ORG_UNIT,O=$ORG,L=$CITY,ST=$STATE,C=$COUNTRY"

    # Create client CSR
    keytool -certreq -noprompt \
        -alias kafka-client \
        -keystore kafka-client.keystore.jks \
        -storepass $KEYSTORE_PASSWORD \
        -keypass $KEY_PASSWORD \
        -file kafka-client.csr

    # Sign client certificate
    openssl x509 -req \
        -CA ca-cert \
        -CAkey ca-key \
        -in kafka-client.csr \
        -out kafka-client-signed.crt \
        -days $VALIDITY_DAYS \
        -CAcreateserial \
        -passin pass:$KEY_PASSWORD

    # Import CA into client keystore
    keytool -import -noprompt \
        -alias ca-cert \
        -file ca-cert \
        -keystore kafka-client.keystore.jks \
        -storepass $KEYSTORE_PASSWORD

    # Import signed client certificate
    keytool -import -noprompt \
        -alias kafka-client \
        -file kafka-client-signed.crt \
        -keystore kafka-client.keystore.jks \
        -storepass $KEYSTORE_PASSWORD \
        -keypass $KEY_PASSWORD

    # Create client truststore
    keytool -import -noprompt \
        -alias ca-cert \
        -file ca-cert \
        -keystore kafka-client.truststore.jks \
        -storepass $TRUSTSTORE_PASSWORD

    echo -e "${GREEN}✓ Client certificates generated${NC}"
fi

# ============================================================================
# Clean up temporary files
# ============================================================================
echo ""
echo -e "${YELLOW}Cleaning up temporary files...${NC}"
rm -f *.csr *.srl

# ============================================================================
# Update .env file
# ============================================================================
cd ..

echo ""
echo -e "${YELLOW}Updating .env file...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}Created .env from .env.example${NC}"
fi

# Update or add SSL configuration in .env
sed -i.bak "s|^KAFKA_ADVERTISED_HOST=.*|KAFKA_ADVERTISED_HOST=$KAFKA_HOST|" .env
sed -i.bak "s|^KAFKA_SSL_KEYSTORE_PASSWORD=.*|KAFKA_SSL_KEYSTORE_PASSWORD=$KEYSTORE_PASSWORD|" .env
sed -i.bak "s|^KAFKA_SSL_KEY_PASSWORD=.*|KAFKA_SSL_KEY_PASSWORD=$KEY_PASSWORD|" .env
sed -i.bak "s|^KAFKA_SSL_TRUSTSTORE_PASSWORD=.*|KAFKA_SSL_TRUSTSTORE_PASSWORD=$TRUSTSTORE_PASSWORD|" .env

echo -e "${GREEN}✓ .env file updated${NC}"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}SSL Setup Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo -e "${BLUE}Generated files in $SSL_DIR:${NC}"
ls -lh "$SSL_DIR"/*.jks "$SSL_DIR"/ca-cert 2>/dev/null
echo ""
echo -e "${BLUE}Certificate Details:${NC}"
echo "- Hostname: $KAFKA_HOST"
echo "- Validity: $VALIDITY_DAYS days (10 years)"
echo "- Key size: $KEY_SIZE bits"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Verify .env file contains correct SSL settings"
echo "2. Deploy with SSL: docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d"
echo "3. Open port 9093 in your firewall: sudo ufw allow 9093/tcp"
echo "4. Test SSL connection: ./scripts/test-services.sh"
echo ""
echo -e "${BLUE}Client configuration:${NC}"
echo "- Copy $SSL_DIR/ca-cert to your clients"
echo "- Configure clients to connect to: $KAFKA_HOST:9093"
echo "- Use SSL protocol with the CA certificate"
echo ""
if [ -f "$SSL_DIR/kafka-client.keystore.jks" ]; then
    echo -e "${BLUE}Mutual TLS:${NC}"
    echo "- Client keystore: $SSL_DIR/kafka-client.keystore.jks"
    echo "- Client truststore: $SSL_DIR/kafka-client.truststore.jks"
    echo "- Copy these files to your client applications"
    echo ""
fi
echo -e "${YELLOW}Important: Keep your SSL passwords secure!${NC}"
echo -e "${YELLOW}Do not commit .env or SSL certificates to version control!${NC}"
