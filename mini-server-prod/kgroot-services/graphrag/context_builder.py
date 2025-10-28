"""
GraphRAG Context Builder

Builds enriched context from graph data for LLM analysis.
"""

from typing import Dict, List, Optional
from models.graph import FaultPropagationGraph, FaultEventKnowledgeGraph
from models.event import Event


class GraphContextBuilder:
    """Builds context from graph structures for LLM consumption"""

    def __init__(self):
        pass

    def build_context_from_fpg(self, fpg: FaultPropagationGraph) -> Dict:
        """
        Build context from Fault Propagation Graph

        Returns:
            Dict with graph summary, event timeline, service topology
        """
        context = {
            "fault_id": fpg.fault_id,
            "event_count": len(fpg.events),
            "services_affected": list(set(e.service for e in fpg.events.values())),
            "time_window": fpg.time_window_seconds,
            "event_types": [e.event_type.value for e in fpg.events.values()],
            "timeline": self._build_timeline(fpg),
            "relationships": self._build_relationships(fpg),
        }
        return context

    def build_context_from_fekg(self, fekg: FaultEventKnowledgeGraph) -> Dict:
        """
        Build context from Fault Event Knowledge Graph (historical pattern)

        Returns:
            Dict with pattern summary, root cause, frequency
        """
        context = {
            "pattern_id": fekg.pattern_id,
            "root_cause": fekg.root_cause_event.event_type.value if fekg.root_cause_event else None,
            "event_count": len(fekg.events),
            "services": list(set(e.service for e in fekg.events.values())),
            "frequency": getattr(fekg, 'frequency', 1),
            "event_sequence": [e.event_type.value for e in fekg.events.values()],
        }
        return context

    def _build_timeline(self, fpg: FaultPropagationGraph) -> List[Dict]:
        """Build chronological event timeline"""
        events = sorted(fpg.events.values(), key=lambda e: e.timestamp)
        return [
            {
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type.value,
                "service": e.service,
                "severity": e.severity.value,
                "message": e.message[:100] if e.message else ""
            }
            for e in events
        ]

    def _build_relationships(self, fpg: FaultPropagationGraph) -> List[Dict]:
        """Build relationship summary"""
        return [
            {
                "source": rel.source_event_id,
                "target": rel.target_event_id,
                "type": rel.relation_type.value,
                "confidence": rel.confidence
            }
            for rel in fpg.relations
        ]