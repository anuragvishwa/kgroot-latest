"""
Catalog API endpoints - Resource catalog and topology views
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from ..models.schemas import ResourceFilter, ResourceInfo, TopologyView, CatalogResponse
from ..services.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/resources/{client_id}", response_model=CatalogResponse)
async def get_resources_catalog(
    client_id: str,
    kinds: Optional[List[str]] = Query(None, description="Filter by resource kinds"),
    namespaces: Optional[List[str]] = Query(None, description="Filter by namespaces"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500)
):
    """
    Get catalog of resources with metadata, ownership, dependencies

    Examples:
    - GET /api/v1/catalog/resources/ab-01?kinds=Pod&kinds=Service
    - GET /api/v1/catalog/resources/ab-01?namespaces=production&page=2
    """
    try:
        offset = (page - 1) * page_size

        result = neo4j_service.get_resources_catalog(
            client_id=client_id,
            kinds=kinds,
            namespaces=namespaces,
            limit=page_size,
            offset=offset
        )

        # Convert to ResourceInfo objects
        resources = [
            ResourceInfo(
                resource_id=r.get('name', ''),
                name=r['name'],
                kind=r['kind'],
                namespace=r['namespace'],
                client_id=client_id,
                labels=r.get('labels'),
                owner=r.get('owner'),
                size=r.get('size'),
                created_at=r['created_at'],
                dependencies=r.get('dependencies', []),
                recent_events=r.get('recent_events', 0)
            )
            for r in result['resources']
        ]

        return CatalogResponse(
            resources=resources,
            total_count=result['total_count'],
            filtered_count=len(resources),
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"Failed to get resources catalog: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topology/{client_id}/{namespace}/{resource_name}", response_model=TopologyView)
async def get_topology_view(
    client_id: str,
    namespace: str,
    resource_name: str
):
    """
    Get topology view for a specific resource

    Shows:
    - Pods selected by service
    - Nodes pods run on
    - Upstream/downstream services
    - Dependencies
    """
    try:
        topology = neo4j_service.get_topology_for_resource(
            resource_name=resource_name,
            namespace=namespace,
            client_id=client_id
        )

        if not topology:
            raise HTTPException(status_code=404, detail="Resource not found")

        # Determine health status
        unhealthy_pods = sum(1 for p in topology.get('pods', []) if p.get('status') != 'Running')
        health_status = "Healthy" if unhealthy_pods == 0 else "Degraded" if unhealthy_pods < len(topology.get('pods', [])) / 2 else "Unhealthy"

        return TopologyView(
            service_name=topology['service_name'],
            namespace=topology['namespace'],
            pods=topology.get('pods', []),
            nodes=topology.get('nodes', []),
            upstream_services=topology.get('upstream_services', []),
            downstream_services=topology.get('downstream_resources', []),
            health_status=health_status
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get topology view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/owners/{client_id}")
async def get_resource_owners(client_id: str):
    """
    Get list of resource owners/teams
    """
    try:
        # This would ideally come from your resource metadata
        # For now, return a simple aggregation
        resources = neo4j_service.get_resources_catalog(
            client_id=client_id,
            limit=10000
        )['resources']

        owners = {}
        for r in resources:
            owner = r.get('owner', 'Unknown')
            if owner not in owners:
                owners[owner] = {
                    "owner": owner,
                    "resource_count": 0,
                    "resource_types": set()
                }
            owners[owner]["resource_count"] += 1
            owners[owner]["resource_types"].add(r['kind'])

        # Convert sets to lists
        for owner_data in owners.values():
            owner_data["resource_types"] = list(owner_data["resource_types"])

        return {
            "client_id": client_id,
            "owners": list(owners.values())
        }

    except Exception as e:
        logger.error(f"Failed to get owners: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespaces/{client_id}")
async def get_namespaces(client_id: str):
    """
    Get list of namespaces with resource counts
    """
    try:
        resources = neo4j_service.get_resources_catalog(
            client_id=client_id,
            limit=10000
        )['resources']

        namespaces = {}
        for r in resources:
            ns = r['namespace']
            if ns not in namespaces:
                namespaces[ns] = {
                    "namespace": ns,
                    "resource_count": 0,
                    "resource_types": set()
                }
            namespaces[ns]["resource_count"] += 1
            namespaces[ns]["resource_types"].add(r['kind'])

        # Convert sets to lists
        for ns_data in namespaces.values():
            ns_data["resource_types"] = list(ns_data["resource_types"])

        return {
            "client_id": client_id,
            "namespaces": list(namespaces.values())
        }

    except Exception as e:
        logger.error(f"Failed to get namespaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))
