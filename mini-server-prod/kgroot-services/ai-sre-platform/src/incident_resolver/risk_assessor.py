"""
Risk Assessor - Classifies remediation actions by risk level
"""

import logging
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk levels for remediation actions"""
    LOW = "LOW"           # Read-only, safe operations
    MEDIUM = "MEDIUM"     # Pod restarts, config changes
    HIGH = "HIGH"         # Scaling, resource modifications
    CRITICAL = "CRITICAL" # Deletions, cluster-wide changes


@dataclass
class RiskAssessment:
    """Risk assessment result"""
    level: RiskLevel
    requires_approval: bool
    risk_factors: List[str]
    mitigation_steps: List[str]
    estimated_impact: str
    rollback_complexity: str  # "simple" | "moderate" | "complex"


class RiskAssessor:
    """
    Assesses risk level of remediation actions

    Risk Classification Rules:
    - LOW: kubectl get, describe, logs (read-only)
    - MEDIUM: pod restart, single resource edits
    - HIGH: scaling operations, multi-resource changes
    - CRITICAL: deletions, namespace operations, cluster config
    """

    # Action patterns and their base risk levels
    ACTION_RISK_MAP = {
        # LOW risk - read-only operations
        "kubectl get": RiskLevel.LOW,
        "kubectl describe": RiskLevel.LOW,
        "kubectl logs": RiskLevel.LOW,
        "kubectl top": RiskLevel.LOW,

        # MEDIUM risk - single resource restarts/edits
        "kubectl delete pod": RiskLevel.MEDIUM,
        "kubectl rollout restart": RiskLevel.MEDIUM,
        "kubectl edit": RiskLevel.MEDIUM,
        "kubectl patch": RiskLevel.MEDIUM,
        "kubectl annotate": RiskLevel.MEDIUM,
        "kubectl label": RiskLevel.MEDIUM,

        # HIGH risk - scaling and resource changes
        "kubectl scale": RiskLevel.HIGH,
        "kubectl autoscale": RiskLevel.HIGH,
        "kubectl set resources": RiskLevel.HIGH,
        "kubectl apply": RiskLevel.HIGH,

        # CRITICAL risk - deletions and cluster operations
        "kubectl delete deployment": RiskLevel.CRITICAL,
        "kubectl delete service": RiskLevel.CRITICAL,
        "kubectl delete namespace": RiskLevel.CRITICAL,
        "kubectl delete pvc": RiskLevel.CRITICAL,
    }

    # Risk elevation factors
    RISK_ELEVATION_KEYWORDS = [
        "production", "prod", "prd",
        "critical", "important",
        "stateful", "database", "db",
        "pvc", "persistent"
    ]

    def __init__(self):
        """Initialize risk assessor"""
        pass

    def assess_action(
        self,
        action_type: str,
        action_description: str,
        affected_resources: List[Dict[str, Any]],
        namespace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAssessment:
        """
        Assess risk level of a remediation action

        Args:
            action_type: Type of action (e.g., "pod_restart", "config_fix", "scale")
            action_description: Human-readable description
            affected_resources: List of resources affected
            namespace: Kubernetes namespace
            context: Additional context (health status, blast radius, etc.)

        Returns:
            RiskAssessment with level, factors, mitigation steps
        """
        logger.info(f"Assessing risk for action: {action_type}")

        # 1. Determine base risk level
        base_risk = self._get_base_risk(action_type, action_description)
        logger.debug(f"Base risk level: {base_risk}")

        # 2. Identify risk elevation factors
        risk_factors = self._identify_risk_factors(
            action_type,
            affected_resources,
            namespace,
            context
        )

        # 3. Elevate risk if necessary
        final_risk = self._elevate_risk(base_risk, risk_factors)
        logger.info(f"Final risk level: {final_risk} (base: {base_risk}, factors: {len(risk_factors)})")

        # 4. Determine if approval required
        requires_approval = final_risk in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        # 5. Generate mitigation steps
        mitigation_steps = self._generate_mitigation_steps(final_risk, action_type, affected_resources)

        # 6. Estimate impact
        estimated_impact = self._estimate_impact(final_risk, affected_resources, context)

        # 7. Assess rollback complexity
        rollback_complexity = self._assess_rollback_complexity(action_type, affected_resources)

        return RiskAssessment(
            level=final_risk,
            requires_approval=requires_approval,
            risk_factors=risk_factors,
            mitigation_steps=mitigation_steps,
            estimated_impact=estimated_impact,
            rollback_complexity=rollback_complexity
        )

    def _get_base_risk(self, action_type: str, action_description: str) -> RiskLevel:
        """Determine base risk level from action type"""
        action_lower = action_description.lower()

        # Check exact matches first
        for pattern, risk in self.ACTION_RISK_MAP.items():
            if pattern.lower() in action_lower:
                return risk

        # Fallback based on action_type
        if action_type in ["investigation", "analyze", "diagnose"]:
            return RiskLevel.LOW
        elif action_type in ["pod_restart", "config_fix"]:
            return RiskLevel.MEDIUM
        elif action_type in ["resource_scale", "apply_changes"]:
            return RiskLevel.HIGH
        else:
            # Unknown action - be conservative
            return RiskLevel.HIGH

    def _identify_risk_factors(
        self,
        action_type: str,
        affected_resources: List[Dict[str, Any]],
        namespace: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Identify factors that increase risk"""
        factors = []

        # 1. Production namespace
        if namespace and any(keyword in namespace.lower() for keyword in ["prod", "production", "prd"]):
            factors.append("Production namespace")

        # 2. Multiple resources affected
        if len(affected_resources) > 5:
            factors.append(f"Multiple resources affected ({len(affected_resources)})")

        # 3. Stateful resources (StatefulSet, PVC)
        stateful_kinds = [r for r in affected_resources if r.get("kind") in ["StatefulSet", "PersistentVolumeClaim"]]
        if stateful_kinds:
            factors.append(f"Stateful resources: {', '.join([r.get('kind') for r in stateful_kinds])}")

        # 4. Critical services (database, queue, etc.)
        for resource in affected_resources:
            name = resource.get("name", "").lower()
            if any(keyword in name for keyword in ["db", "database", "postgres", "mysql", "redis", "kafka", "rabbitmq"]):
                factors.append(f"Critical service: {resource.get('name')}")
                break

        # 5. High blast radius
        if context and context.get("blast_radius", {}).get("count", 0) > 20:
            factors.append(f"High blast radius ({context['blast_radius']['count']} affected events)")

        # 6. Active critical incidents
        if context and context.get("error_summary", {}).get("critical_incidents", 0) > 0:
            factors.append("Active critical incidents")

        # 7. Cluster-wide operation
        if action_type in ["cluster_config", "namespace_operation"]:
            factors.append("Cluster-wide operation")

        return factors

    def _elevate_risk(self, base_risk: RiskLevel, risk_factors: List[str]) -> RiskLevel:
        """Elevate risk level based on risk factors"""
        if not risk_factors:
            return base_risk

        # Count high-severity factors
        high_severity_count = sum(1 for factor in risk_factors if any(
            keyword in factor.lower()
            for keyword in ["production", "critical", "stateful", "database", "cluster-wide"]
        ))

        # Elevate if multiple high-severity factors
        if high_severity_count >= 2:
            if base_risk == RiskLevel.LOW:
                return RiskLevel.MEDIUM
            elif base_risk == RiskLevel.MEDIUM:
                return RiskLevel.HIGH
            elif base_risk == RiskLevel.HIGH:
                return RiskLevel.CRITICAL

        # Elevate if any single critical factor
        if high_severity_count >= 1 and base_risk == RiskLevel.MEDIUM:
            return RiskLevel.HIGH

        return base_risk

    def _generate_mitigation_steps(
        self,
        risk_level: RiskLevel,
        action_type: str,
        affected_resources: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate mitigation steps based on risk level"""
        steps = []

        if risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]:
            steps.append("Create rollback snapshot before execution")
            steps.append("Monitor resource health during and after action")

        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            steps.append("Notify on-call team before execution")
            steps.append("Prepare manual rollback procedure")
            steps.append("Execute during maintenance window if possible")

        if risk_level == RiskLevel.CRITICAL:
            steps.append("Require manual approval from senior engineer")
            steps.append("Document decision and rationale")
            steps.append("Have rollback plan reviewed and ready")

        if action_type == "resource_scale":
            steps.append("Verify resource limits and quotas before scaling")
            steps.append("Scale incrementally (1 replica at a time)")

        if any(r.get("kind") == "StatefulSet" for r in affected_resources):
            steps.append("Ensure PVC backups exist before changes")

        return steps

    def _estimate_impact(
        self,
        risk_level: RiskLevel,
        affected_resources: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Estimate impact of the action"""
        resource_count = len(affected_resources)

        if risk_level == RiskLevel.LOW:
            return f"Minimal impact - read-only operation affecting {resource_count} resource(s)"

        elif risk_level == RiskLevel.MEDIUM:
            return f"Moderate impact - temporary disruption to {resource_count} resource(s), service may experience brief downtime"

        elif risk_level == RiskLevel.HIGH:
            blast_radius = context.get("blast_radius", {}).get("count", 0) if context else 0
            return f"High impact - affects {resource_count} resource(s), potential downstream effects on {blast_radius} events"

        else:  # CRITICAL
            return f"Critical impact - cluster-wide or stateful changes to {resource_count} resource(s), potential data loss or extended downtime"

    def _assess_rollback_complexity(
        self,
        action_type: str,
        affected_resources: List[Dict[str, Any]]
    ) -> str:
        """Assess complexity of rolling back this action"""

        # Simple rollback
        if action_type in ["pod_restart", "investigation"]:
            return "simple"

        # Complex rollback
        if action_type in ["cluster_config", "namespace_operation"]:
            return "complex"

        # Check for stateful resources
        if any(r.get("kind") in ["StatefulSet", "PersistentVolumeClaim"] for r in affected_resources):
            return "complex"

        # Moderate by default
        return "moderate"
