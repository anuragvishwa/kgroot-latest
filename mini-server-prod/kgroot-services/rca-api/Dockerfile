# Multi-stage build for smaller image size
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies to /install directory
# Use --prefix to install to a specific location for easier cleanup
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ ./src/

# Create directories for cache and logs
RUN mkdir -p embeddings_cache logs

# Expose port
EXPOSE 8083

# Health check - use socket connection instead of HTTP to avoid deadlock
HEALTHCHECK --interval=30s --timeout=3s --start-period=90s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', 8083)); s.close()" || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8083", "--workers", "1", "--timeout-keep-alive", "75"]
