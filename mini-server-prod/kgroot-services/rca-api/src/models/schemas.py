"""
Pydantic models for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ReasoningEffort(str, Enum):
    """GPT-5 reasoning effort levels"""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Verbosity(str, Enum):
    """GPT-5 response verbosity"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================================
# RCA Models
# ============================================================================

class RCARequest(BaseModel):
    """Natural language RCA query"""
    query: str = Field(..., description="Natural language question about failures")
    client_id: Optional[str] = Field(None, description="Client ID for multi-tenancy")
    time_range_hours: int = Field(24, description="Look back hours", ge=1, le=168)
    reasoning_effort: ReasoningEffort = Field(ReasoningEffort.MEDIUM, description="GPT-5 reasoning level")
    verbosity: Verbosity = Field(Verbosity.MEDIUM, description="Response verbosity")
    include_remediation: bool = Field(True, description="Include fix suggestions")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Why did nginx pods fail in the default namespace?",
                "client_id": "ab-01",
                "time_range_hours": 24,
                "reasoning_effort": "medium",
                "include_remediation": True
            }
        }


class CausalChain(BaseModel):
    """A causal relationship chain"""
    step: int
    event_reason: str
    resource: str
    namespace: str
    timestamp: datetime
    confidence: float
    is_root_cause: bool


class RCAResponse(BaseModel):
    """RCA analysis result"""
    query: str
    summary: str = Field(..., description="Natural language summary from GPT-5")
    root_causes: List[Dict[str, Any]] = Field(..., description="Identified root causes")
    causal_chains: List[List[CausalChain]] = Field(..., description="Causal chains")
    affected_resources: List[Dict[str, Any]] = Field(..., description="Blast radius")
    remediation_steps: Optional[List[str]] = Field(None, description="Suggested fixes")
    confidence_score: float = Field(..., description="Overall confidence", ge=0.0, le=1.0)
    reasoning_tokens: Optional[int] = Field(None, description="GPT-5 reasoning tokens used")
    processing_time_ms: int

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Why did nginx pods fail?",
                "summary": "The nginx pods failed due to OOMKilled errors...",
                "root_causes": [
                    {
                        "reason": "OOMKilled",
                        "resource": "Pod/nginx-pod-1",
                        "namespace": "default",
                        "timestamp": "2025-01-15T10:30:00Z",
                        "confidence": 0.92
                    }
                ],
                "confidence_score": 0.88,
                "processing_time_ms": 1250
            }
        }


# ============================================================================
# Search Models
# ============================================================================

class SearchRequest(BaseModel):
    """Natural language search across events and resources"""
    query: str = Field(..., description="Natural language search query")
    client_id: Optional[str] = Field(None, description="Client ID")
    time_range_hours: Optional[int] = Field(24, description="Time range filter", ge=1)
    resource_types: Optional[List[str]] = Field(None, description="Filter by resource types")
    namespaces: Optional[List[str]] = Field(None, description="Filter by namespaces")
    limit: int = Field(20, description="Max results", ge=1, le=100)

    class Config:
        json_schema_extra = {
            "example": {
                "query": "show me all OOM errors in production namespace last 6 hours",
                "client_id": "ab-01",
                "time_range_hours": 6,
                "namespaces": ["production"],
                "limit": 20
            }
        }


class SearchResult(BaseModel):
    """Search result with semantic similarity"""
    item_type: str = Field(..., description="Event or Resource")
    item_id: str
    content: str = Field(..., description="Human-readable description")
    metadata: Dict[str, Any]
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    timestamp: Optional[datetime] = None


class SearchResponse(BaseModel):
    """Search results"""
    query: str
    results: List[SearchResult]
    total_results: int
    query_embedding_time_ms: int
    search_time_ms: int

    class Config:
        json_schema_extra = {
            "example": {
                "query": "OOM errors in production",
                "results": [
                    {
                        "item_type": "Event",
                        "item_id": "evt-123",
                        "content": "Pod nginx-pod-1 OOMKilled in production namespace",
                        "similarity_score": 0.95,
                        "timestamp": "2025-01-15T10:30:00Z"
                    }
                ],
                "total_results": 15
            }
        }


