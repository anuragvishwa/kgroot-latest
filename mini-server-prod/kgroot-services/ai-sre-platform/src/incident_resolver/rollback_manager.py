"""
Rollback Manager - Manages rollback snapshots and undo operations
"""

import logging
import json
import subprocess
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import uuid

logger = logging.getLogger(__name__)


@dataclass
class RollbackSnapshot:
    """Snapshot for rollback"""
    snapshot_id: str
    resolution_id: str
    client_id: str
    namespace: str
    action_type: str
    affected_resources: List[Dict[str, Any]]
    state_before: Dict[str, Any]
    rollback_commands: List[str]
    created_at: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class RollbackManager:
    """
    Manages rollback snapshots and undo operations

    Features:
    - Pre-action state capture
    - Rollback command generation
    - Automated rollback execution
    - Rollback verification
    - Snapshot history
    """

    def __init__(self, kubectl_context: Optional[str] = None):
        """
        Args:
            kubectl_context: Optional kubectl context for multi-cluster
        """
        self.kubectl_context = kubectl_context
        self.snapshots: Dict[str, RollbackSnapshot] = {}
        self.rollback_history: List[Dict[str, Any]] = []

    async def create_snapshot(
        self,
        resolution_id: str,
        client_id: str,
        namespace: str,
        action_type: str,
        affected_resources: List[Dict[str, Any]],
        action_commands: Optional[List[str]] = None
    ) -> RollbackSnapshot:
        """
        Create rollback snapshot before executing action

        Args:
            resolution_id: Incident resolution ID
            client_id: Client/tenant ID
            namespace: Kubernetes namespace
            action_type: Type of action being performed
            affected_resources: Resources that will be affected
            action_commands: Commands that will be executed

        Returns:
            RollbackSnapshot object
        """
        snapshot_id = str(uuid.uuid4())
        logger.info(f"Creating rollback snapshot {snapshot_id} for {action_type}")

        # Capture current state
        state_before = await self._capture_state(namespace, affected_resources)

        # Generate rollback commands
        rollback_commands = self._generate_rollback_commands(
            action_type,
            affected_resources,
            state_before,
            action_commands
        )

        snapshot = RollbackSnapshot(
            snapshot_id=snapshot_id,
            resolution_id=resolution_id,
            client_id=client_id,
            namespace=namespace,
            action_type=action_type,
            affected_resources=affected_resources,
            state_before=state_before,
            rollback_commands=rollback_commands,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={
                "action_commands": action_commands or [],
                "resource_count": len(affected_resources)
            }
        )

        self.snapshots[snapshot_id] = snapshot
        logger.info(f"Snapshot {snapshot_id} created with {len(rollback_commands)} rollback commands")

        return snapshot

    async def rollback(
        self,
        snapshot_id: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute rollback from snapshot

        Args:
            snapshot_id: Snapshot ID to rollback to
            dry_run: If True, only show commands without executing

        Returns:
            {
                "success": bool,
                "snapshot_id": str,
                "commands_executed": list,
                "results": list,
                "errors": list
            }
        """
        if snapshot_id not in self.snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")

        snapshot = self.snapshots[snapshot_id]
        logger.info(f"Starting rollback from snapshot {snapshot_id} (dry_run={dry_run})")

        results = []
        errors = []

        for i, command in enumerate(snapshot.rollback_commands, 1):
            try:
                logger.info(f"[{i}/{len(snapshot.rollback_commands)}] Executing: {command}")

                if dry_run:
                    results.append({
                        "command": command,
                        "status": "dry_run",
                        "output": "DRY RUN - command not executed"
                    })
                    continue

                # Execute command
                result = await self._execute_kubectl_command(command)
                results.append({
                    "command": command,
                    "status": "success" if result["return_code"] == 0 else "failed",
                    "output": result["output"],
                    "return_code": result["return_code"]
                })

                if result["return_code"] != 0:
                    error_msg = f"Command failed: {command}\n{result['output']}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            except Exception as e:
                error_msg = f"Exception executing command '{command}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                results.append({
                    "command": command,
                    "status": "exception",
                    "error": str(e)
                })

        success = len(errors) == 0

        # Record rollback in history
        self.rollback_history.append({
            "snapshot_id": snapshot_id,
            "resolution_id": snapshot.resolution_id,
            "action_type": snapshot.action_type,
            "namespace": snapshot.namespace,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "success": success,
            "commands_count": len(snapshot.rollback_commands),
            "errors_count": len(errors)
        })

        logger.info(f"Rollback completed: success={success}, commands={len(results)}, errors={len(errors)}")

        return {
            "success": success,
            "snapshot_id": snapshot_id,
            "dry_run": dry_run,
            "commands_executed": len(results),
            "results": results,
            "errors": errors
        }

    async def _capture_state(
        self,
        namespace: str,
        affected_resources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Capture current state of affected resources"""
        state = {
            "namespace": namespace,
            "resources": []
        }

        for resource in affected_resources:
            kind = resource.get("kind")
            name = resource.get("name")

            if not kind or not name:
                logger.warning(f"Skipping resource with missing kind or name: {resource}")
                continue

            try:
                # Get current YAML representation
                command = f"kubectl get {kind} {name} -n {namespace} -o yaml"
                result = await self._execute_kubectl_command(command)

                if result["return_code"] == 0:
                    state["resources"].append({
                        "kind": kind,
                        "name": name,
                        "yaml": result["output"],
                        "captured_at": datetime.now(timezone.utc).isoformat()
                    })
                    logger.debug(f"Captured state for {kind}/{name}")
                else:
                    logger.warning(f"Failed to capture state for {kind}/{name}: {result['output']}")

            except Exception as e:
                logger.error(f"Exception capturing state for {kind}/{name}: {e}")

        logger.info(f"Captured state for {len(state['resources'])} resources")
        return state

    def _generate_rollback_commands(
        self,
        action_type: str,
        affected_resources: List[Dict[str, Any]],
        state_before: Dict[str, Any],
        action_commands: Optional[List[str]]
    ) -> List[str]:
        """Generate rollback commands based on action type"""
        commands = []

        if action_type == "pod_restart":
            # Pod restarts are self-healing, no explicit rollback needed
            # But we can force pods back if needed
            for resource in affected_resources:
                if resource.get("kind") == "Pod":
                    # Pods will auto-restart, no rollback command
                    pass
            logger.info("Pod restart: No explicit rollback needed (self-healing)")

        elif action_type == "config_fix":
            # Restore previous ConfigMap/Secret state
            namespace = state_before.get("namespace")
            for resource_state in state_before.get("resources", []):
                kind = resource_state["kind"]
                name = resource_state["name"]

                # Save YAML to temp file and apply
                temp_file = f"/tmp/rollback_{name}.yaml"
                commands.append(f"echo '{resource_state['yaml']}' > {temp_file}")
                commands.append(f"kubectl apply -f {temp_file} -n {namespace}")
                commands.append(f"rm {temp_file}")

        elif action_type == "resource_scale":
            # Scale back to original replica count
            for resource in affected_resources:
                kind = resource.get("kind")
                name = resource.get("name")
                namespace = state_before.get("namespace")

                # Find original replica count from state_before
                for resource_state in state_before.get("resources", []):
                    if resource_state["kind"] == kind and resource_state["name"] == name:
                        # Parse YAML to get original replicas
                        try:
                            import yaml
                            yaml_data = yaml.safe_load(resource_state["yaml"])
                            original_replicas = yaml_data.get("spec", {}).get("replicas", 1)
                            commands.append(f"kubectl scale {kind} {name} --replicas={original_replicas} -n {namespace}")
                            logger.debug(f"Rollback: Scale {kind}/{name} to {original_replicas} replicas")
                        except Exception as e:
                            logger.error(f"Failed to parse YAML for rollback: {e}")

        else:
            # Generic rollback: restore all resources from snapshot
            namespace = state_before.get("namespace")
            for resource_state in state_before.get("resources", []):
                kind = resource_state["kind"]
                name = resource_state["name"]
                temp_file = f"/tmp/rollback_{name}.yaml"
                commands.append(f"echo '{resource_state['yaml']}' > {temp_file}")
                commands.append(f"kubectl apply -f {temp_file} -n {namespace}")
                commands.append(f"rm {temp_file}")

        if not commands:
            logger.warning(f"No rollback commands generated for action_type={action_type}")
            commands.append("echo 'No rollback commands generated - manual intervention may be required'")

        return commands

    async def _execute_kubectl_command(self, command: str) -> Dict[str, Any]:
        """Execute kubectl command and return result"""
        try:
            # Add context if specified
            if self.kubectl_context:
                command = command.replace("kubectl ", f"kubectl --context={self.kubectl_context} ")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "command": command,
                "return_code": result.returncode,
                "output": result.stdout if result.returncode == 0 else result.stderr
            }

        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "return_code": -1,
                "output": "Command timed out after 30 seconds"
            }
        except Exception as e:
            return {
                "command": command,
                "return_code": -1,
                "output": f"Exception: {str(e)}"
            }

    def get_snapshot(self, snapshot_id: str) -> Optional[RollbackSnapshot]:
        """Get snapshot by ID"""
        return self.snapshots.get(snapshot_id)

    def get_snapshots_for_resolution(self, resolution_id: str) -> List[RollbackSnapshot]:
        """Get all snapshots for a resolution"""
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.resolution_id == resolution_id
        ]

    def get_rollback_history(
        self,
        resolution_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get rollback history"""
        history = self.rollback_history

        if resolution_id:
            history = [h for h in history if h["resolution_id"] == resolution_id]

        # Sort by executed_at (most recent first)
        history.sort(key=lambda x: x["executed_at"], reverse=True)

        return history[:limit]

    def cleanup_snapshot(self, snapshot_id: str):
        """Clean up snapshot after successful resolution"""
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]
            logger.info(f"Cleaned up snapshot {snapshot_id}")
