"""
RCA Orchestrator
Main entry point for KGroot RCA system
Coordinates all components to perform root cause analysis
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from models.event import Event
from models.graph import FaultPropagationGraph, FaultEventKnowledgeGraph
from models.pattern import PatternMatch
from core.event_graph_builder import EventGraphBuilder
from core.pattern_matcher import PatternMatcher
from core.root_cause_ranker import RootCauseRanker
from graphrag.embeddings import EmbeddingService
from graphrag.llm_analyzer import LLMAnalyzer

logger = logging.getLogger(__name__)


class RCAResult:
    """Container for RCA results"""
    def __init__(self):
        self.fault_id: Optional[str] = None
        self.timestamp: datetime = datetime.now()

        # Graph analysis
        self.fpg: Optional[FaultPropagationGraph] = None
        self.matched_patterns: List[PatternMatch] = []

        # Root cause analysis
        self.top_root_causes: List[Dict] = []
        self.root_cause_confidence: float = 0.0

        # LLM analysis
        self.llm_analysis: Optional[Dict] = None
        self.recommended_actions: List[str] = []

        # Performance metrics
        self.analysis_duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Export to dictionary"""
        return {
            'fault_id': self.fault_id,
            'timestamp': self.timestamp.isoformat(),
            'graph_statistics': self.fpg.get_graph_statistics() if self.fpg else {},
            'matched_patterns': [p.to_dict() for p in self.matched_patterns],
            'top_root_causes': self.top_root_causes,
            'root_cause_confidence': self.root_cause_confidence,
            'llm_analysis': self.llm_analysis,
            'recommended_actions': self.recommended_actions,
            'analysis_duration_seconds': self.analysis_duration_seconds
        }


