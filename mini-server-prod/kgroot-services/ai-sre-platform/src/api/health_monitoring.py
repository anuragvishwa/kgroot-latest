"""Health monitoring endpoints for cluster status and incidents"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class HealthReportRequest(BaseModel):
    channel: str = Field(..., description="Slack channel or notification target")
    include_recommendations: bool = Field(True, description="Include AI recommendations")


@router.get("/status/{client_id}")
async def get_health_status(
    client_id: str,
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    time_window_hours: int = Query(1, description="Time window for health check")
):
    """
    Get overall health status of the cluster

    Returns:
    - Pod health (Running, Failed, Pending)
    - Recent error events
    - Resource utilization alerts
    - Active incidents
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(hours=time_window_hours)

        # Query for health metrics
        query = """
        // Get pod status distribution
        MATCH (r:Resource {client_id: $client_id, kind: 'Pod'})
        WHERE ($namespace IS NULL OR r.ns = $namespace)
        WITH r.ns as namespace,
             count(CASE WHEN r.status = 'Running' THEN 1 END) as running,
             count(CASE WHEN r.status = 'Failed' THEN 1 END) as failed,
             count(CASE WHEN r.status = 'Pending' THEN 1 END) as pending,
             count(CASE WHEN r.status NOT IN ['Running', 'Failed', 'Pending'] THEN 1 END) as other

        // Get recent error events
        OPTIONAL MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > $from_time
          AND e.event_time <= $to_time
          AND e.reason IN ['Failed', 'BackOff', 'Unhealthy', 'OOMKilled', 'Error', 'CrashLoopBackOff']
          AND ($namespace IS NULL OR e.ns = $namespace)

        RETURN namespace,
               running, failed, pending, other,
               count(DISTINCT e) as recent_errors
        ORDER BY namespace
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                namespace=namespace,
                from_time=from_time,
                to_time=to_time
            )

            health_data = []
            total_errors = 0

            for record in result:
                ns_health = {
                    "namespace": record["namespace"],
                    "pods": {
                        "running": record["running"],
                        "failed": record["failed"],
                        "pending": record["pending"],
                        "other": record["other"]
                    },
                    "recent_errors": record["recent_errors"],
                    "status": "healthy" if record["failed"] == 0 and record["pending"] == 0 else "degraded"
                }
                health_data.append(ns_health)
                total_errors += record["recent_errors"]

            # Determine overall status
            overall_status = "healthy"
            if total_errors > 10:
                overall_status = "critical"
            elif total_errors > 0:
                overall_status = "warning"

            return {
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
                "time_window_hours": time_window_hours,
                "overall_status": overall_status,
                "total_errors": total_errors,
                "namespaces": health_data
            }

    except Exception as e:
        logger.error(f"Failed to get health status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/{client_id}")
async def get_active_incidents(
    client_id: str,
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low)")
):
    """
    Get active incidents based on recent failures and error patterns

    Identifies ongoing issues that require attention
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        # Look for events in the last 15 minutes that indicate active incidents
        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(minutes=15)

        # Find events with high blast radius (active incidents)
        query = """
        MATCH (e:Episodic {client_id: $client_id})
        WHERE e.event_time > $from_time
          AND e.event_time <= $to_time
          AND e.reason IN ['Failed', 'BackOff', 'Unhealthy', 'OOMKilled', 'Error', 'CrashLoopBackOff', 'FailedScheduling']
          AND ($namespace IS NULL OR e.ns = $namespace)

        OPTIONAL MATCH (e)-[:ABOUT]->(r:Resource)
        OPTIONAL MATCH (e)-[:POTENTIAL_CAUSE]->(downstream:Episodic {client_id: $client_id})

        WITH e, r, count(DISTINCT downstream) as blast_radius
        WHERE blast_radius > 0

        RETURN e.eid as event_id,
               e.reason as reason,
               e.event_time as timestamp,
               e.message as message,
               r.kind as resource_kind,
               r.name as resource_name,
               r.ns as namespace,
               blast_radius
        ORDER BY blast_radius DESC, e.event_time DESC
        LIMIT 20
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                namespace=namespace,
                from_time=from_time,
                to_time=to_time
            )

            incidents = []
            for record in result:
                # Determine severity based on blast radius and reason
                blast = record["blast_radius"]
                reason = record["reason"]

                if blast > 20 or reason in ['OOMKilled', 'CrashLoopBackOff']:
                    incident_severity = "critical"
                elif blast > 10 or reason in ['Failed', 'BackOff']:
                    incident_severity = "high"
                elif blast > 5:
                    incident_severity = "medium"
                else:
                    incident_severity = "low"

                # Skip if severity filter doesn't match
                if severity and incident_severity != severity:
                    continue

                incident = {
                    "event_id": record["event_id"],
                    "reason": reason,
                    "timestamp": record["timestamp"].isoformat() if record["timestamp"] else None,
                    "message": record["message"],
                    "resource": {
                        "kind": record["resource_kind"],
                        "name": record["resource_name"],
                        "namespace": record["namespace"]
                    },
                    "blast_radius": blast,
                    "severity": incident_severity,
                    "status": "active"
                }
                incidents.append(incident)

            return {
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat(),
                "incidents": incidents,
                "count": len(incidents),
                "filters": {"namespace": namespace, "severity": severity}
            }

    except Exception as e:
        logger.error(f"Failed to get incidents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-health-report/{client_id}")
async def send_health_report(
    client_id: str,
    request: HealthReportRequest
):
    """
    Generate and send health report to specified channel

    Creates a comprehensive health report with:
    - Current status
    - Active incidents
    - AI recommendations
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        # Get health status
        health_response = await get_health_status(client_id, namespace=None, time_window_hours=1)

        # Get active incidents
        incidents_response = await get_active_incidents(client_id, namespace=None, severity=None)

        # Generate report
        report = {
            "client_id": client_id,
            "generated_at": datetime.utcnow().isoformat(),
            "health_status": health_response,
            "active_incidents": incidents_response["incidents"],
            "summary": {
                "overall_status": health_response["overall_status"],
                "total_errors": health_response["total_errors"],
                "critical_incidents": len([i for i in incidents_response["incidents"] if i["severity"] == "critical"]),
                "high_incidents": len([i for i in incidents_response["incidents"] if i["severity"] == "high"])
            }
        }

        # TODO: Actually send to Slack/notification channel
        # For now, just return the report
        logger.info(f"Health report generated for {client_id}, channel: {request.channel}")

        return {
            "status": "success",
            "channel": request.channel,
            "report": report,
            "message": "Health report generated (notification integration pending)"
        }

    except Exception as e:
        logger.error(f"Failed to send health report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
