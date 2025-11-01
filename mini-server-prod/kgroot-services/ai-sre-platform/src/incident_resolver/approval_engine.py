"""
Approval Engine - Manages customer approval workflow for remediation actions
"""

import logging
import asyncio
from enum import Enum
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
import uuid

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Approval status for remediation actions"""
    PENDING = "PENDING"       # Waiting for customer approval
    APPROVED = "APPROVED"     # Customer approved
    REJECTED = "REJECTED"     # Customer rejected
    TIMEOUT = "TIMEOUT"       # Approval request timed out
    AUTO_APPROVED = "AUTO_APPROVED"  # Auto-approved (LOW risk only)


@dataclass
class ApprovalRequest:
    """Approval request data"""
    approval_id: str
    resolution_id: str
    client_id: str
    action_type: str
    action_description: str
    risk_level: str
    risk_factors: list
    affected_resources: list
    estimated_impact: str
    mitigation_steps: list
    rollback_complexity: str
    created_at: str
    expires_at: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class ApprovalEngine:
    """
    Manages customer approval workflow

    Features:
    - Automatic approval for LOW risk actions
    - Manual approval required for MEDIUM+ risk
    - Timeout handling (default 5 minutes)
    - Approval history tracking
    - Customer notification callbacks
    """

    def __init__(self, default_timeout_seconds: int = 300):
        """
        Args:
            default_timeout_seconds: Default timeout for approval requests (5 minutes)
        """
        self.default_timeout = default_timeout_seconds
        self.pending_approvals: Dict[str, ApprovalRequest] = {}
        self.approval_history: Dict[str, ApprovalRequest] = {}
        self.notification_callback: Optional[Callable] = None

    def set_notification_callback(self, callback: Callable):
        """
        Set callback for sending notifications to customers

        Callback signature: async def notify(approval_request: ApprovalRequest) -> bool
        """
        self.notification_callback = callback

    async def request_approval(
        self,
        resolution_id: str,
        client_id: str,
        action_type: str,
        action_description: str,
        risk_assessment: Any,  # RiskAssessment object
        affected_resources: list,
        timeout_seconds: Optional[int] = None
    ) -> ApprovalRequest:
        """
        Request approval for a remediation action

        Args:
            resolution_id: Incident resolution ID
            client_id: Client/tenant ID
            action_type: Type of action
            action_description: Human-readable description
            risk_assessment: RiskAssessment from RiskAssessor
            affected_resources: List of affected resources
            timeout_seconds: Custom timeout (defaults to 5 minutes)

        Returns:
            ApprovalRequest object
        """
        approval_id = str(uuid.uuid4())
        timeout = timeout_seconds or self.default_timeout

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=timeout)

        # Auto-approve LOW risk actions
        if risk_assessment.level == "LOW":
            logger.info(f"Auto-approving LOW risk action: {action_type}")
            approval_request = ApprovalRequest(
                approval_id=approval_id,
                resolution_id=resolution_id,
                client_id=client_id,
                action_type=action_type,
                action_description=action_description,
                risk_level=risk_assessment.level,
                risk_factors=risk_assessment.risk_factors,
                affected_resources=affected_resources,
                estimated_impact=risk_assessment.estimated_impact,
                mitigation_steps=risk_assessment.mitigation_steps,
                rollback_complexity=risk_assessment.rollback_complexity,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
                status=ApprovalStatus.AUTO_APPROVED,
                approved_at=now.isoformat()
            )
            self.approval_history[approval_id] = approval_request
            return approval_request

        # Create approval request for MEDIUM+ risk
        approval_request = ApprovalRequest(
            approval_id=approval_id,
            resolution_id=resolution_id,
            client_id=client_id,
            action_type=action_type,
            action_description=action_description,
            risk_level=risk_assessment.level,
            risk_factors=risk_assessment.risk_factors,
            affected_resources=affected_resources,
            estimated_impact=risk_assessment.estimated_impact,
            mitigation_steps=risk_assessment.mitigation_steps,
            rollback_complexity=risk_assessment.rollback_complexity,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            status=ApprovalStatus.PENDING
        )

        self.pending_approvals[approval_id] = approval_request
        logger.info(f"Created approval request {approval_id} for {action_type} (risk: {risk_assessment.level})")

        # Send notification to customer
        if self.notification_callback:
            try:
                await self.notification_callback(approval_request)
                logger.info(f"Sent approval notification for {approval_id}")
            except Exception as e:
                logger.error(f"Failed to send approval notification: {e}")

        # Start timeout timer
        asyncio.create_task(self._handle_timeout(approval_id, timeout))

        return approval_request

    async def approve(
        self,
        approval_id: str,
        approved_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Approve a pending request

        Args:
            approval_id: Approval request ID
            approved_by: User who approved (email, username, etc.)
            notes: Optional approval notes

        Returns:
            True if approved successfully, False if not found or already processed
        """
        if approval_id not in self.pending_approvals:
            logger.warning(f"Approval {approval_id} not found or already processed")
            return False

        approval = self.pending_approvals[approval_id]

        # Check if expired
        if datetime.now(timezone.utc) > datetime.fromisoformat(approval.expires_at):
            logger.warning(f"Approval {approval_id} has expired")
            approval.status = ApprovalStatus.TIMEOUT
            self.approval_history[approval_id] = approval
            del self.pending_approvals[approval_id]
            return False

        # Approve
        approval.status = ApprovalStatus.APPROVED
        approval.approved_by = approved_by
        approval.approved_at = datetime.now(timezone.utc).isoformat()

        # Move to history
        self.approval_history[approval_id] = approval
        del self.pending_approvals[approval_id]

        logger.info(f"Approval {approval_id} approved by {approved_by}")
        return True

    async def reject(
        self,
        approval_id: str,
        rejected_by: str,
        reason: str
    ) -> bool:
        """
        Reject a pending request

        Args:
            approval_id: Approval request ID
            rejected_by: User who rejected
            reason: Rejection reason

        Returns:
            True if rejected successfully, False if not found
        """
        if approval_id not in self.pending_approvals:
            logger.warning(f"Approval {approval_id} not found or already processed")
            return False

        approval = self.pending_approvals[approval_id]

        # Reject
        approval.status = ApprovalStatus.REJECTED
        approval.approved_by = rejected_by
        approval.approved_at = datetime.now(timezone.utc).isoformat()
        approval.rejection_reason = reason

        # Move to history
        self.approval_history[approval_id] = approval
        del self.pending_approvals[approval_id]

        logger.info(f"Approval {approval_id} rejected by {rejected_by}: {reason}")
        return True

    async def wait_for_approval(
        self,
        approval_id: str,
        poll_interval: float = 1.0
    ) -> ApprovalStatus:
        """
        Wait for approval decision (blocking)

        Args:
            approval_id: Approval request ID
            poll_interval: Polling interval in seconds

        Returns:
            Final approval status (APPROVED, REJECTED, TIMEOUT, or AUTO_APPROVED)
        """
        # Check if auto-approved
        if approval_id in self.approval_history:
            approval = self.approval_history[approval_id]
            if approval.status == ApprovalStatus.AUTO_APPROVED:
                return ApprovalStatus.AUTO_APPROVED

        # Wait for approval
        while approval_id in self.pending_approvals:
            await asyncio.sleep(poll_interval)

        # Get final status from history
        if approval_id in self.approval_history:
            return self.approval_history[approval_id].status

        # Should not happen, but handle gracefully
        logger.error(f"Approval {approval_id} disappeared from tracking")
        return ApprovalStatus.TIMEOUT

    def get_approval_status(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Get current approval status"""
        # Check pending first
        if approval_id in self.pending_approvals:
            return self.pending_approvals[approval_id]

        # Check history
        if approval_id in self.approval_history:
            return self.approval_history[approval_id]

        return None

    def get_pending_approvals(self, client_id: Optional[str] = None) -> list:
        """Get all pending approvals, optionally filtered by client_id"""
        approvals = list(self.pending_approvals.values())

        if client_id:
            approvals = [a for a in approvals if a.client_id == client_id]

        return approvals

    def get_approval_history(
        self,
        client_id: Optional[str] = None,
        limit: int = 50
    ) -> list:
        """Get approval history, optionally filtered by client_id"""
        history = list(self.approval_history.values())

        if client_id:
            history = [a for a in history if a.client_id == client_id]

        # Sort by created_at (most recent first)
        history.sort(key=lambda x: x.created_at, reverse=True)

        return history[:limit]

    async def _handle_timeout(self, approval_id: str, timeout_seconds: int):
        """Handle approval timeout"""
        await asyncio.sleep(timeout_seconds)

        # Check if still pending
        if approval_id in self.pending_approvals:
            approval = self.pending_approvals[approval_id]
            approval.status = ApprovalStatus.TIMEOUT

            # Move to history
            self.approval_history[approval_id] = approval
            del self.pending_approvals[approval_id]

            logger.warning(f"Approval {approval_id} timed out after {timeout_seconds}s")

    def cleanup_old_history(self, days: int = 7):
        """Remove approval history older than N days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        to_remove = [
            approval_id
            for approval_id, approval in self.approval_history.items()
            if datetime.fromisoformat(approval.created_at) < cutoff
        ]

        for approval_id in to_remove:
            del self.approval_history[approval_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old approval records")