# ============================================================================
# Catalog Models
# ============================================================================

class ResourceFilter(BaseModel):
    """Filter criteria for resource catalog"""
    client_id: Optional[str] = None
    namespaces: Optional[List[str]] = None
    kinds: Optional[List[str]] = None
    owners: Optional[List[str]] = None
    labels: Optional[Dict[str, str]] = None
    healthy_only: bool = False


class ResourceInfo(BaseModel):
    """Resource metadata"""
    resource_id: str
    name: str
    kind: str
    namespace: str
    client_id: str
    labels: Optional[Dict[str, str]] = None
    owner: Optional[str] = Field(None, description="Owner/team")
    size: Optional[str] = Field(None, description="Small/Medium/Large")
    created_at: Optional[datetime] = None
    status: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list, description="Dependent resources")
    recent_events: int = Field(0, description="Event count in last 24h")


class TopologyView(BaseModel):
    """Service topology view"""
    service_name: str
    namespace: str
    pods: List[Dict[str, Any]]
    nodes: List[str]
    upstream_services: List[str] = Field(default_factory=list)
    downstream_services: List[str] = Field(default_factory=list)
    health_status: str


class CatalogResponse(BaseModel):
    """Catalog API response"""
    resources: List[ResourceInfo]
    total_count: int
    filtered_count: int
    page: int
    page_size: int


# ============================================================================
# Real-Time Monitoring Models
# ============================================================================

class HealthStatus(BaseModel):
    """Real-time health status"""
    client_id: str
    healthy_resources: int
    unhealthy_resources: int
    total_resources: int
    active_incidents: int
    health_percentage: float
    top_issues: List[Dict[str, Any]]
    timestamp: datetime


class IncidentSummary(BaseModel):
    """Active incident summary"""
    incident_id: str
    root_cause: Optional[str]
    affected_services: List[str]
    affected_namespaces: List[str]
    severity: str  # critical, high, medium, low
    started_at: datetime
    event_count: int
    blast_radius: int


# ============================================================================
# Slack Integration Models
# ============================================================================

class SlackAlert(BaseModel):
    """Slack alert payload"""
    client_id: str
    alert_type: str  # incident, warning, info
    title: str
    description: str
    root_cause: Optional[str] = None
    affected_resources: List[str]
    severity: str
    runbook_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


# ============================================================================
# Embeddings Models
# ============================================================================

class EmbeddingRequest(BaseModel):
    """Request to generate embeddings"""
    texts: List[str] = Field(..., description="Texts to embed")
    cache: bool = Field(True, description="Use cached embeddings if available")


class EmbeddingResponse(BaseModel):
    """Embedding vectors response"""
    embeddings: List[List[float]]
    model: str
    dimension: int
    cached_count: int
    computed_count: int
    processing_time_ms: int


# ============================================================================
# GPT-5 Assistant Models
# ============================================================================

class ChatRequest(BaseModel):
    """Conversational assistant request"""
    message: str = Field(..., description="User message")
    client_id: Optional[str] = None
    conversation_id: Optional[str] = Field(None, description="For multi-turn conversations")
    context_events: Optional[List[str]] = Field(None, description="Event IDs for context")
    reasoning_effort: ReasoningEffort = Field(ReasoningEffort.LOW, description="Response speed")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What's causing high memory usage in the auth service?",
                "client_id": "ab-01",
                "reasoning_effort": "low"
            }
        }


class ChatResponse(BaseModel):
    """Assistant response"""
    message: str
    conversation_id: str
    suggested_queries: List[str] = Field(default_factory=list)
    related_events: List[str] = Field(default_factory=list)
    confidence: float
    reasoning_summary: Optional[str] = None
