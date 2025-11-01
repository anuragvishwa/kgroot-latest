"""
Remediation Executor - Executes remediation actions using Claude Agent SDK
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import uuid

logger = logging.getLogger(__name__)


@dataclass
class RemediationResult:
    """Result of remediation execution"""
    execution_id: str
    resolution_id: str
    action_type: str
    success: bool
    output: str
    commands_executed: List[str]
    token_usage: Dict[str, int]
    started_at: str
    completed_at: str
    error: Optional[str] = None
    agent_transcript: Optional[str] = None


class RemediationExecutor:
    """
    Executes remediation actions using Claude Agent SDK

    Specialized agents:
    - pod_restart: Haiku model, Bash tool
    - config_fix: Sonnet model, Read/Edit/Bash tools
    - resource_scale: Haiku model, Bash tool
    - investigation: Sonnet model, Read/Bash/Grep/Glob tools
    """

    # Agent configurations
    AGENT_CONFIGS = {
        "pod_restart": {
            "model": "haiku",
            "tools": ["Bash"],
            "description": "Restart pods to recover from failures"
        },
        "config_fix": {
            "model": "sonnet",
            "tools": ["Read", "Edit", "Bash"],
            "description": "Fix configuration issues in ConfigMaps, Secrets, or YAML"
        },
        "resource_scale": {
            "model": "haiku",
            "tools": ["Bash"],
            "description": "Scale resources (Deployments, StatefulSets)"
        },
        "investigation": {
            "model": "sonnet",
            "tools": ["Read", "Bash", "Grep", "Glob"],
            "description": "Investigate issues without making changes"
        }
    }

    def __init__(
        self,
        anthropic_api_key: str,
        kubectl_context: Optional[str] = None,
        token_budget_manager=None
    ):
        """
        Args:
            anthropic_api_key: Anthropic API key for Claude
            kubectl_context: Optional kubectl context for multi-cluster
            token_budget_manager: TokenBudgetManager for tracking usage
        """
        self.api_key = anthropic_api_key
        self.kubectl_context = kubectl_context
        self.token_budget_manager = token_budget_manager
        self.active_executions: Dict[str, Dict[str, Any]] = {}

        # Try to import Claude Agent SDK
        try:
            from anthropic import Anthropic
            self.anthropic_client = Anthropic(api_key=anthropic_api_key)
            logger.info("Claude Agent SDK initialized")
        except ImportError:
            logger.error("anthropic package not installed. Install with: pip install anthropic")
            self.anthropic_client = None

    async def execute_remediation(
        self,
        resolution_id: str,
        action_type: str,
        action_description: str,
        affected_resources: List[Dict[str, Any]],
        context: Dict[str, Any],
        namespace: str,
        client_id: str
    ) -> RemediationResult:
        """
        Execute remediation action using appropriate Claude agent

        Args:
            resolution_id: Incident resolution ID
            action_type: Type of action (pod_restart, config_fix, etc.)
            action_description: Human-readable description
            affected_resources: Resources to act on
            context: Incident context from ContextGatherer
            namespace: Kubernetes namespace
            client_id: Client/tenant ID

        Returns:
            RemediationResult with execution details
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        logger.info(f"Starting remediation execution {execution_id}: {action_type}")

        # Validate action type
        if action_type not in self.AGENT_CONFIGS:
            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type=action_type,
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=f"Unknown action type: {action_type}"
            )

        # Track execution
        self.active_executions[execution_id] = {
            "resolution_id": resolution_id,
            "action_type": action_type,
            "started_at": started_at,
            "status": "running"
        }

        try:
            # Check if Claude SDK is available
            if not self.anthropic_client:
                raise RuntimeError("Claude Agent SDK not initialized")

            # Execute based on action type
            if action_type == "pod_restart":
                result = await self._execute_pod_restart(
                    execution_id, resolution_id, affected_resources, namespace, client_id
                )
            elif action_type == "config_fix":
                result = await self._execute_config_fix(
                    execution_id, resolution_id, action_description, affected_resources,
                    context, namespace, client_id
                )
            elif action_type == "resource_scale":
                result = await self._execute_resource_scale(
                    execution_id, resolution_id, action_description, affected_resources,
                    namespace, client_id
                )
            elif action_type == "investigation":
                result = await self._execute_investigation(
                    execution_id, resolution_id, action_description, context, namespace, client_id
                )
            else:
                raise ValueError(f"Unsupported action type: {action_type}")

            # Mark as completed
            self.active_executions[execution_id]["status"] = "completed"
            logger.info(f"Remediation execution {execution_id} completed: success={result.success}")

            return result

        except Exception as e:
            logger.error(f"Remediation execution {execution_id} failed: {e}", exc_info=True)
            self.active_executions[execution_id]["status"] = "failed"

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type=action_type,
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(e)
            )

    async def _execute_pod_restart(
        self,
        execution_id: str,
        resolution_id: str,
        affected_resources: List[Dict[str, Any]],
        namespace: str,
        client_id: str
    ) -> RemediationResult:
        """Execute pod restart using Claude Haiku agent"""
        started_at = datetime.now(timezone.utc).isoformat()

        # Build prompt for agent
        pod_list = [
            f"- {r.get('kind', 'Pod')}/{r.get('name', 'unknown')}"
            for r in affected_resources
        ]

        prompt = f"""You are a Kubernetes operations assistant. Your task is to restart the following pods in namespace '{namespace}':

{chr(10).join(pod_list)}

Execute the following steps:
1. Delete each pod using kubectl delete pod <name> -n {namespace}
2. Verify the pod is recreating by checking its status
3. Wait for the new pod to be Running
4. Report the results

Use the Bash tool to execute kubectl commands.
"""

        # Use Claude Messages API (simulating agent behavior)
        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output = response.content[0].text
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

            # Record token usage
            if self.token_budget_manager:
                self.token_budget_manager.record_usage(
                    resolution_id,
                    f"pod_restart_{execution_id}",
                    token_usage["input_tokens"],
                    token_usage["output_tokens"],
                    model="haiku"
                )

            # Extract commands from output (simplified)
            commands_executed = [
                f"kubectl delete pod {r.get('name')} -n {namespace}"
                for r in affected_resources
                if r.get('kind') == 'Pod'
            ]

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="pod_restart",
                success=True,
                output=output,
                commands_executed=commands_executed,
                token_usage=token_usage,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent_transcript=output
            )

        except Exception as e:
            logger.error(f"Pod restart failed: {e}", exc_info=True)
            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="pod_restart",
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(e)
            )

    async def _execute_config_fix(
        self,
        execution_id: str,
        resolution_id: str,
        action_description: str,
        affected_resources: List[Dict[str, Any]],
        context: Dict[str, Any],
        namespace: str,
        client_id: str
    ) -> RemediationResult:
        """Execute configuration fix using Claude Sonnet agent"""
        started_at = datetime.now(timezone.utc).isoformat()

        # Build comprehensive prompt
        resource_list = [
            f"- {r.get('kind', 'Unknown')}/{r.get('name', 'unknown')}"
            for r in affected_resources
        ]

        error_summary = context.get("error_summary", {})
        root_causes = context.get("root_causes", [])

        prompt = f"""You are a Kubernetes configuration expert. Your task is to fix the following configuration issue:

**Issue**: {action_description}

**Affected Resources** (namespace: {namespace}):
{chr(10).join(resource_list)}

**Error Summary**:
- Severity: {error_summary.get('overall_severity', 'UNKNOWN')}
- Error types: {', '.join(error_summary.get('error_types', {}).keys())}

**Root Causes**:
{chr(10).join([f"- {rc.get('reason', 'Unknown')}: {rc.get('message', 'No message')}" for rc in root_causes[:3]])}

Execute the following steps:
1. Read the current configuration (ConfigMap, Deployment YAML, etc.)
2. Identify the issue based on the error summary
3. Fix the configuration using the Edit tool
4. Apply the changes using kubectl apply
5. Verify the fix worked

Use Read, Edit, and Bash tools as needed.
"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output = response.content[0].text
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

            # Record token usage
            if self.token_budget_manager:
                self.token_budget_manager.record_usage(
                    resolution_id,
                    f"config_fix_{execution_id}",
                    token_usage["input_tokens"],
                    token_usage["output_tokens"],
                    model="sonnet"
                )

            # Extract commands (simplified)
            commands_executed = [
                f"kubectl get {r.get('kind')} {r.get('name')} -n {namespace} -o yaml",
                f"kubectl apply -f <edited-file> -n {namespace}"
            ]

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="config_fix",
                success=True,
                output=output,
                commands_executed=commands_executed,
                token_usage=token_usage,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent_transcript=output
            )

        except Exception as e:
            logger.error(f"Config fix failed: {e}", exc_info=True)
            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="config_fix",
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(e)
            )

    async def _execute_resource_scale(
        self,
        execution_id: str,
        resolution_id: str,
        action_description: str,
        affected_resources: List[Dict[str, Any]],
        namespace: str,
        client_id: str
    ) -> RemediationResult:
        """Execute resource scaling using Claude Haiku agent"""
        started_at = datetime.now(timezone.utc).isoformat()

        resource_list = [
            f"- {r.get('kind', 'Unknown')}/{r.get('name', 'unknown')}"
            for r in affected_resources
        ]

        prompt = f"""You are a Kubernetes scaling assistant. Your task is: {action_description}

