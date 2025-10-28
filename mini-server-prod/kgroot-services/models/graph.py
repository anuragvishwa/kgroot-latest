"""
Graph models for KGroot RCA
Implements FPG (Fault Propagation Graph) and FEKG (Fault Event Knowledge Graph)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
from enum import Enum
import networkx as nx

from .event import Event, AbstractEvent, EventType


class RelationType(Enum):
    """Types of relationships between events"""
    CAUSES = "causes"  # Causal relationship
    SEQUENTIAL = "sequential"  # Sequential occurrence
    PROPAGATES_TO = "propagates_to"  # Propagation through dependencies
    CORRELATES_WITH = "correlates_with"  # Correlation without causation


@dataclass
class EventRelation:
    """Relationship between two events"""
    source_event_id: str
    target_event_id: str
    relation_type: RelationType
    confidence: float = 0.0  # 0.0 to 1.0
    time_delta_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FaultPropagationGraph:
    """
    Online Fault Propagation Graph (FPG)
    Constructed in real-time when a failure occurs
    Based on Algorithm 1 from KGroot paper
    """

    def __init__(self, fault_id: str, time_window_seconds: int = 300):
        self.fault_id = fault_id
        self.time_window_seconds = time_window_seconds
        self.graph = nx.DiGraph()
        self.events: Dict[str, Event] = {}
        self.relations: List[EventRelation] = []
        self.creation_time = datetime.now()

    def add_event(self, event: Event):
        """Add event to the graph"""
        self.events[event.event_id] = event
        self.graph.add_node(
            event.event_id,
            event_type=event.event_type.value,
            service=event.service,
            namespace=event.namespace,
            timestamp=event.timestamp.isoformat(),
            severity=event.severity.value,
            pod_name=event.pod_name,
            is_root_cause=event.is_root_cause
        )

    def add_relation(self, relation: EventRelation):
        """Add relationship between events"""
        if relation.source_event_id not in self.events:
            raise ValueError(f"Source event {relation.source_event_id} not in graph")
        if relation.target_event_id not in self.events:
            raise ValueError(f"Target event {relation.target_event_id} not in graph")

        self.relations.append(relation)
        self.graph.add_edge(
            relation.source_event_id,
            relation.target_event_id,
            relation_type=relation.relation_type.value,
            confidence=relation.confidence,
            time_delta=relation.time_delta_seconds
        )

    def get_root_candidates(self) -> List[Event]:
        """
        Get potential root cause events
        Events with no incoming edges are likely root causes
        """
        root_candidates = []
        for event_id in self.graph.nodes():
            if self.graph.in_degree(event_id) == 0:
                root_candidates.append(self.events[event_id])

        # Sort by timestamp (earlier events more likely to be root cause)
        root_candidates.sort(key=lambda e: e.timestamp)
        return root_candidates

    def get_event_propagation_path(self, event_id: str) -> List[str]:
        """Get propagation path from root to given event"""
        root_candidates = self.get_root_candidates()
        if not root_candidates:
            return []

        # Find shortest path from any root to this event
        shortest_path = None
        for root in root_candidates:
            try:
                path = nx.shortest_path(self.graph, root.event_id, event_id)
                if shortest_path is None or len(path) < len(shortest_path):
                    shortest_path = path
            except nx.NetworkXNoPath:
                continue

        return shortest_path or []

    def to_abstract_graph(self) -> 'FaultEventKnowledgeGraph':
        """
        Convert concrete FPG to abstract FEKG
        For pattern matching and storage
        """
        fekg = FaultEventKnowledgeGraph(
            pattern_id=f"pattern_from_{self.fault_id}",
            root_cause_type=self._infer_root_cause_type()
        )

        # Convert events to abstract events
        abstract_events = {}
        for event_id, event in self.events.items():
            abstract_event = event.get_abstract_event()
            signature = abstract_event.get_signature()
            abstract_events[event_id] = signature

            if signature not in fekg.abstract_events:
                fekg.add_abstract_event(abstract_event)

        # Convert relations to abstract relations
        for relation in self.relations:
            source_sig = abstract_events[relation.source_event_id]
            target_sig = abstract_events[relation.target_event_id]

            fekg.add_abstract_relation(
                source_sig,
                target_sig,
                relation.relation_type
            )

        return fekg

    def _infer_root_cause_type(self) -> str:
        """Infer root cause type from events"""
        root_candidates = self.get_root_candidates()
        if root_candidates:
            return root_candidates[0].event_type.value
        return "unknown"

    def get_graph_statistics(self) -> Dict[str, Any]:
        """Get statistics about the graph"""
        return {
            'fault_id': self.fault_id,
            'num_events': len(self.events),
            'num_relations': len(self.relations),
            'num_root_candidates': len(self.get_root_candidates()),
            'event_types': list(set(e.event_type.value for e in self.events.values())),
            'affected_services': list(set(e.service for e in self.events.values())),
            'time_span_seconds': self._get_time_span(),
            'graph_density': nx.density(self.graph),
            'creation_time': self.creation_time.isoformat()
        }

    def _get_time_span(self) -> float:
        """Get time span of events in seconds"""
        if not self.events:
            return 0.0
        timestamps = [e.timestamp for e in self.events.values()]
        return (max(timestamps) - min(timestamps)).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Export graph to dictionary"""
        return {
            'fault_id': self.fault_id,
            'events': [e.to_dict() for e in self.events.values()],
            'relations': [
                {
                    'source': r.source_event_id,
                    'target': r.target_event_id,
                    'type': r.relation_type.value,
                    'confidence': r.confidence,
                    'time_delta': r.time_delta_seconds
                }
                for r in self.relations
            ],
            'statistics': self.get_graph_statistics()
        }


