"""Catalog API endpoints for resource discovery and topology"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/namespaces/{client_id}")
async def get_namespaces(
    client_id: str,
    include_counts: bool = Query(True, description="Include resource counts per namespace")
):
    """
    Get all namespaces for a client

    Returns list of namespaces with optional resource counts
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        query = """
        MATCH (r:Resource {client_id: $client_id})
        WHERE r.ns IS NOT NULL
        WITH r.ns as namespace, count(r) as resource_count
        RETURN namespace, resource_count
        ORDER BY namespace
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(query, client_id=client_id)
            namespaces = [
                {
                    "namespace": record["namespace"],
                    "resource_count": record["resource_count"] if include_counts else None
                }
                for record in result
            ]

        return {
            "client_id": client_id,
            "namespaces": namespaces,
            "total": len(namespaces)
        }

    except Exception as e:
        logger.error(f"Failed to get namespaces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/{client_id}")
async def get_resources(
    client_id: str,
    namespace: Optional[str] = Query(None, description="Filter by namespace"),
    kind: Optional[str] = Query(None, description="Filter by resource kind (Pod, Service, etc.)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results")
):
    """
    Get resources catalog with optional filters

    Returns list of resources with metadata
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        # Build query with optional filters
        where_clauses = ["r.client_id = $client_id"]
        params = {"client_id": client_id, "limit": limit}

        if namespace:
            where_clauses.append("r.ns = $namespace")
            params["namespace"] = namespace

        if kind:
            where_clauses.append("r.kind = $kind")
            params["kind"] = kind

        query = f"""
        MATCH (r:Resource)
        WHERE {" AND ".join(where_clauses)}
        RETURN r.kind as kind, r.name as name, r.ns as namespace,
               r.owner as owner, r.labels as labels
        ORDER BY r.ns, r.kind, r.name
        LIMIT $limit
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(query, **params)
            resources = [
                {
                    "kind": record["kind"],
                    "name": record["name"],
                    "namespace": record["namespace"],
                    "owner": record["owner"],
                    "labels": record["labels"]
                }
                for record in result
            ]

        return {
            "client_id": client_id,
            "filters": {"namespace": namespace, "kind": kind},
            "resources": resources,
            "count": len(resources)
        }

    except Exception as e:
        logger.error(f"Failed to get resources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/owners/{client_id}")
async def get_owners(
    client_id: str,
    namespace: Optional[str] = Query(None, description="Filter by namespace")
):
    """
    Get resource owners (Deployments, StatefulSets, DaemonSets, etc.)

    Returns list of owner resources with their managed resources
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        where_clause = "r.client_id = $client_id AND r.owner IS NOT NULL"
        params = {"client_id": client_id}

        if namespace:
            where_clause += " AND r.ns = $namespace"
            params["namespace"] = namespace

        query = f"""
        MATCH (r:Resource)
        WHERE {where_clause}
        WITH r.owner as owner, r.ns as namespace, collect({{kind: r.kind, name: r.name}}) as managed_resources
        RETURN owner, namespace, managed_resources, size(managed_resources) as count
        ORDER BY namespace, owner
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(query, **params)
            owners = [
                {
                    "owner": record["owner"],
                    "namespace": record["namespace"],
                    "managed_resources": record["managed_resources"],
                    "count": record["count"]
                }
                for record in result
            ]

        return {
            "client_id": client_id,
            "namespace": namespace,
            "owners": owners,
            "total": len(owners)
        }

    except Exception as e:
        logger.error(f"Failed to get owners: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topology/{client_id}/{namespace}/{resource_name}")
async def get_topology(
    client_id: str,
    namespace: str,
    resource_name: str,
    depth: int = Query(2, ge=1, le=5, description="Traversal depth")
):
    """
    Get topology view for a specific resource

    Returns connected resources via RUNS_ON, SELECTS, CONTROLS relationships
    """
    from src.api.main import orchestrator

    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    try:
        query = f"""
        MATCH (r:Resource {{client_id: $client_id, ns: $namespace, name: $resource_name}})

        // Get connected resources within depth
        CALL {{
            WITH r
            MATCH path = (r)-[:RUNS_ON|SELECTS|CONTROLS*1..{depth}]-(connected)
            RETURN connected, relationships(path) as rels
        }}

        RETURN r as source,
               collect(DISTINCT {{
                   resource: connected,
                   relationships: [rel IN rels | type(rel)]
               }}) as topology
        """

        with orchestrator.neo4j.driver.session() as session:
            result = session.run(
                query,
                client_id=client_id,
                namespace=namespace,
                resource_name=resource_name
            )

            record = result.single()
            if not record:
                raise HTTPException(status_code=404, detail="Resource not found")

            source = record["source"]
            topology_data = record["topology"]

            return {
                "client_id": client_id,
                "source": {
                    "kind": source["kind"],
                    "name": source["name"],
                    "namespace": source["ns"]
                },
                "topology": [
                    {
                        "kind": t["resource"]["kind"],
                        "name": t["resource"]["name"],
                        "namespace": t["resource"].get("ns"),
                        "relationships": t["relationships"]
                    }
                    for t in topology_data if t["resource"]
                ],
                "depth": depth
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get topology: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
