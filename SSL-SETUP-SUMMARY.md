# SSL Setup - Executive Summary

## What Was Created

I've prepared a complete SSL/TLS setup for your Kafka production server to enable secure, encrypted client connections.

### 📁 Documentation Created

1. **[SSL-SETUP-GUIDE.md](SSL-SETUP-GUIDE.md)** - Complete guide with:
   - Step-by-step server setup instructions
   - Client configuration examples
   - Troubleshooting section
   - Certificate renewal process
   - Security considerations

2. **[SSL-CHECKLIST.md](SSL-CHECKLIST.md)** - Quick checklist for setup

3. **[PRODUCTION-SETUP.md](PRODUCTION-SETUP.md)** - Already exists (updated with SSL info)

### 🛠️ Scripts Created (Already on Server)

1. **`complete-ssl-setup.sh`** - Automated SSL setup script
   - Installs certbot
   - Generates Let's Encrypt certificate
   - Creates Java keystores
   - Updates docker-compose
   - Restarts Kafka with SSL

2. **`test-kafka-ssl.sh`** - SSL verification script
   - Tests port connectivity
   - Verifies certificate
   - Checks Kafka SSL configuration

## Architecture After SSL Setup

```
External Clients (Encrypted)
         ↓
    SSL (port 9093)
         ↓
  kafka.lumniverse.com
         ↓
    Kafka Broker
         ↓
  Plaintext (port 9092) ← Internal Services
         ↓                (graph-builder, etc)
    Docker Network
```

**Key Points:**
- External clients use **port 9093 with SSL** (encrypted)
- Internal services use **port 9092 plaintext** (performance)
- Both protocols run simultaneously
- Certificate auto-renews every 90 days

## Before You Run Setup

### ⚠️ IMPORTANT: Edit Configuration First!

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
nano complete-ssl-setup.sh

# CHANGE THESE LINES:
EMAIL="your-email@company.com"              # Line 8
KEYSTORE_PASSWORD="YourSecurePassword123"   # Line 9

# Save: Ctrl+X, Y, Enter
```

### Prerequisites Checklist

- [ ] Your email address (for Let's Encrypt notifications)
- [ ] Strong keystore password (NOT 'changeit123')
- [ ] AWS Security Group - **Port 80 open temporarily**
  ```
  Type: HTTP
  Port: 80
  Source: 0.0.0.0/0
  Description: Temporary - Let's Encrypt verification
  ```

## Quick Start (3 Steps)

### Step 1: Configure and Run Setup

```bash
# 1. Edit the script (see above)
ssh mini-server
cd /home/ec2-user/kgroot-latest
nano complete-ssl-setup.sh

# 2. Save your changes

# 3. Run the setup
chmod +x complete-ssl-setup.sh
sudo ./complete-ssl-setup.sh
```

**Duration**: ~5 minutes

### Step 2: Update AWS Security Group

1. **Close port 80** (no longer needed)
2. **Open port 9093**:
   ```
   Type: Custom TCP
   Port: 9093
   Source: 0.0.0.0/0
   Description: Kafka SSL - external clients
   ```

### Step 3: Test SSL

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
chmod +x test-kafka-ssl.sh
./test-kafka-ssl.sh
```

**Expected output:**
```
✓ Port 9093 is reachable
✓ Certificate expires: <date>
✓ SSL handshake successful
✓ Internal plaintext connection working
```

## What Happens During Setup

1. **Certbot Installation** - Installs Let's Encrypt client
2. **Certificate Generation** - Creates SSL certificate for kafka.lumniverse.com
3. **KeyStore Creation** - Converts certificates to Java KeyStore (Kafka format)
4. **Docker Compose Update** - Adds SSL configuration
5. **Kafka Restart** - Applies new SSL configuration
6. **Verification** - Checks everything is working

## After Setup

### Client Connection Changes

