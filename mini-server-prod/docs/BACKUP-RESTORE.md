# Backup and Restore Guide

## Overview

This guide covers backup strategies, procedures, and recovery processes for the KG RCA platform.

## What Gets Backed Up

### Critical Data

1. **Neo4j Database**
   - Graph data (nodes, relationships)
   - Indexes
   - Constraints
   - Location: `/var/lib/docker/volumes/mini-server-prod_neo4j-data`

2. **Kafka Data** (Optional)
   - Topic data (messages)
   - Topic configurations
   - Consumer offsets
   - Location: `/var/lib/docker/volumes/mini-server-prod_kafka-data`

3. **Configuration Files**
   - docker-compose.yml
   - .env file (sanitized)
   - Prometheus config
   - Grafana dashboards
   - SSL certificates

### Non-Critical Data

- Logs (can be regenerated)
- Metrics (Prometheus data)
- Temporary files

## Backup Strategies

### Strategy 1: Manual Backups (Development)

**When**: Before major changes, on-demand
**Retention**: 7 days
**Method**: Script-based

### Strategy 2: Scheduled Backups (Production)

**When**: Daily at 2 AM
**Retention**: 30 days
**Method**: Cron + script

### Strategy 3: Continuous Backups (Enterprise)

**When**: Real-time replication
**Retention**: Point-in-time recovery
**Method**: Neo4j Enterprise backup, Kafka MirrorMaker

## Backup Procedures

### Manual Backup

#### Using the Backup Script

```bash
cd ~/kg-rca/mini-server-prod

# Run backup script
./scripts/backup.sh

# Check backup
ls -lh backups/
```

#### Manual Step-by-Step

```bash
# 1. Create backup directory
BACKUP_DIR="./backups/manual-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 2. Backup Neo4j
docker run --rm \
    --volumes-from kg-neo4j \
    -v "$BACKUP_DIR:/backup" \
    ubuntu \
    tar czf /backup/neo4j-data.tar.gz /data

# 3. Backup Kafka metadata
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --describe > "$BACKUP_DIR/kafka-topics.txt"

# 4. Backup configurations
cp docker-compose*.yml "$BACKUP_DIR/"
cp -r config "$BACKUP_DIR/"
grep -v -E 'PASSWORD|KEY|SECRET' .env > "$BACKUP_DIR/env-template.txt"

# 5. Backup SSL certificates
cp -r ssl "$BACKUP_DIR/" 2>/dev/null || true

# 6. Create manifest
cat > "$BACKUP_DIR/manifest.txt" <<EOF
Backup created: $(date)
Hostname: $(hostname)
Docker version: $(docker --version)
Services: $(docker compose ps --services)
EOF

# 7. Compress
tar czf "backups/manual-$(date +%Y%m%d_%H%M%S).tar.gz" -C "$BACKUP_DIR" .
rm -rf "$BACKUP_DIR"

echo "Backup complete!"
```

### Automated Backups

#### Setup Cron Job

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /home/ubuntu/kg-rca/mini-server-prod && ./scripts/backup.sh >> /home/ubuntu/backup.log 2>&1

# Add weekly backup to S3
0 3 * * 0 aws s3 sync /home/ubuntu/kg-rca/mini-server-prod/backups s3://your-backup-bucket/kg-rca/ >> /home/ubuntu/s3-sync.log 2>&1
```

#### Verify Cron Jobs

```bash
# List cron jobs
crontab -l

# Check cron logs
grep CRON /var/log/syslog

# Test backup script
./scripts/backup.sh
```

### Backup to Cloud Storage

#### AWS S3

```bash
# Install AWS CLI
sudo apt install awscli -y

# Configure credentials
aws configure

# Create bucket
aws s3 mb s3://kg-rca-backups

# Enable versioning
aws s3api put-bucket-versioning \
    --bucket kg-rca-backups \
    --versioning-configuration Status=Enabled

