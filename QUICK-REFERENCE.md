# Quick Reference Card

## Server Info
- **IP**: 98.90.147.12 (Elastic IP)
- **Domain**: kafka.lumniverse.com
- **SSH**: `ssh mini-server`

## Exposed Ports (AWS Security Group)
- **9092**: Kafka (clients) - ✓ MUST BE OPEN
- **22**: SSH (admin) - ✓ MUST BE OPEN

## Internal Ports (SSH Tunnel Only)
```bash
ssh -L 7474:localhost:7474 -L 7687:localhost:7687 -L 8080:localhost:8080 -L 7777:localhost:7777 -L 3000:localhost:3000 mini-server
```
- **7474**: Neo4j Browser → http://localhost:7474
- **7687**: Neo4j Bolt → bolt://localhost:7687
- **8080**: KG API → http://localhost:8080
- **7777**: Kafka UI → http://localhost:7777
- **3000**: Grafana → http://localhost:3000

## Client Connection
```bash
helm install client-name saas/client/helm-chart/kg-rca-agent \
  --set client.id=<unique-id> \
  --set client.apiKey=<secure-key> \
  --set server.kafka.brokers="kafka.lumniverse.com:9092"
```

## Common Commands

### Check Service Status
```bash
ssh mini-server "docker ps"
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml ps"
```

### View Logs
```bash
# Kafka
ssh mini-server "docker logs kgroot-latest-kafka-1 --tail 50 -f"

# Graph Builder
ssh mini-server "docker logs kgroot-latest-graph-builder-1 --tail 50 -f"

# KG API
ssh mini-server "docker logs kgroot-latest-kg-api-1 --tail 50 -f"
```

### Kafka Operations
```bash
# List topics
ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-topics.sh --bootstrap-server localhost:9092 --list"

# Consumer groups
ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list"

# Check consumer lag
ssh mini-server "docker exec kgroot-latest-kafka-1 kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --all-groups"

# Read from topic
ssh mini-server "timeout 3 docker exec kgroot-latest-kafka-1 kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic events.normalized --from-beginning --max-messages 5"
```

### Restart Services
```bash
# Restart all
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml restart"

# Restart specific service
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml restart kafka"
```

### System Health
```bash
# Disk space
ssh mini-server "df -h"

# Memory
ssh mini-server "free -h"

# Docker stats
ssh mini-server "docker stats --no-stream"
```

## Test Client Connection
```bash
# From client cluster
nslookup kafka.lumniverse.com  # Should return 98.90.147.12
telnet kafka.lumniverse.com 9092  # Should connect
```

## Neo4j Access
```bash
# Via SSH tunnel
ssh -L 7474:localhost:7474 mini-server
# Browse: http://localhost:7474
# User: neo4j / Pass: anuragvishwa
```

## Monitoring Access
```bash
# Via SSH tunnel
ssh -L 7777:localhost:7777 -L 3000:localhost:3000 mini-server
# Kafka UI: http://localhost:7777
# Grafana: http://localhost:3000 (admin/admin)
```

## Emergency Commands

### Stop Everything
```bash
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml down"
```

### Start Everything
```bash
ssh mini-server "cd /home/ec2-user/kgroot-latest && docker-compose -f docker-compose-fixed.yml up -d"
```

### Check Kafka Config
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 sh -c 'env | grep KAFKA'"
```

### Verify Advertised Listener
```bash
ssh mini-server "docker exec kgroot-latest-kafka-1 sh -c 'env | grep ADVERTISED'"
# Must show: KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka.lumniverse.com:9092
```

## Files Location
- **Docker Compose**: `/home/ec2-user/kgroot-latest/docker-compose-fixed.yml`
- **Services**: `/home/ec2-user/kgroot-latest/`
- **Data Volumes**: Docker volumes (kafka-data, neo4jdata, etc.)

## Client Graph Access Options

### Option 1: SSH Tunnel (Secure)
```bash
# Give client: ssh -L 7474:localhost:7474 user@kafka.lumniverse.com
# Access: http://localhost:7474
```

### Option 2: Direct Access (Less Secure)
```bash
# Open port 7474 in AWS Security Group
# Access: http://kafka.lumniverse.com:7474
```

### Option 3: Custom Dashboard (Production)
```bash
# Build web UI that queries KG API (port 8080)
# Deploy on: dashboard.lumniverse.com
# Keeps backend secure, provides branded UI
```

## SSL/TLS (Optional - Not Currently Configured)
```bash
# To add later:
sudo yum install certbot -y
sudo certbot certonly --standalone -d kafka.lumniverse.com
# Then configure Kafka SSL settings
```

## Support
- **Docs**: See PRODUCTION-SETUP.md for detailed instructions
- **Logs**: Check service logs when issues occur
- **AWS**: Ensure Security Group allows port 9092
