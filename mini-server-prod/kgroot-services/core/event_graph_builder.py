"""
Event Graph Builder
Implements Algorithm 1 from KGroot paper (FPG Construction)
Builds Fault Propagation Graphs from event sequences
"""

import networkx as nx
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta
import logging

from models.event import Event, EventSequence, EventType
from models.graph import FaultPropagationGraph, EventRelation, RelationType

logger = logging.getLogger(__name__)


class EventGraphBuilder:
    """
    Constructs Fault Propagation Graph (FPG) from event sequences
    Based on KGroot Algorithm 1 - FPG Construction
    """

    def __init__(
        self,
        time_window_seconds: int = 300,  # 5 minutes
        max_related_events: int = 5,  # M in paper
        min_correlation_threshold: float = 0.3  # θ in paper
    ):
        self.time_window_seconds = time_window_seconds
        self.max_related_events = max_related_events
        self.min_correlation_threshold = min_correlation_threshold

        # Service dependency graph (should be loaded from topology)
        self.service_dependencies: Dict[str, List[str]] = {}

    def set_service_dependencies(self, dependencies: Dict[str, List[str]]):
        """
        Set service dependency graph
        Format: {service_name: [list of services it depends on]}
        """
        self.service_dependencies = dependencies

    def build_online_graph(
        self,
        events: List[Event],
        fault_id: str
    ) -> FaultPropagationGraph:
        """
        Build online FPG from event sequence
        Implements Algorithm 1 from KGroot paper

        Args:
            events: List of events in chronological order
            fault_id: Unique identifier for this fault

        Returns:
            FaultPropagationGraph
        """
        fpg = FaultPropagationGraph(fault_id, self.time_window_seconds)

        if not events:
            logger.warning(f"No events provided for fault {fault_id}")
            return fpg

        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        logger.info(f"Building FPG for fault {fault_id} with {len(sorted_events)} events")

        # Algorithm 1: Line 1-18
        for i, event in enumerate(sorted_events):
            # Add event to graph
            fpg.add_event(event)

            if i == 0:
                # First event, no predecessors
                continue

            # Get candidate graphs by adding edges to previous events
            candidate_graphs = self._get_candidate_graphs(
                fpg,
                event,
                sorted_events[:i]
            )

            if not candidate_graphs:
                # No relationships found, event stands alone
                continue

            # Select best candidate graph
            best_graph_edges = self._get_best_graph(
                candidate_graphs,
                self.min_correlation_threshold
            )

            # Add edges from best graph to FPG
            for source_id, target_id, relation_type, confidence in best_graph_edges:
                source_event = fpg.events[source_id]
                target_event = fpg.events[target_id]

                time_delta = (target_event.timestamp - source_event.timestamp).total_seconds()

                relation = EventRelation(
                    source_event_id=source_id,
                    target_event_id=target_id,
                    relation_type=relation_type,
                    confidence=confidence,
                    time_delta_seconds=time_delta
                )

                fpg.add_relation(relation)

        logger.info(
            f"Built FPG: {len(fpg.events)} events, "
            f"{len(fpg.relations)} relations, "
            f"{len(fpg.get_root_candidates())} root candidates"
        )

        return fpg

    def _get_candidate_graphs(
        self,
        current_fpg: FaultPropagationGraph,
        new_event: Event,
        previous_events: List[Event]
    ) -> List[List[Tuple[str, str, RelationType, float]]]:
        """
        Generate candidate graphs by adding new event
        Returns list of possible edge configurations
        """
        candidates = []

        # Look back at most recent events (limited by max_related_events)
        lookback_events = previous_events[-self.max_related_events:]

        for prev_event in lookback_events:
            # Check if events are related
            relation_type, confidence = self._classify_relationship(
                prev_event,
                new_event,
                current_fpg
            )

            if confidence >= self.min_correlation_threshold:
                # Create candidate with this edge
                candidate_edges = [(
                    prev_event.event_id,
                    new_event.event_id,
                    relation_type,
                    confidence
                )]
                candidates.append(candidate_edges)

        # Also consider multiple predecessors
        if len(lookback_events) >= 2:
            # Try combinations of 2 predecessors
            for i, prev1 in enumerate(lookback_events[-3:]):
                for prev2 in lookback_events[i+1:]:
                    rel1_type, conf1 = self._classify_relationship(prev1, new_event, current_fpg)
                    rel2_type, conf2 = self._classify_relationship(prev2, new_event, current_fpg)

                    if conf1 >= self.min_correlation_threshold and conf2 >= self.min_correlation_threshold:
                        candidate_edges = [
                            (prev1.event_id, new_event.event_id, rel1_type, conf1),
                            (prev2.event_id, new_event.event_id, rel2_type, conf2)
                        ]
                        candidates.append(candidate_edges)

        return candidates

    def _get_best_graph(
        self,
        candidates: List[List[Tuple[str, str, RelationType, float]]],
        threshold: float
    ) -> List[Tuple[str, str, RelationType, float]]:
        """
        Select best candidate graph based on edge confidence
        Returns edges from best candidate
        """
        if not candidates:
            return []

        # Score each candidate by sum of confidence scores
        best_candidate = None
        best_score = 0.0

        for candidate in candidates:
            score = sum(conf for _, _, _, conf in candidate)
            if score > best_score:
                best_score = score
                best_candidate = candidate

        # Return best candidate if above threshold
        if best_candidate and best_score >= threshold:
            return best_candidate

        return []

    def _classify_relationship(
        self,
        source_event: Event,
        target_event: Event,
        current_fpg: FaultPropagationGraph
    ) -> Tuple[RelationType, float]:
        """
        Classify relationship between two events
        Returns (RelationType, confidence_score)

        This is a rule-based classifier (replaces SVM from paper)
        """
        confidence = 0.0
        relation_type = RelationType.CORRELATES_WITH

        # Factor 1: Time proximity (closer in time = higher confidence)
        time_diff = (target_event.timestamp - source_event.timestamp).total_seconds()
        if time_diff < 0:
            # Target happened before source, no relationship
            return (RelationType.CORRELATES_WITH, 0.0)

        time_score = self._time_proximity_score(time_diff)
        confidence += time_score * 0.3

        # Factor 2: Same service (higher confidence)
        if source_event.service == target_event.service:
            confidence += 0.25
            relation_type = RelationType.SEQUENTIAL

        # Factor 3: Service dependency
        if self._has_dependency(source_event.service, target_event.service):
            confidence += 0.25
            relation_type = RelationType.PROPAGATES_TO

        # Factor 4: Event type causality patterns
        causality_score = self._event_causality_score(
            source_event.event_type,
            target_event.event_type
        )
        confidence += causality_score * 0.2

        if causality_score > 0.7:
            relation_type = RelationType.CAUSES

        # Factor 5: Same pod/container (strong signal)
        if source_event.pod_name and source_event.pod_name == target_event.pod_name:
            confidence += 0.15

        # Factor 6: Existing graph context
        context_score = self._context_score(source_event, target_event, current_fpg)
        confidence += context_score * 0.15

        # Normalize confidence to [0, 1]
        confidence = min(1.0, max(0.0, confidence))

        return (relation_type, confidence)

    def _time_proximity_score(self, time_diff_seconds: float) -> float:
        """
        Score based on time proximity
        Closer in time = higher score
        """
        if time_diff_seconds <= 0:
            return 0.0

        # Exponential decay: score = e^(-t/τ)
        # τ = 60 seconds (time constant)
        tau = 60.0
        score = 2.0 ** (-time_diff_seconds / tau)

        return min(1.0, score)

    def _has_dependency(self, source_service: str, target_service: str) -> bool:
        """Check if target service depends on source service"""
        if target_service not in self.service_dependencies:
            return False

        dependencies = self.service_dependencies[target_service]
        return source_service in dependencies

    def _event_causality_score(
        self,
        source_type: EventType,
        target_type: EventType
    ) -> float:
        """
        Score based on known causality patterns between event types
        Returns score 0.0 to 1.0
        """
        # Define causality rules
        causality_rules = {
            # Resource issues cause failures
            (EventType.CPU_HIGH, EventType.POD_RESTART): 0.8,
            (EventType.MEMORY_HIGH, EventType.OOM_KILL): 0.9,
            (EventType.OOM_KILL, EventType.POD_RESTART): 0.95,
            (EventType.DISK_HIGH, EventType.POD_FAILED): 0.7,

            # Failures cause service issues
            (EventType.POD_RESTART, EventType.SERVICE_DOWN): 0.8,
            (EventType.POD_FAILED, EventType.SERVICE_DOWN): 0.9,

            # Service issues cause performance problems
            (EventType.SERVICE_DOWN, EventType.LATENCY_HIGH): 0.7,
            (EventType.NETWORK_ERROR, EventType.LATENCY_HIGH): 0.75,
            (EventType.SERVICE_DOWN, EventType.ERROR_RATE_HIGH): 0.8,

            # Configuration and deployments cause various issues
            (EventType.CONFIG_CHANGE, EventType.POD_RESTART): 0.6,
            (EventType.DEPLOYMENT, EventType.POD_RESTART): 0.5,
            (EventType.CONFIG_CHANGE, EventType.SERVICE_DOWN): 0.65,

            # Health check failures
            (EventType.HEALTH_CHECK_FAILED, EventType.POD_RESTART): 0.7,
            (EventType.HEALTH_CHECK_FAILED, EventType.SERVICE_DOWN): 0.75,

            # Resource pressure cascade
            (EventType.CPU_HIGH, EventType.LATENCY_HIGH): 0.6,
            (EventType.MEMORY_HIGH, EventType.LATENCY_HIGH): 0.5,
        }

        return causality_rules.get((source_type, target_type), 0.1)

    def _context_score(
        self,
        source_event: Event,
        target_event: Event,
        current_fpg: FaultPropagationGraph
    ) -> float:
        """
        Score based on graph context
        Events that fit well into existing propagation paths score higher
        """
        if source_event.event_id not in current_fpg.events:
            return 0.0

        score = 0.0

        # Check if source is already connected to other events
        source_out_degree = current_fpg.graph.out_degree(source_event.event_id)
        if source_out_degree > 0:
            # Source already propagates to other events
            score += 0.3

        # Check if source is a known root cause pattern
        source_in_degree = current_fpg.graph.in_degree(source_event.event_id)
        if source_in_degree == 0:
            # Source has no predecessors, likely root cause
            score += 0.4

        # Check if adding this edge creates a valid propagation chain
        if source_out_degree > 0:
            # Check transitivity: if source -> A and A -> target type, this is likely valid
            for successor in current_fpg.graph.successors(source_event.event_id):
                successor_event = current_fpg.events[successor]
                causality = self._event_causality_score(
                    successor_event.event_type,
                    target_event.event_type
                )
                if causality > 0.5:
                    score += 0.3
                    break

        return min(1.0, score)

    def build_historical_graphs(
        self,
        fault_events_by_fault: Dict[str, List[Event]]
    ) -> Dict[str, FaultPropagationGraph]:
        """
        Build FPGs for multiple historical faults
        Used for pattern learning

        Args:
            fault_events_by_fault: Dict mapping fault_id to list of events

        Returns:
            Dict mapping fault_id to FaultPropagationGraph
        """
        fpgs = {}

        for fault_id, events in fault_events_by_fault.items():
            try:
                fpg = self.build_online_graph(events, fault_id)
                fpgs[fault_id] = fpg
            except Exception as e:
                logger.error(f"Failed to build FPG for fault {fault_id}: {e}")
                continue

        logger.info(f"Built {len(fpgs)} historical FPGs")
        return fpgs
