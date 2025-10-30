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


@router.post("/build-causality/{client_id}")
async def build_causality_on_demand(
    client_id: str,
    time_range_hours: int = 24,
    min_confidence: float = 0.3,
    build_relationships: bool = True
):
    """
    Build POTENTIAL_CAUSE relationships on-demand for a client

    This analyzes events and creates causal relationships based on:
    - Adaptive time windows (2-15 min based on failure type)
    - 30+ domain knowledge patterns (KGroot paper)
    - Service topology integration (SELECTS, RUNS_ON, CONTROLS)
    - Top-5 filtering (keeps only top 5 causes per event)
    - Multi-dimensional confidence scoring

    Parameters:
    - client_id: Client identifier
    - time_range_hours: Hours of history to analyze (default 24)
    - min_confidence: Minimum confidence threshold (default 0.3)
    - build_relationships: If True, creates relationships; if False, only diagnostics

    Use this after ingesting new events to immediately build the causal graph.
    """
    try:
        logger.info(f"Building causality for client {client_id} (build={build_relationships})")
        start_time = time.time()

        # Count events before building
        count_query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > datetime() - duration({hours: $hours})
        RETURN count(e) as event_count
        """

        with neo4j_service.driver.session() as session:
            result = session.run(count_query, client_id=client_id, hours=time_range_hours)
            event_count = result.single()['event_count']

        # Count existing relationships before
        rel_count_query = """
        MATCH ()-[r:POTENTIAL_CAUSE {client_id: $client_id}]->()
        RETURN count(r) as relationship_count
        """

        with neo4j_service.driver.session() as session:
            result = session.run(rel_count_query, client_id=client_id)
            rel_count_before = result.single()['relationship_count']

        if not build_relationships:
            # Diagnostic mode only
            return {
                "client_id": client_id,
                "status": "diagnostic_complete",
                "events_found": event_count,
                "existing_relationships": rel_count_before,
                "message": f"Found {event_count} events and {rel_count_before} existing relationships.",
                "build_relationships": False
            }

        # ============================================================================
        # ENHANCED CAUSALITY BUILDING (from CREATE-CAUSAL-RELATIONSHIPS-ENHANCED.cypher)
        # ============================================================================

        causality_build_query = """
        MATCH (e1:Episodic)
        WHERE e1.client_id = $client_id
          AND e1.event_time > datetime() - duration({hours: $hours})

        MATCH (e2:Episodic)
        WHERE e2.client_id = $client_id
          AND e1.client_id = e2.client_id

        // Adaptive time window based on failure type
        WITH e1, e2,
             CASE
               WHEN e1.reason IN ['OOMKilled', 'Killing', 'Error'] THEN 2
               WHEN e1.reason CONTAINS 'ImagePull' THEN 5
               WHEN e1.reason IN ['FailedScheduling', 'FailedMount'] THEN 15
               ELSE 10
             END as adaptive_window_minutes

        WHERE e2.event_time > e1.event_time
          AND e2.event_time < e1.event_time + duration({minutes: adaptive_window_minutes})

        // Get resources and topology path
        OPTIONAL MATCH (e1)-[:ABOUT]->(r1:Resource {client_id: $client_id})
        OPTIONAL MATCH (e2)-[:ABOUT]->(r2:Resource {client_id: $client_id})
        OPTIONAL MATCH topology_path = (r1)-[:SELECTS|RUNS_ON|CONTROLS*1..3]-(r2)
        WHERE ALL(rel IN relationships(topology_path) WHERE rel.client_id = $client_id)

        WITH e1, e2, r1, r2, topology_path,
             duration.between(e1.event_time, e2.event_time).seconds as time_diff_seconds

        // Domain knowledge: 30+ Kubernetes failure patterns
        WITH e1, e2, r1, r2, topology_path, time_diff_seconds,
             CASE
               // Resource exhaustion patterns
               WHEN e1.reason = 'OOMKilled' AND e2.reason IN ['BackOff', 'Failed', 'Killing'] THEN 0.95
               WHEN e1.reason = 'OOMKilled' AND e2.reason = 'Evicted' THEN 0.90
               WHEN e1.reason = 'MemoryPressure' AND e2.reason IN ['OOMKilled', 'Evicted'] THEN 0.88
               WHEN e1.reason = 'DiskPressure' AND e2.reason IN ['Evicted', 'Failed'] THEN 0.85
               WHEN e1.reason = 'PIDPressure' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.82

               // Image/registry issues
               WHEN e1.reason CONTAINS 'ImagePull' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.90
               WHEN e1.reason = 'ImagePullBackOff' AND e2.reason = 'Failed' THEN 0.92
               WHEN e1.reason = 'ErrImagePull' AND e2.reason = 'ImagePullBackOff' THEN 0.93
               WHEN e1.reason = 'InvalidImageName' AND e2.reason CONTAINS 'ImagePull' THEN 0.88
               WHEN e1.reason = 'RegistryUnavailable' AND e2.reason CONTAINS 'ImagePull' THEN 0.87

               // Health check failures
               WHEN e1.reason = 'Unhealthy' AND e2.reason IN ['Killing', 'Failed', 'BackOff'] THEN 0.88
               WHEN e1.reason = 'ProbeWarning' AND e2.reason = 'Unhealthy' THEN 0.85
               WHEN e1.reason = 'LivenessProbe' AND e2.reason IN ['Killing', 'BackOff'] THEN 0.87
               WHEN e1.reason = 'ReadinessProbe' AND e2.reason = 'Unhealthy' THEN 0.83

               // Scheduling failures
               WHEN e1.reason = 'FailedScheduling' AND e2.reason IN ['Pending', 'Failed'] THEN 0.90
               WHEN e1.reason = 'Unschedulable' AND e2.reason = 'FailedScheduling' THEN 0.88
               WHEN e1.reason = 'NodeAffinity' AND e2.reason IN ['FailedScheduling', 'Pending'] THEN 0.86
               WHEN e1.reason = 'Taints' AND e2.reason IN ['FailedScheduling', 'Pending'] THEN 0.85
               WHEN e1.reason = 'InsufficientResources' AND e2.reason = 'FailedScheduling' THEN 0.89

               // Volume/mount issues
               WHEN e1.reason = 'FailedMount' AND e2.reason IN ['Failed', 'ContainerCreating'] THEN 0.88
               WHEN e1.reason = 'VolumeFailure' AND e2.reason IN ['FailedMount', 'Failed'] THEN 0.87
               WHEN e1.reason = 'FailedAttachVolume' AND e2.reason = 'FailedMount' THEN 0.90
               WHEN e1.reason = 'VolumeNotFound' AND e2.reason IN ['FailedMount', 'Failed'] THEN 0.86

               // Network failures
               WHEN e1.reason = 'NetworkNotReady' AND e2.reason IN ['Failed', 'Pending'] THEN 0.85
               WHEN e1.reason = 'FailedCreatePodSandBox' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.87
               WHEN e1.reason = 'CNIFailed' AND e2.reason = 'NetworkNotReady' THEN 0.88
               WHEN e1.reason = 'IPAllocationFailed' AND e2.reason IN ['Failed', 'Pending'] THEN 0.86
               WHEN e1.reason = 'DNSConfigForming' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.82

               // Crash/exit patterns
               WHEN e1.reason = 'Error' AND e2.reason IN ['BackOff', 'Failed', 'CrashLoopBackOff'] THEN 0.87
               WHEN e1.reason = 'Completed' AND e2.reason = 'BackOff' THEN 0.75
               WHEN e1.reason = 'CrashLoopBackOff' AND e2.reason = 'Failed' THEN 0.85
               WHEN e1.reason CONTAINS 'Exit' AND e2.reason IN ['BackOff', 'Failed'] THEN 0.80

               // Config/RBAC issues
               WHEN e1.reason = 'FailedCreate' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.84
               WHEN e1.reason = 'Forbidden' AND e2.reason IN ['Failed', 'FailedCreate'] THEN 0.88
               WHEN e1.reason = 'Unauthorized' AND e2.reason IN ['Failed', 'Forbidden'] THEN 0.87
               WHEN e1.reason = 'InvalidConfiguration' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.86
               WHEN e1.reason = 'ConfigMapNotFound' AND e2.reason IN ['Failed', 'BackOff'] THEN 0.85

               // Generic fallback
               ELSE 0.30
             END as domain_score

        // Temporal score: Linear decay over 5 minutes
        WITH e1, e2, r1, r2, topology_path, time_diff_seconds, domain_score,
             CASE
               WHEN time_diff_seconds <= 0 THEN 0.0
               WHEN time_diff_seconds >= 300 THEN 0.1
               ELSE 1.0 - (toFloat(time_diff_seconds) / 300.0) * 0.9
             END as temporal_score

        // Distance score: Topology-aware distance
        WITH e1, e2, time_diff_seconds, domain_score, temporal_score, topology_path, r1, r2,
             CASE
               WHEN r1.name = r2.name AND r1.name IS NOT NULL THEN 0.95
               WHEN topology_path IS NOT NULL AND length(topology_path) = 1 THEN 0.85
               WHEN topology_path IS NOT NULL AND length(topology_path) = 2 THEN 0.70
               WHEN topology_path IS NOT NULL AND length(topology_path) = 3 THEN 0.55
               WHEN r1.ns = r2.ns AND r1.kind = r2.kind AND r1.ns IS NOT NULL THEN 0.40
               ELSE 0.20
             END as distance_score

        // Overall confidence: Weighted combination
        WITH e1, e2, temporal_score, distance_score, domain_score, time_diff_seconds,
             (0.4 * temporal_score + 0.3 * distance_score + 0.3 * domain_score) as confidence

        WHERE confidence > $min_confidence

        // Top-5 filtering: Keep only top 5 causes per event
        WITH e2, e1, confidence, temporal_score, distance_score, domain_score, time_diff_seconds
        ORDER BY e2.eid, confidence DESC

        WITH e2, collect({
          e1_id: e1.eid,
          confidence: confidence,
          temporal_score: temporal_score,
          distance_score: distance_score,
          domain_score: domain_score,
          time_diff_seconds: time_diff_seconds
        })[0..5] as top_causes

        UNWIND top_causes as cause

        MATCH (e1:Episodic {eid: cause.e1_id, client_id: $client_id})

        // Create relationship with full client_id isolation
        MERGE (e1)-[pc:POTENTIAL_CAUSE]->(e2)
        ON CREATE SET
          pc.client_id = $client_id,
          pc.confidence = round(cause.confidence * 1000.0) / 1000.0,
          pc.temporal_score = round(cause.temporal_score * 1000.0) / 1000.0,
          pc.distance_score = round(cause.distance_score * 1000.0) / 1000.0,
          pc.domain_score = round(cause.domain_score * 1000.0) / 1000.0,
          pc.time_gap_seconds = cause.time_diff_seconds,
          pc.created_at = datetime(),
          pc.version = 'enhanced_v1'
        ON MATCH SET
          pc.confidence = round(cause.confidence * 1000.0) / 1000.0,
          pc.temporal_score = round(cause.temporal_score * 1000.0) / 1000.0,
          pc.distance_score = round(cause.distance_score * 1000.0) / 1000.0,
          pc.domain_score = round(cause.domain_score * 1000.0) / 1000.0,
          pc.time_gap_seconds = cause.time_diff_seconds,
          pc.updated_at = datetime()

        RETURN count(*) as relationships_created
        """

        logger.info(f"Executing enhanced causality building for {event_count} events...")

        # Execute the causality building query
        with neo4j_service.driver.session() as session:
            result = session.run(
                causality_build_query,
                client_id=client_id,
                hours=time_range_hours,
                min_confidence=min_confidence
            )
            relationships_created = result.single()['relationships_created']

        # Count relationships after
        with neo4j_service.driver.session() as session:
            result = session.run(rel_count_query, client_id=client_id)
            rel_count_after = result.single()['relationship_count']

        # Get statistics
        stats_query = """
        MATCH (e1:Episodic {client_id: $client_id})-[pc:POTENTIAL_CAUSE {client_id: $client_id}]->(e2:Episodic {client_id: $client_id})
        RETURN
          count(pc) as total_relationships,
          round(avg(pc.confidence) * 1000.0) / 1000.0 as avg_confidence,
          round(max(pc.confidence) * 1000.0) / 1000.0 as max_confidence,
          round(min(pc.confidence) * 1000.0) / 1000.0 as min_confidence
        """

        with neo4j_service.driver.session() as session:
            result = session.run(stats_query, client_id=client_id)
            stats = result.single()

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(f"Causality building complete: {relationships_created} relationships, {processing_time}ms")

        return {
            "client_id": client_id,
            "status": "success",
            "events_analyzed": event_count,
            "relationships_before": rel_count_before,
            "relationships_after": rel_count_after,
            "relationships_created_or_updated": relationships_created,
            "statistics": {
                "total_relationships": stats['total_relationships'],
                "avg_confidence": stats['avg_confidence'],
                "max_confidence": stats['max_confidence'],
                "min_confidence": stats['min_confidence']
            },
            "processing_time_ms": processing_time,
            "message": f"Successfully built {relationships_created} POTENTIAL_CAUSE relationships with enhanced KGroot algorithm",
            "next_steps": [
                "Query root causes: GET /api/v1/rca/root-causes/{client_id}",
                "Run RCA analysis: POST /api/v1/rca/analyze",
                "Check blast radius: GET /api/v1/rca/blast-radius/{event_id}"
            ]
        }

    except Exception as e:
        logger.error(f"Failed to build causality: {e}", exc_info=True)
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
