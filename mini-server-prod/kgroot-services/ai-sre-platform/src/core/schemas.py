"""Pydantic models for AI SRE Platform"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    """Event severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


class IncidentScope(BaseModel):
    """Defines the scope of an incident investigation"""
    tenant_id: str
    service: Optional[str] = None
    namespace: Optional[str] = None
    time_window_start: datetime
    time_window_end: datetime
    pivot_event_id: Optional[str] = None
    correlation_ids: Dict[str, str] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentFinding(BaseModel):
    """A single finding from an agent"""
    kind: str  # e.g., "root_cause", "causal_chain", "metric_anomaly"
    detail: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentArtifact(BaseModel):
    """Artifact produced by an agent (charts, logs, etc.)"""
    type: str  # "timeseries", "log_excerpt", "topology_graph"
    ref: str  # Reference URL or path
    description: Optional[str] = None


class AgentResult(BaseModel):
    """Result from a single agent execution"""
    agent: str
    findings: List[AgentFinding]
    artifacts: List[AgentArtifact] = Field(default_factory=list)
    cost: Dict[str, float] = Field(default_factory=lambda: {"llm_usd": 0.0, "api_usd": 0.0})
    latency_ms: int
    success: bool = True
    error: Optional[str] = None

    @property
    def total_cost(self) -> float:
        return sum(self.cost.values())


class RouterDecision(BaseModel):
    """Decision from the router about which agents to execute"""
    agents: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    llm_used: bool = False
    parallel_execution: bool = True


class InvestigationSynthesis(BaseModel):
    """Synthesized findings from all agents"""
    summary: str
    root_causes: List[Dict[str, Any]]
    contributing_factors: List[str]
    blast_radius: Dict[str, Any]
    immediate_actions: List[str]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_breakdown: Dict[str, float] = Field(default_factory=dict)


class InvestigationResult(BaseModel):
    """Complete investigation result"""
    incident_id: str
    tenant_id: str
    query: str
    scope: IncidentScope
    router_decision: RouterDecision
    agent_results: Dict[str, AgentResult]
    synthesis: InvestigationSynthesis
    total_cost_usd: float
    total_latency_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }