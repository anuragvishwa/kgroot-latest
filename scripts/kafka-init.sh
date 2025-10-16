#!/usr/bin/env bash
set -euo pipefail

# Make Kafka CLI tools available on PATH for Bitnami images
export PATH="$PATH:/opt/bitnami/kafka/bin"

TOPICS="kafka-topics.sh"
BROKER="kafka:9092"

echo "[kafka-init] Waiting for Kafka at $BROKER..."
# Show real errors while waiting so you can see what's wrong
until $TOPICS --bootstrap-server "$BROKER" --list >/dev/null 2>&1; do
  echo "[kafka-init] broker not ready yet, retrying..."
  sleep 2
done
echo "[kafka-init] Broker reachable. Creating topics…"

DAY_MS=$((24*3600*1000))
WEEK_MS=$((7*24*3600*1000))
MONTH_MS=$((30*24*3600*1000))
YEAR_MS=$((365*24*3600*1000))

create_topic () {
  local NAME="$1" PARTS="$2" RET_MS="$3"
  shift 3
  echo "[kafka-init] Ensuring topic: $NAME"
  $TOPICS --bootstrap-server "$BROKER" --create --if-not-exists \
    --topic "$NAME" --partitions "$PARTS" --replication-factor 1 \
    --config "compression.type=gzip" \
    --config "retention.ms=$RET_MS" \
    "$@"
}

# ---------- RAW streams (append-only) ----------
create_topic raw.k8s.logs       6  $((3*DAY_MS))
create_topic raw.k8s.events     3  $((14*DAY_MS))
create_topic raw.prom.alerts    3  $MONTH_MS
create_topic events.normalized  6  $((60*DAY_MS))
create_topic logs.normalized    6  $((14*DAY_MS))
create_topic alerts.enriched    3  $MONTH_MS

# ---------- Compacted state (latest truth) ----------
COMPACT_RATIO="0.1"
SEGMENT_MS=$DAY_MS

create_topic state.k8s.resource 3 $YEAR_MS \
  --config "cleanup.policy=compact" \
  --config "min.cleanable.dirty.ratio=$COMPACT_RATIO" \
  --config "segment.ms=$SEGMENT_MS"

create_topic state.k8s.topology 3 $YEAR_MS \
  --config "cleanup.policy=compact" \
  --config "min.cleanable.dirty.ratio=$COMPACT_RATIO" \
  --config "segment.ms=$SEGMENT_MS"

create_topic state.prom.rules   1 $YEAR_MS \
  --config "cleanup.policy=compact" \
  --config "min.cleanable.dirty.ratio=$COMPACT_RATIO" \
  --config "segment.ms=$SEGMENT_MS"

create_topic state.prom.targets 1 $WEEK_MS \
  --config "cleanup.policy=compact" \
  --config "min.cleanable.dirty.ratio=$COMPACT_RATIO" \
  --config "segment.ms=$SEGMENT_MS"

create_topic graph.commands     3 $YEAR_MS \
  --config "cleanup.policy=compact" \
  --config "min.cleanable.dirty.ratio=$COMPACT_RATIO" \
  --config "segment.ms=$SEGMENT_MS"

# ---------- DLQs ----------
create_topic dlq.raw            3  $WEEK_MS
create_topic dlq.normalized     3  $WEEK_MS

echo "[kafka-init] All topics ensured."
# Keep container running for visibility
tail -f /dev/null
