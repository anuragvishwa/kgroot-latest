"""
Event Normalizer Service
Transforms raw K8s events into structured abstract events for FPG construction

Based on KGroot Paper (arxiv.org/abs/2402.13264):
- Algorithm 1: FPG Construction requires structured events
- Section 3: Data Preprocessing Module
- Converts unstructured events to structured abstract events
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from dataclasses import dataclass, asdict
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NormalizedEvent:
    """Structured event representation for knowledge graph"""
    event_id: str
    client_id: str
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


class EventNormalizer:
    """
    Normalizes raw K8s events into structured format for FPG construction

    Implements data preprocessing from KGroot paper:
    1. Event Generation: Transform unstructured data to structured events
    2. Event Abstraction: Convert specific events to abstract event types
    3. Context Enrichment: Add metadata for causality discovery
    """

    # Event type mapping (based on KGroot paper event categories)
    EVENT_TYPE_MAPPING = {
        # Pod lifecycle events
        "Pulling": "POD_IMAGE_PULL",
        "Pulled": "POD_IMAGE_PULLED",
        "Created": "POD_CREATED",
        "Started": "POD_STARTED",
        "Killing": "POD_KILLING",
        "Failed": "POD_FAILED",
        "BackOff": "POD_BACKOFF",
        "CrashLoopBackOff": "POD_CRASH_LOOP",

        # Resource events
        "OOMKilled": "MEMORY_OOM",
        "Evicted": "POD_EVICTED",
        "FailedScheduling": "SCHEDULING_FAILED",
        "FailedMount": "VOLUME_MOUNT_FAILED",

        # Network events
        "FailedCreatePodSandBox": "NETWORK_SETUP_FAILED",
        "NetworkNotReady": "NETWORK_NOT_READY",

        # Health check events
        "Unhealthy": "HEALTH_CHECK_FAILED",
        "ProbeWarning": "PROBE_WARNING",

        # Node events
        "NodeNotReady": "NODE_NOT_READY",
        "NodeReady": "NODE_READY",
        "RegisteredNode": "NODE_REGISTERED",

        # Service events
        "FailedDiscovery": "SERVICE_DISCOVERY_FAILED",
        "UpdatedEndpoints": "ENDPOINTS_UPDATED",
    }

    SEVERITY_MAPPING = {
        "Normal": "INFO",
        "Warning": "WARNING",
        "Error": "ERROR",
    }

    def __init__(self, kafka_brokers: str, consumer_group: str = "event-normalizer"):
        self.kafka_brokers = kafka_brokers
        self.consumer_group = consumer_group

        self.consumer = KafkaConsumer(
            'raw.k8s.events',
            bootstrap_servers=kafka_brokers,
            group_id=consumer_group,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
        )

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            compression_type='lz4',
        )

        self.dlq_producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        )

        logger.info(f"Event Normalizer initialized with brokers: {kafka_brokers}")

    def _extract_client_id(self, raw_event: Dict) -> str:
        """Extract client_id from Kafka key or event metadata"""
        # Assuming Kafka key format: "client-id::event-type::uid"
        return raw_event.get('client_id', 'unknown')

    def _abstract_event_type(self, reason: str, event_type: str) -> str:
        """
        Convert specific event to abstract event type for FEKG

        From KGroot paper: Events are abstracted to event types for
        knowledge graph construction (e.g., specific CPU overload → CPU_HIGH)
        """
        # Direct mapping
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

        # Heuristic-based severity
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

        Implements Algorithm 1 (FPG Construction) preprocessing:
        - Extract event metadata
        - Abstract to event type
        - Enrich with context
        """
        try:
            metadata = raw_event.get('metadata', {})
            involved_object = raw_event.get('involvedObject', {})

            # Extract core fields
            event_id = self._generate_event_id(raw_event)
            client_id = self._extract_client_id(raw_event)
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

            normalized_event = NormalizedEvent(
                event_id=event_id,
                client_id=client_id,
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
        logger.info("🚀 Event Normalizer started. Consuming from 'raw.k8s.events'...")

        processed_count = 0
        error_count = 0

        try:
            for message in self.consumer:
                try:
                    raw_event = message.value

                    # Normalize event
                    normalized = self.normalize(raw_event)

                    if normalized:
                        # Publish to normalized topic
                        kafka_key = f"{normalized.client_id}::{normalized.event_id}"

                        self.producer.send(
                            'events.normalized',
                            key=kafka_key.encode('utf-8'),
                            value=normalized.to_dict()
                        )

                        processed_count += 1

                        if processed_count % 100 == 0:
                            logger.info(f"✅ Processed {processed_count} events (errors: {error_count})")

                    else:
                        # Send to DLQ
                        self.dlq_producer.send('dlq.normalized', value={
                            'original_message': raw_event,
                            'error': 'Normalization returned None',
                            'timestamp': datetime.utcnow().isoformat()
                        })
                        error_count += 1

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    error_count += 1

                    # Send to DLQ
                    self.dlq_producer.send('dlq.normalized', value={
                        'original_message': message.value if hasattr(message, 'value') else str(message),
                        'error': str(e),
                        'timestamp': datetime.utcnow().isoformat()
                    })

        except KeyboardInterrupt:
            logger.info("Shutting down Event Normalizer...")

        finally:
            self.consumer.close()
            self.producer.close()
            self.dlq_producer.close()
            logger.info(f"Final stats - Processed: {processed_count}, Errors: {error_count}")


if __name__ == "__main__":
    import os

    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    normalizer = EventNormalizer(kafka_brokers)
    normalizer.run()
