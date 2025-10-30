"""Semantic search tools using OpenAI embeddings (GraphRAG)"""

from src.core.tool_registry import BaseTool, ToolMetadata, tool_registry
from src.services.embedding_service import OpenAIEmbeddingService
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class SemanticSearchTool(BaseTool):
    """
    Semantic search for events using natural language queries

    This implements GraphRAG:
    - Retrieval: Vector similarity search with OpenAI embeddings
    - Augmented: Enriched with Neo4j graph context (causal chains, blast radius)
    - Generation: Results used by LLM for intelligent synthesis
    """

    def __init__(self, embedding_service: OpenAIEmbeddingService):
        self.embedding = embedding_service
        tool_registry.register(self)

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="semantic_search_events",
            description="Search for events using natural language queries. Supports questions like 'show me OOM errors in production', 'find DNS failures', 'connection refused errors'. Returns semantically similar events with causal context.",
            category="search",
            requires_auth=False,
            rate_limit_per_min=30,  # Limit to control costs
            cost_per_call=0.0001  # ~$0.0001 per embedding
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute semantic search"""
        try:
            query = params['query']
            client_id = params['client_id']
            limit = params.get('limit', 10)
            time_range_hours = params.get('time_range_hours')
            include_context = params.get('include_context', True)

            logger.info(f"Semantic search: '{query}' (limit={limit}, context={include_context})")

            # Reset per-request token budget
            self.embedding.reset_request_budget()

            # Perform search
            if include_context:
                results = await self.embedding.semantic_search_with_context(
                    query=query,
                    client_id=client_id,
                    limit=limit,
                    include_causal_context=True
                )
            else:
                results = await self.embedding.semantic_search_events(
                    query=query,
                    client_id=client_id,
                    limit=limit,
                    time_range_hours=time_range_hours
                )

            # Get token stats
            token_stats = self.embedding.get_token_stats()

            return {
                "success": True,
                "data": results,
                "count": len(results),
                "token_usage": token_stats,
                "is_graphrag": include_context  # True if using GraphRAG
            }

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return {
                "success": False,
                "data": [],
                "error": str(e)
            }

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query (e.g., 'DNS failures', 'OOM errors in production')"
                        },
                        "client_id": {
                            "type": "string",
                            "description": "Client/tenant identifier"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 10
                        },
                        "time_range_hours": {
                            "type": "integer",
                            "description": "Filter results to last N hours",
                            "default": None
                        },
                        "include_context": {
                            "type": "boolean",
                            "description": "Include causal graph context (GraphRAG)",
                            "default": True
                        }
                    },
                    "required": ["query", "client_id"]
                }
            }
        }
