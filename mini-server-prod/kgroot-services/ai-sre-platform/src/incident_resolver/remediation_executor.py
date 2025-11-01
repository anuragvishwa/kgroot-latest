"""
Remediation Executor - Executes remediation actions using Claude Agent SDK

Uses the official Claude Agent SDK to execute remediation actions with real tool support.
This enables Claude to actually run kubectl commands, edit files, and interact with the system.
"""

import logging
import os
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
    session_id: Optional[str] = None


class RemediationExecutor:
    """
    Executes remediation actions using Claude Agent SDK

    This uses the official claude-agent-sdk to enable:
    - Real tool execution (Bash, Read, Write, Edit, etc.)
    - Conversation continuity across multiple steps
    - Permission control via hooks
    - Interrupt capability for long-running tasks

    Specialized agents:
    - pod_restart: Haiku model, Bash tool (fast kubectl operations)
    - config_fix: Sonnet 4.5, Read/Edit/Bash tools (complex config changes)
    - resource_scale: Haiku model, Bash tool (scaling operations)
    - investigation: Sonnet 4.5, Read/Bash/Grep/Glob tools (diagnostics)
    """

    # Agent configurations with tools
    AGENT_CONFIGS = {
        "pod_restart": {
            "model": "haiku",
            "tools": ["Bash"],
            "description": "Restart pods to recover from failures",
            "permission_mode": "default"
        },
        "config_fix": {
            "model": "sonnet",
            "tools": ["Read", "Edit", "Bash", "Write"],
            "description": "Fix configuration issues in ConfigMaps, Secrets, or YAML",
            "permission_mode": "acceptEdits"
        },
        "resource_scale": {
            "model": "haiku",
            "tools": ["Bash", "Read"],
            "description": "Scale resources (Deployments, StatefulSets)",
            "permission_mode": "default"
        },
        "investigation": {
            "model": "sonnet",
            "tools": ["Read", "Bash", "Grep", "Glob"],
            "description": "Investigate issues without making changes",
            "permission_mode": "default"
        }
    }

    def __init__(
        self,
        kubectl_context: Optional[str] = None,
        token_budget_manager=None,
        use_bedrock: bool = False,
        aws_region: str = "us-east-1",
        base_cwd: Optional[str] = None
    ):
        """
        Args:
            kubectl_context: Optional kubectl context for multi-cluster
            token_budget_manager: TokenBudgetManager for tracking usage
            use_bedrock: Use AWS Bedrock instead of direct Anthropic API
            aws_region: AWS region for Bedrock (default: us-east-1)
            base_cwd: Base working directory for Claude Agent
        """
        self.kubectl_context = kubectl_context
        self.token_budget_manager = token_budget_manager
        self.use_bedrock = use_bedrock
        self.aws_region = aws_region
        self.base_cwd = base_cwd or os.getcwd()
        self.active_executions: Dict[str, Dict[str, Any]] = {}

        # Model mappings for Bedrock vs Direct API
        self.bedrock_models = {
            "haiku": "haiku",  # SDK handles Bedrock model IDs
            "sonnet": "sonnet",
            "opus": "opus"
        }
        self.direct_models = {
            "haiku": "haiku",
            "sonnet": "sonnet",
            "opus": "opus"
        }

        # Verify Claude Agent SDK is installed
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
            self.sdk_available = True
            logger.info(f"Claude Agent SDK initialized (use_bedrock={use_bedrock}, region={aws_region})")
        except ImportError as e:
            logger.error(f"Claude Agent SDK not installed: {e}")
            logger.error("Install with: pip install claude-agent-sdk")
            self.sdk_available = False

        # Set up environment for Bedrock if needed
        if use_bedrock:
            # Claude Agent SDK will use AWS credentials from environment
            os.environ["USE_BEDROCK"] = "true"
            os.environ["AWS_REGION"] = aws_region
            logger.info(f"Configured for AWS Bedrock in region {aws_region}")

    def _get_model_id(self, model_type: str) -> str:
        """Get correct model ID for the SDK"""
        # Claude Agent SDK uses model names: "haiku", "sonnet", "opus"
        # It handles Bedrock vs direct API internally based on environment
        return model_type

    def _build_system_prompt(
        self,
        action_type: str,
        action_description: str,
        affected_resources: List[Dict[str, Any]],
        context: Dict[str, Any],
        namespace: str
    ) -> str:
        """Build comprehensive system prompt for the agent"""

        config = self.AGENT_CONFIGS.get(action_type, self.AGENT_CONFIGS["investigation"])

        # Build resource list
        resource_list = [
            f"- {r.get('kind', 'Unknown')}/{r.get('name', 'unknown')}"
            for r in affected_resources
        ]

        # Extract context information
        error_summary = context.get("error_summary", {})
        root_causes = context.get("root_causes", [])
        health_status = context.get("health_status", {})

        # Build kubectl context flag
        kubectl_context_flag = f"--context={self.kubectl_context}" if self.kubectl_context else ""

        # Base prompt
        prompt = f"""You are a Kubernetes SRE assistant helping resolve production incidents.

**Action**: {action_description}

**Namespace**: {namespace}
**Kubectl Context**: {self.kubectl_context or "default"}

**Affected Resources**:
{chr(10).join(resource_list) if resource_list else "- No specific resources identified"}

**Error Summary**:
- Severity: {error_summary.get('overall_severity', 'UNKNOWN')}
- Total incidents: {error_summary.get('total_incidents', 0)}
- Error types: {', '.join(error_summary.get('error_types', {}).keys()) or 'None identified'}

**Root Causes** (Top 3):
{chr(10).join([f"{i+1}. {rc.get('reason', 'Unknown')}: {rc.get('message', 'No details')}" for i, rc in enumerate(root_causes[:3])]) if root_causes else "- No root causes identified"}

**Health Status**:
- Overall: {health_status.get('overall_status', 'unknown')}
- Failed pods: {health_status.get('pod_status', {}).get('Failed', 0)}
- Running pods: {health_status.get('pod_status', {}).get('Running', 0)}

"""

        # Action-specific instructions
        if action_type == "pod_restart":
            prompt += f"""
**Task**: Restart the affected pods to recover from failures.

**Steps**:
1. Use `kubectl get pods -n {namespace} {kubectl_context_flag}` to list pods
2. Identify pods with errors (CrashLoopBackOff, Error, etc.)
3. For each failing pod:
   - Delete it: `kubectl delete pod <pod-name> -n {namespace} {kubectl_context_flag}`
   - Wait a moment for it to recreate
   - Verify: `kubectl get pod <pod-name> -n {namespace} {kubectl_context_flag}`
4. Check final status: `kubectl get pods -n {namespace} {kubectl_context_flag}`
5. Report results clearly

**Important**:
- Only restart pods that are actually failing
- Wait for pods to start recreating before moving to next one
- Report any errors encountered
"""

        elif action_type == "config_fix":
            prompt += f"""
**Task**: Fix configuration issues in Kubernetes resources.

**Steps**:
1. Identify the problematic configuration:
   - Use `kubectl get <resource> <name> -n {namespace} -o yaml {kubectl_context_flag}` to read current config
   - Look for issues mentioned in error summary
2. Fix the configuration:
   - Save to a temp file
   - Edit the problematic fields
   - Apply: `kubectl apply -f <file> -n {namespace} {kubectl_context_flag}`
3. Verify the fix:
   - Check resource status: `kubectl get <resource> <name> -n {namespace} {kubectl_context_flag}`
   - Check events: `kubectl get events -n {namespace} --field-selector involvedObject.name=<name> {kubectl_context_flag}`
4. Report what was changed and the outcome

**Important**:
- Make minimal, targeted changes
- Preserve existing configuration where possible
- Verify changes work before completing
"""

        elif action_type == "resource_scale":
            prompt += f"""
**Task**: Scale Kubernetes resources (Deployments, StatefulSets, etc.).

**Steps**:
1. Check current replica count:
   - `kubectl get deployment <name> -n {namespace} {kubectl_context_flag}`
2. Determine target replica count based on error summary
3. Scale the resource:
   - `kubectl scale deployment <name> --replicas=<N> -n {namespace} {kubectl_context_flag}`
4. Monitor the scaling:
   - `kubectl rollout status deployment <name> -n {namespace} {kubectl_context_flag}`
5. Verify pods are running:
   - `kubectl get pods -n {namespace} -l app=<label> {kubectl_context_flag}`
6. Report the scaling action and results

**Important**:
- Scale incrementally (don't jump from 1 to 100 replicas)
- Verify each pod starts successfully
- Consider resource limits and quotas
"""

        elif action_type == "investigation":
            prompt += f"""
**Task**: Investigate the incident using READ-ONLY commands.

**Steps**:
1. List pods: `kubectl get pods -n {namespace} {kubectl_context_flag}`
2. Check failing pods:
   - Describe: `kubectl describe pod <name> -n {namespace} {kubectl_context_flag}`
   - Logs: `kubectl logs <name> -n {namespace} --tail=100 {kubectl_context_flag}`
   - Previous logs if crashed: `kubectl logs <name> -n {namespace} --previous {kubectl_context_flag}`
3. Check events: `kubectl get events -n {namespace} --sort-by='.lastTimestamp' {kubectl_context_flag}`
4. Check resource status:
   - Deployments: `kubectl get deployments -n {namespace} {kubectl_context_flag}`
   - Services: `kubectl get services -n {namespace} {kubectl_context_flag}`
5. Analyze patterns and provide recommendations

**Important**:
- This is READ-ONLY investigation
- Do NOT make any changes
- Provide clear diagnosis and recommendations
"""

        prompt += f"""

**Available Tools**: {', '.join(config['tools'])}

Execute the task step by step. Report progress and results clearly.
"""

        return prompt

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
        Execute remediation action using Claude Agent SDK

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

        # Validate SDK availability
        if not self.sdk_available:
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
                error="Claude Agent SDK not installed"
            )

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
            # Import SDK
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock, ResultMessage

            # Get agent configuration
            config = self.AGENT_CONFIGS[action_type]

            # Build system prompt
            system_prompt = self._build_system_prompt(
                action_type, action_description, affected_resources, context, namespace
            )

            # Configure agent options
            options = ClaudeAgentOptions(
                model=self._get_model_id(config["model"]),
                allowed_tools=config["tools"],
                permission_mode=config["permission_mode"],
                cwd=self.base_cwd,
                system_prompt=system_prompt,
                # Add kubectl context to environment if specified
                env={
                    "KUBECONFIG": os.environ.get("KUBECONFIG", ""),
                    "KUBECTL_CONTEXT": self.kubectl_context or ""
                } if self.kubectl_context else {}
            )

            # Execute with Claude Agent SDK
            logger.info(f"[{execution_id}] Starting Claude Agent SDK client...")

            output_lines = []
            commands_executed = []
            token_usage = {"input_tokens": 0, "output_tokens": 0}
            session_id = None

            async with ClaudeSDKClient(options=options) as client:
                # Send the task
                await client.query(action_description)

                # Process responses
                async for message in client.receive_response():
                    # Assistant messages (text and thinking)
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                output_lines.append(block.text)
                                logger.debug(f"[{execution_id}] Claude: {block.text[:100]}...")
                            elif isinstance(block, ToolUseBlock):
                                # Track tool usage
                                commands_executed.append(f"{block.name}: {block.input}")
                                logger.info(f"[{execution_id}] Tool: {block.name} with {block.input}")

                    # Result message (final)
                    elif isinstance(message, ResultMessage):
                        session_id = message.session_id

                        # Extract token usage
                        if message.usage:
                            token_usage = {
                                "input_tokens": message.usage.get("input_tokens", 0),
                                "output_tokens": message.usage.get("output_tokens", 0)
                            }

                        # Record token usage
                        if self.token_budget_manager:
                            self.token_budget_manager.record_usage(
                                resolution_id,
                                f"{action_type}_{execution_id}",
                                token_usage["input_tokens"],
                                token_usage["output_tokens"],
                                model=config["model"]
                            )

                        # Check if successful
                        success = not message.is_error

                        logger.info(f"[{execution_id}] Completed: success={success}, tokens={token_usage['input_tokens'] + token_usage['output_tokens']}")

            # Mark as completed
            self.active_executions[execution_id]["status"] = "completed"

            # Build result
            output = "\n".join(output_lines)

            return RemediationResult(
                execution_id=execution_id,
                resolution_id=resolution_id,
                action_type=action_type,
                success=success,
                output=output,
                commands_executed=commands_executed,
                token_usage=token_usage,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                agent_transcript=output,
                session_id=session_id
            )

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

    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get status of active execution"""
        return self.active_executions.get(execution_id)

    def get_active_executions(self, resolution_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all active executions, optionally filtered by resolution_id"""
        executions = list(self.active_executions.values())

        if resolution_id:
            executions = [e for e in executions if e["resolution_id"] == resolution_id]

        return executions

    async def create_custom_tool_agent(
        self,
        action_type: str,
        custom_tools: List[str],
        description: str,
        model: str = "sonnet",
        permission_mode: str = "default"
    ):
        """
        Create a custom agent with specific tools (for future extensibility)

        This allows adding new agent types dynamically:
        - Slack integration (custom Slack MCP tool)
        - Terraform operations (custom Terraform MCP tool)
        - GitHub PR analysis (custom GitHub MCP tool)

        Args:
            action_type: Unique action type identifier
            custom_tools: List of tool names (including MCP tools)
            description: What this agent does
            model: Model to use (haiku/sonnet/opus)
            permission_mode: Permission mode for this agent
        """
        self.AGENT_CONFIGS[action_type] = {
            "model": model,
            "tools": custom_tools,
            "description": description,
            "permission_mode": permission_mode
        }

        logger.info(f"Registered custom agent: {action_type} with tools {custom_tools}")
