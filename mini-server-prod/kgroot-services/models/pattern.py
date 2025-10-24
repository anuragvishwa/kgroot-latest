"""
Pattern models for failure pattern matching
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class FailurePattern:
    """
    Represents a recurring failure pattern
    Simplified version of FEKG for quick matching
    """
    pattern_id: str
    name: str
    root_cause_type: str
    event_signature: List[str]  # Ordered list of event type signatures

    # Pattern metadata
    frequency: int = 0
    confidence: float = 0.0
    last_matched: Optional[datetime] = None

    # Affected resources
    affected_services: List[str] = field(default_factory=list)
    affected_namespaces: List[str] = field(default_factory=list)

    # Resolution information
    resolution_steps: List[str] = field(default_factory=list)
    avg_resolution_time_seconds: Optional[float] = None

    # Pattern characteristics
    typical_duration_seconds: Optional[float] = None
    typical_event_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'pattern_id': self.pattern_id,
            'name': self.name,
            'root_cause_type': self.root_cause_type,
            'event_signature': self.event_signature,
            'frequency': self.frequency,
            'confidence': self.confidence,
            'last_matched': self.last_matched.isoformat() if self.last_matched else None,
            'affected_services': self.affected_services,
            'affected_namespaces': self.affected_namespaces,
            'resolution_steps': self.resolution_steps,
            'avg_resolution_time_seconds': self.avg_resolution_time_seconds,
            'typical_duration_seconds': self.typical_duration_seconds,
            'typical_event_count': self.typical_event_count
        }


@dataclass
class PatternMatch:
    """
    Result of matching an online graph with a historical pattern
    """
    pattern: FailurePattern
    similarity_score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0

    # Detailed scoring breakdown
    jaccard_similarity: float = 0.0
    service_overlap: float = 0.0
    sequence_similarity: float = 0.0
    graph_structure_similarity: float = 0.0

    # Match details
    matched_events: List[str] = field(default_factory=list)
    missing_events: List[str] = field(default_factory=list)
    extra_events: List[str] = field(default_factory=list)

    # Timing
    match_timestamp: datetime = field(default_factory=datetime.now)

    def get_explanation(self) -> Dict[str, Any]:
        """Get human-readable explanation of the match"""
        return {
            'pattern_name': self.pattern.name,
            'root_cause_type': self.pattern.root_cause_type,
            'similarity_score': f"{self.similarity_score:.2%}",
            'confidence': f"{self.confidence:.2%}",
            'breakdown': {
                'event_overlap': f"{self.jaccard_similarity:.2%}",
                'service_overlap': f"{self.service_overlap:.2%}",
                'sequence_match': f"{self.sequence_similarity:.2%}",
                'structure_match': f"{self.graph_structure_similarity:.2%}"
            },
            'matched_events': len(self.matched_events),
            'total_pattern_events': len(self.pattern.event_signature),
            'extra_events_detected': len(self.extra_events),
            'recommendation': self.pattern.resolution_steps,
            'expected_resolution_time': (
                f"{self.pattern.avg_resolution_time_seconds / 60:.1f} minutes"
                if self.pattern.avg_resolution_time_seconds
                else "Unknown"
            )
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'pattern': self.pattern.to_dict(),
            'similarity_score': self.similarity_score,
            'confidence': self.confidence,
            'scores': {
                'jaccard_similarity': self.jaccard_similarity,
                'service_overlap': self.service_overlap,
                'sequence_similarity': self.sequence_similarity,
                'graph_structure_similarity': self.graph_structure_similarity
            },
            'matched_events': self.matched_events,
            'missing_events': self.missing_events,
            'extra_events': self.extra_events,
            'match_timestamp': self.match_timestamp.isoformat(),
            'explanation': self.get_explanation()
        }
