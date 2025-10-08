FROM python:3.11-slim

WORKDIR /app

# Copy all Python test apps
COPY *.py /app/

# Make them executable
RUN chmod +x /app/*.py

# Default command (can be overridden in K8s)
CMD ["python3", "-u", "error-logger.py"]
