"""
LLM Analyzer for GraphRAG-enhanced RCA
Uses GPT-5 (or GPT-4o fallback) to provide contextual analysis and recommendations
"""

import openai
from typing import List, Dict, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """
    LLM-based analyzer for root cause analysis
    Provides natural language explanations and recommendations
    Supports both GPT-5 (Responses API) and GPT-4o (Chat Completions API)
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5",  # GPT-5 (or "gpt-4o" for fallback)
        reasoning_effort: str = "medium",  # For GPT-5: minimal, low, medium, high
        verbosity: str = "medium"  # For GPT-5: low, medium, high
    ):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity

        # Check if using GPT-5 or fallback
        self.is_gpt5 = model.startswith("gpt-5")

        if self.is_gpt5:
            logger.info(f"Using GPT-5 with reasoning effort: {reasoning_effort}, verbosity: {verbosity}")
        else:
            logger.info(f"Using {model} (Chat Completions API)")

    async def analyze_failure(
        self,
        online_graph_summary: Dict[str, Any],
        matched_patterns: List[Dict[str, Any]],
        ranked_causes: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze failure using LLM with graph context

        Args:
            online_graph_summary: Summary of online FPG
            matched_patterns: List of matched historical patterns
            ranked_causes: List of ranked root causes
            context: Additional context (recent changes, metrics, etc.)

        Returns:
            Dict with analysis results
        """
        prompt = self._build_analysis_prompt(
            online_graph_summary,
            matched_patterns,
            ranked_causes,
            context
        )

        try:
            if self.is_gpt5:
                # Use GPT-5 Responses API
                # Add system instructions to the prompt itself
                full_prompt = "You are an expert SRE analyzing Kubernetes failures. Provide clear, actionable insights in JSON format.\n\n" + prompt

                response = self.client.responses.create(
                    model=self.model,
                    input=full_prompt,
                    reasoning={
                        "effort": self.reasoning_effort
                    },
                    text={
                        "verbosity": self.verbosity
                    }
                )

                # Parse output from GPT-5
                analysis_text = response.output_text
                # Try to parse as JSON
                try:
                    analysis = json.loads(analysis_text)
                except json.JSONDecodeError:
                    # If not JSON, wrap it
                    analysis = {
                        "root_cause_diagnosis": analysis_text,
                        "confidence_level": "medium",
                        "raw_output": True
                    }

            else:
                # Use GPT-4o Chat Completions API (fallback)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert SRE analyzing Kubernetes failures. Provide clear, actionable insights."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )

                analysis = json.loads(response.choices[0].message.content)

            return analysis

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {"error": str(e)}

    def _build_analysis_prompt(
        self,
        graph_summary: Dict,
        matched_patterns: List[Dict],
        ranked_causes: List[Dict],
        context: Optional[Dict]
    ) -> str:
        """Build comprehensive analysis prompt"""

        prompt_parts = [
            "# Root Cause Analysis Request",
            "",
            "## Current Failure",
            f"- Fault ID: {graph_summary.get('fault_id', 'unknown')}",
            f"- Event Count: {graph_summary.get('num_events', 0)}",
            f"- Affected Services: {', '.join(graph_summary.get('affected_services', []))}",
            f"- Time Span: {graph_summary.get('time_span_seconds', 0):.0f} seconds",
            f"- Event Types: {', '.join(graph_summary.get('event_types', []))}",
            "",
            "## Matched Historical Patterns",
        ]

        for i, pattern in enumerate(matched_patterns[:3], 1):
            prompt_parts.extend([
                f"### Pattern {i}: {pattern.get('pattern', {}).get('name', 'Unknown')}",
                f"- Root Cause Type: {pattern.get('pattern', {}).get('root_cause_type', 'unknown')}",
                f"- Similarity Score: {pattern.get('similarity_score', 0):.2%}",
                f"- Confidence: {pattern.get('confidence', 0):.2%}",
                f"- Resolution Steps: {'; '.join(pattern.get('pattern', {}).get('resolution_steps', []))}",
                ""
            ])

        prompt_parts.extend([
            "## Ranked Root Causes",
        ])

        for i, cause in enumerate(ranked_causes[:3], 1):
            prompt_parts.extend([
                f"### Candidate {i}:",
                f"- Event Type: {cause.get('event_type', 'unknown')}",
                f"- Service: {cause.get('service', 'unknown')}",
                f"- Confidence: {cause.get('confidence', 'unknown')}",
                f"- Explanation: {cause.get('explanation', 'No explanation')}",
                ""
            ])

        if context:
            prompt_parts.extend([
                "## Additional Context",
                ""
            ])
            if context.get('recent_deployments'):
                prompt_parts.append(f"- Recent Deployments: {context['recent_deployments']}")
            if context.get('config_changes'):
                prompt_parts.append(f"- Config Changes: {context['config_changes']}")
            if context.get('resource_metrics'):
                prompt_parts.append(f"- Resource Metrics: {context['resource_metrics']}")

        prompt_parts.extend([
            "",
            "## Analysis Required (Respond in VALID JSON format):",
            "Provide a comprehensive analysis with the following structure:",
            "{",
            '  "summary": "One-sentence summary of the root cause",',
            '  "root_cause_diagnosis": "Detailed explanation of the most likely root cause",',
            '  "confidence_level": "high/medium/low with percentage (e.g., high - 95%)",',
            '  "propagation_analysis": "How the failure propagated through the system",',
            '  "top_3_solutions": [',
            '    {',
            '      "solution": "Primary solution title",',
            '      "description": "Detailed explanation",',
            '      "probability_of_success": "95% - high confidence based on evidence",',
            '      "blast_radius": "Low - affects only api-gateway pods",',
            '      "estimated_downtime": "30 seconds per pod rolling restart",',
            '      "risk_level": "Low",',
            '      "impact_analysis": {',
            '        "affected_components": ["api-gateway", "load-balancer"],',
            '        "affected_users": "~100 concurrent users during restart",',
            '        "data_loss_risk": "None - stateless pods",',
            '        "rollback_difficulty": "Easy - just revert config"',
            '      },',
            '      "prerequisites": ["Check current memory usage", "Verify cluster capacity"],',
            '      "action_steps": ["kubectl set resources...", "kubectl rollout status..."],',
            '      "verification_steps": ["kubectl top pods", "Check error rate metrics"]',
            '    },',
            '    {',
            '      "solution": "Secondary solution title",',
            '      "description": "Alternative approach",',
            '      "probability_of_success": "80%",',
            '      "blast_radius": "Medium",',
            '      "estimated_downtime": "5 minutes",',
            '      "risk_level": "Medium",',
            '      "impact_analysis": {},',
            '      "prerequisites": [],',
            '      "action_steps": [],',
            '      "verification_steps": []',
            '    },',
            '    {',
            '      "solution": "Tertiary solution title",',
            '      "description": "Long-term fix",',
            '      "probability_of_success": "70%",',
            '      "blast_radius": "High - requires code deployment",',
            '      "estimated_downtime": "10-15 minutes",',
            '      "risk_level": "High",',
            '      "impact_analysis": {},',
            '      "prerequisites": [],',
            '      "action_steps": [],',
            '      "verification_steps": []',
            '    }',
            '  ],',
            '  "blast_radius_analysis": {',
            '    "immediate_impact": "api-gateway degraded, 30% requests failing",',
            '    "potential_cascade": "payment-service may timeout if not fixed within 10min",',
            '    "downstream_services": ["payment-service", "user-service"],',
            '    "upstream_services": ["load-balancer", "nginx-ingress"],',
            '    "user_impact_percentage": "25% of active users affected",',
            '    "data_integrity_risk": "None - no database writes affected"',
            '  },',
            '  "recommended_action": {',
            '    "priority": "P0-Critical",',
            '    "time_to_action": "Immediate - within 5 minutes",',
            '    "escalation_needed": false,',
            '    "approval_required": false,',
            '    "on_call_team": "platform-team"',
            '  },',
            '  "immediate_actions": ["Action 1", "Action 2", "Action 3"],',
            '  "investigation_steps": ["Step 1", "Step 2"],',
            '  "preventive_measures": ["Measure 1", "Measure 2"],',
            '  "estimated_resolution_time": "5-10 minutes",',
            '  "similar_incidents": "Reference if applicable"',
            "}",
            "",
            "IMPORTANT: Ensure the JSON is valid and properly formatted. Use actual quotes, not smart quotes."
        ])

        return "\n".join(prompt_parts)

    async def generate_runbook(
        self,
        root_cause_type: str,
        affected_services: List[str],
        resolution_steps: List[str]
    ) -> str:
        """
        Generate detailed runbook for this failure type

        Args:
            root_cause_type: Type of root cause
            affected_services: List of affected services
            resolution_steps: Known resolution steps

        Returns:
            Markdown formatted runbook
        """
        prompt = f"""
Generate a detailed runbook for resolving this Kubernetes failure:

Root Cause Type: {root_cause_type}
Affected Services: {', '.join(affected_services)}
Known Resolution Steps: {'; '.join(resolution_steps)}

Create a comprehensive runbook in Markdown format with:
1. Problem Description
2. Diagnosis Steps
3. Resolution Steps (with kubectl commands)
4. Verification Steps
5. Prevention Measures
6. Rollback Procedures (if needed)
"""

        try:
            if self.is_gpt5:
                # Use GPT-5 for runbook generation
                response = self.client.responses.create(
                    model=self.model,
                    input=prompt,
                    reasoning={"effort": "low"},  # Don't need deep reasoning for runbooks
                    text={"verbosity": "high"},  # Want detailed output
                    developer_message={
                        "role": "developer",
                        "content": "You are an expert SRE creating operational runbooks. Be detailed and practical."
                    }
                )
                return response.output_text

            else:
                # GPT-4o fallback
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are an expert SRE creating operational runbooks."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Runbook generation failed: {e}")
            return f"# Error\nFailed to generate runbook: {e}"
