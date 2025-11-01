"""RCA utility endpoints for causality and root cause analysis"""

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)


class RunbookRequest(BaseModel):
    issue_description: str = Field(..., description="Description of the issue")
    root_causes: List[Dict[str, Any]] = Field(..., description="Root causes from RCA")
    blast_radius: Optional[Dict[str, Any]] = Field(None, description="Blast radius data")


@router.post("/build-causality/{client_id}")
async def build_causality(
    client_id: str,
    time_window_hours: int = Query(24, description="Hours of history to build causality for"),
    force_rebuild: bool = Query(False, description="Force rebuild even if relationships exist")
):
    """
    Build POTENTIAL_CAUSE relationships using the causality builder

    This triggers the enhanced KGroot algorithm to analyze temporal proximity,
    domain patterns, and topology to create causal relationships.
    """
    try:
        # Call the RCA API's build-causality endpoint
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"http://kg-rca-api-v2:8083/api/v1/rca/build-causality/{client_id}",
                params={
                    "time_window_hours": time_window_hours,
                    "force_rebuild": force_rebuild
                }
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPError as e:
        logger.error(f"Failed to build causality: {e}")
        raise HTTPException(status_code=502, detail=f"Causality builder failed: {str(e)}")
    except Exception as e:
        logger.error(f"Build causality error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/root-causes/{client_id}")
async def get_root_causes(
    client_id: str,
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    time_window_hours: int = Query(24, description="Hours of history"),
    limit: int = Query(10, ge=1, le=100)
):
    """
    Get root causes directly from Neo4j

    Returns events with low upstream causes but high downstream effects
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        to_time = datetime.now()
        from_time = to_time - timedelta(hours=time_window_hours)

        root_causes = orchestrator.neo4j.find_root_causes(
            client_id=client_id,
            time_range_hours=time_window_hours,
            limit=limit,
            namespace=namespace,
            from_time=from_time,
            to_time=to_time
        )

        return {
            "client_id": client_id,
            "namespace": namespace,
            "time_window": {
                "from": from_time.isoformat(),
                "to": to_time.isoformat(),
                "hours": time_window_hours
            },
            "root_causes": root_causes,
            "count": len(root_causes)
        }

    except Exception as e:
        logger.error(f"Failed to get root causes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/causal-chain/{event_id}")
async def get_causal_chain(
    event_id: str,
    client_id: str = Query(..., description="Client/tenant ID"),
    max_hops: int = Query(3, ge=1, le=10, description="Maximum hops to traverse")
):
    """
    Get causal chain from root cause to a specific event

    Traces the path of causality showing how one event led to another
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        chain = orchestrator.neo4j.find_causal_chain(
            event_id=event_id,
            client_id=client_id,
            max_hops=max_hops
        )

        return {
            "event_id": event_id,
            "client_id": client_id,
            "chain": chain,
            "length": len(chain)
        }

    except Exception as e:
        logger.error(f"Failed to get causal chain: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blast-radius/{event_id}")
async def get_blast_radius(
    event_id: str,
    client_id: str = Query(..., description="Client/tenant ID"),
    limit: int = Query(50, ge=1, le=500, description="Maximum affected events")
):
    """
    Get blast radius - all events affected by a root cause

    Shows downstream impact and propagation of failures
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        affected = orchestrator.neo4j.get_blast_radius(
            root_event_id=event_id,
            client_id=client_id,
            limit=limit
        )

        return {
            "root_event_id": event_id,
            "client_id": client_id,
            "affected_events": affected,
            "count": len(affected)
        }

    except Exception as e:
        logger.error(f"Failed to get blast radius: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cross-service-failures/{client_id}")
async def get_cross_service_failures(
    client_id: str,
    time_window_hours: int = Query(24, description="Hours of history"),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get failures that propagated across services

    Uses topology relationships to identify cross-service impact
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        failures = orchestrator.neo4j.get_cross_service_failures(
            client_id=client_id,
            time_window_hours=time_window_hours,
            limit=limit
        )

        return {
            "client_id": client_id,
            "time_window_hours": time_window_hours,
            "cross_service_failures": failures,
            "count": len(failures)
        }

    except Exception as e:
        logger.error(f"Failed to get cross-service failures: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runbook")
async def generate_runbook(request: RunbookRequest):
    """
    Generate automated runbook from RCA results

    Creates step-by-step remediation guide based on root causes and blast radius
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        # Use GPT-5 to generate runbook
        prompt = f"""Generate a detailed runbook for the following issue:

Issue: {request.issue_description}

Root Causes:
{chr(10).join([f"- {rc.get('reason', 'Unknown')}: {rc.get('resource', 'N/A')}" for rc in request.root_causes])}

Blast Radius: {request.blast_radius.get('affected_pods', 0) if request.blast_radius else 0} pods affected

Create a runbook with:
1. Executive Summary
2. Root Cause Analysis
3. Immediate Actions (stop the bleeding)
4. Remediation Steps (fix the root cause)
5. Prevention Measures (avoid recurrence)
6. Validation Steps (confirm fix)

Format each step with clear commands where applicable."""

        # Call GPT-5 via the synthesis method
        from openai import AsyncOpenAI
        import os

        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = await client.chat.completions.create(
            model="gpt-4",  # Fallback to GPT-4 if GPT-5 not available
            messages=[
                {"role": "system", "content": "You are an expert SRE creating operational runbooks."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        runbook = response.choices[0].message.content

        return {
            "issue": request.issue_description,
            "runbook": runbook,
            "root_causes_count": len(request.root_causes),
            "generated_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to generate runbook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