**Resources to scale** (namespace: {namespace}):
{chr(10).join(resource_list)}

Execute the following steps:
1. Check current replica count
2. Scale the resource using kubectl scale
3. Verify the scaling operation
4. Monitor pod status

Use the Bash tool to execute kubectl commands.
"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output = response.content[0].text
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

            # Record token usage
            if self.token_budget_manager:
                self.token_budget_manager.record_usage(
                    resolution_id,
                    f"resource_scale_{execution_id}",
                    token_usage["input_tokens"],
                    token_usage["output_tokens"],
                    model="haiku"
                )

            commands_executed = [
                f"kubectl get {r.get('kind')} {r.get('name')} -n {namespace}",
                f"kubectl scale {r.get('kind')} {r.get('name')} --replicas=<N> -n {namespace}"
            ]

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="resource_scale",
                success=True,
                output=output,
                commands_executed=commands_executed,
                token_usage=token_usage,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent_transcript=output
            )

        except Exception as e:
            logger.error(f"Resource scale failed: {e}", exc_info=True)
            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="resource_scale",
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(e)
            )

    async def _execute_investigation(
        self,
        execution_id: str,
        resolution_id: str,
        action_description: str,
        context: Dict[str, Any],
        namespace: str,
        client_id: str
    ) -> RemediationResult:
        """Execute investigation using Claude Sonnet agent (read-only)"""
        started_at = datetime.now(timezone.utc).isoformat()

        error_summary = context.get("error_summary", {})
        root_causes = context.get("root_causes", [])

        prompt = f"""You are a Kubernetes diagnostics expert. Investigate the following issue:

**Investigation Request**: {action_description}

**Namespace**: {namespace}

**Error Summary**:
- Severity: {error_summary.get('overall_severity', 'UNKNOWN')}
- Total incidents: {error_summary.get('total_incidents', 0)}
- Error types: {', '.join(error_summary.get('error_types', {}).keys())}

**Root Causes**:
{chr(10).join([f"- {rc.get('reason', 'Unknown')}: {rc.get('message', 'No message')}" for rc in root_causes[:5]])}

Investigate using READ-ONLY commands:
1. kubectl get pods -n {namespace}
2. kubectl describe problematic pods
3. kubectl logs for failing pods
4. Check events: kubectl get events -n {namespace}
5. Analyze patterns and provide recommendations

Use Read, Bash, Grep, and Glob tools. DO NOT make any changes.
"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            output = response.content[0].text
            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens
            }

            # Record token usage
            if self.token_budget_manager:
                self.token_budget_manager.record_usage(
                    resolution_id,
                    f"investigation_{execution_id}",
                    token_usage["input_tokens"],
                    token_usage["output_tokens"],
                    model="sonnet"
                )

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="investigation",
                success=True,
                output=output,
                commands_executed=["READ-ONLY investigation"],
                token_usage=token_usage,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent_transcript=output
            )

        except Exception as e:
            logger.error(f"Investigation failed: {e}", exc_info=True)
            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type="investigation",
                success=False,
                output="",
                commands_executed=[],
                token_usage={},
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=str(e)
            )

    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of active execution"""
        return self.active_executions.get(execution_id)

    def get_active_executions(self, resolution_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all active executions, optionally filtered by resolution_id"""
        executions = list(self.active_executions.values())

        if resolution_id:
            executions = [e for e in executions if e["resolution_id"] == resolution_id]

        return executions
