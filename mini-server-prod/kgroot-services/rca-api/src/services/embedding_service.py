"""
Embedding service for semantic search
"""
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
from typing import List, Dict, Any, Tuple
import pickle
import os
import logging
from datetime import datetime

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating and searching embeddings"""

    def __init__(self):
        self.model: Optional[SentenceTransformer] = None
        self.index: Optional[faiss.IndexFlatIP] = None  # Inner product (cosine similarity)
        self.metadata_store: List[Dict[str, Any]] = []
        self.cache_file = os.path.join(settings.embedding_cache_dir, "embeddings_cache.pkl")

    def initialize(self):
        """Load embedding model"""
        try:
            logger.info(f"Loading embedding model: {settings.embedding_model}")
            self.model = SentenceTransformer(settings.embedding_model)

            # Create cache directory
            os.makedirs(settings.embedding_cache_dir, exist_ok=True)

            # Load cached embeddings if they exist
            if os.path.exists(self.cache_file):
                self._load_cache()
            else:
                # Initialize empty FAISS index
                self.index = faiss.IndexFlatIP(settings.embedding_dimension)

            logger.info("Embedding service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize embedding service: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for texts
        """
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,  # For cosine similarity
            show_progress_bar=False
        )
        return embeddings

    def add_items(self, texts: List[str], metadata: List[Dict[str, Any]]):
        """
        Add items to the searchable index
        """
        if len(texts) != len(metadata):
            raise ValueError("Texts and metadata must have same length")

        # Generate embeddings
        embeddings = self.embed_texts(texts)

        # Add to FAISS index
        self.index.add(embeddings.astype('float32'))

        # Store metadata
        self.metadata_store.extend(metadata)

        logger.info(f"Added {len(texts)} items to embedding index")

    def search(
        self,
        query: str,
        limit: int = 20,
        score_threshold: float = 0.5
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Search for similar items
        Returns list of (metadata, similarity_score) tuples
        """
        # Generate query embedding
        query_embedding = self.embed_texts([query])

        # Search in FAISS
        similarities, indices = self.index.search(
            query_embedding.astype('float32'),
            min(limit * 2, len(self.metadata_store))  # Get extra for filtering
        )

        # Filter by threshold and return results
        results = []
        for sim, idx in zip(similarities[0], indices[0]):
            if sim >= score_threshold and idx < len(self.metadata_store):
                results.append((self.metadata_store[idx], float(sim)))

        return results[:limit]

    def build_event_index(self, events: List[Dict[str, Any]]):
        """
        Build searchable index from events
        """
        texts = []
        metadata = []

        for event in events:
            # Create searchable text representation
            text_parts = [
                f"Event: {event.get('reason', 'Unknown')}",
                f"Resource: {event.get('resource_kind', '')}/{event.get('resource_name', '')}",
                f"Namespace: {event.get('namespace', '')}",
                f"Time: {event.get('timestamp', '')}",
            ]

            if event.get('message'):
                text_parts.append(f"Message: {event['message']}")

            text = " | ".join(filter(None, text_parts))
            texts.append(text)

            # Store metadata
            metadata.append({
                "item_type": "Event",
                "item_id": event.get('event_id', ''),
                "content": text,
                "event_data": event,
                "timestamp": event.get('timestamp')
            })

        if texts:
            self.add_items(texts, metadata)
            logger.info(f"Built event index with {len(texts)} events")

    def build_resource_index(self, resources: List[Dict[str, Any]]):
        """
        Build searchable index from resources
        """
        texts = []
        metadata = []

        for resource in resources:
            # Create searchable text representation
            text_parts = [
                f"Resource: {resource.get('kind', '')}/{resource.get('name', '')}",
                f"Namespace: {resource.get('namespace', '')}",
                f"Owner: {resource.get('owner', 'Unknown')}",
                f"Size: {resource.get('size', 'Unknown')}",
            ]

            if resource.get('labels'):
                labels_str = ", ".join([f"{k}:{v}" for k, v in resource['labels'].items()])
                text_parts.append(f"Labels: {labels_str}")

            if resource.get('dependencies'):
                deps = ", ".join(resource['dependencies'][:5])
                text_parts.append(f"Dependencies: {deps}")

            text = " | ".join(filter(None, text_parts))
            texts.append(text)

            # Store metadata
            metadata.append({
                "item_type": "Resource",
                "item_id": resource.get('name', ''),
                "content": text,
                "resource_data": resource,
                "timestamp": resource.get('created_at')
            })

        if texts:
            self.add_items(texts, metadata)
            logger.info(f"Built resource index with {len(texts)} resources")

    def rebuild_index(self, events: List[Dict[str, Any]], resources: List[Dict[str, Any]]):
        """
        Rebuild entire search index
        """
        # Reset index
        self.index = faiss.IndexFlatIP(settings.embedding_dimension)
        self.metadata_store = []

        # Build indexes
        self.build_event_index(events)
        self.build_resource_index(resources)

        # Save to cache
        self._save_cache()

    def _save_cache(self):
        """Save embeddings and metadata to disk"""
        try:
            cache_data = {
                "index": faiss.serialize_index(self.index),
                "metadata": self.metadata_store,
                "timestamp": datetime.now().isoformat()
            }

            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)

            logger.info(f"Saved embedding cache with {len(self.metadata_store)} items")
        except Exception as e:
            logger.error(f"Failed to save embedding cache: {e}")

    def _load_cache(self):
        """Load embeddings and metadata from disk"""
        try:
            with open(self.cache_file, 'rb') as f:
                cache_data = pickle.load(f)

            self.index = faiss.deserialize_index(cache_data["index"])
            self.metadata_store = cache_data["metadata"]

            logger.info(f"Loaded embedding cache with {len(self.metadata_store)} items from {cache_data.get('timestamp', 'unknown time')}")
        except Exception as e:
            logger.error(f"Failed to load embedding cache: {e}")
            # Initialize empty index on failure
            self.index = faiss.IndexFlatIP(settings.embedding_dimension)
            self.metadata_store = []


# Global embedding service instance
embedding_service = EmbeddingService()