**Before (Plaintext):**
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9092"
```

**After (SSL):**
```bash
--set server.kafka.brokers="kafka.lumniverse.com:9093"
--set server.kafka.security.protocol="SSL"
```

### Certificate Auto-Renewal

Certificates expire in 90 days. Set up auto-renewal:

```bash
ssh mini-server

# Create renewal script
nano /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh
# (See SSL-SETUP-GUIDE.md for content, update password)

chmod +x /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh

# Add to crontab
sudo crontab -e
# Add this line:
0 0 * * * /usr/bin/certbot renew --quiet --deploy-hook "/home/ec2-user/kgroot-latest/renew-kafka-ssl.sh"
```

### Monitor Certificate Expiry

```bash
# Check certificate status
ssh mini-server "sudo certbot certificates"

# Check expiry date
ssh mini-server "echo | openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com 2>/dev/null | openssl x509 -noout -dates"
```

## Why SSL is Important for Clients

### Security Benefits
✓ **Encrypted communication** - Data can't be intercepted
✓ **Server authentication** - Clients verify they're connecting to the right server
✓ **Compliance** - Many enterprises require SSL/TLS
✓ **Trust** - Professional setup for production use

### What SSL Provides
- Data encryption in transit (TLS 1.2/1.3)
- Protection against man-in-the-middle attacks
- Certificate-based server verification
- Industry-standard security

### What SSL Doesn't Provide (Optional Additions)
- Client authentication (use SASL for this)
- Authorization/ACLs (configure separately)
- Encryption at rest (use EBS encryption)

## Testing with Real Clients

### Test Client Deployment

```bash
# From client's Kubernetes cluster
helm install test-ssl-client saas/client/helm-chart/kg-rca-agent \
  --set client.id=test-ssl-client-001 \
  --set client.apiKey=test-secure-key \
  --set server.kafka.brokers="kafka.lumniverse.com:9093" \
  --set server.kafka.security.protocol="SSL"

# Check logs
kubectl logs -l app=kg-rca-agent --tail=50 -f
```

**Expected log output:**
```
INFO  Connecting to Kafka: kafka.lumniverse.com:9093
INFO  Security protocol: SSL
INFO  Successfully connected to broker
INFO  Producing events to topic: raw.k8s.events
```

### Verify Data Flow

```bash
# On server, check for incoming messages
ssh mini-server "timeout 5 docker exec kgroot-latest-kafka-1 kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic raw.k8s.events --from-beginning --max-messages 5"
```

## Troubleshooting Quick Reference

### Issue: Certificate Generation Fails

**Check:**
1. Port 80 is open in AWS Security Group
2. DNS resolves: `nslookup kafka.lumniverse.com` returns 98.90.147.12
3. Domain is accessible: `curl http://kafka.lumniverse.com/.well-known/acme-challenge/test`

**Solution:**
```bash
# Check certbot logs
ssh mini-server "sudo tail -f /var/log/letsencrypt/letsencrypt.log"
```

### Issue: Kafka Won't Start with SSL

**Check:**
1. Keystore files exist: `ls -la /home/ec2-user/kafka-ssl/`
2. Permissions are correct: `sudo chown -R 1000:1000 /home/ec2-user/kafka-ssl`
3. Password is correct in docker-compose

**Solution:**
```bash
# Check Kafka logs
ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 100"
```

### Issue: Client Can't Connect

**Check:**
1. Port 9093 is open in AWS Security Group
2. DNS resolves from client: `nslookup kafka.lumniverse.com`
3. Port is reachable: `telnet kafka.lumniverse.com 9093`
4. Certificate is valid: `openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com`

**Solution:**
```bash
# Temporary: Disable certificate verification (testing only)
--set server.kafka.ssl.endpoint.identification.algorithm=""
```

## Migration Strategy

### Phase 1: Dual Mode (After SSL Setup)
- Both 9092 (plaintext) and 9093 (SSL) work
- Existing clients continue on 9092
- New clients use 9093

### Phase 2: Gradual Migration
- Update one client at a time to SSL
- Test thoroughly before next client
- Monitor for issues

