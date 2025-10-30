"""GraphAgent for causality analysis using Neo4j"""

from src.agents.base import BaseAgent, AgentCapability
from src.core.schemas import AgentResult, AgentFinding, AgentArtifact
from typing import Dict, Any, List
import logging
import time

logger = logging.getLogger(__name__)


class GraphAgent(BaseAgent):
    """Agent specialized in Neo4j causality graph analysis"""

    @property
    def capability(self) -> AgentCapability:
        return AgentCapability(
            name="GraphAgent",
            description="Analyzes Neo4j causality graphs and Kubernetes topology for root cause analysis",
            tools=[
                "neo4j_find_root_causes",
                "neo4j_get_causal_chain",
                "neo4j_get_blast_radius",
                "neo4j_get_cross_service_failures"
            ],
            expertise="Kubernetes event causality, topology-aware RCA, multi-hop failure propagation"
        )

    async def investigate(self, query: str, scope: Dict[str, Any]) -> AgentResult:
        """
        Investigate using causality graph

        Steps:
        1. Find root causes in time window
        2. Get causal chains for top root causes
        3. Calculate blast radius
        4. Detect cross-service failures
        """
        start_time = time.time()
        findings: List[AgentFinding] = []
        artifacts: List[AgentArtifact] = []

        try:
            tenant_id = scope['tenant_id']
            logger.info(f"GraphAgent investigating for tenant {tenant_id}")

            # Step 1: Find root causes
            root_causes_result = await self._call_tool("neo4j_find_root_causes", {
                "client_id": tenant_id,
                "time_range_hours": 24,
                "limit": 10
            })

            if not root_causes_result['success']:
                return AgentResult(
                    agent=self.capability.name,
                    findings=[],
                    success=False,
                    error=root_causes_result.get('error'),
                    latency_ms=int((time.time() - start_time) * 1000)
                )

            root_causes = root_causes_result['data']
            logger.info(f"Found {len(root_causes)} root causes")

            # Add root causes as findings
            for rc in root_causes[:5]:  # Top 5
                findings.append(AgentFinding(
                    kind="root_cause",
                    detail=rc,
                    confidence=0.85  # Base confidence from graph analysis
                ))

            # Step 2: Get causal chains for top root causes
            if root_causes:
                top_root_cause = root_causes[0]

                # Get causal chain from this root cause
                chain_result = await self._call_tool("neo4j_get_causal_chain", {
                    "event_id": top_root_cause['event_id'],
                    "client_id": tenant_id,
                    "max_hops": 3
                })

                if chain_result['success'] and chain_result['data']:
                    findings.append(AgentFinding(
                        kind="causal_chain",
                        detail={
                            "root_cause": top_root_cause,
                            "chain": chain_result['data']
                        },
                        confidence=0.90
                    ))

                # Step 3: Get blast radius
                blast_radius_result = await self._call_tool("neo4j_get_blast_radius", {
                    "root_event_id": top_root_cause['event_id'],
                    "client_id": tenant_id,
                    "limit": 50
                })

                if blast_radius_result['success']:
                    affected_count = blast_radius_result['affected_count']
                    findings.append(AgentFinding(
                        kind="blast_radius",
                        detail={
                            "root_cause": top_root_cause,
                            "affected_events": affected_count,
                            "sample_affected": blast_radius_result['data'][:10]
                        },
                        confidence=0.88
                    ))

            # Step 4: Detect cross-service failures
            cross_service_result = await self._call_tool("neo4j_get_cross_service_failures", {
                "client_id": tenant_id,
                "time_range_hours": 24,
                "limit": 20
            })

            if cross_service_result['success'] and cross_service_result['data']:
                findings.append(AgentFinding(
                    kind="cross_service_failure",
                    detail={
                        "count": cross_service_result['count'],
                        "failures": cross_service_result['data'][:5]  # Top 5
                    },
                    confidence=0.92  # High confidence for topology-based detection
                ))

            latency_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                agent=self.capability.name,
                findings=findings,
                artifacts=artifacts,
                cost={"llm_usd": 0.0, "api_usd": 0.0},  # No LLM used yet
                latency_ms=latency_ms,
                success=True
            )

        except Exception as e:
            logger.error(f"GraphAgent investigation failed: {e}", exc_info=True)
            latency_ms = int((time.time() - start_time) * 1000)

            return AgentResult(
                agent=self.capability.name,
                findings=findings,  # Return partial findings
                success=False,
                error=str(e),
                latency_ms=latency_ms
            )