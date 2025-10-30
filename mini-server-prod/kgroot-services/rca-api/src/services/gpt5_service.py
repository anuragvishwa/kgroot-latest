"""
GPT-5 service for intelligent RCA analysis
"""
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
import json
import logging
import asyncio

from ..config import settings

logger = logging.getLogger(__name__)


class GPT5Service:
    """Service for GPT-5 powered RCA analysis"""

    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None

    def initialize(self):
        """Initialize OpenAI client"""
        try:
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=60.0  # 60 second timeout to prevent hanging
            )
            logger.info("GPT-5 service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GPT-5 service: {e}")
            raise

    async def analyze_rca(
        self,
        query: str,
        root_causes: List[Dict[str, Any]],
        causal_chains: List[List[Dict[str, Any]]],
        blast_radius: List[Dict[str, Any]],
        cross_service_failures: List[Dict[str, Any]],
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        include_remediation: bool = True
    ) -> Dict[str, Any]:
        """
        Use GPT-5 to analyze RCA data and provide intelligent insights
        """
        # Build context for GPT-5
        context = self._build_context(
            root_causes,
            causal_chains,
            blast_radius,
            cross_service_failures
        )

        # Create system prompt
        system_prompt = self._create_system_prompt()

        # Create user prompt
        user_prompt = self._create_user_prompt(
            query,
            context,
            include_remediation
        )

        try:
            # Try GPT-5 Responses API first
            if hasattr(self.client, 'responses'):
                response = await self.client.responses.create(
                    model=settings.openai_model,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    reasoning={"effort": reasoning_effort},
                    text={"verbosity": verbosity}
                )
                output_text = response.output_text
                reasoning_tokens = getattr(response.usage, 'reasoning_tokens', None)
                total_tokens = getattr(response.usage, 'total_tokens', None)
            else:
                # Fallback to Chat Completions API
                logger.warning("Responses API not available, using Chat Completions API")
                response = await self.client.chat.completions.create(
                    model="gpt-4-turbo" if "gpt-5" in settings.openai_model else settings.openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )
                output_text = response.choices[0].message.content
                reasoning_tokens = None
                total_tokens = response.usage.total_tokens

            # Extract summary and remediation
            result = self._parse_response(output_text)

            # Add metadata
            result["reasoning_tokens"] = reasoning_tokens
            result["total_tokens"] = total_tokens

            return result

        except Exception as e:
            logger.error(f"GPT-5 analysis failed: {e}")
            # Return fallback response
            return {
                "summary": f"Analysis failed: {str(e)}",
                "remediation_steps": [],
                "confidence_assessment": "low",
                "error": str(e)
            }

    async def chat_assistant(
        self,
        message: str,
        context_data: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_effort: str = "low"
    ) -> Dict[str, Any]:
        """
        Conversational assistant for RCA questions
        """
        system_prompt = """You are an expert Kubernetes SRE assistant specializing in root cause analysis.
You help users understand failures, troubleshoot issues, and provide actionable remediation steps.
Be concise, accurate, and helpful. Focus on practical solutions."""

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add context if provided
        if context_data:
            context_str = f"\nContext:\n{json.dumps(context_data, indent=2, default=str)}"
            message = message + context_str

        messages.append({"role": "user", "content": message})

        try:
            response = await self.client.responses.create(
                model=settings.openai_model,
                input=messages,
                reasoning={"effort": reasoning_effort},
                text={"verbosity": "medium"}
            )

            return {
                "message": response.output_text,
                "reasoning_summary": getattr(response, 'reasoning_summary', None),
                "confidence": self._estimate_confidence(response.output_text)
            }

        except Exception as e:
            logger.error(f"Chat assistant failed: {e}")
            return {
                "message": f"I encountered an error: {str(e)}",
                "confidence": 0.0,
                "error": str(e)
            }

    async def generate_slack_alert(
        self,
        incident_data: Dict[str, Any],
        reasoning_effort: str = "minimal"
    ) -> str:
        """
        Generate concise Slack alert message
        """
        system_prompt = """You are a concise alert generator. Create brief, actionable Slack alerts.
Format:
- One line summary
- Key details (bullet points, max 3)
- Severity indicator
Keep it under 200 characters for the summary."""

        user_prompt = f"""Generate a Slack alert for this incident:
{json.dumps(incident_data, indent=2, default=str)}"""

        try:
            response = await self.client.responses.create(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                reasoning={"effort": reasoning_effort},
                text={"verbosity": "low"}
            )

            return response.output_text

        except Exception as e:
            logger.error(f"Slack alert generation failed: {e}")
            # Fallback to simple template
            return f"🚨 Incident: {incident_data.get('title', 'Unknown issue')}\nAffected: {', '.join(incident_data.get('affected_resources', [])[:3])}"

    async def suggest_runbook(
        self,
        failure_pattern: str,
        resource_type: str
    ) -> Dict[str, Any]:
        """
        Suggest runbook steps for common failure patterns
        """
        system_prompt = """You are a runbook generator for Kubernetes issues.
Provide step-by-step troubleshooting and remediation procedures.
Include kubectl commands and verification steps."""

        user_prompt = f"""Create a runbook for:
Failure: {failure_pattern}
Resource Type: {resource_type}

Include:
1. Investigation steps
2. Common causes
3. Remediation commands
4. Verification steps"""

        try:
            response = await self.client.responses.create(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                reasoning={"effort": "medium"},
                text={"verbosity": "high"}
            )

            return {
                "runbook": response.output_text,
                "pattern": failure_pattern,
                "resource_type": resource_type
            }

        except Exception as e:
            logger.error(f"Runbook generation failed: {e}")
            return {
                "runbook": "Failed to generate runbook",
                "error": str(e)
            }

    def _build_context(
        self,
        root_causes: List[Dict[str, Any]],
        causal_chains: List[List[Dict[str, Any]]],
        blast_radius: List[Dict[str, Any]],
        cross_service_failures: List[Dict[str, Any]]
    ) -> str:
        """Build formatted context for GPT-5"""
        context_parts = []

        # Root causes
        if root_causes:
            context_parts.append("## Root Causes")
            for rc in root_causes[:5]:
                context_parts.append(
                    f"- {rc.get('reason')} on {rc.get('resource_kind')}/{rc.get('resource_name')} "
                    f"in {rc.get('namespace')} at {rc.get('timestamp')} "
                    f"(caused {rc.get('blast_radius', 0)} downstream events)"
                )

        # Causal chains
        if causal_chains:
            context_parts.append("\n## Causal Chains")
            for i, chain in enumerate(causal_chains[:3], 1):
                context_parts.append(f"\nChain {i}:")
                for step in chain:
                    context_parts.append(
                        f"  {step.get('step')}. {step.get('reason')} on "
                        f"{step.get('resource_kind')}/{step.get('resource_name')} "
                        f"(confidence: {step.get('confidence_to_next', 'N/A')})"
                    )

        # Blast radius
        if blast_radius:
            context_parts.append(f"\n## Blast Radius ({len(blast_radius)} affected events)")
            for item in blast_radius[:10]:
                context_parts.append(
                    f"- {item.get('reason')} on {item.get('resource_kind')}/{item.get('resource_name')} "
                    f"({item.get('distance_from_root')} hops from root)"
                )

        # Cross-service failures
        if cross_service_failures:
            context_parts.append(f"\n## Cross-Service Failures ({len(cross_service_failures)} detected)")
            for csf in cross_service_failures[:5]:
                context_parts.append(
                    f"- {csf.get('cause_reason')} on {csf.get('cause_resource')} → "
                    f"{csf.get('effect_reason')} on {csf.get('effect_resource')} "
                    f"(confidence: {csf.get('confidence')})"
                )

        return "\n".join(context_parts)

    def _create_system_prompt(self) -> str:
        """Create system prompt for RCA analysis"""
        return """You are an expert Site Reliability Engineer specializing in Kubernetes root cause analysis.

Your role is to:
1. Analyze failure patterns and causal relationships
2. Identify true root causes vs symptoms
3. Explain the failure cascade in clear terms
4. Provide actionable remediation steps
5. Assess confidence in your analysis

Guidelines:
- Be precise and technical but clear
- Distinguish between correlation and causation
- Consider both immediate causes and systemic issues
- Prioritize fixes by impact and ease
- Acknowledge uncertainty when appropriate

Focus on practical, actionable insights that help SREs resolve incidents quickly."""

    def _create_user_prompt(
        self,
        query: str,
        context: str,
        include_remediation: bool
    ) -> str:
        """Create user prompt with context"""
        prompt = f"""User Question: {query}

## Analysis Data:
{context}

Please provide:
1. **Summary**: Clear explanation of what happened and why
2. **Root Cause**: The actual root cause(s) vs symptoms
3. **Impact Assessment**: Scope and severity of the failure"""

        if include_remediation:
            prompt += """
4. **Remediation Steps**: Specific actions to fix (with kubectl commands if applicable)
5. **Prevention**: How to prevent this in the future"""

        prompt += """

**Confidence Assessment**: Rate your confidence in this analysis (high/medium/low) and explain why."""

        return prompt

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse GPT-5 response into structured format"""
        # Simple parsing - extract sections
        result = {
            "summary": "",
            "remediation_steps": [],
            "confidence_assessment": "medium"
        }

        lines = response_text.split('\n')
        current_section = None
        remediation_lines = []

        for line in lines:
            line_lower = line.lower().strip()

            # Detect sections
            if 'summary' in line_lower or 'explanation' in line_lower:
                current_section = "summary"
            elif 'remediation' in line_lower or 'fix' in line_lower:
                current_section = "remediation"
            elif 'confidence' in line_lower:
                current_section = "confidence"
                # Extract confidence level
                if 'high' in line_lower:
                    result["confidence_assessment"] = "high"
                elif 'low' in line_lower:
                    result["confidence_assessment"] = "low"
                else:
                    result["confidence_assessment"] = "medium"
            elif current_section == "summary" and line.strip():
                result["summary"] += line + "\n"
            elif current_section == "remediation" and line.strip():
                # Extract numbered steps or bullet points
                if line.strip().startswith(('-', '*', '•')) or line.strip()[0].isdigit():
                    remediation_lines.append(line.strip().lstrip('-*•0123456789. '))

        result["summary"] = result["summary"].strip()
        result["remediation_steps"] = remediation_lines if remediation_lines else ["Review the analysis above"]

        # If summary is empty, use first few lines
        if not result["summary"]:
            result["summary"] = "\n".join(lines[:10])

        return result

    def _estimate_confidence(self, response_text: str) -> float:
        """Estimate confidence from response"""
        text_lower = response_text.lower()

        if any(word in text_lower for word in ['high confidence', 'very confident', 'certain']):
            return 0.9
        elif any(word in text_lower for word in ['low confidence', 'uncertain', 'unclear']):
            return 0.3
        elif any(word in text_lower for word in ['medium confidence', 'fairly confident', 'likely']):
            return 0.6
        else:
            return 0.5


# Global GPT-5 service instance
gpt5_service = GPT5Service()
