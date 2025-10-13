#!/bin/bash

# ============================================================================
# KG RCA Mini Server - Ubuntu Setup Script
# ============================================================================
# This script prepares your Ubuntu server for KG RCA deployment
# Run as root or with sudo
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}KG RCA Mini Server - Ubuntu Setup${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# ============================================================================
# Check if running as root or with sudo
# ============================================================================
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root or with sudo${NC}"
   echo "Usage: sudo ./setup-ubuntu.sh"
   exit 1
fi

# ============================================================================
# Detect Ubuntu version
# ============================================================================
echo -e "${YELLOW}[1/8] Checking Ubuntu version...${NC}"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "OS: $NAME"
    echo "Version: $VERSION"

    # Check if Ubuntu
    if [[ "$ID" != "ubuntu" ]]; then
        echo -e "${YELLOW}Warning: This script is designed for Ubuntu. Detected: $ID${NC}"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
else
    echo -e "${RED}Cannot detect OS version${NC}"
    exit 1
fi

# ============================================================================
# Update system packages
# ============================================================================
echo ""
echo -e "${YELLOW}[2/8] Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# ============================================================================
# Install required packages
# ============================================================================
echo ""
echo -e "${YELLOW}[3/8] Installing required packages...${NC}"
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    git \
    wget \
    unzip \
    jq \
    htop \
    net-tools \
    ufw

echo -e "${GREEN}✓ Required packages installed${NC}"

# ============================================================================
# Install Docker
# ============================================================================
echo ""
echo -e "${YELLOW}[4/8] Installing Docker...${NC}"

# Remove old versions if any
apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Verify Docker installation
docker --version
docker compose version

echo -e "${GREEN}✓ Docker installed successfully${NC}"

# ============================================================================
# Configure Docker (optional optimizations)
# ============================================================================
echo ""
echo -e "${YELLOW}[5/8] Configuring Docker...${NC}"

# Create Docker daemon configuration
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "default-address-pools": [
    {
      "base": "172.17.0.0/12",
      "size": 24
    }
  ]
}
EOF

# Restart Docker to apply configuration
systemctl restart docker

echo -e "${GREEN}✓ Docker configured${NC}"

# ============================================================================
# Add non-root user to docker group (if not root)
# ============================================================================
echo ""
echo -e "${YELLOW}[6/8] Configuring Docker permissions...${NC}"

# Get the user who invoked sudo
ACTUAL_USER="${SUDO_USER:-$USER}"

if [ "$ACTUAL_USER" != "root" ]; then
    usermod -aG docker "$ACTUAL_USER"
    echo -e "${GREEN}✓ User '$ACTUAL_USER' added to docker group${NC}"
    echo -e "${YELLOW}  Note: You may need to log out and back in for group changes to take effect${NC}"
else
    echo -e "${YELLOW}  Running as root, skipping user group configuration${NC}"
fi

# ============================================================================
# Configure firewall (UFW)
# ============================================================================
echo ""
echo -e "${YELLOW}[7/8] Configuring firewall...${NC}"

# Ask user if they want to configure UFW
read -p "Configure UFW firewall? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Enable UFW
    ufw --force enable

    # Allow SSH (IMPORTANT!)
    ufw allow 22/tcp comment 'SSH'

    # Ask about other ports
    echo ""
    echo "Which ports would you like to open?"
    echo "1. Minimal (SSH only) - Recommended for production"
    echo "2. Development (SSH + all services)"
    echo "3. Custom (you choose)"
    read -p "Select option (1-3): " -n 1 -r
    echo

    case $REPLY in
        1)
            echo "Opening minimal ports..."
            ufw allow 9093/tcp comment 'Kafka SSL'
            ;;
        2)
            echo "Opening development ports..."
            ufw allow 9093/tcp comment 'Kafka SSL'
            ufw allow 7474/tcp comment 'Neo4j HTTP'
            ufw allow 7687/tcp comment 'Neo4j Bolt'
            ufw allow 8080/tcp comment 'KG API'
            ufw allow 3000/tcp comment 'Grafana'
            ufw allow 9091/tcp comment 'Prometheus'
            ufw allow 7777/tcp comment 'Kafka UI'
            ;;
        3)
            echo "Manual port configuration required after setup"
            ;;
    esac

    # Show firewall status
    ufw status
    echo -e "${GREEN}✓ Firewall configured${NC}"
else
    echo -e "${YELLOW}  Skipping firewall configuration${NC}"
fi

# ============================================================================
# System optimizations for Kafka and Neo4j
# ============================================================================
echo ""
echo -e "${YELLOW}[8/8] Applying system optimizations...${NC}"

# Increase file descriptor limits
cat >> /etc/security/limits.conf <<EOF

# KG RCA Platform optimizations
* soft nofile 65536
* hard nofile 65536
* soft nproc 32768
* hard nproc 32768
EOF

# Kernel parameters for Kafka
cat >> /etc/sysctl.conf <<EOF

# KG RCA Platform - Kafka optimizations
vm.max_map_count=262144
vm.swappiness=1
net.core.somaxconn=1024
net.ipv4.tcp_max_syn_backlog=3240
EOF

# Apply kernel parameters
sysctl -p

echo -e "${GREEN}✓ System optimizations applied${NC}"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Next steps:"
echo "1. If you added a user to docker group, log out and back in"
echo "2. Clone your KG RCA repository or copy files to this server"
echo "3. Navigate to the mini-server-prod directory"
echo "4. Copy .env.example to .env and configure it"
echo "5. Run: docker compose up -d"
echo ""
echo "Optional:"
echo "- Configure SSL: ./scripts/setup-ssl.sh"
echo "- Test services: ./scripts/test-services.sh"
echo ""
echo -e "${YELLOW}System Information:${NC}"
echo "- Docker version: $(docker --version)"
echo "- Docker Compose version: $(docker compose version)"
echo "- Available memory: $(free -h | awk '/^Mem:/ {print $2}')"
echo "- Available disk: $(df -h / | awk 'NR==2 {print $4}')"
echo ""
echo -e "${GREEN}Ready to deploy KG RCA!${NC}"
