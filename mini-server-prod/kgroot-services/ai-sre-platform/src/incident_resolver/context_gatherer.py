"""
Context Gatherer - Collects comprehensive incident context from knowledge graph and APIs
"""

import httpx
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class ContextGatherer:
    """
    Gathers incident context from:
    - Root cause analysis API
    - Causal chain API
    - Blast radius API
    - Topology API
    - Health monitoring API
    - Neo4j knowledge graph
    """

    def __init__(self, base_url: str = "http://localhost:8084", neo4j_service=None):
        """
        Args:
            base_url: Base URL for AI SRE Platform API
            neo4j_service: Optional Neo4jService for direct graph queries
        """
        self.base_url = base_url
        self.neo4j_service = neo4j_service
        self.timeout = httpx.Timeout(30.0)

    async def gather_incident_context(
        self,
        client_id: str,
        event_id: Optional[str] = None,
        namespace: Optional[str] = None,
        time_window_hours: float = 2.0
    ) -> Dict[str, Any]:
        """
        Gather comprehensive context for incident resolution

        Returns:
            {
                "root_causes": [...],
                "causal_chain": [...],
                "blast_radius": {...},
                "topology": {...},
                "health_status": {...},
                "affected_resources": [...],
                "error_summary": {...}
            }
        """
        logger.info(f"Gathering context for client_id={client_id}, event_id={event_id}, namespace={namespace}")

        context = {
            "client_id": client_id,
            "event_id": event_id,
            "namespace": namespace,
            "time_window_hours": time_window_hours,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            # 1. Get root causes
            try:
                response = await client.get(
                    f"/api/v1/rca/root-causes/{client_id}",
                    params={
                        "namespace": namespace,
                        "time_window_hours": time_window_hours,
                        "limit": 10
                    }
                )
                response.raise_for_status()
                context["root_causes"] = response.json().get("root_causes", [])
                logger.info(f"Found {len(context['root_causes'])} root causes")
            except Exception as e:
                logger.error(f"Failed to get root causes: {e}")
                context["root_causes"] = []

            # 2. Get causal chain if event_id provided
            if event_id:
                try:
                    response = await client.get(
                        f"/api/v1/rca/causal-chain/{event_id}",
                        params={"client_id": client_id, "max_hops": 5}
                    )
                    response.raise_for_status()
                    context["causal_chain"] = response.json().get("chain", [])
                    logger.info(f"Found causal chain with {len(context['causal_chain'])} events")
                except Exception as e:
                    logger.error(f"Failed to get causal chain: {e}")
                    context["causal_chain"] = []

            # 3. Get blast radius if event_id provided
            if event_id:
                try:
                    response = await client.get(
                        f"/api/v1/rca/blast-radius/{event_id}",
                        params={"client_id": client_id, "limit": 100}
                    )
                    response.raise_for_status()
                    blast_data = response.json()
                    context["blast_radius"] = {
                        "affected_events": blast_data.get("affected_events", []),
                        "count": blast_data.get("count", 0)
                    }
                    logger.info(f"Blast radius: {context['blast_radius']['count']} affected events")
                except Exception as e:
                    logger.error(f"Failed to get blast radius: {e}")
                    context["blast_radius"] = {"affected_events": [], "count": 0}

            # 4. Get health status
            try:
                response = await client.get(
                    f"/api/v1/health/status/{client_id}",
                    params={
                        "namespace": namespace,
                        "time_window_hours": time_window_hours
                    }
                )
                response.raise_for_status()
                context["health_status"] = response.json()
                logger.info(f"Health status: {context['health_status'].get('overall_status')}")
            except Exception as e:
                logger.error(f"Failed to get health status: {e}")
                context["health_status"] = {}

            # 5. Get active incidents
            try:
                response = await client.get(
                    f"/api/v1/health/incidents/{client_id}",
                    params={"namespace": namespace, "severity": None}
                )
                response.raise_for_status()
                incidents_data = response.json()
                context["active_incidents"] = incidents_data.get("incidents", [])
                logger.info(f"Found {len(context['active_incidents'])} active incidents")
            except Exception as e:
                logger.error(f"Failed to get active incidents: {e}")
                context["active_incidents"] = []

            # 6. Get namespaces for catalog info
            try:
                response = await client.get(
                    f"/api/v1/catalog/namespaces/{client_id}",
                    params={"include_counts": True}
                )
                response.raise_for_status()
                context["namespaces"] = response.json().get("namespaces", [])
            except Exception as e:
                logger.error(f"Failed to get namespaces: {e}")
                context["namespaces"] = []

        # 7. Extract affected resources from root causes
        context["affected_resources"] = self._extract_affected_resources(context)

        # 8. Create error summary
        context["error_summary"] = self._create_error_summary(context)

        logger.info(f"Context gathering complete: {len(context['root_causes'])} root causes, "
                   f"{len(context.get('affected_resources', []))} affected resources")

        return context

    def _extract_affected_resources(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract unique affected resources from context"""
        resources = []
        seen = set()

        # From root causes
        for rc in context.get("root_causes", []):
            resource = rc.get("resource", {})
            if resource and resource.get("name"):
                key = f"{resource.get('kind', 'Unknown')}:{resource.get('namespace', '')}:{resource['name']}"
                if key not in seen:
                    seen.add(key)
                    resources.append({
                        "kind": resource.get("kind", "Unknown"),
                        "name": resource["name"],
                        "namespace": resource.get("namespace"),
                        "source": "root_cause"
                    })

        # From active incidents
        for incident in context.get("active_incidents", []):
            resource = incident.get("resource", {})
            if resource and resource.get("name"):
                key = f"{resource.get('kind', 'Unknown')}:{resource.get('namespace', '')}:{resource['name']}"
                if key not in seen:
                    seen.add(key)
                    resources.append({
                        "kind": resource.get("kind", "Unknown"),
                        "name": resource["name"],
                        "namespace": resource.get("namespace"),
                        "source": "active_incident"
                    })

        return resources

    def _create_error_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Create summary of errors and issues"""
        root_causes = context.get("root_causes", [])
        incidents = context.get("active_incidents", [])
        health = context.get("health_status", {})

        # Count error types
        error_types = {}
        for rc in root_causes:
            reason = rc.get("reason", "Unknown")
            error_types[reason] = error_types.get(reason, 0) + 1

        for incident in incidents:
            reason = incident.get("reason", "Unknown")
            error_types[reason] = error_types.get(reason, 0) + 1

        # Determine severity
        critical_count = sum(1 for i in incidents if i.get("severity") == "critical")
        high_count = sum(1 for i in incidents if i.get("severity") == "high")

        if critical_count > 0:
            overall_severity = "CRITICAL"
        elif high_count > 0:
            overall_severity = "HIGH"
        elif len(incidents) > 0:
            overall_severity = "MEDIUM"
        else:
            overall_severity = "LOW"

        return {
            "overall_severity": overall_severity,
            "total_root_causes": len(root_causes),
            "total_incidents": len(incidents),
            "critical_incidents": critical_count,
            "high_incidents": high_count,
            "error_types": error_types,
            "health_overall_status": health.get("overall_status", "unknown"),
            "total_errors": health.get("total_errors", 0)
        }

    async def get_resource_topology(
        self,
        client_id: str,
        namespace: str,
        resource_name: str,
        depth: int = 2
    ) -> Optional[Dict[str, Any]]:
        """Get topology for a specific resource"""
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.get(
                    f"/api/v1/catalog/topology/{client_id}/{namespace}/{resource_name}",
                    params={"depth": depth}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get topology for {resource_name}: {e}")
            return None
