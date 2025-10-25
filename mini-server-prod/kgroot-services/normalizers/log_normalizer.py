"""
Log Normalizer Service
Transforms raw container logs into structured format for RCA

Based on KGroot Paper:
- Section 4: Logs provide application-level errors and stack traces
- Used for event-driven RCA at fine granularity
"""

import json
import logging
import re
from typing import Dict, Optional
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from dataclasses import dataclass, asdict
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class NormalizedLog:
    """Structured log representation"""
    log_id: str
    client_id: str
    cluster_name: str
    timestamp: str

    # Location context
    namespace: str
    pod_name: str
    container_name: str
    node: Optional[str]

    # Log content
    message: str
    severity: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_level: Optional[str]  # Original level from log

    # Error detection
    is_error: bool
    error_type: Optional[str]  # e.g., "NullPointerException", "ConnectionTimeout"
    stack_trace: Optional[str]

    # Metadata
    labels: Dict
    raw_log_id: str

    def to_dict(self) -> Dict:
        return asdict(self)


class LogNormalizer:
    """Normalizes raw logs for FPG construction"""

    # Error patterns for detection
    ERROR_PATTERNS = [
        (r'(?i)exception', 'EXCEPTION'),
        (r'(?i)error', 'ERROR'),
        (r'(?i)fatal', 'FATAL'),
        (r'(?i)panic', 'PANIC'),
        (r'(?i)timeout', 'TIMEOUT'),
        (r'(?i)connection\s+refused', 'CONNECTION_REFUSED'),
        (r'(?i)out\s+of\s+memory', 'OOM'),
        (r'(?i)null\s+pointer', 'NULL_POINTER'),
        (r'(?i)failed\s+to', 'OPERATION_FAILED'),
        (r'(?i)cannot\s+connect', 'CONNECTION_ERROR'),
    ]

    # Severity level mapping
    SEVERITY_MAP = {
        'TRACE': 'DEBUG',
        'DEBUG': 'DEBUG',
        'INFO': 'INFO',
        'WARN': 'WARNING',
        'WARNING': 'WARNING',
        'ERROR': 'ERROR',
        'FATAL': 'CRITICAL',
        'CRITICAL': 'CRITICAL',
        'PANIC': 'CRITICAL',
    }

    def __init__(self, kafka_brokers: str):
        self.kafka_brokers = kafka_brokers

        self.consumer = KafkaConsumer(
            'raw.k8s.logs',
            bootstrap_servers=kafka_brokers,
            group_id='log-normalizer',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
        )

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            compression_type='lz4',
        )

        logger.info(f"Log Normalizer initialized")

    def _detect_error(self, message: str) -> tuple[bool, Optional[str]]:
        """Detect if log contains error and classify type"""
        for pattern, error_type in self.ERROR_PATTERNS:
            if re.search(pattern, message):
                return True, error_type
        return False, None

    def _extract_stack_trace(self, message: str) -> Optional[str]:
        """Extract stack trace if present"""
        # Look for Java stack traces
        if 'at ' in message and ('Exception' in message or 'Error' in message):
            lines = message.split('\n')
            stack_lines = [line for line in lines if line.strip().startswith('at ')]
            if stack_lines:
                return '\n'.join(stack_lines[:10])  # First 10 lines

        # Look for Python tracebacks
        if 'Traceback (most recent call last)' in message:
            return message  # Return full message for Python

        return None

    def _parse_severity(self, message: str, log_level: Optional[str]) -> str:
        """Determine log severity"""
        if log_level:
            normalized = log_level.upper().strip()
            return self.SEVERITY_MAP.get(normalized, 'INFO')

        # Heuristic based on message content
        if re.search(r'(?i)(fatal|critical|panic)', message):
            return 'CRITICAL'
        elif re.search(r'(?i)error', message):
            return 'ERROR'
        elif re.search(r'(?i)(warn|warning)', message):
            return 'WARNING'
        else:
            return 'INFO'

    def normalize(self, raw_log: Dict) -> Optional[NormalizedLog]:
        """Transform raw log to structured format"""
        try:
            # Generate log ID
            timestamp_str = raw_log.get('timestamp', datetime.utcnow().isoformat())
            hash_input = f"{raw_log.get('pod_name', '')}:{timestamp_str}".encode('utf-8')
            log_id = f"log-{hashlib.sha256(hash_input).hexdigest()[:16]}"

            # Extract message and level
            message = raw_log.get('message', raw_log.get('log', ''))
            log_level = raw_log.get('level') or raw_log.get('severity')

            # Error detection
            is_error, error_type = self._detect_error(message)
            stack_trace = self._extract_stack_trace(message) if is_error else None

            # Severity
            severity = self._parse_severity(message, log_level)

            normalized_log = NormalizedLog(
                log_id=log_id,
                client_id=raw_log.get('client_id', 'unknown'),
                cluster_name=raw_log.get('cluster_name', 'unknown'),
                timestamp=timestamp_str,
                namespace=raw_log.get('namespace', 'default'),
                pod_name=raw_log.get('pod_name', 'unknown'),
                container_name=raw_log.get('container_name', 'unknown'),
                node=raw_log.get('node'),
                message=message[:1000],  # Truncate long messages
                severity=severity,
                log_level=log_level,
                is_error=is_error,
                error_type=error_type,
                stack_trace=stack_trace,
                labels=raw_log.get('labels', {}),
                raw_log_id=raw_log.get('id', ''),
            )

            return normalized_log

        except Exception as e:
            logger.error(f"Failed to normalize log: {e}", exc_info=True)
            return None

    def run(self):
        """Main processing loop"""
        logger.info("🚀 Log Normalizer started. Consuming from 'raw.k8s.logs'...")

        processed_count = 0

        try:
            for message in self.consumer:
                raw_log = message.value
                normalized = self.normalize(raw_log)

                if normalized:
                    kafka_key = f"{normalized.client_id}::{normalized.log_id}"

                    self.producer.send(
                        'logs.normalized',
                        key=kafka_key.encode('utf-8'),
                        value=normalized.to_dict()
                    )

                    processed_count += 1

                    if processed_count % 1000 == 0:
                        logger.info(f"✅ Processed {processed_count} logs")

        except KeyboardInterrupt:
            logger.info("Shutting down Log Normalizer...")

        finally:
            self.consumer.close()
            self.producer.close()
            logger.info(f"Final stats - Processed: {processed_count}")


if __name__ == "__main__":
    import os

    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    normalizer = LogNormalizer(kafka_brokers)
    normalizer.run()
