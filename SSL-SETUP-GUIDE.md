# Kafka SSL/TLS Setup Guide

## Overview

This guide covers setting up SSL/TLS encryption for Kafka to secure client connections. After setup, clients will connect using encrypted SSL connections while internal services continue to use plaintext for efficiency.

## Architecture

```
┌─────────────────┐                 ┌──────────────────────┐
│  External       │   SSL (9093)    │                      │
│  Clients        │────────────────▶│   Kafka Broker       │
│  (Encrypted)    │                 │  kafka.lumniverse.com│
└─────────────────┘                 │                      │
                                    │  Port 9092: Plaintext│
┌─────────────────┐   Plaintext     │  Port 9093: SSL      │
│  Internal       │   (9092)        │                      │
│  Services       │◀───────────────▶│                      │
│  (Docker)       │                 │                      │
└─────────────────┘                 └──────────────────────┘
```

## Prerequisites

Before starting:
- [ ] AWS Security Group has port 80 open (temporarily for Let's Encrypt)
- [ ] DNS record: kafka.lumniverse.com → 98.90.147.12 (already configured)
- [ ] Email address for Let's Encrypt notifications
- [ ] Strong keystore password (not 'changeit123'!)

## Part 1: Server Setup

### Step 1: Prepare Setup Scripts

Upload the setup scripts to your server:

```bash
# From your local machine
scp /tmp/complete-ssl-setup.sh mini-server:/home/ec2-user/kgroot-latest/
scp /tmp/test-kafka-ssl.sh mini-server:/home/ec2-user/kgroot-latest/
```

### Step 2: Edit Configuration

**IMPORTANT**: Before running the setup, edit the script to set:

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
nano complete-ssl-setup.sh

# Change these lines:
EMAIL="your-email@company.com"           # Your real email
KEYSTORE_PASSWORD="YourSecurePassword123"  # Strong password
```

Save and exit (Ctrl+X, Y, Enter).

### Step 3: Open Port 80 Temporarily

In AWS Console:
1. Go to EC2 → Security Groups
2. Find your instance's security group
3. Add inbound rule:
   ```
   Type: HTTP
   Port: 80
   Source: 0.0.0.0/0
   Description: Temporary - Let's Encrypt verification
   ```

### Step 4: Run SSL Setup

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
chmod +x complete-ssl-setup.sh
sudo ./complete-ssl-setup.sh
```

The script will:
1. Install certbot
2. Generate Let's Encrypt SSL certificate
3. Convert certificates to Java KeyStore format
4. Update docker-compose configuration
5. Restart Kafka with SSL enabled

**Expected output:**
```
╔══════════════════════════════════════════════════════════════╗
║               SSL Setup Complete!                            ║
╚══════════════════════════════════════════════════════════════╝

Configuration Summary:
  • SSL Certificate: /etc/letsencrypt/live/kafka.lumniverse.com
  • KeyStore: /home/ec2-user/kafka-ssl/kafka.keystore.jks
  • KeyStore Password: <your-password>
```

**Save your keystore password securely!** You'll need it for troubleshooting.

### Step 5: Close Port 80

After successful setup, **remove the port 80 rule** from AWS Security Group (no longer needed).

### Step 6: Open Port 9093 for SSL

In AWS Security Group, add:
```
Type: Custom TCP
Port: 9093
Source: 0.0.0.0/0 (or specific client IP ranges)
Description: Kafka SSL - external client access
```

### Step 7: Test SSL Connection

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
chmod +x test-kafka-ssl.sh
./test-kafka-ssl.sh
```

**Expected results:**
```
✓ Port 9093 is reachable
✓ Certificate expires: <date>
✓ SSL handshake successful
✓ Internal plaintext connection working
```

If all tests pass, SSL is configured correctly!

### Step 8: Set Up Auto-Renewal

Let's Encrypt certificates expire after 90 days. Set up automatic renewal:

```bash
ssh mini-server
sudo crontab -e

# Add this line:
0 0 * * * /usr/bin/certbot renew --quiet --deploy-hook "cd /home/ec2-user/kgroot-latest && ./renew-kafka-ssl.sh"
```

Create the renewal script:

```bash
cat > /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh << 'EOF'
#!/bin/bash
# Regenerate Kafka keystores after certificate renewal

DOMAIN="kafka.lumniverse.com"
CERT_DIR="/home/ec2-user/kafka-ssl"
KEYSTORE_PASSWORD="YourSecurePassword123"  # Use your actual password

# Convert renewed certificates
sudo openssl pkcs12 -export \
    -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    -inkey /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out $CERT_DIR/kafka.p12 \
    -name kafka \
    -password pass:$KEYSTORE_PASSWORD

sudo keytool -importkeystore \
    -srckeystore $CERT_DIR/kafka.p12 \
    -srcstoretype PKCS12 \
    -srcstorepass $KEYSTORE_PASSWORD \
    -destkeystore $CERT_DIR/kafka.keystore.jks \
    -deststoretype JKS \
    -deststorepass $KEYSTORE_PASSWORD \
    -noprompt

# Restart Kafka
cd /home/ec2-user/kgroot-latest
docker-compose -f docker-compose-fixed.yml restart kafka

echo "Kafka SSL certificates renewed and Kafka restarted"
EOF

chmod +x /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh
```

## Part 2: Client Configuration

### Helm Chart Installation with SSL

Clients should now use SSL when connecting:

```bash
helm install <client-name> saas/client/helm-chart/kg-rca-agent \
  --set client.id=<unique-client-id> \
  --set client.apiKey=<secure-api-key> \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --set server.kafka.security.protocol="SSL"
```

### Client Configuration Options

**Option 1: SSL with Server Verification (Recommended)**
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9093"
--set server.kafka.security.protocol="SSL"
--set server.kafka.ssl.endpoint.identification.algorithm="https"
```

This verifies the server certificate automatically (Let's Encrypt is in standard trust stores).

**Option 2: SSL without Certificate Verification (Less Secure)**
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9093"
--set server.kafka.security.protocol="SSL"
--set server.kafka.ssl.endpoint.identification.algorithm=""
```

Use this only for testing or if certificate verification fails.

### Testing Client Connection

From the client cluster:

```bash
# Test DNS
nslookup kafka.lumniverse.com

# Test SSL port
openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com

# Deploy test client
helm install test-ssl-client saas/client/helm-chart/kg-rca-agent \
  --set client.id=test-ssl-client \
  --set client.apiKey=test-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --set server.kafka.security.protocol="SSL"

# Check logs
kubectl logs -l app=kg-rca-agent --tail=50
```

**Expected log messages:**
```
INFO  Successfully connected to Kafka broker kafka.lumniverse.com:9093
INFO  Security protocol: SSL
INFO  Producing events to topic: raw.k8s.events
```

## Part 3: Updating Helm Chart

If your Helm chart doesn't have SSL configuration options, add them:

### Update [values.yaml](saas/client/helm-chart/kg-rca-agent/values.yaml)

```yaml
server:
  kafka:
    brokers: "kafka.lumniverse.com:9093"
    security:
      protocol: "SSL"  # Options: PLAINTEXT, SSL, SASL_SSL
      ssl:
        endpoint:
          identification:
            algorithm: "https"  # Set to "" to disable cert verification
```

### Update Deployment Template

In [deployment.yaml](saas/client/helm-chart/kg-rca-agent/templates/deployment.yaml):

```yaml
env:
- name: KAFKA_BROKERS
  value: {{ .Values.server.kafka.brokers | quote }}
- name: KAFKA_SECURITY_PROTOCOL
  value: {{ .Values.server.kafka.security.protocol | default "PLAINTEXT" | quote }}
- name: KAFKA_SSL_ENDPOINT_IDENTIFICATION_ALGORITHM
  value: {{ .Values.server.kafka.security.ssl.endpoint.identification.algorithm | default "https" | quote }}
```

### Update Client Code

In your Kafka producer/consumer configuration:

```go
// Go example
config := sarama.NewConfig()
config.Net.TLS.Enable = true
config.Net.TLS.Config = &tls.Config{
    InsecureSkipVerify: false,  // Set to false for production
}

client, err := sarama.NewClient([]string{"kafka.lumniverse.com:9093"}, config)
```

```javascript
// Node.js example
const kafka = new Kafka({
  brokers: ['kafka.lumniverse.com:9093'],
  ssl: {
    rejectUnauthorized: true  // Verify certificate
  }
})
```

```python
# Python example
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers=['kafka.lumniverse.com:9093'],
    security_protocol='SSL',
    ssl_check_hostname=True
)
```

## Troubleshooting

### Certificate Verification Fails

**Symptom:**
```
ERROR SSL handshake failed
ERROR Certificate verification failed
```

**Solutions:**

1. **Check DNS resolution:**
   ```bash
   nslookup kafka.lumniverse.com
   # Must return: 98.90.147.12
   ```

2. **Verify certificate:**
   ```bash
   openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com
   # Look for "Verify return code: 0 (ok)"
   ```

3. **Check certificate expiry:**
   ```bash
   echo | openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com 2>/dev/null | openssl x509 -noout -dates
   ```

4. **Temporary workaround** (testing only):
   ```bash
   # Disable certificate verification
   --set server.kafka.ssl.endpoint.identification.algorithm=""
   ```

### Port 9093 Not Reachable

**Check AWS Security Group:**
```
Inbound Rule:
Type: Custom TCP
Port: 9093
Source: 0.0.0.0/0
```

**Test from client:**
```bash
telnet kafka.lumniverse.com 9093
# OR
nc -zv kafka.lumniverse.com 9093
```

### Kafka Not Starting

**Check logs:**
```bash
ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 100"
```

**Common issues:**

1. **KeyStore not found:**
   ```bash
   # Verify files exist
   ssh mini-server "ls -la /home/ec2-user/kafka-ssl/"

   # Should show:
   # kafka.keystore.jks
   # kafka.truststore.jks
   # kafka.p12
   ```

2. **Permission errors:**
   ```bash
   ssh mini-server "sudo chown -R 1000:1000 /home/ec2-user/kafka-ssl"
   ssh mini-server "sudo chmod 644 /home/ec2-user/kafka-ssl/*.jks"
   ```

3. **Wrong password:**
   - Check KEYSTORE_PASSWORD in docker-compose matches what you used during setup

### Internal Services Broken

If graph-builder, alerts-enricher stop working:

**Check they're using plaintext (port 9092):**
```bash
ssh mini-server "docker exec kgroot-latest-graph-builder-1 env | grep KAFKA"
# Should show: KAFKA_BROKERS=kafka:9092 (NOT 9093)
```

Internal services should use `kafka:9092` (plaintext), not SSL.

## Security Considerations

### Current Setup (SSL)

✓ Encrypted communication between clients and Kafka
✓ Certificate verification (prevents MITM attacks)
✓ Free, auto-renewing certificates
✓ Internal services use plaintext (better performance)

### What's NOT Included (Optional Additions)

- **Client authentication** (mutual TLS)
  - Requires client certificates
  - More complex setup
  - Use SASL/SCRAM instead if needed

- **Authorization** (Kafka ACLs)
  - Control which clients can access which topics
  - Requires Kafka ACL configuration

- **Encryption at rest**
  - Data on disk is not encrypted
  - Use EBS encryption if needed

### Compliance

This SSL setup provides:
- ✓ Data encryption in transit
- ✓ Server authentication
- ✓ Industry-standard TLS 1.2/1.3
- ✓ Automatic certificate management

Suitable for most production use cases.

## Monitoring SSL Connections

### Check Active SSL Connections

```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 netstat -tn | grep :9093"
```

### Monitor in Kafka UI

```bash
# Via SSH tunnel
ssh -L 7777:localhost:7777 mini-server
# Browse: http://localhost:7777
```

Check:
- Consumer groups (should show SSL clients)
- Broker metrics (connection count)

### Grafana Dashboard

Add metrics for SSL connections:
- Connection count by protocol
- SSL handshake errors
- Certificate expiry countdown

## Migration Plan (Plaintext → SSL)

If you have existing clients on plaintext (9092), migrate gradually:

### Phase 1: Dual Protocol (Current)
- Plaintext: kafka.lumniverse.com:9092
- SSL: kafka.lumniverse.com:9093
- Both work simultaneously

### Phase 2: Migrate Clients
1. Update one client at a time to use 9093
2. Test thoroughly
3. Move to next client

### Phase 3: Deprecate Plaintext (Optional)
Once all clients on SSL:
1. Remove port 9092 from external access
2. Keep internal plaintext for services

## Certificate Renewal Process

### Automatic (Recommended)

Certbot will auto-renew. The cron job handles:
1. Check for expiring certificates (daily)
2. Renew if < 30 days remaining
3. Regenerate Kafka keystores
4. Restart Kafka

### Manual Renewal

If auto-renewal fails:

```bash
ssh mini-server
sudo certbot renew --force-renewal
cd /home/ec2-user/kgroot-latest
sudo ./renew-kafka-ssl.sh
```

### Verify Renewal Status

```bash
ssh mini-server "sudo certbot certificates"
```

## Quick Reference

### Server Endpoints
- **Plaintext (internal)**: kafka:9092
- **SSL (external)**: kafka.lumniverse.com:9093

### Client Connection
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9093"
--set server.kafka.security.protocol="SSL"
```

### Test SSL
```bash
openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com
```

### Restart Kafka
```bash
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml restart kafka"
```

### Check Logs
```bash
ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 50 -f"
```

### View Certificate
```bash
ssh mini-server "sudo certbot certificates"
```

## Next Steps

After SSL setup is complete:

- [ ] Update client documentation with SSL connection details
- [ ] Test with one pilot client
- [ ] Migrate remaining clients
- [ ] Set up monitoring for certificate expiry
- [ ] Document incident response (if certificate expires)
- [ ] Consider adding SASL authentication for additional security

## Support

For SSL issues:
1. Check AWS Security Group (port 9093 open)
2. Verify DNS resolves correctly
3. Test certificate with openssl
4. Check Kafka logs
5. See PRODUCTION-SETUP.md for additional troubleshooting
