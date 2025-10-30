"""
RCA API endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any
import time
import logging

from ..models.schemas import (
    RCARequest,
    RCAResponse,
    CausalChain
)
from ..services.neo4j_service import neo4j_service
from ..services.gpt5_service import gpt5_service
from ..services.slack_service import slack_service
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze", response_model=RCAResponse)
async def analyze_rca(
    request: RCARequest,
    background_tasks: BackgroundTasks
):
    """
    Perform intelligent RCA analysis using GPT-5 and Neo4j

    This endpoint:
    1. Searches Neo4j for relevant events and causal relationships
    2. Uses GPT-5 to analyze the data and provide insights
    3. Returns root causes, causal chains, and remediation steps

    Example:
    ```json
    {
      "query": "Why did nginx pods fail in the default namespace?",
      "client_id": "ab-01",
      "time_range_hours": 24,
      "reasoning_effort": "medium",
      "include_remediation": true
    }
    ```
    """
    start_time = time.time()
    client_id = request.client_id or settings.default_client_id

    try:
        logger.info(f"Starting RCA analysis for client {client_id}: {request.query}")

        # Step 1: Find root causes from Neo4j
        root_causes = neo4j_service.find_root_causes(
            client_id=client_id,
            time_range_hours=request.time_range_hours,
            limit=10
        )

        logger.info(f"Found {len(root_causes)} potential root causes")

        # Step 2: Get causal chains for top root causes
        causal_chains_data = []
        for rc in root_causes[:3]:  # Top 3 root causes
            chain = neo4j_service.find_causal_chain(
                event_id=rc['event_id'],
                client_id=client_id,
                max_hops=3
            )
            if chain:
                causal_chains_data.append(chain)

        logger.info(f"Found {len(causal_chains_data)} causal chains")

        # Step 3: Get blast radius for primary root cause
        blast_radius = []
        if root_causes:
            blast_radius = neo4j_service.get_blast_radius(
                root_event_id=root_causes[0]['event_id'],
                client_id=client_id,
                limit=50
            )

        logger.info(f"Blast radius: {len(blast_radius)} affected events")

        # Step 4: Get cross-service failures
        cross_service_failures = neo4j_service.get_cross_service_failures(
            client_id=client_id,
            time_range_hours=request.time_range_hours,
            limit=20
        )

        logger.info(f"Found {len(cross_service_failures)} cross-service failures")

        # Step 5: Use GPT-5 to analyze and provide insights
        gpt5_analysis = await gpt5_service.analyze_rca(
            query=request.query,
            root_causes=root_causes,
            causal_chains=causal_chains_data,
            blast_radius=blast_radius,
            cross_service_failures=cross_service_failures,
            reasoning_effort=request.reasoning_effort.value,
            verbosity=request.verbosity.value,
            include_remediation=request.include_remediation
        )

        logger.info("GPT-5 analysis completed")

        # Convert causal chains to response format
        causal_chains_response = []
        for chain in causal_chains_data:
            chain_items = []
            for step in chain:
                chain_items.append(CausalChain(
                    step=step['step'],
                    event_reason=step['reason'],
                    resource=f"{step['resource_kind']}/{step['resource_name']}",
                    namespace=step['namespace'],
                    timestamp=step['timestamp'],
                    confidence=step.get('confidence_to_next', 1.0) or 1.0,
                    is_root_cause=(step['step'] == 1)
                ))
            causal_chains_response.append(chain_items)

        # Calculate confidence score
        confidence_map = {"high": 0.9, "medium": 0.7, "low": 0.4}
        confidence_score = confidence_map.get(
            gpt5_analysis.get("confidence_assessment", "medium"),
            0.7
        )

        # Build response
        response = RCAResponse(
            query=request.query,
            summary=gpt5_analysis.get("summary", "Analysis completed"),
            root_causes=root_causes,
            causal_chains=causal_chains_response,
            affected_resources=blast_radius,
            remediation_steps=gpt5_analysis.get("remediation_steps"),
            confidence_score=confidence_score,
            reasoning_tokens=gpt5_analysis.get("reasoning_tokens"),
            processing_time_ms=int((time.time() - start_time) * 1000)
        )

        # Background task: Send Slack alert if critical
        if root_causes and request.include_remediation:
            background_tasks.add_task(
                _maybe_send_slack_alert,
                client_id,
                root_causes[0],
                gpt5_analysis
            )

        return response

    except Exception as e:
        logger.error(f"RCA analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"RCA analysis failed: {str(e)}")


@router.get("/root-causes/{client_id}")
async def get_root_causes(
    client_id: str,
    time_range_hours: int = 24,
    limit: int = 10
):
    """
    Get list of likely root causes

    Returns events that have no upstream causes but caused downstream events
    """
    try:
        root_causes = neo4j_service.find_root_causes(
            client_id=client_id,
            time_range_hours=time_range_hours,
            limit=limit
        )

        return {
            "client_id": client_id,
            "time_range_hours": time_range_hours,
            "root_causes": root_causes,
            "count": len(root_causes)
        }

    except Exception as e:
        logger.error(f"Failed to get root causes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/causal-chain/{event_id}")
async def get_causal_chain(
    event_id: str,
    client_id: str,
    max_hops: int = 3
):
    """
    Get causal chain leading to a specific event
    """
    try:
        chain = neo4j_service.find_causal_chain(
            event_id=event_id,
            client_id=client_id,
            max_hops=max_hops
        )

        return {
            "event_id": event_id,
            "client_id": client_id,
            "causal_chain": chain,
            "length": len(chain)
        }

    except Exception as e:
        logger.error(f"Failed to get causal chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blast-radius/{event_id}")
async def get_blast_radius(
    event_id: str,
    client_id: str,
    limit: int = 50
):
    """
    Get blast radius (all events affected by a root cause)
    """
    try:
        blast_radius = neo4j_service.get_blast_radius(
            root_event_id=event_id,
            client_id=client_id,
            limit=limit
        )

        return {
            "root_event_id": event_id,
            "client_id": client_id,
            "affected_events": blast_radius,
            "blast_radius_size": len(blast_radius)
        }

    except Exception as e:
        logger.error(f"Failed to get blast radius: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cross-service-failures/{client_id}")
async def get_cross_service_failures(
    client_id: str,
    time_range_hours: int = 24,
    limit: int = 20
):
    """
    Get failures that propagated across services (topology-enhanced)
    """
    try:
        failures = neo4j_service.get_cross_service_failures(
            client_id=client_id,
            time_range_hours=time_range_hours,
            limit=limit
        )

        return {
            "client_id": client_id,
            "time_range_hours": time_range_hours,
            "cross_service_failures": failures,
            "count": len(failures)
        }

    except Exception as e:
        logger.error(f"Failed to get cross-service failures: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runbook")
async def generate_runbook(
    failure_pattern: str,
    resource_type: str
):
    """
    Generate runbook for a failure pattern using GPT-5
    """
    try:
        runbook = await gpt5_service.suggest_runbook(
            failure_pattern=failure_pattern,
            resource_type=resource_type
        )

        return runbook

    except Exception as e:
        logger.error(f"Failed to generate runbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _maybe_send_slack_alert(
    client_id: str,
    root_cause: Dict[str, Any],
    analysis: Dict[str, Any]
):
    """
    Background task to send Slack alert for critical incidents
    """
    try:
        # Determine if this is critical enough for Slack
        blast_radius = root_cause.get('blast_radius', 0)
        if blast_radius < 5:  # Only alert if significant impact
            return

        incident_data = {
            "client_id": client_id,
            "title": f"RCA Alert: {root_cause['reason']} in {root_cause['namespace']}",
            "description": analysis.get("summary", "")[:200],
            "root_cause": f"{root_cause['reason']} on {root_cause['resource_kind']}/{root_cause['resource_name']}",
            "affected_resources": [f"{root_cause['resource_kind']}/{root_cause['resource_name']}"],
            "severity": "high" if blast_radius > 10 else "medium",
            "timestamp": str(root_cause['timestamp']),
            "tags": [root_cause['reason'], root_cause['namespace']]
        }

        slack_service.send_rca_alert(incident_data)
        logger.info(f"Sent Slack alert for incident: {root_cause['event_id']}")

    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
