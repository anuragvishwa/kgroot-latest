"""
Search API endpoints - Natural language semantic search
"""
from fastapi import APIRouter, HTTPException
import time
import logging

from ..models.schemas import SearchRequest, SearchResponse, SearchResult
from ..services.neo4j_service import neo4j_service
from ..services.embedding_service import embedding_service
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=SearchResponse)
async def semantic_search(request: SearchRequest):
    """
    Natural language search across events and resources using embeddings

    Examples:
    - "show me all OOM errors in production namespace last 6 hours"
    - "find pods owned by team-backend that failed"
    - "what resources are in the default namespace"
    - "unhealthy services in the last hour"
    """
    start_time = time.time()
    client_id = request.client_id or settings.default_client_id

    try:
        logger.info(f"Search query: {request.query}")

        # Generate query embedding and search
        embedding_start = time.time()
        search_results = embedding_service.search(
            query=request.query,
            limit=request.limit,
            score_threshold=0.3  # Minimum similarity
        )
        embedding_time = int((time.time() - embedding_start) * 1000)

        logger.info(f"Found {len(search_results)} results from embedding search")

        # Filter results by client_id and other criteria
        filtered_results = []
        for metadata, similarity in search_results:
            # Check client_id match
            if client_id:
                if metadata['item_type'] == 'Event':
                    event_client = metadata['event_data'].get('client_id')
                    if event_client and event_client != client_id:
                        continue
                elif metadata['item_type'] == 'Resource':
                    resource_client = metadata['resource_data'].get('client_id')
                    if resource_client and resource_client != client_id:
                        continue

            # Apply time range filter
            if request.time_range_hours and metadata.get('timestamp'):
                from datetime import datetime, timedelta
                cutoff = datetime.now() - timedelta(hours=request.time_range_hours)
                if metadata['timestamp'] < cutoff:
                    continue

            # Apply namespace filter
            if request.namespaces:
                if metadata['item_type'] == 'Event':
                    ns = metadata['event_data'].get('namespace')
                else:
                    ns = metadata['resource_data'].get('namespace')

                if ns not in request.namespaces:
                    continue

            # Apply resource type filter
            if request.resource_types:
                if metadata['item_type'] == 'Event':
                    kind = metadata['event_data'].get('resource_kind')
                else:
                    kind = metadata['resource_data'].get('kind')

                if kind not in request.resource_types:
                    continue

            # Build search result
            result = SearchResult(
                item_type=metadata['item_type'],
                item_id=metadata['item_id'],
                content=metadata['content'],
                metadata=metadata.get('event_data') or metadata.get('resource_data', {}),
                similarity_score=similarity,
                timestamp=metadata.get('timestamp')
            )
            filtered_results.append(result)

        total_time = int((time.time() - start_time) * 1000)

        return SearchResponse(
            query=request.query,
            results=filtered_results[:request.limit],
            total_results=len(filtered_results),
            query_embedding_time_ms=embedding_time,
            search_time_ms=total_time
        )

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/rebuild-index/{client_id}")
async def rebuild_search_index(
    client_id: str,
    time_range_hours: int = 24
):
    """
    Rebuild the semantic search index for a client

    This should be called periodically (e.g., every hour) to keep the index fresh
    """
    try:
        logger.info(f"Rebuilding search index for client {client_id}")

        # Get recent events
        events = neo4j_service.find_events_by_criteria(
            client_id=client_id,
            time_range_hours=time_range_hours,
            limit=10000
        )

        # Get resources
        resources_data = neo4j_service.get_resources_catalog(
            client_id=client_id,
            limit=5000
        )
        resources = resources_data["resources"]

        # Rebuild index
        embedding_service.rebuild_index(events, resources)

        return {
            "status": "success",
            "client_id": client_id,
            "events_indexed": len(events),
            "resources_indexed": len(resources),
            "total_items": len(events) + len(resources)
        }

    except Exception as e:
        logger.error(f"Failed to rebuild index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions")
async def get_search_suggestions(
    partial_query: str,
    limit: int = 5
):
    """
    Get search query suggestions based on partial input

    Useful for autocomplete/typeahead functionality
    """
    # Common search templates
    suggestions = [
        "show me all OOM errors in {namespace}",
        "find pods that failed in the last {hours} hours",
        "what resources are owned by {team}",
        "unhealthy services in {namespace}",
        "pods with high memory usage",
        "failed deployments in production",
        "recent image pull errors",
        "network failures affecting {service}",
    ]

    # Filter based on partial query
    partial_lower = partial_query.lower()
    matched = [s for s in suggestions if partial_lower in s.lower()]

    return {
        "suggestions": matched[:limit],
        "partial_query": partial_query
    }