# Enable lifecycle policy (delete after 30 days)
cat > lifecycle.json <<EOF
{
    "Rules": [
        {
            "Id": "DeleteOldBackups",
            "Status": "Enabled",
            "Expiration": {
                "Days": 30
            }
        }
    ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
    --bucket kg-rca-backups \
    --lifecycle-configuration file://lifecycle.json

# Upload backup
aws s3 cp backups/kg-rca-backup-*.tar.gz s3://kg-rca-backups/

# Sync entire backup directory
aws s3 sync backups/ s3://kg-rca-backups/
```

#### Google Cloud Storage

```bash
# Install gsutil
curl https://sdk.cloud.google.com | bash
gcloud init

# Create bucket
gsutil mb gs://kg-rca-backups

# Enable versioning
gsutil versioning set on gs://kg-rca-backups

# Upload
gsutil cp backups/kg-rca-backup-*.tar.gz gs://kg-rca-backups/
```

#### DigitalOcean Spaces

```bash
# Install s3cmd
sudo apt install s3cmd -y

# Configure
s3cmd --configure

# Upload
s3cmd put backups/kg-rca-backup-*.tar.gz s3://your-space/
```

## Restore Procedures

### Full System Restore

#### Step 1: Stop Services

```bash
cd ~/kg-rca/mini-server-prod
docker compose down
```

#### Step 2: Extract Backup

```bash
# List available backups
ls -lh backups/

# Extract backup
BACKUP_FILE="backups/kg-rca-backup-20240101_020000.tar.gz"
RESTORE_DIR="./restore-temp"
mkdir -p "$RESTORE_DIR"
tar xzf "$BACKUP_FILE" -C "$RESTORE_DIR"

# View manifest
cat "$RESTORE_DIR/manifest.txt"
```

#### Step 3: Restore Neo4j Data

```bash
# Remove old volume
docker volume rm mini-server-prod_neo4j-data

# Recreate volume
docker volume create mini-server-prod_neo4j-data

# Restore data
docker run --rm \
    -v mini-server-prod_neo4j-data:/data \
    -v "$(pwd)/$RESTORE_DIR:/backup" \
    ubuntu \
    tar xzf /backup/neo4j-data.tar.gz -C /
```

#### Step 4: Restore Configurations

```bash
# Restore docker-compose files
cp "$RESTORE_DIR"/docker-compose*.yml ./

# Restore configs
cp -r "$RESTORE_DIR/config" ./

# Restore SSL certs (if backed up)
cp -r "$RESTORE_DIR/ssl" ./ 2>/dev/null || true

# Restore .env (you'll need to add passwords manually)
cp "$RESTORE_DIR/env-template.txt" .env
# Edit .env to add passwords
nano .env
```

#### Step 5: Start Services

```bash
# Start services
docker compose up -d

# Wait for services to be healthy
sleep 30
docker compose ps
```

#### Step 6: Recreate Kafka Topics

```bash
# Kafka topics are recreated automatically
# Or manually from backup:
./scripts/create-topics.sh

# Verify
docker exec kg-kafka kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --list
```

#### Step 7: Verify Restore

```bash
# Check services
./scripts/test-services.sh

# Check Neo4j data
docker exec -it kg-neo4j cypher-shell -u neo4j -p YOUR_PASSWORD <<EOF
MATCH (n) RETURN labels(n)[0] as Label, count(n) as Count;
EOF

# Check logs
docker compose logs -f --tail=50
```

### Partial Restore

#### Restore Only Neo4j

```bash
# Stop Neo4j
docker compose stop neo4j

# Backup current data (safety)
docker run --rm \
    --volumes-from kg-neo4j \
    -v "$(pwd)/backups:/backup" \
    ubuntu \
    tar czf /backup/neo4j-before-restore-$(date +%Y%m%d_%H%M%S).tar.gz /data

# Restore
docker run --rm \
    --volumes-from kg-neo4j \
    -v "$(pwd)/restore-temp:/backup" \
    ubuntu \
    bash -c "rm -rf /data/* && tar xzf /backup/neo4j-data.tar.gz -C /"

# Start Neo4j
docker compose start neo4j

# Verify
docker logs kg-neo4j -f
```

#### Restore Only Configurations

```bash
# Backup current config
cp docker-compose.yml docker-compose.yml.bak

# Restore from backup
cp restore-temp/docker-compose.yml ./

# Review changes
diff docker-compose.yml.bak docker-compose.yml

# Apply changes
docker compose up -d
```

### Restore from Cloud Storage

#### AWS S3

```bash
# List backups
aws s3 ls s3://kg-rca-backups/

# Download latest
aws s3 cp s3://kg-rca-backups/kg-rca-backup-20240101_020000.tar.gz ./backups/

# Download all
aws s3 sync s3://kg-rca-backups/ ./backups/

# Then follow full restore procedure above
```

#### Point-in-Time Restore (S3 Versioning)

```bash
# List versions
aws s3api list-object-versions \
    --bucket kg-rca-backups \
    --prefix kg-rca-backup-

# Restore specific version
aws s3api get-object \
    --bucket kg-rca-backups \
    --key kg-rca-backup-20240101_020000.tar.gz \
    --version-id VERSION_ID \
    ./backups/restored-backup.tar.gz
```

## Disaster Recovery

### Scenario 1: Complete Server Loss

**Recovery Time Objective (RTO)**: 2 hours
**Recovery Point Objective (RPO)**: 24 hours (daily backups)

#### Recovery Steps:

1. **Provision New Server**
   ```bash
   # Launch new EC2/Droplet with same specs
   # Note new IP address
   ```

2. **Initial Setup**
   ```bash
   # SSH to new server
   ssh ubuntu@NEW_SERVER_IP

   # Run setup script
   sudo apt update
   sudo apt install git -y
   git clone https://github.com/your-org/kgroot_latest.git
   cd kgroot_latest/mini-server-prod
   sudo ./scripts/setup-ubuntu.sh
   ```

3. **Download Backup**
   ```bash
   # Install AWS CLI
   sudo apt install awscli -y
   aws configure

   # Download latest backup
   mkdir -p backups
   aws s3 cp s3://kg-rca-backups/kg-rca-backup-LATEST.tar.gz ./backups/
   ```

4. **Restore System**
   ```bash
   # Follow full restore procedure above
   # Update DNS/IP addresses
   # Test all services
   ```

5. **Update Clients**
   ```bash
   # Update client Helm values with new server IP
   # Redeploy clients
   ```

### Scenario 2: Data Corruption

**Detection**: Monitoring alerts, query errors

#### Recovery Steps:

1. **Identify Corruption**
   ```bash
   # Check Neo4j consistency
   docker exec kg-neo4j neo4j-admin check-consistency

   # Check logs
   docker logs kg-neo4j | grep -i "corrupt\|error"
   ```

2. **Stop Affected Services**
   ```bash
   docker compose stop neo4j graph-builder
   ```

3. **Restore Last Known Good Backup**
   ```bash
   # Find uncorrupted backup
   ls -lt backups/

   # Restore (follow Neo4j restore procedure)
   ```

4. **Verify Integrity**
   ```bash
   docker exec kg-neo4j neo4j-admin check-consistency
   ```

5. **Restart Services**
   ```bash
   docker compose start neo4j graph-builder
   ```

### Scenario 3: Accidental Deletion

**Example**: Accidentally deleted Neo4j data

#### Recovery Steps:

1. **Stop Further Damage**
   ```bash
   docker compose stop
   ```

2. **Restore Most Recent Backup**
   ```bash
   # Follow full restore procedure
   # Use most recent backup
   ```

3. **Replay Kafka Messages (if possible)**
   ```bash
   # Kafka retains messages based on retention policy
   # Graph Builder will reprocess from earliest available offset
   docker compose start kafka zookeeper

   # Reset consumer group to earliest
   docker exec kg-kafka kafka-consumer-groups.sh \
       --bootstrap-server localhost:9092 \
       --group kg-builder \
       --reset-offsets --to-earliest --execute --all-topics

   # Start Graph Builder
   docker compose start graph-builder
   ```

## Backup Verification

### Regular Verification (Monthly)

```bash
# 1. Restore to test environment
# 2. Verify data integrity
# 3. Test application functionality
# 4. Document results
```

### Automated Verification Script

```bash
#!/bin/bash
# verify-backup.sh

BACKUP_FILE="$1"
TEST_DIR="/tmp/backup-verify-$(date +%s)"

echo "Verifying backup: $BACKUP_FILE"

# Extract
mkdir -p "$TEST_DIR"
tar xzf "$BACKUP_FILE" -C "$TEST_DIR"

# Check manifest
if [ ! -f "$TEST_DIR/manifest.txt" ]; then
    echo "ERROR: No manifest file"
    exit 1
fi

# Check Neo4j data
if [ ! -f "$TEST_DIR/neo4j-data.tar.gz" ]; then
    echo "ERROR: No Neo4j data"
    exit 1
fi

# Verify tar integrity
tar tzf "$TEST_DIR/neo4j-data.tar.gz" > /dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Corrupted Neo4j data"
    exit 1
fi

# Check size
SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE")
if [ $SIZE -lt 1000000 ]; then  # Less than 1MB is suspicious
    echo "WARNING: Backup file is very small ($SIZE bytes)"
fi

echo "✓ Backup verification passed"
rm -rf "$TEST_DIR"
```

## Backup Monitoring

### Monitor Backup Success

```bash
# Check last backup time
ls -lt backups/ | head -5

# Check backup size trends
du -h backups/* | tail -10

# Alert if no recent backup
if [ $(find backups/ -name "*.tar.gz" -mtime -1 | wc -l) -eq 0 ]; then
    echo "WARNING: No backup in last 24 hours"
fi
```

### Grafana Dashboard

Create dashboard with:
- Last backup time
- Backup size trend
- Backup success rate
- Storage usage

## Best Practices

1. **3-2-1 Rule**
   - 3 copies of data
   - 2 different media
   - 1 off-site

2. **Automate Everything**
   - Scheduled backups
   - Verification tests
   - Monitoring alerts

3. **Test Restores**
   - Monthly restore tests
   - Document procedures
   - Time the process

4. **Secure Backups**
   - Encrypt backups
   - Restrict access
   - Audit access logs

5. **Monitor & Alert**
   - Backup success/failure
   - Storage capacity
   - Backup age

6. **Document Everything**
   - Backup procedures
   - Restore procedures
   - Lessons learned

## Troubleshooting

### Backup Fails

```bash
# Check disk space
df -h

# Check permissions
ls -la backups/

# Check Docker volumes
docker volume ls
docker volume inspect mini-server-prod_neo4j-data

# Check logs
tail -f /home/ubuntu/backup.log
```

### Restore Fails

```bash
# Check backup integrity
tar tzf backup-file.tar.gz

# Check Docker volume
docker volume inspect mini-server-prod_neo4j-data

# Check service logs
docker logs kg-neo4j
```

### Large Backup Size

```bash
# Check what's consuming space
docker exec kg-neo4j du -sh /data/*

# Clean old Neo4j logs
docker exec kg-neo4j find /logs -name "*.log" -mtime +7 -delete

# Compact Kafka logs
docker exec kg-kafka kafka-log-dirs.sh --bootstrap-server localhost:9092 --describe
```

## Recovery Time Estimates

| Scenario | RTO | RPO | Complexity |
|----------|-----|-----|------------|
| Single service failure | 5 min | 0 | Low |
| Partial data loss | 30 min | 24h | Medium |
| Complete server loss | 2 hours | 24h | High |
| Disaster recovery | 4 hours | 24h | High |

## Contacts

**Backup Issues**: sysadmin@example.com
**Emergency Recovery**: oncall@example.com
**Cloud Storage**: cloud-team@example.com

---

**Remember: Backups are only as good as your ability to restore from them. Test regularly!**
