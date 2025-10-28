"""
Event models for KGroot RCA system
Based on KGroot paper event definitions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum


class EventType(Enum):
    """Event types for fault analysis"""
    CPU_HIGH = "cpu_high"
    MEMORY_HIGH = "memory_high"
    DISK_HIGH = "disk_high"
    POD_RESTART = "pod_restart"
    POD_FAILED = "pod_failed"
    SERVICE_DOWN = "service_down"
    NETWORK_ERROR = "network_error"
    OOM_KILL = "oom_kill"
    CONFIG_CHANGE = "config_change"
    DEPLOYMENT = "deployment"
    SCALE_EVENT = "scale_event"
    HEALTH_CHECK_FAILED = "health_check_failed"
    LATENCY_HIGH = "latency_high"
    ERROR_RATE_HIGH = "error_rate_high"
    CUSTOM = "custom"


class EventSeverity(Enum):
    """Event severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Event:
    """
    Concrete event instance
    Represents a specific occurrence at a point in time
    """
    event_id: str
    event_type: EventType
    timestamp: datetime
    service: str
    namespace: str
    severity: EventSeverity

    # Optional attributes
    pod_name: Optional[str] = None
    container: Optional[str] = None
    node: Optional[str] = None

    # Metrics associated with event
    metric_value: Optional[float] = None
    metric_unit: Optional[str] = None
    threshold: Optional[float] = None

    # Additional metadata
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)

    # Context
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    # For RCA
    is_root_cause: bool = False
    root_cause_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'service': self.service,
            'namespace': self.namespace,
            'severity': self.severity.value,
            'pod_name': self.pod_name,
            'container': self.container,
            'node': self.node,
            'metric_value': self.metric_value,
            'metric_unit': self.metric_unit,
            'threshold': self.threshold,
            'labels': self.labels,
            'annotations': self.annotations,
            'message': self.message,
            'details': self.details,
            'is_root_cause': self.is_root_cause,
            'root_cause_confidence': self.root_cause_confidence
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create event from dictionary"""
        return cls(
            event_id=data['event_id'],
            event_type=EventType(data['event_type']),
            timestamp=datetime.fromisoformat(data['timestamp']),
            service=data['service'],
            namespace=data['namespace'],
            severity=EventSeverity(data['severity']),
            pod_name=data.get('pod_name'),
            container=data.get('container'),
            node=data.get('node'),
            metric_value=data.get('metric_value'),
            metric_unit=data.get('metric_unit'),
            threshold=data.get('threshold'),
            labels=data.get('labels', {}),
            annotations=data.get('annotations', {}),
            message=data.get('message'),
            details=data.get('details', {}),
            is_root_cause=data.get('is_root_cause', False),
            root_cause_confidence=data.get('root_cause_confidence', 0.0)
        )

    def get_abstract_event(self) -> 'AbstractEvent':
        """
        Convert to abstract event (removes specific identifiers)
        Used for pattern matching
        """
        return AbstractEvent(
            event_type=self.event_type,
            service_pattern=self._generalize_service(),
            severity=self.severity,
            metric_threshold_pattern=self._generalize_threshold()
        )

    def _generalize_service(self) -> str:
        """Generalize service name for pattern matching"""
        # Example: api-gateway-abc123 -> api-gateway-*
        # Remove pod hash suffixes
        parts = self.service.rsplit('-', 1)
        if len(parts) == 2 and len(parts[1]) > 8:
            return f"{parts[0]}-*"
        return self.service

    def _generalize_threshold(self) -> Optional[str]:
        """Generalize threshold for pattern matching"""
        if self.metric_value and self.threshold:
            if self.metric_value > self.threshold:
                return "above_threshold"
            return "below_threshold"
        return None


@dataclass
class AbstractEvent:
    """
    Abstract event type for pattern matching
    Represents event class rather than specific instance

    Used in Fault Event Knowledge Graph (FEKG)
    """
    event_type: EventType
    service_pattern: str  # e.g., "api-gateway-*" or specific service
    severity: EventSeverity
    metric_threshold_pattern: Optional[str] = None

    # Pattern metadata
    occurrence_count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    def matches(self, event: Event) -> bool:
        """Check if concrete event matches this abstract pattern"""
        # Type must match exactly
        if event.event_type != self.event_type:
            return False

        # Severity must match
        if event.severity != self.severity:
            return False

        # Service pattern matching
        if not self._matches_service_pattern(event.service):
            return False

        # Threshold pattern matching
        if self.metric_threshold_pattern:
            event_threshold_pattern = event._generalize_threshold()
            if event_threshold_pattern != self.metric_threshold_pattern:
                return False

        return True

    def _matches_service_pattern(self, service: str) -> bool:
        """Check if service matches the pattern"""
        if self.service_pattern == "*":
            return True

        if self.service_pattern.endswith("-*"):
            prefix = self.service_pattern[:-2]
            return service.startswith(prefix)

        return service == self.service_pattern

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'event_type': self.event_type.value,
            'service_pattern': self.service_pattern,
            'severity': self.severity.value,
            'metric_threshold_pattern': self.metric_threshold_pattern,
            'occurrence_count': self.occurrence_count,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }

    def get_signature(self) -> str:
        """Get unique signature for this abstract event"""
        parts = [
            self.event_type.value,
            self.service_pattern,
            self.severity.value
        ]
        if self.metric_threshold_pattern:
            parts.append(self.metric_threshold_pattern)
        return "|".join(parts)


@dataclass
class EventSequence:
    """Sequence of events within a time window"""
    events: List[Event] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def add_event(self, event: Event):
        """Add event to sequence"""
        self.events.append(event)
        self.events.sort(key=lambda e: e.timestamp)

        if not self.start_time or event.timestamp < self.start_time:
            self.start_time = event.timestamp
        if not self.end_time or event.timestamp > self.end_time:
            self.end_time = event.timestamp

    def get_event_types(self) -> List[EventType]:
        """Get sequence of event types"""
        return [e.event_type for e in self.events]

    def get_services(self) -> List[str]:
        """Get sequence of services"""
        return [e.service for e in self.events]

    def duration_seconds(self) -> float:
        """Get duration of event sequence in seconds"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
