"""
Pattern Matcher
Matches online FPGs with historical FEKG patterns
Simplified version without GCN (rule-based similarity)
"""

import networkx as nx
from typing import List, Dict, Tuple, Optional
import logging
from difflib import SequenceMatcher

from models.graph import FaultPropagationGraph, FaultEventKnowledgeGraph
from models.pattern import FailurePattern, PatternMatch
from models.event import EventType

logger = logging.getLogger(__name__)


class PatternMatcher:
    """
    Matches online fault graphs with historical patterns
    Implements simplified version of KGroot's GCN-based matching
    """

    def __init__(
        self,
        jaccard_weight: float = 0.35,
        service_weight: float = 0.25,
        sequence_weight: float = 0.30,
        structure_weight: float = 0.10
    ):
        """
        Initialize with similarity weights
        These weights sum to 1.0
        """
        self.jaccard_weight = jaccard_weight
        self.service_weight = service_weight
        self.sequence_weight = sequence_weight
        self.structure_weight = structure_weight

    def find_similar_patterns(
        self,
        online_fpg: FaultPropagationGraph,
        pattern_library: List[FaultEventKnowledgeGraph],
        top_k: int = 3
    ) -> List[PatternMatch]:
        """
        Find top-k most similar patterns to online FPG

        Args:
            online_fpg: Online fault propagation graph
            pattern_library: List of historical FEKGs
            top_k: Number of top matches to return

        Returns:
            List of PatternMatch objects, sorted by similarity
        """
        if not pattern_library:
            logger.warning("Pattern library is empty")
            return []

        matches = []

        for pattern in pattern_library:
            similarity = self._compute_similarity(online_fpg, pattern)
            matches.append(similarity)

        # Sort by similarity score (descending)
        matches.sort(key=lambda m: m.similarity_score, reverse=True)

        return matches[:top_k]

    def _compute_similarity(
        self,
        online_fpg: FaultPropagationGraph,
        fekg: FaultEventKnowledgeGraph
    ) -> PatternMatch:
        """
        Compute multi-factor similarity between FPG and FEKG
        Returns PatternMatch with detailed scores
        """
        # Extract event types from online graph
        online_event_types = set(e.event_type for e in online_fpg.events.values())
        online_services = set(e.service for e in online_fpg.events.values())

        # Extract event types from pattern
        pattern_event_types = set(
            ae.event_type for ae in fekg.abstract_events.values()
        )
        pattern_services = set(
            ae.service_pattern.rstrip('-*')  # Remove wildcard
            for ae in fekg.abstract_events.values()
        )

        # Factor 1: Jaccard similarity (event type overlap)
        jaccard = self._jaccard_similarity(online_event_types, pattern_event_types)

        # Factor 2: Service overlap
        service_sim = self._jaccard_similarity(online_services, pattern_services)

        # Factor 3: Sequence similarity
        online_seq = [e.event_type for e in sorted(online_fpg.events.values(), key=lambda x: x.timestamp)]
        pattern_seq = [fekg.abstract_events[sig].event_type for sig in fekg.event_sequence]
        sequence_sim = self._sequence_similarity(online_seq, pattern_seq)

        # Factor 4: Graph structure similarity
        structure_sim = self._structure_similarity(online_fpg, fekg)

        # Weighted combination
        total_similarity = (
            self.jaccard_weight * jaccard +
            self.service_weight * service_sim +
            self.sequence_weight * sequence_sim +
            self.structure_weight * structure_sim
        )

        # Calculate confidence based on pattern frequency and similarity
        confidence = self._calculate_confidence(total_similarity, fekg.frequency)

        # Create simplified FailurePattern from FEKG
        pattern = FailurePattern(
            pattern_id=fekg.pattern_id,
            name=f"{fekg.fault_type} Pattern",
            root_cause_type=fekg.root_cause_type,
            event_signature=[sig for sig in fekg.event_sequence],
            frequency=fekg.frequency,
            confidence=confidence,
            last_matched=fekg.last_seen,
            affected_services=list(pattern_services),
            resolution_steps=fekg.resolution_steps,
            avg_resolution_time_seconds=fekg.avg_resolution_time_seconds
        )

        # Identify matched, missing, and extra events
        matched_events = list(online_event_types & pattern_event_types)
        missing_events = list(pattern_event_types - online_event_types)
        extra_events = list(online_event_types - pattern_event_types)

        return PatternMatch(
            pattern=pattern,
            similarity_score=total_similarity,
            confidence=confidence,
            jaccard_similarity=jaccard,
            service_overlap=service_sim,
            sequence_similarity=sequence_sim,
            graph_structure_similarity=structure_sim,
            matched_events=[et.value for et in matched_events],
            missing_events=[et.value for et in missing_events],
            extra_events=[et.value for et in extra_events]
        )

    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """
        Calculate Jaccard similarity between two sets
        J(A, B) = |A ∩ B| / |A ∪ B|
        """
        if not set1 and not set2:
            return 1.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _sequence_similarity(self, seq1: List, seq2: List) -> float:
        """
        Calculate sequence similarity using longest common subsequence (LCS)
        """
        if not seq1 or not seq2:
            return 0.0

        # Convert to strings for SequenceMatcher
        str1 = '|'.join(str(x.value if hasattr(x, 'value') else x) for x in seq1)
        str2 = '|'.join(str(x.value if hasattr(x, 'value') else x) for x in seq2)

        matcher = SequenceMatcher(None, str1, str2)
        return matcher.ratio()

    def _structure_similarity(
        self,
        fpg: FaultPropagationGraph,
        fekg: FaultEventKnowledgeGraph
    ) -> float:
        """
        Calculate graph structure similarity
        Based on edge count ratio and path similarities
        """
        fpg_edges = fpg.graph.number_of_edges()
        fekg_edges = fekg.graph.number_of_edges()

        if fpg_edges == 0 and fekg_edges == 0:
            return 1.0

        # Edge count ratio
        edge_ratio = min(fpg_edges, fekg_edges) / max(fpg_edges, fekg_edges, 1)

        # Density similarity
        fpg_density = nx.density(fpg.graph)
        fekg_density = nx.density(fekg.graph)

        if fpg_density == 0 and fekg_density == 0:
            density_sim = 1.0
        else:
            density_sim = 1.0 - abs(fpg_density - fekg_density)

        # Average
        return (edge_ratio + density_sim) / 2.0

    def _calculate_confidence(self, similarity: float, frequency: int) -> float:
        """
        Calculate confidence score based on similarity and pattern frequency
        More frequent patterns with high similarity get higher confidence
        """
        # Frequency factor (log scale, capped at 0.3)
        freq_factor = min(0.3, 0.1 * (frequency ** 0.5))

        # Similarity is the main factor (0.7 weight)
        confidence = 0.7 * similarity + freq_factor

        return min(1.0, confidence)
