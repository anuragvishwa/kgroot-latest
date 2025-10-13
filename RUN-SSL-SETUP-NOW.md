# Run SSL Setup Now - Step by Step

## Current Status

❌ SSL is **NOT enabled** - that's why you're getting connection errors
✅ DNS works: kafka.lumniverse.com → 98.90.147.12
✅ SSL scripts are ready on the server

## Step 1: Configure AWS Security Group (5 minutes)

### Go to AWS Console

1. Open: https://console.aws.amazon.com/ec2/
2. Click **Security Groups** (left sidebar)
3. Find your instance's security group

### Add These Rules Temporarily

**Add Inbound Rule #1 (Temporary for SSL setup)**:
```
Type: HTTP
Protocol: TCP
Port: 80
Source: 0.0.0.0/0
Description: Temporary - Let's Encrypt verification
```

**Add Inbound Rule #2 (Permanent for SSL)**:
```
Type: Custom TCP
Protocol: TCP
Port: 9093
Source: 0.0.0.0/0
Description: Kafka SSL - client connections
```

**Your security group should now have**:
- Port 22 (SSH) ✓ Already there
- Port 80 (HTTP) ✓ Just added (temporary)
- Port 9092 (Kafka plaintext) ✓ Already there
- Port 9093 (Kafka SSL) ✓ Just added

Click **"Save rules"**

## Step 2: Edit SSL Setup Script (2 minutes)

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest
nano complete-ssl-setup.sh
```

**Find and change these lines (around line 8-9)**:

```bash
# BEFORE:
EMAIL="admin@lumniverse.com"  # CHANGE THIS
KEYSTORE_PASSWORD="changeit123"  # CHANGE THIS to a secure password

# AFTER (use your values):
EMAIL="support@lumniverse.com"  # Your real email
KEYSTORE_PASSWORD="LumniSecure2024!@#"  # Strong password - SAVE THIS!
```

**Save the file**:
- Press `Ctrl + X`
- Press `Y`
- Press `Enter`

**IMPORTANT**: Write down your KEYSTORE_PASSWORD somewhere safe!

## Step 3: Run SSL Setup (5-10 minutes)

```bash
# Still on the server:
cd /home/ec2-user/kgroot-latest
chmod +x complete-ssl-setup.sh
sudo ./complete-ssl-setup.sh
```

**What will happen**:
1. Installs certbot
2. Stops Kafka temporarily
3. Generates SSL certificate from Let's Encrypt
4. Creates Java KeyStores for Kafka
5. Updates docker-compose configuration
6. Restarts Kafka with SSL enabled
7. Verifies setup

**Expected output (end)**:
```
╔══════════════════════════════════════════════════════════════╗
║               SSL Setup Complete!                            ║
╚══════════════════════════════════════════════════════════════╝

Configuration Summary:
  • SSL Certificate: /etc/letsencrypt/live/kafka.lumniverse.com
  • KeyStore: /home/ec2-user/kafka-ssl/kafka.keystore.jks
  • KeyStore Password: <your-password>

Kafka Endpoints:
  • Plaintext (internal): kafka:9092
  • SSL (external): kafka.lumniverse.com:9093
```

**If it fails**, check:
- Port 80 is open in AWS Security Group
- DNS resolves correctly: `nslookup kafka.lumniverse.com`
- No other service is using port 80: `sudo lsof -i :80`

## Step 4: Test SSL Connection (2 minutes)

```bash
# On the server:
cd /home/ec2-user/kgroot-latest
chmod +x test-kafka-ssl.sh
./test-kafka-ssl.sh
```

**Expected output**:
```
✓ Port 9093 is reachable
✓ Certificate expires: <date>
✓ SSL handshake successful
✓ Internal plaintext connection working
```

**Also test from your local machine**:
```bash
# From your Mac:
openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com
```

Should show:
```
Verify return code: 0 (ok)
```

## Step 5: Close Port 80 (1 minute)

Once SSL setup is complete, **close port 80** in AWS Security Group:

1. Go back to AWS Console → Security Groups
2. Find the rule with Port 80
3. Click "Delete" on that rule
4. Save

**Keep these ports open**:
- Port 22 (SSH)
- Port 9092 (Kafka plaintext - optional, for backward compatibility)
- Port 9093 (Kafka SSL - required)

## Step 6: Verify from Outside (1 minute)

```bash
# From your local Mac:

# Test port connectivity
nc -zv kafka.lumniverse.com 9093

# Test SSL certificate
openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com </dev/null 2>&1 | grep "Verify return code"
```

Should show:
```
Verify return code: 0 (ok)
```

## What's Next

After SSL is working:

1. ✅ Update chart to use SSL by default (I'll do this)
2. ✅ Publish to Artifact Hub
3. ✅ Test with a real client

## Troubleshooting

### Error: Port 80 connection refused

**Solution**: Make sure port 80 is open in AWS Security Group

### Error: certbot fails

**Check**:
```bash
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

Common issues:
- Port 80 not open
- DNS not resolving correctly
- Another service using port 80

### Error: Kafka won't start

**Check logs**:
```bash
docker logs kgroot-latest-kafka-1 --tail 100
```

Common issues:
- KeyStore permissions: `sudo chown -R 1000:1000 /home/ec2-user/kafka-ssl`
- Wrong password in docker-compose

### SSL test fails

**Check Kafka is listening**:
```bash
docker exec kgroot-latest-kafka-1 netstat -tuln | grep 9093
```

Should show:
```
tcp        0      0 0.0.0.0:9093            0.0.0.0:*               LISTEN
```

## Quick Reference

```bash
# SSH to server
ssh mini-server

# Check Kafka status
docker ps | grep kafka

# Check SSL configuration
docker exec kgroot-latest-kafka-1 sh -c 'env | grep SSL'

# Check logs
docker logs kgroot-latest-kafka-1 --tail 50

# Test SSL locally (on server)
timeout 3 openssl s_client -connect localhost:9093 </dev/null

# Restart Kafka if needed
cd /home/ec2-user/kgroot-latest
docker-compose -f docker-compose-fixed.yml restart kafka
```

---

**Ready? Start with Step 1!** 🚀
