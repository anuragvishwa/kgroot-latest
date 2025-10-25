"""
Event Normalizer V2 - Pure Control Plane Model
Transforms raw K8s events into structured abstract events for FPG construction

Key Changes from V1:
- NO client_id in message payload (only in Kafka key)
- Spawned per-client by control plane with dedicated consumer group
- Client isolation via consumer groups, not message filtering

Architecture:
  Control Plane sees "af-9" in cluster.registry
    → Spawns: kg-event-normalizer-af-9
    → Consumer group: "event-normalizer-af-9"
    → Reads from: raw.k8s.events (shared topic)
    → Writes to: events.normalized (shared topic)
    → Kafka key format: "af-9::{event-id}"
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from dataclasses import dataclass, asdict
import hashlib
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NormalizedEvent:
    """
    Structured event representation for knowledge graph

    NOTE: NO client_id field! Client is identified by Kafka key only.
    """
    event_id: str
    cluster_name: str
    timestamp: str

    # Abstract event type (for FEKG)
    event_type_abstract: str  # e.g., "CPU_HIGH", "POD_FAILED"

    # Location context
    namespace: str
    pod_name: Optional[str]
    node: Optional[str]
    service: Optional[str]

    # Event details
    reason: str
    message: str
    severity: str  # INFO, WARNING, ERROR, CRITICAL

    # Metadata for causality inference
    involved_object_kind: str
    involved_object_name: str

    # Original raw event reference
    raw_event_id: str

    def to_dict(self) -> Dict:
        return asdict(self)


class EventNormalizerV2:
    """
    Normalizes raw K8s events into structured format for FPG construction

    Spawned per-client by control plane:
      - Client ID passed as constructor parameter
      - Consumer group is unique per client: "event-normalizer-{client_id}"
      - Kafka automatically partitions by key hash
    """

    EVENT_TYPE_MAPPING = {
        "Pulling": "POD_IMAGE_PULL",
        "Pulled": "POD_IMAGE_PULLED",
        "Created": "POD_CREATED",
        "Started": "POD_STARTED",
        "Killing": "POD_KILLING",
        "Failed": "POD_FAILED",
        "BackOff": "POD_BACKOFF",
        "CrashLoopBackOff": "POD_CRASH_LOOP",
        "OOMKilled": "MEMORY_OOM",
        "Evicted": "POD_EVICTED",
        "FailedScheduling": "SCHEDULING_FAILED",
        "FailedMount": "VOLUME_MOUNT_FAILED",
        "FailedCreatePodSandBox": "NETWORK_SETUP_FAILED",
        "NetworkNotReady": "NETWORK_NOT_READY",
        "Unhealthy": "HEALTH_CHECK_FAILED",
        "ProbeWarning": "PROBE_WARNING",
        "NodeNotReady": "NODE_NOT_READY",
        "NodeReady": "NODE_READY",
        "RegisteredNode": "NODE_REGISTERED",
        "FailedDiscovery": "SERVICE_DISCOVERY_FAILED",
        "UpdatedEndpoints": "ENDPOINTS_UPDATED",
    }

    SEVERITY_MAPPING = {
        "Normal": "INFO",
        "Warning": "WARNING",
        "Error": "ERROR",
    }

    def __init__(self, kafka_brokers: str, client_id: str):
        """
        Initialize normalizer for specific client

        Args:
            kafka_brokers: Kafka broker addresses
            client_id: Client identifier (e.g., "af-9")
        """
        self.kafka_brokers = kafka_brokers
        self.client_id = client_id
        self.consumer_group = f"event-normalizer-{client_id}"

        # Consumer with CLIENT-SPECIFIC consumer group
        # Kafka will automatically assign partitions based on key hash
        self.consumer = KafkaConsumer(
            'raw.k8s.events',
            bootstrap_servers=kafka_brokers,
            group_id=self.consumer_group,  # ← Unique per client!
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='latest',
            enable_auto_commit=True,
        )

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            compression_type='lz4',
        )

        self.dlq_producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
        )

        logger.info(f"✅ Event Normalizer initialized for client: {client_id}")
        logger.info(f"   Consumer group: {self.consumer_group}")
        logger.info(f"   Reading from: raw.k8s.events (shared topic)")
        logger.info(f"   Writing to: events.normalized (shared topic)")

    def _extract_client_from_key(self, kafka_key: str) -> Optional[str]:
        """
        Extract client_id from Kafka key

        Expected format: "client-id::event-type::uid"
        Example: "af-9::k8s-event::abc123"
        """
        if not kafka_key:
            return None

        parts = kafka_key.split("::")
        if len(parts) >= 1:
            return parts[0]

        return None

    def _abstract_event_type(self, reason: str, event_type: str) -> str:
        """Convert specific event to abstract event type for FEKG"""
        if reason in self.EVENT_TYPE_MAPPING:
            return self.EVENT_TYPE_MAPPING[reason]

        # Pattern-based mapping
        if "OOM" in reason or "OutOfMemory" in reason:
            return "MEMORY_OOM"
        elif "CPU" in reason:
            return "CPU_HIGH"
        elif "Disk" in reason or "Volume" in reason:
            return "DISK_ISSUE"
        elif "Network" in reason or "Connection" in reason:
            return "NETWORK_ISSUE"
        elif "Timeout" in reason:
            return "TIMEOUT"
        elif "Crash" in reason:
            return "POD_CRASH_LOOP"
        else:
            return "CUSTOM"

    def _determine_severity(self, event_type: str, reason: str, message: str) -> str:
        """Determine event severity for prioritization"""
        if event_type in self.SEVERITY_MAPPING:
            return self.SEVERITY_MAPPING[event_type]

        critical_keywords = ["OOM", "Crash", "Failed", "Error", "Evicted"]
        warning_keywords = ["BackOff", "Unhealthy", "Probe"]

        if any(kw in reason for kw in critical_keywords):
            return "ERROR"
        elif any(kw in reason for kw in warning_keywords):
            return "WARNING"
        else:
            return "INFO"

    def _generate_event_id(self, raw_event: Dict) -> str:
        """Generate deterministic event ID"""
        uid = raw_event.get('metadata', {}).get('uid', '')
        timestamp = raw_event.get('metadata', {}).get('creationTimestamp', '')
        hash_input = f"{uid}:{timestamp}".encode('utf-8')
        return f"evt-{hashlib.sha256(hash_input).hexdigest()[:16]}"

    def normalize(self, raw_event: Dict) -> Optional[NormalizedEvent]:
        """
        Transform raw K8s event to structured normalized event

        NOTE: Returns event WITHOUT client_id field!
        Client is tracked via Kafka key only.
        """
        try:
            metadata = raw_event.get('metadata', {})
            involved_object = raw_event.get('involvedObject', {})

            # Extract core fields
            event_id = self._generate_event_id(raw_event)
            cluster_name = raw_event.get('cluster_name', 'unknown')

            # Timestamp handling
            last_timestamp = raw_event.get('lastTimestamp') or raw_event.get('eventTime')
            if not last_timestamp:
                last_timestamp = metadata.get('creationTimestamp', datetime.utcnow().isoformat())

            # Event type abstraction
            reason = raw_event.get('reason', 'Unknown')
            event_type = raw_event.get('type', 'Normal')
            event_type_abstract = self._abstract_event_type(reason, event_type)

            # Location context
            namespace = involved_object.get('namespace', 'default')
            pod_name = involved_object.get('name') if involved_object.get('kind') == 'Pod' else None
            node = raw_event.get('source', {}).get('host')

            # Service extraction (if available)
            service = None
            labels = metadata.get('labels', {})
            if 'app' in labels:
                service = labels['app']
            elif 'k8s-app' in labels:
                service = labels['k8s-app']

            # Severity determination
            severity = self._determine_severity(event_type, reason, raw_event.get('message', ''))

            # Create normalized event WITHOUT client_id field
            normalized_event = NormalizedEvent(
                event_id=event_id,
                cluster_name=cluster_name,
                timestamp=last_timestamp,
                event_type_abstract=event_type_abstract,
                namespace=namespace,
                pod_name=pod_name,
                node=node,
                service=service,
                reason=reason,
                message=raw_event.get('message', ''),
                severity=severity,
                involved_object_kind=involved_object.get('kind', 'Unknown'),
                involved_object_name=involved_object.get('name', 'Unknown'),
                raw_event_id=metadata.get('uid', ''),
            )

            return normalized_event

        except Exception as e:
            logger.error(f"Failed to normalize event: {e}", exc_info=True)
            return None

    def run(self):
        """Main processing loop"""
        logger.info(f"🚀 Event Normalizer started for client: {self.client_id}")
        logger.info(f"   Consumer group: {self.consumer_group}")
        logger.info(f"   Consuming from 'raw.k8s.events' (shared topic)...")

        processed_count = 0
        error_count = 0
        skipped_count = 0

        try:
            for message in self.consumer:
                try:
                    # Extract client_id from Kafka key
                    kafka_key = message.key
                    message_client_id = self._extract_client_from_key(kafka_key)

                    # Verify this message is for our client
                    if message_client_id != self.client_id:
                        # This shouldn't happen with consumer groups, but safety check
                        skipped_count += 1
                        if skipped_count % 100 == 0:
                            logger.warning(f"⚠️  Skipped {skipped_count} messages for other clients")
                        continue

                    raw_event = message.value

                    # Normalize event
                    normalized = self.normalize(raw_event)

                    if normalized:
                        # Publish to normalized topic with same Kafka key
                        # Key format: "af-9::evt-abc123"
                        output_key = f"{self.client_id}::{normalized.event_id}"

                        self.producer.send(
                            'events.normalized',
                            key=output_key,
                            value=normalized.to_dict()
                        )

                        processed_count += 1

                        if processed_count % 100 == 0:
                            logger.info(f"✅ Client {self.client_id}: Processed {processed_count} events (errors: {error_count})")

                    else:
                        # Send to DLQ with client_id in key
                        dlq_key = f"{self.client_id}::error::{datetime.utcnow().timestamp()}"
                        self.dlq_producer.send('dlq.normalized', key=dlq_key, value={
                            'original_message': raw_event,
                            'error': 'Normalization returned None',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        error_count += 1

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    error_count += 1

                    # Send to DLQ
                    dlq_key = f"{self.client_id}::error::{datetime.utcnow().timestamp()}"
                    self.dlq_producer.send('dlq.normalized', key=dlq_key, value={
                        'original_message': message.value if hasattr(message, 'value') else str(message),
                        'error': str(e),
                        'timestamp': datetime.utcnow().isoformat()
                    })

        except KeyboardInterrupt:
            logger.info(f"Shutting down Event Normalizer for client {self.client_id}...")

        finally:
            self.consumer.close()
            self.producer.close()
            self.dlq_producer.close()
            logger.info(f"Final stats for {self.client_id} - Processed: {processed_count}, Errors: {error_count}, Skipped: {skipped_count}")


if __name__ == "__main__":
    import os

    # Get configuration from environment (set by control plane)
    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    client_id = os.getenv("CLIENT_ID")

    if not client_id:
        logger.error("❌ CLIENT_ID environment variable not set!")
        logger.error("   This normalizer must be spawned by control plane with CLIENT_ID set.")
        sys.exit(1)

    normalizer = EventNormalizerV2(kafka_brokers, client_id)
    normalizer.run()
