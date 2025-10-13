# SSL Setup Checklist

## Pre-Setup (Do This First!)

- [ ] **Edit the setup script** with your actual values:
  ```bash
  ssh mini-server
  cd /home/ec2-user/kgroot-latest
  nano complete-ssl-setup.sh

  # Change:
  EMAIL="your-email@company.com"
  KEYSTORE_PASSWORD="YourSecurePassword123"  # Use a strong password!
  ```

- [ ] **Open port 80 temporarily** in AWS Security Group:
  ```
  Type: HTTP
  Port: 80
  Source: 0.0.0.0/0
  Description: Temporary for Let's Encrypt
  ```

## Run Setup

- [ ] **Execute the SSL setup script:**
  ```bash
  ssh mini-server
  cd /home/ec2-user/kgroot-latest
  chmod +x complete-ssl-setup.sh
  sudo ./complete-ssl-setup.sh
  ```

- [ ] **Save the keystore password** displayed at the end (you'll need it!)

## Post-Setup

- [ ] **Close port 80** (no longer needed)

- [ ] **Open port 9093** in AWS Security Group:
  ```
  Type: Custom TCP
  Port: 9093
  Source: 0.0.0.0/0
  Description: Kafka SSL - external clients
  ```

- [ ] **Test SSL connection:**
  ```bash
  ssh mini-server
  cd /home/ec2-user/kgroot-latest
  chmod +x test-kafka-ssl.sh
  ./test-kafka-ssl.sh
  ```

- [ ] **Set up certificate auto-renewal:**
  ```bash
  # Create renewal script
  ssh mini-server
  nano /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh
  # (Copy content from SSL-SETUP-GUIDE.md, update password)

  chmod +x /home/ec2-user/kgroot-latest/renew-kafka-ssl.sh

  # Add to crontab
  sudo crontab -e
  # Add: 0 0 * * * /usr/bin/certbot renew --quiet --deploy-hook "/home/ec2-user/kgroot-latest/renew-kafka-ssl.sh"
  ```

## Update Client Documentation

- [ ] **Update client onboarding docs** with SSL connection string:
  ```bash
  --set server.kafka.brokers="kafka.lumniverse.com:9093"
  --set server.kafka.security.protocol="SSL"
  ```

- [ ] **Test with one pilot client** before rolling out to all

## AWS Security Group Final State

Your security group should now have:

```
Inbound Rules:
┌────────────┬─────────┬──────────────────┬─────────────────────────────┐
│ Type       │ Port    │ Source           │ Description                 │
├────────────┼─────────┼──────────────────┼─────────────────────────────┤
│ SSH        │ 22      │ Your-IP/32       │ Admin access                │
│ Custom TCP │ 9092    │ 0.0.0.0/0        │ Kafka Plaintext (optional)  │
│ Custom TCP │ 9093    │ 0.0.0.0/0        │ Kafka SSL (required)        │
└────────────┴─────────┴──────────────────┴─────────────────────────────┘
```

**Note**: Port 9092 can remain open for backward compatibility, or close it if all clients use SSL.

## Client Testing

- [ ] **Test DNS from client cluster:**
  ```bash
  nslookup kafka.lumniverse.com
  # Should return: 98.90.147.12
  ```

- [ ] **Test SSL port:**
  ```bash
  openssl s_client -connect kafka.lumniverse.com:9093 -servername kafka.lumniverse.com
  ```

- [ ] **Deploy test client:**
  ```bash
  helm install test-ssl-client saas/client/helm-chart/kg-rca-agent \
    --set client.id=test-ssl-client \
    --set client.apiKey=test-key \
    --set server.kafka.brokers="kafka.lumniverse.com:9093" \
    --set server.kafka.security.protocol="SSL"
  ```

- [ ] **Check client logs for successful connection:**
  ```bash
  kubectl logs -l app=kg-rca-agent --tail=50
  # Look for: "Successfully connected" and "Security protocol: SSL"
  ```

## Monitoring

- [ ] **Set up certificate expiry monitoring:**
  - Add Grafana dashboard
  - Or use: `sudo certbot certificates` to check manually

- [ ] **Monitor SSL connections:**
  ```bash
  ssh mini-server "docker exec kgroot-latest-kafka-1 netstat -tn | grep :9093"
  ```

- [ ] **Check logs regularly:**
  ```bash
  ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 100 | grep SSL"
  ```

## Troubleshooting Resources

If something goes wrong:
1. See [SSL-SETUP-GUIDE.md](SSL-SETUP-GUIDE.md) - Troubleshooting section
2. Check Kafka logs: `docker logs kgroot-latest-kafka-1`
3. Verify AWS Security Group rules
4. Test DNS resolution
5. Check certificate validity: `sudo certbot certificates`

## Rollback Plan (If Needed)

If SSL setup fails and you need to rollback:

```bash
ssh mini-server
cd /home/ec2-user/kgroot-latest

# Restore backup
cp docker-compose-fixed.yml.backup-* docker-compose-fixed.yml

# Restart Kafka
docker-compose -f docker-compose-fixed.yml restart kafka
```

## Success Criteria

✓ All tests in `test-kafka-ssl.sh` pass
✓ Port 9093 is reachable from outside
✓ Certificate is valid and not expired
✓ Test client connects successfully with SSL
✓ Internal services still work on plaintext (9092)
✓ Auto-renewal is configured

## Next Steps After SSL

Once SSL is working:
- [ ] Migrate existing clients from 9092 → 9093
- [ ] Update all documentation
- [ ] Consider adding SASL authentication
- [ ] Set up alerting for certificate expiry
- [ ] Document disaster recovery procedures

## Important Files

- **Setup script**: `/home/ec2-user/kgroot-latest/complete-ssl-setup.sh`
- **Test script**: `/home/ec2-user/kgroot-latest/test-kafka-ssl.sh`
- **Renewal script**: `/home/ec2-user/kgroot-latest/renew-kafka-ssl.sh`
- **Certificates**: `/etc/letsencrypt/live/kafka.lumniverse.com/`
- **Keystores**: `/home/ec2-user/kafka-ssl/`
- **Docker Compose**: `/home/ec2-user/kgroot-latest/docker-compose-fixed.yml`
- **Backup**: `/home/ec2-user/kgroot-latest/docker-compose-fixed.yml.backup-*`

## Support Contacts

For issues:
- AWS: Check Security Group, EIP, DNS
- Let's Encrypt: Check port 80 access, DNS resolution
- Kafka: Check logs, keystore permissions, environment variables
- Clients: Verify connection string, SSL protocol setting
