# Security Best Practices

## Overview

This guide covers security best practices for deploying and maintaining the KG RCA platform in production.

## Table of Contents
1. [Server Security](#server-security)
2. [Network Security](#network-security)
3. [Application Security](#application-security)
4. [Data Security](#data-security)
5. [Access Control](#access-control)
6. [Monitoring & Auditing](#monitoring--auditing)
7. [Incident Response](#incident-response)

---

## Server Security

### Operating System Hardening

#### 1. Keep System Updated

```bash
# Enable automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# Manual updates
sudo apt update && sudo apt upgrade -y
```

#### 2. Disable Root Login

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Set:
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd
```

#### 3. Configure SSH Keys Only

```bash
# On your local machine, generate key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Copy to server
ssh-copy-id -i ~/.ssh/id_ed25519.pub ubuntu@YOUR_SERVER

# Test
ssh ubuntu@YOUR_SERVER
```

#### 4. Install and Configure Fail2Ban

```bash
# Install
sudo apt install fail2ban -y

# Configure
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local

# Add:
[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600

# Start
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Check status
sudo fail2ban-client status sshd
```

#### 5. Disable Unnecessary Services

```bash
# List running services
systemctl list-units --type=service --state=running

# Disable unused services
sudo systemctl disable <service-name>
sudo systemctl stop <service-name>
```

---

## Network Security

### Firewall Configuration

#### UFW (Uncomplicated Firewall)

```bash
# Enable UFW
sudo ufw enable

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (IMPORTANT!)
sudo ufw allow 22/tcp comment 'SSH'

# Allow only necessary ports
sudo ufw allow 9093/tcp comment 'Kafka SSL'

# Optional - only if needed
sudo ufw allow from YOUR_OFFICE_IP to any port 7474 proto tcp comment 'Neo4j HTTP'
sudo ufw allow from YOUR_OFFICE_IP to any port 3000 proto tcp comment 'Grafana'

# Check status
sudo ufw status verbose

# View rules with numbers
sudo ufw status numbered

# Delete rule
sudo ufw delete <number>
```

#### Cloud Provider Firewall

**AWS Security Groups:**
```
Inbound Rules:
- SSH (22): Your IP only
- Kafka SSL (9093): 0.0.0.0/0 (client clusters)
- Neo4j (7474, 7687): Your IP only (if needed)
- KG API (8080): Client cluster IPs only
- Grafana (3000): Your IP only (or use SSH tunnel)

Outbound Rules:
- All traffic: 0.0.0.0/0
```

**DigitalOcean Firewall:**
```
Inbound:
- SSH: Your IP
- Custom: 9093, TCP, All IPv4
- Custom: 3000, TCP, Your IP (optional)

Outbound:
- All TCP, All IPv4
- All UDP, All IPv4
```

### SSL/TLS Configuration

#### 1. Enable SSL for Kafka

```bash
cd ~/kg-rca/mini-server-prod
./scripts/setup-ssl.sh
```

#### 2. Use Strong Cipher Suites

Edit `docker-compose.ssl.yml`:

```yaml
kafka:
  environment:
    KAFKA_SSL_ENABLED_PROTOCOLS: TLSv1.2,TLSv1.3
    KAFKA_SSL_CIPHER_SUITES: TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
```

#### 3. Enable Mutual TLS (Optional)

```yaml
kafka:
  environment:
    KAFKA_SSL_CLIENT_AUTH: required
```

### Network Segmentation

#### Use Docker Networks

```yaml
# docker-compose.yml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge

services:
  kg-api:
    networks:
      - frontend
      - backend

  neo4j:
    networks:
      - backend  # Not exposed to frontend
```

#### Use VPC (Cloud Providers)

- Place server in private subnet
- Use NAT gateway for outbound traffic
- Use VPC peering for client cluster access
- Use VPN for administrative access

---

## Application Security

### Environment Variables

#### 1. Never Commit Secrets

```bash
# .gitignore
.env
ssl/*.jks
ssl/*-key
ssl/*.pem
backups/
```

#### 2. Use Strong Passwords

```bash
# Generate strong passwords
openssl rand -base64 32

# Update .env
NEO4J_PASSWORD=<strong-password>
GRAFANA_PASSWORD=<strong-password>
KG_API_KEY=<strong-api-key>
```

#### 3. Rotate Credentials Regularly

```bash
# Schedule credential rotation (quarterly)
# 1. Generate new passwords
# 2. Update .env
# 3. Restart services
# 4. Update client configurations
```

### API Security

#### 1. Enable Authentication

```yaml
# docker-compose.yml
kg-api:
  environment:
    API_KEY: ${KG_API_KEY}
    AUTH_ENABLED: "true"
```

#### 2. Rate Limiting

```yaml
kg-api:
  environment:
    RATE_LIMIT_ENABLED: "true"
    RATE_LIMIT_REQUESTS: 100
    RATE_LIMIT_WINDOW: 60  # seconds
```

#### 3. CORS Configuration

```yaml
kg-api:
  environment:
    CORS_ENABLED: "true"
    CORS_ALLOWED_ORIGINS: "https://your-app.com"
```

### Container Security

#### 1. Use Official Images

```yaml
# docker-compose.yml
services:
  neo4j:
    image: neo4j:5.20  # Official image

  kafka:
    image: wurstmeister/kafka:latest  # Well-maintained
```

#### 2. Run as Non-Root User

```yaml
# docker-compose.yml
services:
  kg-api:
    user: "1000:1000"  # Run as non-root
```

#### 3. Read-Only Root Filesystem

```yaml
services:
  kg-api:
    read_only: true
    tmpfs:
      - /tmp
```

#### 4. Resource Limits

```yaml
services:
  neo4j:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

#### 5. Scan Images for Vulnerabilities

```bash
# Install Trivy
sudo apt install wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee -a /etc/apt/sources.list.d/trivy.list
sudo apt update
sudo apt install trivy

# Scan image
trivy image neo4j:5.20
trivy image wurstmeister/kafka:latest
```

---

## Data Security

### Encryption at Rest

#### 1. Encrypt Docker Volumes (Optional)

```bash
# Use LUKS for volume encryption
sudo apt install cryptsetup

# Create encrypted volume
sudo cryptsetup luksFormat /dev/xvdf
sudo cryptsetup open /dev/xvdf encrypted-volume
sudo mkfs.ext4 /dev/mapper/encrypted-volume
sudo mount /dev/mapper/encrypted-volume /var/lib/docker/volumes
```

#### 2. Use Encrypted EBS Volumes (AWS)

- Enable encryption when creating EBS volumes
- Use AWS KMS for key management
- Enable encryption by default

### Encryption in Transit

✅ **Enabled:**
- Kafka SSL (external clients)
- HTTPS for web UIs (via reverse proxy)

❌ **Not Encrypted (Internal Docker Network):**
- Neo4j Bolt (neo4j://neo4j:7687)
- Kafka internal (kafka:9092)

**To encrypt internal traffic:**

```yaml
# Use Neo4j SSL
neo4j:
  environment:
    NEO4J_dbms_ssl_policy_bolt_enabled: "true"
    NEO4J_dbms_ssl_policy_bolt_base_directory: /ssl/bolt
```

### Data Sanitization

#### 1. Log Sanitization

```bash
# Ensure no sensitive data in logs
docker logs kg-api | grep -i "password\|secret\|key"

# Configure log filters in application code
```

#### 2. Backup Encryption

```bash
# Encrypt backups before uploading
tar czf - backup/ | gpg --encrypt --recipient your@email.com > backup.tar.gz.gpg

# Decrypt
gpg --decrypt backup.tar.gz.gpg | tar xzf -
```

---

## Access Control

### Principle of Least Privilege

#### 1. Neo4j User Roles

```cypher
// Create read-only user
CREATE USER reader SET PASSWORD 'password';
GRANT ROLE reader TO reader;

// Create admin user
CREATE USER admin SET PASSWORD 'password';
GRANT ROLE admin TO admin;
```

#### 2. Grafana User Roles

- **Viewer**: Read-only dashboards
- **Editor**: Can edit dashboards
- **Admin**: Full control

```
Settings → Users → Add user
Set appropriate role
```

#### 3. Server Access

```bash
# Create limited user for application
sudo adduser app-user --disabled-password

# Give Docker access only
sudo usermod -aG docker app-user

# No sudo access
```

### Multi-Factor Authentication

#### Enable MFA for AWS

```bash
# AWS CLI with MFA
aws sts get-session-token --serial-number arn:aws:iam::ACCOUNT:mfa/USER --token-code MFA_CODE
```

#### Enable MFA for SSH

```bash
# Install Google Authenticator
sudo apt install libpam-google-authenticator

# Configure
google-authenticator

# Edit PAM config
sudo nano /etc/pam.d/sshd
# Add: auth required pam_google_authenticator.so

# Edit SSH config
sudo nano /etc/sshd_config
# Set: ChallengeResponseAuthentication yes

# Restart
sudo systemctl restart sshd
```

---

## Monitoring & Auditing

### Audit Logging

#### 1. Enable Docker Logging

```yaml
# docker-compose.yml
services:
  kg-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

#### 2. Enable Neo4j Query Logging

```yaml
neo4j:
  environment:
    NEO4J_dbms_logs_query_enabled: "true"
    NEO4J_dbms_logs_query_threshold: "1s"
```

#### 3. Monitor Auth Logs

```bash
# Watch SSH login attempts
sudo tail -f /var/log/auth.log

# Failed login attempts
sudo grep "Failed password" /var/log/auth.log

# Successful logins
sudo grep "Accepted publickey" /var/log/auth.log
```

### Security Monitoring

#### 1. Monitor for Security Events

```bash
# Check for rootkits
sudo apt install rkhunter
sudo rkhunter --check

# Check for malware
sudo apt install clamav
sudo freshclam
sudo clamscan -r /home
```

#### 2. File Integrity Monitoring

```bash
# Install AIDE
sudo apt install aide

# Initialize
sudo aideinit

# Check
sudo aide --check
```

#### 3. Network Monitoring

```bash
# Monitor connections
sudo netstat -tulpn

# Watch for suspicious activity
sudo tcpdump -i any port 9093

# Log network activity
sudo iptables -A INPUT -j LOG --log-prefix "IPTables-Input: "
sudo tail -f /var/log/syslog | grep IPTables
```

---

## Incident Response

### Preparation

#### 1. Create Incident Response Plan

Document:
- Contact information
- Escalation procedures
- Recovery procedures
- Backup locations

#### 2. Regular Backups

```bash
# Automated daily backups
crontab -e

# Add:
0 2 * * * /home/ubuntu/kg-rca/mini-server-prod/scripts/backup.sh
0 3 * * * aws s3 sync /home/ubuntu/kg-rca/mini-server-prod/backups s3://your-backup-bucket/
```

### Detection

#### Monitor for:
- Unusual login attempts
- Unexpected processes
- High network traffic
- Configuration changes
- Service restarts

#### Alerts:
```bash
# Email on SSH login
echo 'echo "SSH login from $(who | tail -1)" | mail -s "SSH Login Alert" admin@example.com' >> ~/.bashrc
```

### Response

#### If Compromised:

1. **Isolate**
   ```bash
   # Block all traffic
   sudo ufw default deny incoming
   sudo ufw default deny outgoing
   ```

2. **Investigate**
   ```bash
   # Check running processes
   ps aux
   top

   # Check network connections
   sudo netstat -tulpn

   # Check auth logs
   sudo grep -i "failed\|error" /var/log/auth.log

   # Check Docker logs
   docker logs --since 24h <container>
   ```

3. **Contain**
   ```bash
   # Stop suspicious containers
   docker stop <container>

   # Change all passwords
   # Rotate API keys
   # Revoke SSH keys
   ```

4. **Eradicate**
   ```bash
   # Remove malicious code
   # Patch vulnerabilities
   # Update all packages
   sudo apt update && sudo apt upgrade -y
   ```

5. **Recover**
   ```bash
   # Restore from backup
   ./scripts/restore-backup.sh

   # Restart services
   docker compose up -d

   # Verify integrity
   ./scripts/test-services.sh
   ```

6. **Document**
   - What happened
   - How it was detected
   - Actions taken
   - Lessons learned

---

## Security Checklist

### Initial Setup
- [ ] SSH key-based authentication
- [ ] Disabled root login
- [ ] UFW firewall configured
- [ ] Fail2Ban installed
- [ ] SSL certificates generated
- [ ] Strong passwords set
- [ ] .env file not in git

### Regular Maintenance
- [ ] System updates (monthly)
- [ ] Security patches (weekly)
- [ ] Log review (weekly)
- [ ] Backup verification (weekly)
- [ ] Credential rotation (quarterly)
- [ ] Access review (quarterly)
- [ ] Vulnerability scan (monthly)

### Ongoing Monitoring
- [ ] Failed login alerts
- [ ] Resource usage alerts
- [ ] Error rate alerts
- [ ] Backup success alerts
- [ ] Certificate expiry alerts

---

## Compliance Considerations

### GDPR
- Data encryption
- Access controls
- Audit logging
- Data retention policies
- Right to deletion

### SOC 2
- Access controls
- Encryption
- Logging and monitoring
- Incident response
- Regular audits

### HIPAA (if applicable)
- Encryption at rest and in transit
- Access controls
- Audit trails
- Backup and recovery
- Physical security

---

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Kubernetes Security Best Practices](https://kubernetes.io/docs/concepts/security/)

---

**Security is an ongoing process. Stay vigilant!**
