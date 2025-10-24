"""
Embedding Service using OpenAI
Creates and manages embeddings for events and patterns
"""

import openai
from typing import List, Dict, Optional
import numpy as np
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for creating and managing OpenAI embeddings
    Used for semantic similarity in GraphRAG
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",  # or text-embedding-ada-002
        cache_embeddings: bool = True
    ):
        """
        Initialize embedding service

        Args:
            api_key: OpenAI API key
            model: Embedding model to use
            cache_embeddings: Whether to cache embeddings
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.cache_embeddings = cache_embeddings
        self._cache: Dict[str, List[float]] = {}

        logger.info(f"Initialized EmbeddingService with model: {model}")

    def embed_text(self, text: str) -> List[float]:
        """
        Create embedding for text

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Check cache
        cache_key = self._get_cache_key(text)
        if self.cache_embeddings and cache_key in self._cache:
            logger.debug(f"Retrieved embedding from cache for: {text[:50]}...")
            return self._cache[cache_key]

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )

            embedding = response.data[0].embedding

            # Cache the embedding
            if self.cache_embeddings:
                self._cache[cache_key] = embedding

            logger.debug(f"Created embedding for: {text[:50]}...")
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise

    def embed_texts_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Create embeddings for multiple texts in batch

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []

        embeddings = []
        uncached_texts = []
        uncached_indices = []

        # Check cache first
        for i, text in enumerate(valid_texts):
            cache_key = self._get_cache_key(text)
            if self.cache_embeddings and cache_key in self._cache:
                embeddings.append(self._cache[cache_key])
            else:
                embeddings.append(None)  # Placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Batch request for uncached texts
        if uncached_texts:
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=uncached_texts
                )

                # Fill in uncached embeddings
                for i, embedding_data in enumerate(response.data):
                    embedding = embedding_data.embedding
                    idx = uncached_indices[i]
                    embeddings[idx] = embedding

                    # Cache
                    if self.cache_embeddings:
                        cache_key = self._get_cache_key(uncached_texts[i])
                        self._cache[cache_key] = embedding

                logger.info(f"Created {len(uncached_texts)} embeddings in batch")

            except Exception as e:
                logger.error(f"Failed to create batch embeddings: {e}")
                raise

        return embeddings

    def cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score between -1 and 1
        """
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)
        return float(similarity)

    def find_most_similar(
        self,
        query_embedding: List[float],
        candidate_embeddings: List[List[float]],
        top_k: int = 5
    ) -> List[tuple[int, float]]:
        """
        Find most similar embeddings to query

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embeddings
            top_k: Number of top results

        Returns:
            List of (index, similarity_score) tuples
        """
        similarities = []

        for i, candidate_emb in enumerate(candidate_embeddings):
            similarity = self.cosine_similarity(query_embedding, candidate_emb)
            similarities.append((i, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        # Use hash of (model, text) as cache key
        content = f"{self.model}:{text}"
        return hashlib.md5(content.encode()).hexdigest()

    def clear_cache(self):
        """Clear embedding cache"""
        self._cache.clear()
        logger.info("Cleared embedding cache")

    def get_cache_size(self) -> int:
        """Get number of cached embeddings"""
        return len(self._cache)

    def save_cache(self, filepath: str):
        """Save cache to file"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self._cache, f)
            logger.info(f"Saved embedding cache to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def load_cache(self, filepath: str):
        """Load cache from file"""
        try:
            with open(filepath, 'r') as f:
                self._cache = json.load(f)
            logger.info(f"Loaded {len(self._cache)} embeddings from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")


class EventEmbedder:
    """
    Specialized embedder for events
    Converts events to text and creates embeddings
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    def embed_event(self, event_data: Dict) -> List[float]:
        """
        Create embedding for event

        Args:
            event_data: Event dictionary

        Returns:
            Embedding vector
        """
        text = self._event_to_text(event_data)
        return self.embedding_service.embed_text(text)

    def embed_events(self, events_data: List[Dict]) -> List[List[float]]:
        """Create embeddings for multiple events"""
        texts = [self._event_to_text(event) for event in events_data]
        return self.embedding_service.embed_texts_batch(texts)

    def _event_to_text(self, event_data: Dict) -> str:
        """
        Convert event to text representation for embedding

        Creates a rich text description of the event
        """
        parts = []

        # Event type
        event_type = event_data.get('event_type', 'unknown')
        parts.append(f"Event type: {event_type}")

        # Service and namespace
        service = event_data.get('service', 'unknown')
        namespace = event_data.get('namespace', 'default')
        parts.append(f"Service: {service} in namespace {namespace}")

        # Severity
        severity = event_data.get('severity', 'info')
        parts.append(f"Severity: {severity}")

        # Pod information
        if event_data.get('pod_name'):
            parts.append(f"Pod: {event_data['pod_name']}")

        # Metrics
        if event_data.get('metric_value') is not None:
            metric_value = event_data['metric_value']
            metric_unit = event_data.get('metric_unit', '')
            parts.append(f"Metric value: {metric_value} {metric_unit}")

        # Message
        if event_data.get('message'):
            parts.append(f"Message: {event_data['message']}")

        # Details
        if event_data.get('details'):
            details_str = "; ".join(
                f"{k}: {v}"
                for k, v in event_data['details'].items()
            )
            parts.append(f"Details: {details_str}")

        return ". ".join(parts)


class PatternEmbedder:
    """
    Specialized embedder for failure patterns
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    def embed_pattern(self, pattern_data: Dict) -> List[float]:
        """Create embedding for pattern"""
        text = self._pattern_to_text(pattern_data)
        return self.embedding_service.embed_text(text)

    def embed_patterns(self, patterns_data: List[Dict]) -> List[List[float]]:
        """Create embeddings for multiple patterns"""
        texts = [self._pattern_to_text(pattern) for pattern in patterns_data]
        return self.embedding_service.embed_texts_batch(texts)

    def _pattern_to_text(self, pattern_data: Dict) -> str:
        """Convert pattern to text representation"""
        parts = []

        # Pattern name and root cause
        name = pattern_data.get('name', 'Unknown pattern')
        root_cause = pattern_data.get('root_cause_type', 'unknown')
        parts.append(f"Failure pattern: {name}")
        parts.append(f"Root cause type: {root_cause}")

        # Event sequence
        event_sig = pattern_data.get('event_signature', [])
        if event_sig:
            parts.append(f"Event sequence: {' -> '.join(event_sig)}")

        # Affected services
        services = pattern_data.get('affected_services', [])
        if services:
            parts.append(f"Affected services: {', '.join(services)}")

        # Resolution steps
        resolution = pattern_data.get('resolution_steps', [])
        if resolution:
            parts.append(f"Resolution: {'; '.join(resolution)}")

        # Frequency
        frequency = pattern_data.get('frequency', 0)
        parts.append(f"Occurrence frequency: {frequency}")

        return ". ".join(parts)
