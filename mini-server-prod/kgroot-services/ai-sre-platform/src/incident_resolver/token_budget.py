"""
Token Budget Manager - Prevents runaway token usage and infinite loops
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token usage tracking"""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, prompt: int, completion: int, cost: float = 0.0):
        """Add token usage"""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += (prompt + completion)
        self.cost_usd += cost

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class TokenBudgetManager:
    """
    Manages token budget to prevent runaway costs

    Features:
    - Per-incident token limits
    - Per-agent token limits
    - Cost tracking
    - Loop detection
    - Budget enforcement
    """

    # Default limits
    DEFAULT_INCIDENT_LIMIT = 100_000  # 100k tokens per incident
    DEFAULT_AGENT_LIMIT = 50_000      # 50k tokens per agent

    # Cost per 1M tokens (approximate, update based on actual pricing)
    COST_PER_MILLION = {
        "gpt-5": 5.00,          # $5 per 1M tokens (estimate)
        "gpt-4": 3.00,          # $3 per 1M tokens (estimate)
        "sonnet": 3.00,         # Claude Sonnet
        "opus": 15.00,          # Claude Opus
        "haiku": 0.25           # Claude Haiku
    }

    def __init__(
        self,
        incident_limit: int = DEFAULT_INCIDENT_LIMIT,
        agent_limit: int = DEFAULT_AGENT_LIMIT
    ):
        """
        Args:
            incident_limit: Maximum tokens per incident resolution
            agent_limit: Maximum tokens per agent execution
        """
        self.incident_limit = incident_limit
        self.agent_limit = agent_limit

        # Tracking
        self.incident_usage: Dict[str, TokenUsage] = {}
        self.agent_usage: Dict[str, Dict[str, TokenUsage]] = {}  # {incident_id: {agent_id: usage}}
        self.incident_metadata: Dict[str, Dict] = {}

    def create_incident_budget(
        self,
        incident_id: str,
        custom_limit: Optional[int] = None
    ):
        """
        Create budget for a new incident

        Args:
            incident_id: Incident resolution ID
            custom_limit: Custom token limit (overrides default)
        """
        limit = custom_limit or self.incident_limit

        self.incident_usage[incident_id] = TokenUsage()
        self.agent_usage[incident_id] = {}
        self.incident_metadata[incident_id] = {
            "limit": limit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "agent_count": 0,
            "iteration_count": 0
        }

        logger.info(f"Created token budget for incident {incident_id}: {limit:,} tokens")

    def check_budget(
        self,
        incident_id: str,
        tokens_needed: int
    ) -> tuple[bool, str]:
        """
        Check if budget allows the requested tokens

        Args:
            incident_id: Incident resolution ID
            tokens_needed: Number of tokens needed

        Returns:
            (allowed: bool, reason: str)
        """
        if incident_id not in self.incident_usage:
            return False, "Incident budget not initialized"

        usage = self.incident_usage[incident_id]
        metadata = self.incident_metadata[incident_id]
        limit = metadata["limit"]

        remaining = limit - usage.total_tokens
        if tokens_needed > remaining:
            return False, f"Budget exceeded: {tokens_needed:,} tokens needed, {remaining:,} remaining"

        return True, "Budget available"

    def record_usage(
        self,
        incident_id: str,
        agent_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "gpt-5"
    ) -> TokenUsage:
        """
        Record token usage for an agent execution

        Args:
            incident_id: Incident resolution ID
            agent_id: Agent identifier
            prompt_tokens: Prompt tokens used
            completion_tokens: Completion tokens used
            model: Model name for cost calculation

        Returns:
            Updated TokenUsage for the incident
        """
        if incident_id not in self.incident_usage:
            logger.warning(f"Recording usage for uninitialized incident {incident_id}")
            self.create_incident_budget(incident_id)

        # Calculate cost
        total = prompt_tokens + completion_tokens
        cost_per_token = self.COST_PER_MILLION.get(model, 5.0) / 1_000_000
        cost = total * cost_per_token

        # Update incident total
        self.incident_usage[incident_id].add(prompt_tokens, completion_tokens, cost)

        # Update agent-specific usage
        if agent_id not in self.agent_usage[incident_id]:
            self.agent_usage[incident_id][agent_id] = TokenUsage()
            self.incident_metadata[incident_id]["agent_count"] += 1

        self.agent_usage[incident_id][agent_id].add(prompt_tokens, completion_tokens, cost)

        # Log usage
        incident_total = self.incident_usage[incident_id].total_tokens
        incident_limit = self.incident_metadata[incident_id]["limit"]
        percent_used = (incident_total / incident_limit) * 100

        logger.info(
            f"Token usage: incident={incident_id}, agent={agent_id}, "
            f"tokens={total:,} (prompt={prompt_tokens:,}, completion={completion_tokens:,}), "
            f"cost=${cost:.4f}, incident_total={incident_total:,}/{incident_limit:,} ({percent_used:.1f}%)"
        )

        # Warn if approaching limit
        if percent_used >= 80:
            logger.warning(f"Incident {incident_id} approaching token limit: {percent_used:.1f}% used")

        return self.incident_usage[incident_id]

    def increment_iteration(self, incident_id: str) -> int:
        """
        Increment iteration counter for loop detection

        Args:
            incident_id: Incident resolution ID

        Returns:
            New iteration count
        """
        if incident_id not in self.incident_metadata:
            logger.warning(f"Incrementing iteration for uninitialized incident {incident_id}")
            self.create_incident_budget(incident_id)

        self.incident_metadata[incident_id]["iteration_count"] += 1
        count = self.incident_metadata[incident_id]["iteration_count"]

        logger.debug(f"Incident {incident_id} iteration: {count}")

        return count

    def check_loop_detection(
        self,
        incident_id: str,
        max_iterations: int = 10
    ) -> tuple[bool, str]:
        """
        Check for potential infinite loops

        Args:
            incident_id: Incident resolution ID
            max_iterations: Maximum allowed iterations

        Returns:
            (safe: bool, reason: str)
        """
        if incident_id not in self.incident_metadata:
            return True, "No iterations yet"

        count = self.incident_metadata[incident_id]["iteration_count"]

        if count >= max_iterations:
            return False, f"Maximum iterations exceeded: {count}/{max_iterations}"

        if count >= max_iterations * 0.8:
            logger.warning(f"Incident {incident_id} approaching iteration limit: {count}/{max_iterations}")

        return True, f"Iterations within limit: {count}/{max_iterations}"

    def get_incident_usage(self, incident_id: str) -> Optional[Dict]:
        """Get usage summary for an incident"""
        if incident_id not in self.incident_usage:
            return None

        usage = self.incident_usage[incident_id]
        metadata = self.incident_metadata[incident_id]
        limit = metadata["limit"]

        return {
            "incident_id": incident_id,
            "total_tokens": usage.total_tokens,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": usage.cost_usd,
            "limit": limit,
            "remaining": limit - usage.total_tokens,
            "percent_used": (usage.total_tokens / limit) * 100,
            "agent_count": metadata["agent_count"],
            "iteration_count": metadata["iteration_count"],
            "created_at": metadata["created_at"]
        }

    def get_agent_usage(
        self,
        incident_id: str,
        agent_id: str
    ) -> Optional[Dict]:
        """Get usage summary for a specific agent"""
        if incident_id not in self.agent_usage:
            return None

        if agent_id not in self.agent_usage[incident_id]:
            return None

        usage = self.agent_usage[incident_id][agent_id]

        return {
            "incident_id": incident_id,
            "agent_id": agent_id,
            "total_tokens": usage.total_tokens,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": usage.cost_usd
        }

    def get_all_agent_usage(self, incident_id: str) -> Dict[str, Dict]:
        """Get usage for all agents in an incident"""
        if incident_id not in self.agent_usage:
            return {}

        result = {}
        for agent_id, usage in self.agent_usage[incident_id].items():
            result[agent_id] = {
                "total_tokens": usage.total_tokens,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost_usd": usage.cost_usd
            }

        return result

    def get_budget_status(self, incident_id: str) -> Dict:
        """
        Get comprehensive budget status

        Returns status for UI display
        """
        usage = self.get_incident_usage(incident_id)
        if not usage:
            return {
                "status": "not_found",
                "incident_id": incident_id
            }

        percent_used = usage["percent_used"]

        # Determine status
        if percent_used >= 100:
            status = "exceeded"
        elif percent_used >= 90:
            status = "critical"
        elif percent_used >= 80:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            "incident_id": incident_id,
            "usage": usage,
            "agents": self.get_all_agent_usage(incident_id)
        }

    def cleanup_incident(self, incident_id: str):
        """Clean up tracking data for completed incident"""
        if incident_id in self.incident_usage:
            del self.incident_usage[incident_id]

        if incident_id in self.agent_usage:
            del self.agent_usage[incident_id]

        if incident_id in self.incident_metadata:
            del self.incident_metadata[incident_id]

        logger.info(f"Cleaned up token tracking for incident {incident_id}")
