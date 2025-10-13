#!/bin/bash
set -e

echo "🚀 KG RCA Server - EC2 Setup Script"
echo "===================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should NOT be run as root"
   exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo "📋 Detected OS: $PRETTY_NAME"
else
    echo "❌ Cannot detect OS"
    exit 1
fi

# Update system based on OS
echo "📦 Updating system packages..."
if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
    sudo apt-get update
    sudo apt-get upgrade -y
elif [[ "$OS" == "amzn" ]] || [[ "$OS" == "rhel" ]] || [[ "$OS" == "centos" ]]; then
    sudo dnf update -y || sudo yum update -y
else
    echo "⚠️  Unknown OS, attempting to continue..."
fi

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
echo "🐳 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Install other utilities based on OS
echo "🔧 Installing utilities..."
if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
    sudo apt-get install -y \
        nginx \
        certbot \
        python3-certbot-nginx \
        git \
        curl \
        wget \
        htop \
        jq
elif [[ "$OS" == "amzn" ]] || [[ "$OS" == "rhel" ]] || [[ "$OS" == "centos" ]]; then
    # Amazon Linux 2023 / RHEL / CentOS
    # Skip curl since curl-minimal is usually already installed
    sudo dnf install -y \
        nginx \
        git \
        wget \
        htop \
        jq \
        python3-pip 2>/dev/null || sudo yum install -y \
        nginx \
        git \
        wget \
        htop \
        jq \
        python3-pip

    # Install certbot via pip for Amazon Linux
    sudo python3 -m pip install --break-system-packages certbot certbot-nginx 2>/dev/null || \
    sudo python3 -m pip install certbot certbot-nginx
fi

# Determine home directory (ec2-user for Amazon Linux, ubuntu for Ubuntu)
if [[ "$OS" == "amzn" ]]; then
    HOME_USER="ec2-user"
elif [[ "$OS" == "ubuntu" ]]; then
    HOME_USER="ubuntu"
else
    HOME_USER="$USER"
fi

# Create project directory
echo "📁 Setting up project directory..."
PROJECT_DIR="/home/$HOME_USER/kg-rca"
if [ ! -d "$PROJECT_DIR" ]; then
    mkdir -p $PROJECT_DIR
fi

# If we're already in server_mini directory, copy from current dir
CURRENT_DIR=$(pwd)
if [[ "$CURRENT_DIR" == *"server_mini"* ]]; then
    echo "📋 Copying configuration files from current directory..."
    cp -f docker-compose.yml $PROJECT_DIR/ 2>/dev/null || true
    cp -rf config $PROJECT_DIR/ 2>/dev/null || true
    cp -rf scripts $PROJECT_DIR/ 2>/dev/null || true
else
    echo "📋 Configuration files will be created in project directory..."
fi

cd $PROJECT_DIR

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cat > .env <<EOF
# Domain Configuration
DOMAIN=localhost
EMAIL=admin@example.com

# Neo4j Configuration
NEO4J_PASSWORD=$(openssl rand -base64 32)

# Kafka Configuration
KAFKA_RETENTION_HOURS=168

# Grafana Configuration
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 32)

# Docker Image Configuration
DOCKER_REGISTRY=
VERSION=latest
EOF
    echo "✅ .env file created with random passwords"
    echo "⚠️  IMPORTANT: Edit .env file and set your DOMAIN and EMAIL before starting services"
else
    echo "✅ .env file already exists"
fi

# Create required directories
echo "📁 Creating required directories..."
mkdir -p config/prometheus
mkdir -p config/grafana/dashboards
mkdir -p config/grafana/datasources
mkdir -p config/nginx/ssl
mkdir -p scripts
mkdir -p backups

# Create Prometheus config
if [ ! -f config/prometheus/prometheus.yml ]; then
    cat > config/prometheus/prometheus.yml <<'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'graph-builder'
    static_configs:
      - targets: ['graph-builder:9090']

  - job_name: 'neo4j'
    static_configs:
      - targets: ['neo4j:2004']
EOF
fi

# Create Nginx config
if [ ! -f config/nginx/nginx.conf ]; then
    cat > config/nginx/nginx.conf <<'EOF'
events {
    worker_connections 1024;
}

http {
    upstream kg_api {
        server kg-api:8080;
    }

    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name _;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate /etc/letsencrypt/live/DOMAIN/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/DOMAIN/privkey.pem;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        location / {
            proxy_pass http://kg_api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
EOF
fi

# Create Kafka init script
if [ ! -f scripts/kafka-init.sh ]; then
    cat > scripts/kafka-init.sh <<'EOF'
#!/bin/bash
set -e

echo "Waiting for Kafka to be ready..."
sleep 10

TOPICS=(
    "raw.k8s.events"
    "raw.events"
    "events.normalized"
    "alerts.enriched"
    "logs.normalized"
    "state.k8s.resource"
    "state.k8s.topology"
    "raw.prom.alerts"
)

for topic in "${TOPICS[@]}"; do
    echo "Creating topic: $topic"
    kafka-topics.sh --create \
        --bootstrap-server kafka:9092 \
        --topic "$topic" \
        --partitions 3 \
        --replication-factor 1 \
        --if-not-exists \
        --config retention.ms=604800000 \
        --config compression.type=gzip
done

echo "✅ All Kafka topics created"
EOF
    chmod +x scripts/kafka-init.sh
fi

# Create health check script
cat > health-check.sh <<'EOF'
#!/bin/bash

echo "🏥 Health Check"
echo "==============="

services=("kafka" "neo4j" "graph-builder" "kg-api" "prometheus" "grafana")

for service in "${services[@]}"; do
    if docker-compose ps | grep -q "$service.*Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service is NOT running"
    fi
done

# Check API health
if curl -sf http://localhost:8080/healthz > /dev/null 2>&1; then
    echo "✅ KG API is healthy"
else
    echo "❌ KG API is NOT healthy"
fi
EOF
chmod +x health-check.sh

# Create backup script
cat > backup.sh <<'EOF'
#!/bin/bash
set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "📦 Creating backup at $TIMESTAMP..."

# Backup Neo4j data
docker-compose exec -T neo4j neo4j-admin database dump neo4j --to-path=/backups
docker cp $(docker-compose ps -q neo4j):/backups/neo4j.dump "$BACKUP_DIR/neo4j_$TIMESTAMP.dump"

# Compress backup
gzip "$BACKUP_DIR/neo4j_$TIMESTAMP.dump"

echo "✅ Backup created: $BACKUP_DIR/neo4j_$TIMESTAMP.dump.gz"
EOF
chmod +x backup.sh

# Setup systemd service for auto-start
echo "🔄 Setting up systemd service for auto-start..."
sudo tee /etc/systemd/system/kg-rca.service > /dev/null <<EOF
[Unit]
Description=KG RCA Docker Compose Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable kg-rca.service

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file and configure:"
echo "   - DOMAIN (your domain name)"
echo "   - EMAIL (for SSL certificate)"
echo "   - NEO4J_PASSWORD (auto-generated, save it!)"
echo ""
echo "2. Point your domain DNS to this server's IP"
echo ""
echo "3. Start services:"
echo "   docker-compose up -d"
echo ""
echo "4. Setup SSL certificate:"
echo "   sudo certbot --nginx -d your-domain.com"
echo ""
echo "5. Check health:"
echo "   ./health-check.sh"
echo ""
echo "⚠️  IMPORTANT: Save the passwords from .env file!"
