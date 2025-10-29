"""
Health monitoring API endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
import logging

from ..models.schemas import HealthStatus, IncidentSummary
from ..services.neo4j_service import neo4j_service
from ..services.slack_service import slack_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status/{client_id}", response_model=HealthStatus)
async def get_health_status(client_id: str):
    """
    Get real-time health status for a client

    Returns:
    - Healthy vs unhealthy resource counts
    - Active incident count
    - Top issues in last 24 hours
    """
    try:
        health_data = neo4j_service.get_health_summary(client_id)

        if not health_data:
            raise HTTPException(status_code=404, detail="No health data found for client")

        total = health_data['total']
        healthy = health_data['healthy']
        health_pct = (healthy / total * 100) if total > 0 else 0

        return HealthStatus(
            client_id=client_id,
            healthy_resources=healthy,
            unhealthy_resources=health_data['unhealthy'],
            total_resources=total,
            active_incidents=health_data['active_incidents'],
            health_percentage=round(health_pct, 1),
            top_issues=health_data.get('top_issues', []),
            timestamp=health_data['timestamp']
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get health status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-health-report/{client_id}")
async def send_health_report(
    client_id: str,
    background_tasks: BackgroundTasks
):
    """
    Send health status report to Slack
    """
    try:
        health_data = neo4j_service.get_health_summary(client_id)

        if not health_data:
            raise HTTPException(status_code=404, detail="No health data found")

        # Calculate health percentage
        total = health_data['total']
        healthy = health_data['healthy']
        health_pct = (healthy / total * 100) if total > 0 else 0

        health_report = {
            "client_id": client_id,
            "healthy_resources": healthy,
            "unhealthy_resources": health_data['unhealthy'],
            "total_resources": total,
            "active_incidents": health_data['active_incidents'],
            "health_percentage": round(health_pct, 1),
            "top_issues": health_data.get('top_issues', [])
        }

        # Send to Slack in background
        background_tasks.add_task(
            slack_service.send_health_summary,
            health_report
        )

        return {
            "status": "success",
            "message": "Health report queued for Slack delivery",
            "health_summary": health_report
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send health report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/incidents/{client_id}")
async def get_active_incidents(client_id: str):
    """
    Get active incidents (root causes with significant blast radius)
    """
    try:
        # Get root causes from last hour with significant impact
        root_causes = neo4j_service.find_root_causes(
            client_id=client_id,
            time_range_hours=1,
            limit=20
        )

        incidents = []
        for rc in root_causes:
            if rc.get('blast_radius', 0) < 3:  # Skip minor issues
                continue

            # Get affected namespaces
            blast_radius = neo4j_service.get_blast_radius(
                root_event_id=rc['event_id'],
                client_id=client_id,
                limit=50
            )

            affected_services = set()
            affected_namespaces = set()
            for event in blast_radius:
                if event.get('resource_kind') == 'Service':
                    affected_services.add(event['resource_name'])
                affected_namespaces.add(event['namespace'])

            # Determine severity
            blast_size = rc.get('blast_radius', 0)
            if blast_size > 20:
                severity = "critical"
            elif blast_size > 10:
                severity = "high"
            elif blast_size > 5:
                severity = "medium"
            else:
                severity = "low"

            incident = IncidentSummary(
                incident_id=rc['event_id'],
                root_cause=f"{rc['reason']} on {rc['resource_kind']}/{rc['resource_name']}",
                affected_services=list(affected_services),
                affected_namespaces=list(affected_namespaces),
                severity=severity,
                started_at=rc['timestamp'],
                event_count=blast_size,
                blast_radius=blast_size
            )
            incidents.append(incident)

        return {
            "client_id": client_id,
            "incidents": incidents,
            "count": len(incidents)
        }

    except Exception as e:
        logger.error(f"Failed to get incidents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