class FaultEventKnowledgeGraph:
    """
    Fault Event Knowledge Graph (FEKG)
    Historical pattern stored in database
    Contains abstract events and their relationships
    """

    def __init__(
        self,
        pattern_id: str,
        root_cause_type: str,
        fault_type: Optional[str] = None
    ):
        self.pattern_id = pattern_id
        self.root_cause_type = root_cause_type
        self.fault_type = fault_type or root_cause_type

        self.graph = nx.DiGraph()
        self.abstract_events: Dict[str, AbstractEvent] = {}
        self.event_sequence: List[str] = []  # Ordered list of event signatures

        # Metadata
        self.frequency = 0  # How many times this pattern has been matched
        self.first_seen: Optional[datetime] = None
        self.last_seen: Optional[datetime] = None
        self.avg_resolution_time_seconds: Optional[float] = None

        # Resolution information
        self.resolution_steps: List[str] = []
        self.prevention_measures: List[str] = []

    def add_abstract_event(self, abstract_event: AbstractEvent):
        """Add abstract event to knowledge graph"""
        signature = abstract_event.get_signature()
        self.abstract_events[signature] = abstract_event

        self.graph.add_node(
            signature,
            event_type=abstract_event.event_type.value,
            service_pattern=abstract_event.service_pattern,
            severity=abstract_event.severity.value
        )

        if signature not in self.event_sequence:
            self.event_sequence.append(signature)

    def add_abstract_relation(
        self,
        source_signature: str,
        target_signature: str,
        relation_type: RelationType,
        confidence: float = 1.0
    ):
        """Add relationship between abstract events"""
        if source_signature not in self.abstract_events:
            raise ValueError(f"Source event {source_signature} not in graph")
        if target_signature not in self.abstract_events:
            raise ValueError(f"Target event {target_signature} not in graph")

        self.graph.add_edge(
            source_signature,
            target_signature,
            relation_type=relation_type.value,
            confidence=confidence
        )

    def matches_event_sequence(self, event_types: List[EventType]) -> float:
        """
        Calculate how well an event sequence matches this pattern
        Returns similarity score 0.0 to 1.0
        """
        pattern_types = [
            self.abstract_events[sig].event_type
            for sig in self.event_sequence
        ]

        # Jaccard similarity
        set1 = set(event_types)
        set2 = set(pattern_types)

        if not set1 and not set2:
            return 1.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def get_expected_propagation_path(self) -> List[str]:
        """Get expected event propagation path"""
        if not self.abstract_events:
            return []

        # Find nodes with no incoming edges (root causes)
        roots = [n for n in self.graph.nodes() if self.graph.in_degree(n) == 0]

        if not roots:
            # If no clear root, return topological sort
            try:
                return list(nx.topological_sort(self.graph))
            except nx.NetworkXError:
                # Graph has cycles, return event sequence
                return self.event_sequence

        # Return longest path from root
        longest_path = []
        for root in roots:
            for node in self.graph.nodes():
                if node != root:
                    try:
                        path = nx.shortest_path(self.graph, root, node)
                        if len(path) > len(longest_path):
                            longest_path = path
                    except nx.NetworkXNoPath:
                        continue

        return longest_path or [roots[0]]

    def update_statistics(self, matched: bool = True):
        """Update pattern statistics after matching attempt"""
        now = datetime.now()

        if matched:
            self.frequency += 1
            self.last_seen = now

        if self.first_seen is None:
            self.first_seen = now

    def to_dict(self) -> Dict[str, Any]:
        """Export to dictionary"""
        return {
            'pattern_id': self.pattern_id,
            'root_cause_type': self.root_cause_type,
            'fault_type': self.fault_type,
            'abstract_events': [
                ae.to_dict() for ae in self.abstract_events.values()
            ],
            'event_sequence': self.event_sequence,
            'edges': [
                {
                    'source': u,
                    'target': v,
                    'relation_type': data['relation_type'],
                    'confidence': data.get('confidence', 1.0)
                }
                for u, v, data in self.graph.edges(data=True)
            ],
            'frequency': self.frequency,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'avg_resolution_time_seconds': self.avg_resolution_time_seconds,
            'resolution_steps': self.resolution_steps,
            'prevention_measures': self.prevention_measures
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FaultEventKnowledgeGraph':
        """Load from dictionary"""
        fekg = cls(
            pattern_id=data['pattern_id'],
            root_cause_type=data['root_cause_type'],
            fault_type=data.get('fault_type')
        )

        # Restore abstract events
        for ae_data in data['abstract_events']:
            abstract_event = AbstractEvent(
                event_type=EventType(ae_data['event_type']),
                service_pattern=ae_data['service_pattern'],
                severity=ae_data['severity'],
                metric_threshold_pattern=ae_data.get('metric_threshold_pattern'),
                occurrence_count=ae_data.get('occurrence_count', 0),
                first_seen=datetime.fromisoformat(ae_data['first_seen']) if ae_data.get('first_seen') else None,
                last_seen=datetime.fromisoformat(ae_data['last_seen']) if ae_data.get('last_seen') else None
            )
            fekg.add_abstract_event(abstract_event)

        # Restore edges
        for edge in data['edges']:
            fekg.add_abstract_relation(
                edge['source'],
                edge['target'],
                RelationType(edge['relation_type']),
                edge.get('confidence', 1.0)
            )

        # Restore metadata
        fekg.frequency = data.get('frequency', 0)
        fekg.first_seen = datetime.fromisoformat(data['first_seen']) if data.get('first_seen') else None
        fekg.last_seen = datetime.fromisoformat(data['last_seen']) if data.get('last_seen') else None
        fekg.avg_resolution_time_seconds = data.get('avg_resolution_time_seconds')
        fekg.resolution_steps = data.get('resolution_steps', [])
        fekg.prevention_measures = data.get('prevention_measures', [])

        return fekg
