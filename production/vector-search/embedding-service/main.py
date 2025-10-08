#!/usr/bin/env python3
"""
Embedding Service - Local sentence-transformers for vector search
Provides REST API for generating text embeddings
"""

from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import numpy as np
import logging
from typing import List, Dict
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load model (lightweight, 80MB)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
model = None

def load_model():
    global model
    logger.info(f"Loading model: {MODEL_NAME}")
    start = time.time()
    model = SentenceTransformer(MODEL_NAME)
    logger.info(f"Model loaded in {time.time() - start:.2f}s")

@app.before_request
def ensure_model_loaded():
    global model
    if model is None:
        load_model()

@app.route('/healthz', methods=['GET'])
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME})

@app.route('/embed', methods=['POST'])
def embed_text():
    """
    Generate embedding for single text

    Request:
    {
        "text": "OOMKilled pod crashed due to memory limit"
    }

    Response:
    {
        "embedding": [0.123, -0.456, ...],  // 384 dimensions
        "dimension": 384
    }
    """
    try:
        data = request.get_json()

        if not data or 'text' not in data:
            return jsonify({"error": "Missing 'text' field"}), 400

        text = data['text']

        if not text.strip():
            return jsonify({"error": "Empty text"}), 400

        # Generate embedding
        embedding = model.encode(text, convert_to_numpy=True)

        return jsonify({
            "embedding": embedding.tolist(),
            "dimension": len(embedding),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/embed/batch', methods=['POST'])
def embed_batch():
    """
    Generate embeddings for multiple texts

    Request:
    {
        "texts": [
            "OOMKilled pod crashed",
            "Service unavailable due to connection timeout",
            ...
        ]
    }

    Response:
    {
        "embeddings": [[...], [...], ...],
        "dimension": 384,
        "count": 2
    }
    """
    try:
        data = request.get_json()

        if not data or 'texts' not in data:
            return jsonify({"error": "Missing 'texts' field"}), 400

        texts = data['texts']

        if not isinstance(texts, list) or len(texts) == 0:
            return jsonify({"error": "texts must be non-empty list"}), 400

        # Generate embeddings
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        return jsonify({
            "embeddings": embeddings.tolist(),
            "dimension": embeddings.shape[1],
            "count": len(embeddings),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/similarity', methods=['POST'])
def compute_similarity():
    """
    Compute cosine similarity between two texts

    Request:
    {
        "text1": "pod crashed due to OOM",
        "text2": "memory limit exceeded"
    }

    Response:
    {
        "similarity": 0.87,
        "text1_embedding": [...],
        "text2_embedding": [...]
    }
    """
    try:
        data = request.get_json()

        if not data or 'text1' not in data or 'text2' not in data:
            return jsonify({"error": "Missing text1 or text2"}), 400

        text1 = data['text1']
        text2 = data['text2']

        # Generate embeddings
        embeddings = model.encode([text1, text2], convert_to_numpy=True)

        # Compute cosine similarity
        similarity = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
        )

        return jsonify({
            "similarity": float(similarity),
            "text1_embedding": embeddings[0].tolist(),
            "text2_embedding": embeddings[1].tolist(),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error computing similarity: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/search', methods=['POST'])
def semantic_search():
    """
    Find most similar texts to query from a corpus

    Request:
    {
        "query": "what caused the crash",
        "corpus": [
            "OOMKilled pod due to memory limit",
            "Service timeout",
            "Disk full error"
        ],
        "top_k": 2
    }

    Response:
    {
        "results": [
            {"index": 0, "text": "OOMKilled pod...", "similarity": 0.85},
            {"index": 1, "text": "Service timeout", "similarity": 0.42}
        ]
    }
    """
    try:
        data = request.get_json()

        if not data or 'query' not in data or 'corpus' not in data:
            return jsonify({"error": "Missing query or corpus"}), 400

        query = data['query']
        corpus = data['corpus']
        top_k = data.get('top_k', 5)

        if not isinstance(corpus, list):
            return jsonify({"error": "corpus must be a list"}), 400

        # Generate embeddings
        query_embedding = model.encode(query, convert_to_numpy=True)
        corpus_embeddings = model.encode(corpus, convert_to_numpy=True, show_progress_bar=False)

        # Compute similarities
        similarities = np.dot(corpus_embeddings, query_embedding) / (
            np.linalg.norm(corpus_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = [
            {
                "index": int(idx),
                "text": corpus[idx],
                "similarity": float(similarities[idx])
            }
            for idx in top_indices
        ]

        return jsonify({
            "results": results,
            "query": query,
            "total_corpus": len(corpus),
            "model": MODEL_NAME
        })

    except Exception as e:
        logger.error(f"Error in semantic search: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Load model on startup
    load_model()

    # Start server
    port = 5000
    logger.info(f"Starting embedding service on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
