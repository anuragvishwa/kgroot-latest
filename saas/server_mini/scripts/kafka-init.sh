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
