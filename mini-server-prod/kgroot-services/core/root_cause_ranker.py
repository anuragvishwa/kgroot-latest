"""
Root Cause Ranker
Implements Equation 3 from KGroot paper
Ranks potential root causes based on time proximity and graph distance
"""

import networkx as nx
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

from models.event import Event
from models.graph import FaultPropagationGraph

logger = logging.getLogger(__name__)


@dataclass
class RankedRootCause:
    """A root cause candidate with ranking information"""
    event: Event
    rank_score: float
    time_rank: float
    distance_rank: float
    time_score: float
    distance_score: float
    propagation_path: List[str]
    explanation: str


class RootCauseRanker:
    """
    Ranks root cause candidates using time-distance scoring
    Implements Equation 3: e = argmax(Wt·Nt(e) + Wd·Nd(e))
    """

    def __init__(
        self,
        time_weight: float = 0.6,  # Wt in paper
        distance_weight: float = 0.4  # Wd in paper
    ):
        """
        Initialize ranker with weights

        Args:
            time_weight: Weight for temporal proximity (Wt)
            distance_weight: Weight for graph distance (Wd)
        """
        self.time_weight = time_weight
        self.distance_weight = distance_weight

        # Service dependency graph
        self.service_graph = nx.DiGraph()

    def set_service_graph(self, service_dependencies: Dict[str, List[str]]):
        """
        Set service dependency topology

        Args:
            service_dependencies: Dict of service -> [dependent services]
        """
        self.service_graph.clear()

        for service, dependencies in service_dependencies.items():
            self.service_graph.add_node(service)
            for dep in dependencies:
                self.service_graph.add_edge(service, dep)

    def rank_root_causes(
        self,
        candidates: List[Event],
        alarm_event: Event,
        fpg: FaultPropagationGraph,
        top_n: int = 5
    ) -> List[RankedRootCause]:
        """
        Rank root cause candidates
        Implements Equation 3 from KGroot paper

        Args:
            candidates: List of potential root cause events
            alarm_event: The alarm/symptom event
            fpg: Fault propagation graph
            top_n: Number of top results to return

        Returns:
            List of RankedRootCause, sorted by score (descending)
        """
        if not candidates:
            logger.warning("No root cause candidates provided")
            return []

        ranked_causes = []

        for candidate in candidates:
            # Calculate temporal score (Nt in paper)
            time_score = self._calculate_time_score(candidate, alarm_event)
            time_rank = self._calculate_rank_position(
                time_score,
                [self._calculate_time_score(c, alarm_event) for c in candidates]
            )

            # Calculate distance score (Nd in paper)
            distance_score = self._calculate_distance_score(
                candidate,
                alarm_event,
                fpg
            )
            distance_rank = self._calculate_rank_position(
                distance_score,
                [self._calculate_distance_score(c, alarm_event, fpg) for c in candidates]
            )

            # Combined ranking score (Equation 3)
            rank_score = (
                self.time_weight * time_rank +
                self.distance_weight * distance_rank
            )

            # Get propagation path
            prop_path = fpg.get_event_propagation_path(alarm_event.event_id)

            # Generate explanation
            explanation = self._generate_explanation(
                candidate,
                alarm_event,
                time_score,
                distance_score,
                prop_path
            )

            ranked_causes.append(RankedRootCause(
                event=candidate,
                rank_score=rank_score,
                time_rank=time_rank,
                distance_rank=distance_rank,
                time_score=time_score,
                distance_score=distance_score,
                propagation_path=prop_path,
                explanation=explanation
            ))

        # Sort by rank score (descending)
        ranked_causes.sort(key=lambda rc: rc.rank_score, reverse=True)

        return ranked_causes[:top_n]

    def _calculate_time_score(self, candidate: Event, alarm: Event) -> float:
        """
        Calculate temporal proximity score
        Events closer in time get higher scores

        Returns: Score between 0.0 and 1.0
        """
        time_diff = abs((alarm.timestamp - candidate.timestamp).total_seconds())

        # If candidate is after alarm, it can't be the root cause
        if candidate.timestamp > alarm.timestamp:
            return 0.0

        # Exponential decay: score = e^(-t/τ)
        # τ = 120 seconds (time constant)
        tau = 120.0
        score = 2.0 ** (-time_diff / tau)

        return min(1.0, score)

    def _calculate_distance_score(
        self,
        candidate: Event,
        alarm: Event,
        fpg: FaultPropagationGraph
    ) -> float:
        """
        Calculate graph distance score
        Events closer in service dependency graph get higher scores

        Returns: Score between 0.0 and 1.0
        """
        # If same service, maximum score
        if candidate.service == alarm.service:
            return 1.0

        # Try to find path in FPG first
        try:
            fpg_path_length = nx.shortest_path_length(
                fpg.graph,
                candidate.event_id,
                alarm.event_id
            )
            # Normalize by graph diameter
            max_distance = fpg.graph.number_of_nodes()
            fpg_score = 1.0 - (fpg_path_length / max_distance)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            fpg_score = 0.0

        # Try service dependency graph
        try:
            service_distance = nx.shortest_path_length(
                self.service_graph,
                candidate.service,
                alarm.service
            )
            # Normalize (assuming max distance of 5 hops)
            service_score = 1.0 - (service_distance / 5.0)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            service_score = 0.0

        # Combine FPG and service graph scores
        # FPG is more reliable (0.7 weight) than service graph (0.3)
        if fpg_score > 0:
            return 0.7 * fpg_score + 0.3 * service_score
        else:
            return service_score

    def _calculate_rank_position(
        self,
        score: float,
        all_scores: List[float]
    ) -> float:
        """
        Calculate rank position normalized to [0, 1]
        Higher scores get higher ranks

        Returns: Normalized rank (1.0 = best, 0.0 = worst)
        """
        if not all_scores:
            return 0.0

        # Sort scores in descending order
        sorted_scores = sorted(all_scores, reverse=True)

        try:
            rank_position = sorted_scores.index(score)
            # Normalize: best rank (0) -> 1.0, worst rank -> 0.0
            normalized_rank = 1.0 - (rank_position / len(sorted_scores))
            return normalized_rank
        except ValueError:
            return 0.0

    def _generate_explanation(
        self,
        candidate: Event,
        alarm: Event,
        time_score: float,
        distance_score: float,
        propagation_path: List[str]
    ) -> str:
        """Generate human-readable explanation for ranking"""
        explanations = []

        # Time proximity explanation
        time_diff = (alarm.timestamp - candidate.timestamp).total_seconds()
        time_diff_mins = time_diff / 60.0
        if time_score > 0.8:
            explanations.append(
                f"occurred {time_diff_mins:.1f} minutes before the alarm (very recent)"
            )
        elif time_score > 0.5:
            explanations.append(
                f"occurred {time_diff_mins:.1f} minutes before the alarm"
            )
        else:
            explanations.append(
                f"occurred {time_diff_mins:.1f} minutes before the alarm (older event)"
            )

        # Service relationship explanation
        if candidate.service == alarm.service:
            explanations.append("in the same service")
        elif distance_score > 0.7:
            explanations.append(f"in upstream service {candidate.service}")
        else:
            explanations.append(f"in related service {candidate.service}")

        # Event type explanation
        explanations.append(f"type: {candidate.event_type.value}")

        # Propagation path
        if len(propagation_path) > 1:
            explanations.append(
                f"propagated through {len(propagation_path)-1} intermediate event(s)"
            )

        return "; ".join(explanations)

    def explain_ranking(
        self,
        ranked_causes: List[RankedRootCause]
    ) -> Dict[str, any]:
        """
        Generate comprehensive explanation of ranking results

        Returns:
            Dict with ranking analysis
        """
        if not ranked_causes:
            return {"error": "No ranked causes provided"}

        top_cause = ranked_causes[0]

        return {
            "top_root_cause": {
                "event_id": top_cause.event.event_id,
                "event_type": top_cause.event.event_type.value,
                "service": top_cause.event.service,
                "pod": top_cause.event.pod_name,
                "timestamp": top_cause.event.timestamp.isoformat(),
                "confidence": f"{top_cause.rank_score:.2%}",
                "explanation": top_cause.explanation
            },
            "scores": {
                "time_proximity": f"{top_cause.time_score:.2%}",
                "graph_distance": f"{top_cause.distance_score:.2%}",
                "time_weight": self.time_weight,
                "distance_weight": self.distance_weight
            },
            "propagation_path": top_cause.propagation_path,
            "alternative_causes": [
                {
                    "event_type": rc.event.event_type.value,
                    "service": rc.event.service,
                    "confidence": f"{rc.rank_score:.2%}",
                    "explanation": rc.explanation
                }
                for rc in ranked_causes[1:3]  # Next 2 alternatives
            ] if len(ranked_causes) > 1 else [],
            "total_candidates_evaluated": len(ranked_causes)
        }
