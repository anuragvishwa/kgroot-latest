"""
Incident Resolution API - FastAPI router for incident resolution endpoints
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import uuid

from .context_gatherer import ContextGatherer
from .risk_assessor import RiskAssessor, RiskLevel
from .approval_engine import ApprovalEngine, ApprovalStatus
from .remediation_executor import RemediationExecutor
from .rollback_manager import RollbackManager
from .token_budget import TokenBudgetManager

logger = logging.getLogger(__name__)
router = APIRouter()

# Global instances (initialized on startup)
context_gatherer: Optional[ContextGatherer] = None
risk_assessor: Optional[RiskAssessor] = None
approval_engine: Optional[ApprovalEngine] = None
remediation_executor: Optional[RemediationExecutor] = None
rollback_manager: Optional[RollbackManager] = None
token_budget_manager: Optional[TokenBudgetManager] = None

# Resolution tracking
active_resolutions: Dict[str, Dict[str, Any]] = {}


class ResolveIncidentRequest(BaseModel):
    """Request to resolve an incident"""
    client_id: str = Field(..., description="Client/tenant ID")
    event_id: Optional[str] = Field(None, description="Specific event ID (optional)")
    namespace: Optional[str] = Field(None, description="Kubernetes namespace")
    action_type: str = Field(..., description="Type of action: pod_restart, config_fix, resource_scale, investigation")
    action_description: str = Field(..., description="Description of what to do")
    time_window_hours: float = Field(2.0, description="Time window for context gathering", ge=0.1, le=48)
    auto_approve: bool = Field(False, description="Auto-approve LOW risk actions (default: False)")
    token_limit: Optional[int] = Field(None, description="Custom token limit (default: 100k)")


class ApprovalDecisionRequest(BaseModel):
    """Request to approve or reject an action"""
    approved_by: str = Field(..., description="User making the decision (email/username)")
    decision: str = Field(..., description="Decision: 'approve' or 'reject'")
    reason: Optional[str] = Field(None, description="Reason (required for rejection)")


class RollbackRequest(BaseModel):
    """Request to rollback a resolution"""
    snapshot_id: str = Field(..., description="Snapshot ID to rollback to")
    dry_run: bool = Field(False, description="If true, show commands without executing")


def initialize_services(neo4j_service=None, base_url: str = "http://localhost:8084"):
    """Initialize incident resolution services"""
    global context_gatherer, risk_assessor, approval_engine, remediation_executor, rollback_manager, token_budget_manager

    logger.info("Initializing incident resolution services...")

    # Initialize services
    context_gatherer = ContextGatherer(base_url=base_url, neo4j_service=neo4j_service)
    risk_assessor = RiskAssessor()
    approval_engine = ApprovalEngine(default_timeout_seconds=300)
    token_budget_manager = TokenBudgetManager()

    # Get AWS config from environment for Claude Agent SDK
    use_bedrock = os.getenv("USE_BEDROCK", "true").lower() == "true"  # Default to Bedrock
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    kubectl_context = os.getenv("KUBECTL_CONTEXT")
    base_cwd = os.getenv("AGENT_CWD", "/tmp/incident-resolver")

    # Create base directory for agent operations
    os.makedirs(base_cwd, exist_ok=True)

    remediation_executor = RemediationExecutor(
        kubectl_context=kubectl_context,
        token_budget_manager=token_budget_manager,
        use_bedrock=use_bedrock,
        aws_region=aws_region,
        base_cwd=base_cwd
    )

    rollback_manager = RollbackManager()

    logger.info("Incident resolution services initialized")


@router.post("/resolve")
async def resolve_incident(request: ResolveIncidentRequest, background_tasks: BackgroundTasks):
    """
    Start incident resolution workflow

    Workflow:
    1. Gather context from knowledge graph and APIs
    2. Assess risk level
    3. Request approval (if needed)
    4. Create rollback snapshot
    5. Execute remediation
    6. Verify and report

    Returns:
        {
            "resolution_id": str,
            "status": "gathering_context" | "awaiting_approval" | "executing" | "completed" | "failed",
            "approval_id": str (if approval required),
            "requires_approval": bool,
            "risk_level": str,
            "message": str
        }
    """
    if not all([context_gatherer, risk_assessor, approval_engine, remediation_executor, rollback_manager, token_budget_manager]):
        raise HTTPException(status_code=503, detail="Incident resolution services not initialized")

    resolution_id = str(uuid.uuid4())
    logger.info(f"Starting incident resolution {resolution_id}: {request.action_type}")

    try:
        # 1. Gather context
        logger.info(f"[{resolution_id}] Gathering context...")
        context = await context_gatherer.gather_incident_context(
            client_id=request.client_id,
            event_id=request.event_id,
            namespace=request.namespace,
            time_window_hours=request.time_window_hours
        )

        # Extract affected resources
        affected_resources = context.get("affected_resources", [])
        if not affected_resources:
            raise HTTPException(
                status_code=404,
                detail="No affected resources found. Cannot proceed with resolution."
            )

        # 2. Assess risk
        logger.info(f"[{resolution_id}] Assessing risk...")
        risk_assessment = risk_assessor.assess_action(
            action_type=request.action_type,
            action_description=request.action_description,
            affected_resources=affected_resources,
            namespace=request.namespace,
            context=context
        )

        logger.info(f"[{resolution_id}] Risk level: {risk_assessment.level}")

        # 3. Create token budget
        token_budget_manager.create_incident_budget(
            incident_id=resolution_id,
            custom_limit=request.token_limit
        )

        # 4. Request approval (if needed)
        approval_request = await approval_engine.request_approval(
            resolution_id=resolution_id,
            client_id=request.client_id,
            action_type=request.action_type,
            action_description=request.action_description,
            risk_assessment=risk_assessment,
            affected_resources=affected_resources
        )

        # Track resolution
        active_resolutions[resolution_id] = {
            "resolution_id": resolution_id,
            "client_id": request.client_id,
            "namespace": request.namespace,
            "action_type": request.action_type,
            "risk_level": risk_assessment.level,
            "approval_id": approval_request.approval_id,
            "approval_status": approval_request.status,
            "created_at": datetime.utcnow().isoformat(),
            "status": "awaiting_approval" if approval_request.status == ApprovalStatus.PENDING else "ready",
            "context": context,
            "affected_resources": affected_resources,
            "risk_assessment": risk_assessment
        }

        # If auto-approved, execute in background
        if approval_request.status == ApprovalStatus.AUTO_APPROVED:
            logger.info(f"[{resolution_id}] Auto-approved, scheduling execution...")
            background_tasks.add_task(
                _execute_resolution,
                resolution_id,
                request,
                context,
                affected_resources,
                risk_assessment
            )

            return {
                "resolution_id": resolution_id,
                "status": "executing",
                "approval_id": approval_request.approval_id,
                "requires_approval": False,
                "risk_level": risk_assessment.level,
                "message": "Action auto-approved and executing"
            }

        # Otherwise, wait for approval
        return {
            "resolution_id": resolution_id,
            "status": "awaiting_approval",
            "approval_id": approval_request.approval_id,
            "requires_approval": True,
            "risk_level": risk_assessment.level,
            "risk_factors": risk_assessment.risk_factors,
            "estimated_impact": risk_assessment.estimated_impact,
            "mitigation_steps": risk_assessment.mitigation_steps,
            "affected_resources": [
                {
                    "kind": r.get("kind"),
                    "name": r.get("name"),
                    "namespace": r.get("namespace")
                }
                for r in affected_resources
            ],
            "message": "Approval required - use /approve endpoint to proceed"
        }

    except Exception as e:
        logger.error(f"[{resolution_id}] Failed to start resolution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{approval_id}")
async def approve_resolution(
    approval_id: str,
    request: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks
):
    """
    Approve or reject a pending resolution

    Returns execution status if approved, or cancellation confirmation if rejected
    """
    if not all([approval_engine, remediation_executor, rollback_manager]):
        raise HTTPException(status_code=503, detail="Services not initialized")

    logger.info(f"Approval decision for {approval_id}: {request.decision} by {request.approved_by}")

    # Get approval status
    approval = approval_engine.get_approval_status(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Approval already processed: {approval.status}"
        )

    # Process decision
    if request.decision.lower() == "approve":
        success = await approval_engine.approve(approval_id, request.approved_by)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to approve - may have expired")

        # Find resolution
        resolution = next(
            (r for r in active_resolutions.values() if r["approval_id"] == approval_id),
            None
        )

        if not resolution:
            raise HTTPException(status_code=404, detail="Resolution not found")

        resolution_id = resolution["resolution_id"]
        resolution["status"] = "executing"
        resolution["approval_status"] = ApprovalStatus.APPROVED

        # Execute in background
        logger.info(f"[{resolution_id}] Approved, scheduling execution...")
        background_tasks.add_task(
            _execute_resolution,
            resolution_id,
            None,  # Will use stored data
            resolution["context"],
            resolution["affected_resources"],
            resolution["risk_assessment"]
        )

        return {
            "resolution_id": resolution_id,
            "approval_id": approval_id,
            "status": "approved",
            "message": "Resolution approved and executing"
        }

    elif request.decision.lower() == "reject":
        if not request.reason:
            raise HTTPException(status_code=400, detail="Rejection reason required")

        success = await approval_engine.reject(approval_id, request.approved_by, request.reason)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to reject")

        # Update resolution status
        resolution = next(
            (r for r in active_resolutions.values() if r["approval_id"] == approval_id),
            None
        )

        if resolution:
            resolution["status"] = "rejected"
            resolution["approval_status"] = ApprovalStatus.REJECTED

        return {
            "approval_id": approval_id,
            "status": "rejected",
            "message": f"Resolution rejected: {request.reason}"
        }

    else:
        raise HTTPException(status_code=400, detail="Invalid decision - must be 'approve' or 'reject'")


@router.post("/rollback")
async def rollback_resolution(request: RollbackRequest):
    """
    Rollback a resolution using snapshot

    Returns rollback execution results
    """
    if not rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    logger.info(f"Rollback requested for snapshot {request.snapshot_id} (dry_run={request.dry_run})")

    try:
        result = await rollback_manager.rollback(
            snapshot_id=request.snapshot_id,
            dry_run=request.dry_run
        )

        return {
            "snapshot_id": request.snapshot_id,
            "dry_run": request.dry_run,
            "success": result["success"],
            "commands_executed": result["commands_executed"],
            "results": result["results"],
            "errors": result["errors"]
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{resolution_id}")
async def get_resolution_status(resolution_id: str):
    """
    Get status of an incident resolution

    Returns current status, execution details, and token usage
    """
    if resolution_id not in active_resolutions:
        raise HTTPException(status_code=404, detail="Resolution not found")

    resolution = active_resolutions[resolution_id]

    # Get token usage
    token_usage = None
    if token_budget_manager:
        token_usage = token_budget_manager.get_incident_usage(resolution_id)

    # Get approval status
    approval_id = resolution.get("approval_id")
    approval_status = None
    if approval_id and approval_engine:
        approval = approval_engine.get_approval_status(approval_id)
        if approval:
            approval_status = approval.to_dict()

    return {
        "resolution_id": resolution_id,
        "client_id": resolution["client_id"],
        "namespace": resolution.get("namespace"),
        "action_type": resolution["action_type"],
        "status": resolution["status"],
        "risk_level": resolution["risk_level"],
        "created_at": resolution["created_at"],
        "approval": approval_status,
        "token_usage": token_usage,
        "snapshot_id": resolution.get("snapshot_id"),
        "execution_result": resolution.get("execution_result")
    }


@router.post("/interrupt/{resolution_id}")
async def interrupt_resolution(resolution_id: str):
    """
    Interrupt a running resolution

    This is a safety mechanism to stop execution if needed
    """
    if resolution_id not in active_resolutions:
        raise HTTPException(status_code=404, detail="Resolution not found")

    resolution = active_resolutions[resolution_id]

    if resolution["status"] not in ["executing", "awaiting_approval"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot interrupt resolution in status: {resolution['status']}"
        )

    # Update status
    resolution["status"] = "interrupted"
    logger.warning(f"Resolution {resolution_id} interrupted by user")

    return {
        "resolution_id": resolution_id,
        "status": "interrupted",
        "message": "Resolution interrupted - rollback if needed"
    }


@router.get("/pending-approvals")
async def get_pending_approvals(client_id: Optional[str] = Query(None)):
    """Get all pending approvals, optionally filtered by client_id"""
    if not approval_engine:
        raise HTTPException(status_code=503, detail="Approval engine not initialized")

    approvals = approval_engine.get_pending_approvals(client_id=client_id)

    return {
        "pending_approvals": [a.to_dict() for a in approvals],
        "count": len(approvals)
    }


@router.get("/history")
async def get_resolution_history(
    client_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    """Get resolution history"""
    resolutions = list(active_resolutions.values())

    if client_id:
        resolutions = [r for r in resolutions if r["client_id"] == client_id]

    # Sort by created_at (most recent first)
    resolutions.sort(key=lambda x: x["created_at"], reverse=True)

    return {
        "resolutions": resolutions[:limit],
        "count": len(resolutions[:limit]),
        "total": len(resolutions)
    }


async def _execute_resolution(
    resolution_id: str,
    request: Optional[ResolveIncidentRequest],
    context: Dict[str, Any],
    affected_resources: List[Dict[str, Any]],
    risk_assessment: Any
):
    """
    Background task to execute resolution

    This is the main execution flow after approval
    """
    logger.info(f"[{resolution_id}] Starting execution...")

    resolution = active_resolutions[resolution_id]
    resolution["status"] = "executing"

    try:
        # 1. Create rollback snapshot
        logger.info(f"[{resolution_id}] Creating rollback snapshot...")
        snapshot = await rollback_manager.create_snapshot(
            resolution_id=resolution_id,
            client_id=resolution["client_id"],
            namespace=resolution.get("namespace", "default"),
            action_type=resolution["action_type"],
            affected_resources=affected_resources
        )

        resolution["snapshot_id"] = snapshot.snapshot_id
        logger.info(f"[{resolution_id}] Snapshot created: {snapshot.snapshot_id}")

        # 2. Check token budget
        allowed, reason = token_budget_manager.check_budget(resolution_id, 10000)
        if not allowed:
            raise RuntimeError(f"Token budget check failed: {reason}")

        # 3. Execute remediation
        logger.info(f"[{resolution_id}] Executing remediation...")
        result = await remediation_executor.execute_remediation(
            resolution_id=resolution_id,
            action_type=resolution["action_type"],
            action_description=request.action_description if request else "Auto-execution",
            affected_resources=affected_resources,
            context=context,
            namespace=resolution.get("namespace", "default"),
            client_id=resolution["client_id"]
        )

        resolution["execution_result"] = {
            "execution_id": result.execution_id,
            "success": result.success,
            "output": result.output,
            "commands_executed": result.commands_executed,
            "error": result.error,
            "completed_at": result.completed_at
        }

        # 4. Determine final status
        if result.success:
            resolution["status"] = "completed"
            logger.info(f"[{resolution_id}] Execution completed successfully")
        else:
            resolution["status"] = "failed"
            logger.error(f"[{resolution_id}] Execution failed: {result.error}")

            # Auto-rollback on failure if configured
            # For now, just log - user can manually rollback
            logger.warning(f"[{resolution_id}] Manual rollback may be required: snapshot={snapshot.snapshot_id}")

    except Exception as e:
        logger.error(f"[{resolution_id}] Execution exception: {e}", exc_info=True)
        resolution["status"] = "failed"
        resolution["execution_result"] = {
            "success": False,
            "error": str(e)
        }
