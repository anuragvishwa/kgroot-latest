"""FastAPI application for AI SRE Platform"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.neo4j_service import Neo4jService
from src.orchestrator.orchestrator import AIRCAOrchestrator

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="AI SRE Platform",
    description="Multi-agent AI system for automated root cause analysis",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator
orchestrator: Optional[AIRCAOrchestrator] = None


# Request/Response models
class InvestigateRequest(BaseModel):
    query: str = Field(..., description="Natural language investigation query")
    tenant_id: str = Field(..., description="Tenant/client identifier")
    service: Optional[str] = Field(None, description="Service name to focus on")
    namespace: Optional[str] = Field(None, description="Kubernetes namespace")
    event_type: Optional[str] = Field(None, description="Event type for routing (e.g., OOMKilled)")
    time_window_hours: int = Field(24, description="Hours of history to analyze", ge=1, le=168)


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool
    available_agents: list[str]
    available_tools: list[str]


# Startup/Shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global orchestrator

    logger.info("=== Starting AI SRE Platform ===")

    # Load config from environment
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL", "gpt-5")

    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    # Initialize Neo4j
    logger.info(f"Connecting to Neo4j at {neo4j_uri}...")
    neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)

    if not neo4j_service.verify_connectivity():
        raise ConnectionError("Failed to connect to Neo4j")

    logger.info("✓ Neo4j connected")

    # Initialize orchestrator
    logger.info(f"Initializing orchestrator with model={model}...")
    orchestrator = AIRCAOrchestrator(
        neo4j_service=neo4j_service,
        openai_api_key=openai_api_key,
        model=model
    )

    logger.info("=== AI SRE Platform ready ===")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down AI SRE Platform...")
    if orchestrator:
        orchestrator.neo4j.close()
    logger.info("Shutdown complete")


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


# Routes
@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {
        "name": "AI SRE Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    neo4j_connected = orchestrator.neo4j.verify_connectivity()

    return HealthResponse(
        status="healthy" if neo4j_connected else "degraded",
        neo4j_connected=neo4j_connected,
        available_agents=list(orchestrator.agents.keys()),
        available_tools=orchestrator.neo4j.__class__.__name__  # Simplified
    )


@app.post("/api/v1/investigate")
async def investigate(request: InvestigateRequest):
    """
    Perform AI-powered RCA investigation

    This endpoint:
    1. Routes to appropriate agents based on event type
    2. Executes agents in parallel
    3. Synthesizes findings using GPT-5
    4. Returns comprehensive RCA report

    Example:
    ```json
    {
      "query": "Why did nginx pods fail?",
      "tenant_id": "acme-01",
      "event_type": "OOMKilled",
      "time_window_hours": 24
    }
    ```
    """
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    logger.info(f"Received investigation request: {request.query} (tenant={request.tenant_id})")

    try:
        # Calculate time window
        time_window_end = datetime.utcnow()
        time_window_start = datetime.utcnow() - timedelta(hours=request.time_window_hours)

        # Perform investigation
        result = await orchestrator.investigate(
            query=request.query,
            tenant_id=request.tenant_id,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            service=request.service,
            namespace=request.namespace,
            event_type=request.event_type
        )

        # Convert to dict for JSON response
        return result.dict()

    except Exception as e:
        logger.error(f"Investigation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Investigation failed: {str(e)}"
        )


@app.get("/api/v1/stats")
async def get_stats():
    """Get platform statistics"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    router_stats = orchestrator.router.get_pattern_coverage()

    return {
        "router": router_stats,
        "agents": {
            "total": len(orchestrator.agents),
            "available": list(orchestrator.agents.keys())
        }
    }


# Import timedelta
from datetime import timedelta


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
