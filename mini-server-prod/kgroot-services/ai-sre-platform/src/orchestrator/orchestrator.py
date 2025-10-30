"""Main AI RCA Orchestrator"""

from src.core.schemas import (
    IncidentScope,
    InvestigationResult,
    InvestigationSynthesis,
    AgentResult
)
from src.core.tool_registry import tool_registry
from src.orchestrator.router import RuleRouter
from src.agents import GraphAgent
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import time
import uuid
import asyncio
import json
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class AIRCAOrchestrator:
    """
    Main orchestrator for AI-powered RCA

    Coordinates:
    - Rule-based routing
    - Agent execution
    - GPT-5 synthesis
    """

    def __init__(
        self,
        neo4j_service,
        openai_api_key: str,
        model: str = "gpt-5"
    ):
        """
        Initialize orchestrator

        Args:
            neo4j_service: Neo4j service instance
            openai_api_key: OpenAI API key for GPT-5
            model: Model to use (gpt-5, gpt-4o, etc.)
        """
        self.neo4j = neo4j_service
        self.router = RuleRouter()
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model

        # Initialize tools
        from src.tools.graph_tools import (
            Neo4jRootCauseTool,
            Neo4jCausalChainTool,
            Neo4jBlastRadiusTool,
            Neo4jCrossServiceFailuresTool
        )

        Neo4jRootCauseTool(neo4j_service)
        Neo4jCausalChainTool(neo4j_service)
        Neo4jBlastRadiusTool(neo4j_service)
        Neo4jCrossServiceFailuresTool(neo4j_service)

        # Initialize agents
        graph_tools = tool_registry.get_tools_by_category('graph')
        self.graph_agent = GraphAgent(tools=graph_tools)

        self.agents = {
            'GraphAgent': self.graph_agent
        }

        logger.info(f"✓ AIRCAOrchestrator initialized with model={model}")
        logger.info(f"✓ Registered agents: {list(self.agents.keys())}")
        logger.info(f"✓ Available tools: {tool_registry.get_tool_names()}")

    async def investigate(
        self,
        query: str,
        tenant_id: str,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
        service: Optional[str] = None,
        namespace: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> InvestigationResult:
        """
        Perform complete AI-powered RCA investigation

        Args:
            query: Natural language query
            tenant_id: Tenant/client ID
            time_window_start: Start of time window
            time_window_end: End of time window
            service: Optional service name
            namespace: Optional namespace
            event_type: Optional event type for routing

        Returns:
            Complete investigation result
        """
        incident_id = f"inc-{uuid.uuid4().hex[:8]}"
        start_time = time.time()

        logger.info(f"=== Starting investigation {incident_id} for tenant {tenant_id} ===")
        logger.info(f"Query: {query}")

        try:
            # Step 1: Create incident scope
            if not time_window_end:
                time_window_end = datetime.utcnow()
            if not time_window_start:
                time_window_start = datetime.utcnow() - timedelta(hours=24)

            scope = IncidentScope(
                tenant_id=tenant_id,
                service=service,
                namespace=namespace,
                time_window_start=time_window_start,
                time_window_end=time_window_end
            )

            # Step 2: Route to agents (rule-based)
            context = {
                'event_type': event_type,
                'service': service,
                'namespace': namespace
            }
            router_decision = self.router.route(scope, context)
            logger.info(f"Router decision: {router_decision.agents} (confidence={router_decision.confidence}, llm_used={router_decision.llm_used})")

            # Step 3: Execute agents
            agent_results = await self._execute_agents(
                router_decision.agents,
                query,
                scope
            )

            # Step 4: Synthesize findings using GPT-5
            synthesis = await self._synthesize_findings(
                query=query,
                scope=scope,
                agent_results=agent_results
            )

            # Calculate total cost and latency
            total_cost = sum(
                result.total_cost for result in agent_results.values()
            )
            total_latency_ms = int((time.time() - start_time) * 1000)

            result = InvestigationResult(
                incident_id=incident_id,
                tenant_id=tenant_id,
                query=query,
                scope=scope,
                router_decision=router_decision,
                agent_results=agent_results,
                synthesis=synthesis,
                total_cost_usd=total_cost,
                total_latency_ms=total_latency_ms
            )

            logger.info(f"=== Investigation {incident_id} complete in {total_latency_ms}ms, cost=${total_cost:.4f} ===")
            logger.info(f"Confidence: {synthesis.confidence:.2f}")

            return result

        except Exception as e:
            logger.error(f"Investigation {incident_id} failed: {e}", exc_info=True)
            raise

    async def _execute_agents(
        self,
        agent_names: list[str],
        query: str,
        scope: IncidentScope
    ) -> Dict[str, AgentResult]:
        """Execute selected agents in parallel"""

        tasks = []
        for agent_name in agent_names:
            agent = self.agents.get(agent_name)
            if agent:
                logger.info(f"Executing {agent_name}...")
                tasks.append(agent.investigate(query, scope.dict()))
            else:
                logger.warning(f"Agent {agent_name} not available")

        if not tasks:
            logger.warning("No agents available to execute")
            return {}

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        agent_results = {}
        for agent_name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                logger.error(f"Agent {agent_name} failed: {result}")
                agent_results[agent_name] = AgentResult(
                    agent=agent_name,
                    findings=[],
                    success=False,
                    error=str(result),
                    latency_ms=0
                )
            else:
                agent_results[agent_name] = result

        return agent_results

    async def _synthesize_findings(
        self,
        query: str,
        scope: IncidentScope,
        agent_results: Dict[str, AgentResult]
    ) -> InvestigationSynthesis:
        """
        Synthesize agent findings using GPT-5

        Uses GPT-5 (or GPT-4o) to analyze all agent findings and produce:
        - Summary
        - Root causes
        - Blast radius
        - Immediate actions
        """
        start_time = time.time()

        # Prepare findings for GPT-5
        findings_text = self._format_findings_for_llm(agent_results)

        system_prompt = """You are an expert Site Reliability Engineer (SRE) performing root cause analysis.

Analyze the findings from multiple specialized agents and provide a comprehensive RCA report.

Focus on:
1. Identifying the PRIMARY root cause (not just symptoms)
2. Explaining the causal chain (how failure propagated)
3. Quantifying blast radius (impact scope)
4. Providing actionable remediation steps

Be concise but thorough. Use technical language. Base conclusions ONLY on provided data."""

        user_prompt = f"""Investigation Query: {query}

Tenant: {scope.tenant_id}
Service: {scope.service or 'All'}
Namespace: {scope.namespace or 'All'}
Time Window: {scope.time_window_start.isoformat()} to {scope.time_window_end.isoformat()}

=== AGENT FINDINGS ===

{findings_text}

=== REQUIRED OUTPUT ===

Provide a JSON response with:
{{
  "summary": "2-3 sentence executive summary",
  "root_causes": [
    {{
      "event_id": "...",
      "reason": "...",
      "resource": "...",
      "explanation": "Why this is the root cause",
      "confidence": 0.0-1.0
    }}
  ],
  "contributing_factors": ["factor 1", "factor 2", ...],
  "blast_radius": {{
    "affected_services": [...],
    "affected_pods": count,
    "affected_namespaces": [...]
  }},
  "immediate_actions": [
    "1. First action",
    "2. Second action",
    ...
  ],
  "confidence": 0.0-1.0,
  "confidence_breakdown": {{
    "graph_analysis": 0.0-1.0,
    "temporal_correlation": 0.0-1.0,
    "domain_pattern_match": 0.0-1.0
  }}
}}"""

        try:
            logger.info(f"Calling {self.model} for synthesis...")

            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,  # Lower temperature for more consistent output
                max_tokens=2000
            )

            synthesis_json = json.loads(response.choices[0].message.content)

            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"{self.model} synthesis completed in {latency_ms}ms")

            return InvestigationSynthesis(**synthesis_json)

        except Exception as e:
            logger.error(f"GPT-5 synthesis failed: {e}", exc_info=True)

            # Fallback: Basic synthesis from agent findings
            return self._fallback_synthesis(agent_results)

    def _format_findings_for_llm(self, agent_results: Dict[str, AgentResult]) -> str:
        """Format agent findings for LLM consumption"""
        sections = []

        for agent_name, result in agent_results.items():
            if not result.success:
                sections.append(f"**{agent_name}**: Failed - {result.error}")
                continue

            section = [f"**{agent_name}**"]
            section.append(f"- Latency: {result.latency_ms}ms")
            section.append(f"- Findings: {len(result.findings)}")

            for finding in result.findings:
                section.append(f"\n**Finding ({finding.kind})**:")
                section.append(f"- Confidence: {finding.confidence:.2f}")

                # Format detail based on kind
                if finding.kind == "root_cause":
                    detail = finding.detail
                    section.append(f"- Event: {detail.get('reason')} on {detail.get('resource_kind')}/{detail.get('resource_name')}")
                    section.append(f"- Namespace: {detail.get('namespace')}")
                    section.append(f"- Blast Radius: {detail.get('blast_radius')} events")

                elif finding.kind == "causal_chain":
                    chain = finding.detail.get('chain', [])
                    section.append(f"- Chain length: {len(chain)} steps")
                    for step in chain[:3]:  # First 3 steps
                        section.append(f"  {step['step']}. {step['reason']} → {step.get('resource_kind')}/{step.get('resource_name')}")

                elif finding.kind == "blast_radius":
                    section.append(f"- Affected events: {finding.detail.get('affected_events', 0)}")

                elif finding.kind == "cross_service_failure":
                    section.append(f"- Cross-service failures detected: {finding.detail.get('count', 0)}")

            sections.append("\n".join(section))

        return "\n\n".join(sections)

    def _fallback_synthesis(self, agent_results: Dict[str, AgentResult]) -> InvestigationSynthesis:
        """Fallback synthesis without LLM (if GPT-5 fails)"""
        logger.warning("Using fallback synthesis (no LLM)")

        # Extract root causes from GraphAgent
        root_causes = []
        for result in agent_results.values():
            for finding in result.findings:
                if finding.kind == "root_cause":
                    root_causes.append({
                        "reason": finding.detail.get('reason'),
                        "resource": f"{finding.detail.get('resource_kind')}/{finding.detail.get('resource_name')}",
                        "explanation": "Identified by causality graph analysis",
                        "confidence": finding.confidence
                    })

        summary = f"Found {len(root_causes)} potential root cause(s) via causality graph analysis."

        return InvestigationSynthesis(
            summary=summary,
            root_causes=root_causes,
            contributing_factors=[],
            blast_radius={},
            immediate_actions=["Review identified root causes", "Check recent deployments"],
            confidence=0.70,
            confidence_breakdown={
                "graph_analysis": 0.85,
                "temporal_correlation": 0.0,
                "domain_pattern_match": 0.0
            }
        )


# Import timedelta
from datetime import timedelta
