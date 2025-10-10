#!/bin/bash
set -e

# Log everything
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Starting KG RCA server setup..."

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo "Detected OS: $PRETTY_NAME"
fi

# Update system
if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
    apt-get update
    apt-get upgrade -y
    MAIN_USER="ubuntu"
elif [[ "$OS" == "amzn" ]] || [[ "$OS" == "rhel" ]] || [[ "$OS" == "centos" ]]; then
    dnf update -y || yum update -y
    MAIN_USER="ec2-user"
else
    apt-get update || dnf update -y || yum update -y
    MAIN_USER="ubuntu"
fi

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $MAIN_USER

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install utilities based on OS
if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
    apt-get install -y \
        git \
        curl \
        wget \
        htop \
        jq \
        nginx \
        certbot \
        python3-certbot-nginx
elif [[ "$OS" == "amzn" ]] || [[ "$OS" == "rhel" ]] || [[ "$OS" == "centos" ]]; then
    dnf install -y \
        git \
        curl \
        wget \
        htop \
        jq \
        nginx \
        python3-pip || yum install -y \
        git \
        curl \
        wget \
        htop \
        jq \
        nginx \
        python3-pip

    # Install certbot via pip
    python3 -m pip install certbot certbot-nginx
fi

# Format and mount data volume
if ! mount | grep -q /mnt/data; then
    # Wait for volume to be attached
    while [ ! -e /dev/nvme1n1 ]; do
        echo "Waiting for data volume..."
        sleep 5
    done

    # Check if volume is formatted
    if ! blkid /dev/nvme1n1; then
        mkfs.ext4 /dev/nvme1n1
    fi

    mkdir -p /mnt/data
    mount /dev/nvme1n1 /mnt/data

    # Add to fstab
    UUID=$(blkid -s UUID -o value /dev/nvme1n1)
    echo "UUID=$UUID /mnt/data ext4 defaults,nofail 0 2" >> /etc/fstab
fi

# Create project directory
mkdir -p /home/$MAIN_USER/kg-rca
chown -R $MAIN_USER:$MAIN_USER /home/$MAIN_USER/kg-rca

# Create data directories on mounted volume
mkdir -p /mnt/data/neo4j
mkdir -p /mnt/data/kafka
mkdir -p /mnt/data/prometheus
mkdir -p /mnt/data/grafana
chown -R $MAIN_USER:$MAIN_USER /mnt/data

echo "Setup complete! SSH to server to continue configuration."
