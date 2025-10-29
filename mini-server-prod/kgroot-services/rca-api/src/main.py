"""
Main FastAPI application for RCA API
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time

from .config import settings
from .services.neo4j_service import neo4j_service
from .services.embedding_service import embedding_service
from .services.gpt5_service import gpt5_service
from .services.slack_service import slack_service

# Import API routers
from .api import rca, search, catalog, health, chat

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle management for the application
    """
    # Startup
    logger.info("Starting RCA API...")

    try:
        # Initialize services
        neo4j_service.connect()
        embedding_service.initialize()
        gpt5_service.initialize()
        slack_service.initialize()

        logger.info("All services initialized successfully")

        # Build initial embedding index
        logger.info("Building initial embedding index...")
        events = neo4j_service.find_events_by_criteria(
            client_id=settings.default_client_id,
            time_range_hours=24,
            limit=1000
        )
        resources = neo4j_service.get_resources_catalog(
            client_id=settings.default_client_id,
            limit=1000
        )["resources"]

        embedding_service.rebuild_index(events, resources)
        logger.info(f"Built embedding index with {len(events)} events and {len(resources)} resources")

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down RCA API...")
    neo4j_service.close()


# Create FastAPI app
app = FastAPI(
    title="KGRoot RCA API",
    description="Intelligent Root Cause Analysis API with GPT-5, Neo4j, and Semantic Search",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(rca.router, prefix="/api/v1/rca", tags=["RCA"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Search"])
app.include_router(catalog.router, prefix="/api/v1/catalog", tags=["Catalog"])
app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "KGRoot RCA API",
        "version": "2.0.0",
        "status": "running",
        "features": [
            "GPT-5 powered RCA analysis",
            "Semantic search with embeddings",
            "Multi-tenant Neo4j graph",
            "Slack integrations",
            "Real-time health monitoring"
        ],
        "endpoints": {
            "rca": "/api/v1/rca",
            "search": "/api/v1/search",
            "catalog": "/api/v1/catalog",
            "health": "/api/v1/health",
            "chat": "/api/v1/chat",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "neo4j": neo4j_service.driver is not None,
            "embeddings": embedding_service.model is not None,
            "gpt5": gpt5_service.client is not None,
            "slack": slack_service.enabled
        }
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers if not settings.debug else 1,
        reload=settings.debug
    )