### Phase 3: SSL Only (Optional)
- Once all clients on SSL, close port 9092
- Internal services still use plaintext in Docker

## Security Posture

### Current Setup Provides
✓ TLS 1.2/1.3 encryption
✓ Let's Encrypt certificate (trusted by all browsers/systems)
✓ Automatic certificate renewal
✓ Server authentication
✓ Industry-standard security

### Good For
- Production SaaS clients
- Enterprise customers
- Compliance requirements
- Public internet exposure

### Consider Adding Later
- SASL authentication (client credentials)
- Kafka ACLs (topic-level permissions)
- mTLS (mutual TLS with client certificates)
- EBS encryption (data at rest)

## Cost

**All free!**
- Let's Encrypt certificates: Free
- Certbot: Open source
- TLS implementation: Built into Kafka
- Renewal: Automated, no maintenance cost

## Performance Impact

- **Minimal** - SSL adds ~1-2% CPU overhead
- Internal services use plaintext (no impact)
- Modern CPUs have hardware AES acceleration
- Connection reuse minimizes handshake overhead

## Files Reference

| File | Location | Purpose |
|------|----------|---------|
| Setup script | `/home/ec2-user/kgroot-latest/complete-ssl-setup.sh` | Automated SSL setup |
| Test script | `/home/ec2-user/kgroot-latest/test-kafka-ssl.sh` | Verify SSL works |
| Certificates | `/etc/letsencrypt/live/kafka.lumniverse.com/` | SSL certificates |
| Keystores | `/home/ec2-user/kafka-ssl/*.jks` | Kafka KeyStores |
| Docker Compose | `/home/ec2-user/kgroot-latest/docker-compose-fixed.yml` | Kafka config |
| Backups | `/home/ec2-user/kgroot-latest/docker-compose-fixed.yml.backup-*` | Config backups |

## Next Actions (In Order)

1. **Edit setup script** - Add your email and password
2. **Open port 80** - Temporarily in AWS Security Group
3. **Run setup** - Execute `complete-ssl-setup.sh`
4. **Close port 80, open 9093** - Update Security Group
5. **Test SSL** - Run `test-kafka-ssl.sh`
6. **Set up auto-renewal** - Add cron job
7. **Test with client** - Deploy one test client with SSL
8. **Update documentation** - Tell clients to use SSL
9. **Migrate clients** - Gradually move all to SSL

## Success Criteria

You know SSL is working when:
- ✓ `test-kafka-ssl.sh` shows all tests passing
- ✓ `openssl s_client -connect kafka.lumniverse.com:9093` shows "Verify return code: 0 (ok)"
- ✓ Test client connects successfully with SSL
- ✓ Client logs show "Security protocol: SSL"
- ✓ Data flows from client → Kafka → Neo4j
- ✓ Internal services still work (graph-builder, etc.)

## Support Resources

- **Detailed Guide**: [SSL-SETUP-GUIDE.md](SSL-SETUP-GUIDE.md)
- **Quick Checklist**: [SSL-CHECKLIST.md](SSL-CHECKLIST.md)
- **Production Setup**: [PRODUCTION-SETUP.md](PRODUCTION-SETUP.md)
- **Quick Commands**: [QUICK-REFERENCE.md](QUICK-REFERENCE.md)

## Questions?

Common questions answered in SSL-SETUP-GUIDE.md:
- How do I update my Helm chart for SSL?
- What if certificate verification fails?
- How do I manually renew certificates?
- Can I use both plaintext and SSL?
- What about client authentication?

---

## Ready to Start?

```bash
# 1. Edit configuration
ssh mini-server
cd /home/ec2-user/kgroot-latest
nano complete-ssl-setup.sh
# Change EMAIL and KEYSTORE_PASSWORD

# 2. Open port 80 in AWS (temporarily)

# 3. Run setup
chmod +x complete-ssl-setup.sh
sudo ./complete-ssl-setup.sh

# 4. That's it! Follow on-screen instructions.
```

**Estimated time: 15-20 minutes total**

Good luck! 🚀
