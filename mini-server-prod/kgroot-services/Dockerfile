FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create config directory for kubeconfig
RUN mkdir -p /config

# Expose ports
# 8081 - Alertmanager webhook
# 8082 - K8s event collector (if needed)
EXPOSE 8081 8082

# Default command (can be overridden in docker-compose)
CMD ["python", "alertmanager_webhook.py"]
