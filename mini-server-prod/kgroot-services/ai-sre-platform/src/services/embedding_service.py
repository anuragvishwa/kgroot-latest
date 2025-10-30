"""
OpenAI-based embedding service for semantic search with token limits
"""
from openai import AsyncOpenAI
from typing import List, Dict, Any, Tuple, Optional
import logging
import asyncio
from datetime import datetime

from src.core.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)


class TokenBudget:
    """Track and limit token usage"""

    def __init__(
        self,
        max_tokens_per_request: int = 8000,
        max_tokens_per_day: int = 1_000_000,
        max_cost_per_request: float = 1.0,
        max_cost_per_day: float = 100.0
    ):
        self.max_tokens_per_request = max_tokens_per_request
        self.max_tokens_per_day = max_tokens_per_day
        self.max_cost_per_request = max_cost_per_request
        self.max_cost_per_day = max_cost_per_day

        # Runtime tracking
        self.current_request_tokens = 0
        self.current_request_cost = 0.0
        self.daily_tokens = 0
        self.daily_cost = 0.0
        self.reset_date = datetime.now().date()

    def reset_if_new_day(self):
        """Reset daily counters if it's a new day"""
        today = datetime.now().date()
        if today != self.reset_date:
            logger.info(f"Resetting daily token budget. Previous usage: {self.daily_tokens} tokens, ${self.daily_cost:.4f}")
            self.daily_tokens = 0
            self.daily_cost = 0.0
            self.reset_date = today

    def reset_request(self):
        """Reset per-request counters"""
        self.current_request_tokens = 0
        self.current_request_cost = 0.0

    def can_use_tokens(self, tokens: int, cost: float = 0.0) -> bool:
        """Check if we can use this many tokens"""
        self.reset_if_new_day()

        # Check per-request limits
        if self.current_request_tokens + tokens > self.max_tokens_per_request:
            logger.warning(f"Would exceed per-request token limit: {self.current_request_tokens + tokens} > {self.max_tokens_per_request}")
            return False

        if self.current_request_cost + cost > self.max_cost_per_request:
            logger.warning(f"Would exceed per-request cost limit: ${self.current_request_cost + cost:.4f} > ${self.max_cost_per_request:.2f}")
            return False

        # Check daily limits
        if self.daily_tokens + tokens > self.max_tokens_per_day:
            logger.warning(f"Would exceed daily token limit: {self.daily_tokens + tokens} > {self.max_tokens_per_day}")
            return False

        if self.daily_cost + cost > self.max_cost_per_day:
            logger.warning(f"Would exceed daily cost limit: ${self.daily_cost + cost:.4f} > ${self.max_cost_per_day:.2f}")
            return False

        return True

    def track_usage(self, tokens: int, cost: float = 0.0):
        """Track token and cost usage"""
        self.current_request_tokens += tokens
        self.current_request_cost += cost
        self.daily_tokens += tokens
        self.daily_cost += cost

        logger.info(f"Token usage - Request: {self.current_request_tokens}/{self.max_tokens_per_request}, Daily: {self.daily_tokens}/{self.max_tokens_per_day}")
        logger.info(f"Cost - Request: ${self.current_request_cost:.4f}/${self.max_cost_per_request:.2f}, Daily: ${self.daily_cost:.4f}/${self.max_cost_per_day:.2f}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        self.reset_if_new_day()
        return {
            "request": {
                "tokens_used": self.current_request_tokens,
                "tokens_limit": self.max_tokens_per_request,
                "cost_used": self.current_request_cost,
                "cost_limit": self.max_cost_per_request
            },
            "daily": {
                "tokens_used": self.daily_tokens,
                "tokens_limit": self.max_tokens_per_day,
                "cost_used": self.daily_cost,
                "cost_limit": self.max_cost_per_day,
                "reset_date": self.reset_date.isoformat()
            }
        }


class OpenAIEmbeddingService:
    """
    Semantic search using OpenAI embeddings + Neo4j vector search

    This is a GraphRAG implementation:
    - Graph: Neo4j stores events with relationships (POTENTIAL_CAUSE)
    - RAG: Retrieval Augmented Generation using embeddings
    - Combines: Vector similarity + Graph traversal for context-aware search
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        neo4j_service: Neo4jService,
        embedding_model: str = "text-embedding-3-small",
        token_budget: Optional[TokenBudget] = None
    ):
        self.openai = openai_client
        self.neo4j = neo4j_service
        self.embedding_model = embedding_model
        self.token_budget = token_budget or TokenBudget()

        # Pricing (per 1M tokens)
        self.embedding_costs = {
            "text-embedding-3-small": 0.02 / 1_000_000,  # $0.02 per 1M tokens
            "text-embedding-3-large": 0.13 / 1_000_000,  # $0.13 per 1M tokens
            "text-embedding-ada-002": 0.10 / 1_000_000   # $0.10 per 1M tokens
        }

        logger.info(f"Initialized OpenAI embedding service with model: {embedding_model}")

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens (rough approximation: 1 token ≈ 4 characters)"""
        return len(text) // 4

    def calculate_cost(self, tokens: int) -> float:
        """Calculate cost for embedding tokens"""
        cost_per_token = self.embedding_costs.get(self.embedding_model, 0.02 / 1_000_000)
        return tokens * cost_per_token

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text using OpenAI
        Returns None if token budget exceeded
        """
        try:
            # Estimate tokens
            estimated_tokens = self.estimate_tokens(text)
            estimated_cost = self.calculate_cost(estimated_tokens)

            # Check budget
            if not self.token_budget.can_use_tokens(estimated_tokens, estimated_cost):
                logger.error("Token budget exceeded, cannot generate embedding")
                return None

            # Generate embedding
            response = await self.openai.embeddings.create(
                model=self.embedding_model,
                input=text
            )

            embedding = response.data[0].embedding

            # Track actual usage
            actual_tokens = response.usage.total_tokens
            actual_cost = self.calculate_cost(actual_tokens)
            self.token_budget.track_usage(actual_tokens, actual_cost)

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    async def semantic_search_events(
        self,
        query: str,
        client_id: str,
        limit: int = 10,
        time_range_hours: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for events using embeddings

        This is GraphRAG:
        1. Generate query embedding (RAG - Retrieval)
        2. Find similar events in Neo4j via vector search
        3. Traverse graph relationships for context (Graph)
        4. Return enriched results with causal context
        """
        try:
            logger.info(f"Semantic search: '{query}' for client {client_id}")

            # Generate query embedding
            query_embedding = await self.generate_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding, falling back to text search")
                return []

            # Search Neo4j using vector similarity
            # Note: This requires Neo4j 5.13+ with vector index
            # For now, we'll do a workaround: get events and compute similarity in-memory

            results = self.neo4j.semantic_search_events(
                query_embedding=query_embedding,
                client_id=client_id,
                time_range_hours=time_range_hours,
                limit=limit
            )

            logger.info(f"Found {len(results)} events via semantic search")
            return results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def semantic_search_with_context(
        self,
        query: str,
        client_id: str,
        limit: int = 10,
        include_causal_context: bool = True
    ) -> List[Dict[str, Any]]:
        """
        GraphRAG: Semantic search + graph traversal for rich context

        For each matching event:
        1. Find via vector similarity (RAG)
        2. Traverse POTENTIAL_CAUSE relationships (Graph)
        3. Return event + upstream/downstream context
        """
        # Get semantically similar events
        events = await self.semantic_search_events(query, client_id, limit=limit)

        if not include_causal_context:
            return events

        # Enrich with graph context
        enriched_results = []
        for event in events:
            event_id = event.get('event_id')
            if not event_id:
                enriched_results.append(event)
                continue

            # Get causal chain (upstream causes)
            causal_chain = self.neo4j.find_causal_chain(
                event_id=event_id,
                client_id=client_id,
                max_hops=2
            )

            # Get blast radius (downstream effects)
            blast_radius = self.neo4j.get_blast_radius(
                root_event_id=event_id,
                client_id=client_id,
                limit=10
            )

            # Combine
            enriched_results.append({
                **event,
                "causal_context": {
                    "upstream_causes": causal_chain,
                    "downstream_effects": blast_radius
                }
            })

        logger.info(f"Enriched {len(enriched_results)} events with graph context (GraphRAG)")
        return enriched_results

    def get_token_stats(self) -> Dict[str, Any]:
        """Get current token usage statistics"""
        return self.token_budget.get_stats()

    def reset_request_budget(self):
        """Reset per-request token budget"""
        self.token_budget.reset_request()


# Example usage:
# embedding_service = OpenAIEmbeddingService(
#     openai_client=AsyncOpenAI(api_key="..."),
#     neo4j_service=neo4j_service,
#     token_budget=TokenBudget(
#         max_tokens_per_request=8000,
#         max_cost_per_request=0.10  # $0.10 per request
#     )
# )
