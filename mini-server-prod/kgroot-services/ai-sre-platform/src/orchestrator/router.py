"""Rule-based router for agent selection"""

from src.core.schemas import RouterDecision, IncidentScope
from typing import Dict, Any, List, Callable
import logging

logger = logging.getLogger(__name__)


class RuleRouter:
    """
    Rule-based router for deterministic agent selection

    Handles 60-70% of cases without LLM, saving cost and latency
    """

    def __init__(self):
        # Event-type patterns (Layer 1 - covers 60-70%)
        self.event_patterns = {
            # K8s resource exhaustion
            'OOMKilled': ['GraphAgent'],
            'Evicted': ['GraphAgent'],
            'MemoryPressure': ['GraphAgent'],
            'DiskPressure': ['GraphAgent'],

            # K8s image/registry issues
            'ImagePullBackOff': ['GraphAgent'],
            'ErrImagePull': ['GraphAgent'],
            'InvalidImageName': ['GraphAgent'],

            # K8s scheduling issues
            'FailedScheduling': ['GraphAgent'],
            'Unschedulable': ['GraphAgent'],

            # K8s health checks
            'Unhealthy': ['GraphAgent'],
            'LivenessProbe': ['GraphAgent'],
            'ReadinessProbe': ['GraphAgent'],

            # K8s crashes
            'CrashLoopBackOff': ['GraphAgent'],
            'Error': ['GraphAgent'],
            'BackOff': ['GraphAgent'],

            # K8s networking
            'NetworkNotReady': ['GraphAgent'],
            'FailedCreatePodSandBox': ['GraphAgent'],

            # K8s volumes
            'FailedMount': ['GraphAgent'],
            'VolumeFailure': ['GraphAgent'],
        }

        logger.info(f"Initialized RuleRouter with {len(self.event_patterns)} event patterns")

    def route(self, scope: IncidentScope, context: Dict[str, Any] = None) -> RouterDecision:
        """
        Route investigation to appropriate agents based on rules

        Args:
            scope: Incident scope
            context: Additional context (event_type, service, etc.)

        Returns:
            RouterDecision with selected agents
        """
        context = context or {}

        # Layer 1: Event-type matching (fastest, most common)
        event_type = context.get('event_type')
        if event_type and event_type in self.event_patterns:
            agents = self.event_patterns[event_type]
            logger.info(f"Rule matched event_type '{event_type}' → agents: {agents}")

            return RouterDecision(
                agents=agents,
                confidence=0.95,
                reasoning=f"Direct event-type match: {event_type}",
                llm_used=False,
                parallel_execution=True
            )

        # Layer 2: Namespace-based patterns
        namespace = scope.namespace
        if namespace:
            # Production namespaces get priority
            if namespace in ['prod', 'production']:
                logger.info(f"Production namespace detected: {namespace}")
                # Always check graph for prod issues
                return RouterDecision(
                    agents=['GraphAgent'],
                    confidence=0.85,
                    reasoning=f"Production namespace: {namespace}",
                    llm_used=False,
                    parallel_execution=True
                )

        # Layer 3: Fallback - use GraphAgent (our strongest agent)
        logger.info("No specific rule matched, using default GraphAgent")
        return RouterDecision(
            agents=['GraphAgent'],
            confidence=0.70,
            reasoning="Default fallback - graph analysis",
            llm_used=False,
            parallel_execution=True
        )

    def add_pattern(self, event_type: str, agents: List[str]):
        """Add a new event pattern"""
        self.event_patterns[event_type] = agents
        logger.info(f"Added pattern: {event_type} → {agents}")

    def get_pattern_coverage(self) -> Dict[str, Any]:
        """Get statistics about pattern coverage"""
        return {
            "total_patterns": len(self.event_patterns),
            "patterns_by_category": self._categorize_patterns()
        }

    def _categorize_patterns(self) -> Dict[str, int]:
        """Categorize patterns by type"""
        categories = {
            "resource_exhaustion": 0,
            "image_registry": 0,
            "scheduling": 0,
            "health_checks": 0,
            "crashes": 0,
            "networking": 0,
            "volumes": 0,
            "other": 0
        }

        resource_exhaustion = ['OOMKilled', 'Evicted', 'MemoryPressure', 'DiskPressure']
        image_registry = ['ImagePullBackOff', 'ErrImagePull', 'InvalidImageName']
        scheduling = ['FailedScheduling', 'Unschedulable']
        health_checks = ['Unhealthy', 'LivenessProbe', 'ReadinessProbe']
        crashes = ['CrashLoopBackOff', 'Error', 'BackOff']
        networking = ['NetworkNotReady', 'FailedCreatePodSandBox']
        volumes = ['FailedMount', 'VolumeFailure']

        for event_type in self.event_patterns.keys():
            if event_type in resource_exhaustion:
                categories["resource_exhaustion"] += 1
            elif event_type in image_registry:
                categories["image_registry"] += 1
            elif event_type in scheduling:
                categories["scheduling"] += 1
            elif event_type in health_checks:
                categories["health_checks"] += 1
            elif event_type in crashes:
                categories["crashes"] += 1
            elif event_type in networking:
                categories["networking"] += 1
            elif event_type in volumes:
                categories["volumes"] += 1
            else:
                categories["other"] += 1

        return categories