class RCAOrchestrator:
    """
    Main orchestrator for KGroot RCA
    Coordinates graph building, pattern matching, and ranking
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        enable_llm: bool = False,
        llm_model: str = "gpt-5",
        reasoning_effort: str = "medium",
        verbosity: str = "medium"
    ):
        """
        Initialize RCA orchestrator

        Args:
            openai_api_key: OpenAI API key for GraphRAG
            enable_llm: Enable LLM-enhanced analysis
            llm_model: Model to use (gpt-5, gpt-5-mini, gpt-5-nano, or gpt-4o)
            reasoning_effort: GPT-5 reasoning effort (minimal, low, medium, high)
            verbosity: GPT-5 output verbosity (low, medium, high)
        """
        # Core components
        self.graph_builder = EventGraphBuilder(
            time_window_seconds=300,
            max_related_events=5,
            min_correlation_threshold=0.3
        )

        self.pattern_matcher = PatternMatcher(
            jaccard_weight=0.35,
            service_weight=0.25,
            sequence_weight=0.30,
            structure_weight=0.10
        )

        self.root_cause_ranker = RootCauseRanker(
            time_weight=0.6,
            distance_weight=0.4
        )

        # GraphRAG components (optional)
        self.enable_llm = enable_llm and openai_api_key
        if self.enable_llm:
            self.embedding_service = EmbeddingService(openai_api_key)
            self.llm_analyzer = LLMAnalyzer(
                api_key=openai_api_key,
                model=llm_model,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity
            )
            logger.info(f"LLM-enhanced analysis enabled with {llm_model}")
        else:
            self.embedding_service = None
            self.llm_analyzer = None
            logger.info("Running in rule-based mode (no LLM)")

        # Pattern library (loaded from Neo4j)
        self.pattern_library: List[FaultEventKnowledgeGraph] = []

        logger.info("RCAOrchestrator initialized")

    def set_service_dependencies(self, dependencies: Dict[str, List[str]]):
        """Set service dependency topology"""
        self.graph_builder.set_service_dependencies(dependencies)
        self.root_cause_ranker.set_service_graph(dependencies)
        logger.info(f"Loaded {len(dependencies)} service dependencies")

    def load_pattern_library(self, patterns: List[FaultEventKnowledgeGraph]):
        """Load historical failure patterns"""
        self.pattern_library = patterns
        logger.info(f"Loaded {len(patterns)} failure patterns")

    async def analyze_failure(
        self,
        fault_id: str,
        events: List[Event],
        context: Optional[Dict[str, Any]] = None
    ) -> RCAResult:
        """
        Perform complete root cause analysis

        Args:
            fault_id: Unique identifier for this fault
            events: List of events related to this fault
            context: Optional context (deployments, config changes, etc.)

        Returns:
            RCAResult with complete analysis
        """
        start_time = datetime.now()
        result = RCAResult()
        result.fault_id = fault_id

        logger.info(f"Starting RCA for fault {fault_id} with {len(events)} events")

        try:
            # Step 1: Build Fault Propagation Graph (FPG)
            logger.info("Step 1: Building FPG...")
            fpg = self.graph_builder.build_online_graph(events, fault_id)
            result.fpg = fpg

            if fpg.graph.number_of_nodes() == 0:
                logger.warning("Empty FPG generated")
                result.llm_analysis = {"error": "No events to analyze"}
                return result

            # Step 2: Match with historical patterns
            logger.info("Step 2: Matching patterns...")
            if self.pattern_library:
                matched_patterns = self.pattern_matcher.find_similar_patterns(
                    fpg,
                    self.pattern_library,
                    top_k=3
                )
                result.matched_patterns = matched_patterns
                logger.info(f"Found {len(matched_patterns)} similar patterns")
            else:
                logger.warning("No pattern library loaded")
                matched_patterns = []

            # Step 3: Identify and rank root causes
            logger.info("Step 3: Ranking root causes...")
            root_candidates = fpg.get_root_candidates()

            if root_candidates:
                # Use alarm event (last event chronologically)
                alarm_event = max(events, key=lambda e: e.timestamp)

                ranked_causes = self.root_cause_ranker.rank_root_causes(
                    root_candidates,
                    alarm_event,
                    fpg,
                    top_n=5
                )

                result.top_root_causes = [
                    {
                        'event_id': rc.event.event_id,
                        'event_type': rc.event.event_type.value,
                        'service': rc.event.service,
                        'pod': rc.event.pod_name,
                        'timestamp': rc.event.timestamp.isoformat(),
                        'confidence': f"{rc.rank_score:.2%}",
                        'explanation': rc.explanation,
                        'propagation_path': rc.propagation_path
                    }
                    for rc in ranked_causes
                ]

                if ranked_causes:
                    result.root_cause_confidence = ranked_causes[0].rank_score

                logger.info(f"Identified {len(ranked_causes)} ranked root causes")
            else:
                logger.warning("No root cause candidates found")

            # Step 4: LLM-enhanced analysis (if enabled)
            if self.enable_llm and self.llm_analyzer:
                logger.info("Step 4: LLM analysis...")
                llm_analysis = await self.llm_analyzer.analyze_failure(
                    online_graph_summary=fpg.get_graph_statistics(),
                    matched_patterns=[p.to_dict() for p in matched_patterns],
                    ranked_causes=result.top_root_causes,
                    context=context
                )
                result.llm_analysis = llm_analysis

                # Extract recommendations
                if 'immediate_actions' in llm_analysis:
                    result.recommended_actions = llm_analysis['immediate_actions']
            else:
                # Use pattern-based recommendations
                if matched_patterns:
                    result.recommended_actions = matched_patterns[0].pattern.resolution_steps

            # Calculate duration
            result.analysis_duration_seconds = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"RCA completed in {result.analysis_duration_seconds:.2f}s, "
                f"confidence: {result.root_cause_confidence:.2%}"
            )

            return result

        except Exception as e:
            logger.error(f"RCA failed for fault {fault_id}: {e}", exc_info=True)
            result.llm_analysis = {"error": str(e)}
            return result

    def get_summary(self, result: RCAResult) -> str:
        """Generate human-readable summary of RCA results"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"ROOT CAUSE ANALYSIS: {result.fault_id}")
        lines.append("=" * 60)

        if result.top_root_causes:
            top_cause = result.top_root_causes[0]
            lines.append(f"\nTOP ROOT CAUSE (Confidence: {top_cause['confidence']}):")
            lines.append(f"  Event Type: {top_cause['event_type']}")
            lines.append(f"  Service: {top_cause['service']}")
            if top_cause['pod']:
                lines.append(f"  Pod: {top_cause['pod']}")
            lines.append(f"  Timestamp: {top_cause['timestamp']}")
            lines.append(f"  Explanation: {top_cause['explanation']}")
        else:
            lines.append("\nNo root cause identified")

        if result.matched_patterns:
            lines.append(f"\nMATCHED PATTERNS: {len(result.matched_patterns)}")
            for i, pattern in enumerate(result.matched_patterns[:2], 1):
                lines.append(f"  {i}. {pattern.pattern.name} "
                           f"(similarity: {pattern.similarity_score:.1%})")

        if result.recommended_actions:
            lines.append("\nRECOMMENDED ACTIONS:")
            for i, action in enumerate(result.recommended_actions, 1):
                lines.append(f"  {i}. {action}")

        if result.llm_analysis and 'root_cause_diagnosis' in result.llm_analysis:
            lines.append("\nLLM ANALYSIS:")
            lines.append(f"  {result.llm_analysis['root_cause_diagnosis']}")

        lines.append(f"\nAnalysis Duration: {result.analysis_duration_seconds:.2f}s")
        lines.append("=" * 60)

        return "\n".join(lines)
