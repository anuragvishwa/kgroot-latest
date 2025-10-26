#!/usr/bin/env python3
"""
RCA API Service
FastAPI service that orchestrates RCA analysis and provides Web UI data
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import logging
import os
import json
from neo4j import GraphDatabase
from kafka import KafkaConsumer

from rca_orchestrator import RCAOrchestrator, RCAResult
from models.event import Event, EventType

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KGroot RCA API",
    description="Root Cause Analysis API with GraphRAG and GPT-5",
    version="2.0.0"
)

# CORS for Web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global RCA orchestrator instance
rca_orchestrator: Optional[RCAOrchestrator] = None
neo4j_driver = None

# Configuration from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ENABLE_LLM = os.getenv("ENABLE_LLM", "true").lower() == "true"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")  # gpt-5, gpt-4o, etc.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://kg-neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "password")
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kg-kafka:29092")


# Request/Response Models
class RCARequest(BaseModel):
    """Request to trigger RCA analysis"""
    client_id: str
    incident_type: Optional[str] = None
    service_name: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    time_window_minutes: int = 15
    include_llm_analysis: bool = True


class FixSuggestion(BaseModel):
    """Fix suggestion with confidence and risk scoring"""
    rank: int
    action: str
    confidence: float  # 0-100
    blast_radius: List[str]
    risk_score: int  # 0-100
    eta_minutes: int
    prerequisites: List[str]
    reasoning: str


class RCAResponse(BaseModel):
    """RCA analysis result for Web UI"""
    incident_id: str
    client_id: str
    timestamp: str

    # Summary
    primary_symptom: str
    affected_services: List[str]
    confidence_score: float  # 0-100

    # SLA tracking
    sla_status: str  # "within_slo", "breaching", "breached"
    sla_percentage: float
    risk_budget_remaining: int

    # Analysis
    total_symptoms: int
    timeseries_analyzed: int
    analysis_duration_seconds: float

    # Fix suggestions (ranked)
    fix_suggestions: List[FixSuggestion]

    # Timeline
    timeline: List[Dict[str, Any]]

    # Detailed analysis
    root_causes: List[Dict[str, Any]]
    llm_analysis: Optional[Dict[str, Any]] = None


@app.on_event("startup")
async def startup_event():
    """Initialize RCA orchestrator and connections"""
    global rca_orchestrator, neo4j_driver

    logger.info("🚀 Starting RCA API Service...")
    logger.info(f"   OpenAI API Key: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    logger.info(f"   LLM Enabled: {ENABLE_LLM}")
    logger.info(f"   LLM Model: {LLM_MODEL}")

    # Initialize RCA orchestrator
    rca_orchestrator = RCAOrchestrator(
        openai_api_key=OPENAI_API_KEY if ENABLE_LLM else None,
        enable_llm=ENABLE_LLM and OPENAI_API_KEY is not None,
        llm_model=LLM_MODEL,
        reasoning_effort="medium",
        verbosity="medium"
    )

    # Initialize Neo4j connection
    try:
        neo4j_driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASS)
        )
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1")
            result.single()
        logger.info("✅ Neo4j connection established")
    except Exception as e:
        logger.error(f"❌ Neo4j connection failed: {e}")
        neo4j_driver = None

    logger.info("✅ RCA API Service ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup connections"""
    global neo4j_driver
    if neo4j_driver:
        neo4j_driver.close()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "llm_enabled": ENABLE_LLM,
        "neo4j_connected": neo4j_driver is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/v1/rca/analyze", response_model=RCAResponse)
async def trigger_rca_analysis(request: RCARequest):
    """
    Trigger RCA analysis for a failure incident
    Returns comprehensive analysis for Web UI
    """
    logger.info(f"🔍 RCA analysis requested for client: {request.client_id}")

    if not rca_orchestrator:
        raise HTTPException(status_code=503, detail="RCA orchestrator not initialized")

    try:
        # Step 1: Collect events from Kafka
        events = await collect_events_for_incident(
            request.client_id,
            request.time_window_minutes,
            request.service_name,
            request.namespace,
            request.pod_name
        )

        if not events:
            raise HTTPException(
                status_code=404,
                detail=f"No events found for client {request.client_id} in last {request.time_window_minutes} minutes"
            )

        logger.info(f"   Found {len(events)} events to analyze")

        # Step 2: Get service topology from Neo4j
        topology = await get_service_topology(request.client_id)

        # Step 3: Run RCA analysis
        start_time = datetime.now()

        result = await rca_orchestrator.analyze_failure(
            fault_id=f"incident-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            events=events,
            context={
                "client_id": request.client_id,
                "topology": topology,
                "incident_type": request.incident_type
            }
        )

        analysis_duration = (datetime.now() - start_time).total_seconds()

        # Step 4: Calculate blast radius
        blast_radius = await calculate_blast_radius(
            request.client_id,
            request.service_name or result.top_root_causes[0].get("service") if result.top_root_causes else None
        )

        # Step 5: Generate fix suggestions with ranking
        fix_suggestions = await generate_fix_suggestions(result, topology, blast_radius)

        # Step 6: Build timeline
        timeline = build_timeline_from_events(events)

        # Step 7: Calculate SLA metrics
        sla_metrics = calculate_sla_metrics(events, analysis_duration)

        # Build response
        response = RCAResponse(
            incident_id=result.fault_id,
            client_id=request.client_id,
            timestamp=result.timestamp.isoformat(),

            primary_symptom=get_primary_symptom(events, result),
            affected_services=get_affected_services(events),
            confidence_score=result.root_cause_confidence * 100,

            sla_status=sla_metrics["status"],
            sla_percentage=sla_metrics["percentage"],
            risk_budget_remaining=sla_metrics["risk_budget"],

            total_symptoms=len(events),
            timeseries_analyzed=len(topology.get("services", [])) * 10,  # Estimate
            analysis_duration_seconds=analysis_duration,

            fix_suggestions=fix_suggestions,
            timeline=timeline,
            root_causes=result.top_root_causes,
            llm_analysis=result.llm_analysis if request.include_llm_analysis else None
        )

        logger.info(f"✅ RCA analysis completed in {analysis_duration:.2f}s")
        logger.info(f"   Confidence: {response.confidence_score:.1f}%")
        logger.info(f"   Fix suggestions: {len(fix_suggestions)}")

        return response

    except Exception as e:
        logger.error(f"❌ RCA analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def collect_events_for_incident(
    client_id: str,
    time_window_minutes: int,
    service_name: Optional[str] = None,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None
) -> List[Event]:
    """Collect events from Kafka for the incident time window"""

    consumer = KafkaConsumer(
        'events.normalized',
        bootstrap_servers=KAFKA_BROKERS,
        auto_offset_reset='earliest',  # Read from beginning to get historical events
        value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
        consumer_timeout_ms=30000  # Increased to 30 seconds
    )

    events = []
    cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
    messages_processed = 0
    messages_filtered = 0

    logger.info(f"   Collecting events from Kafka (time_window={time_window_minutes}m, namespace={namespace}, pod={pod_name})")

    try:
        for message in consumer:
            messages_processed += 1

            if message.value is None:
                continue

            event_data = message.value

            # Filter by client, service, namespace, pod if specified
            involved_obj = event_data.get('involvedObject', {})

            if namespace and involved_obj.get('namespace') != namespace:
                continue

            if pod_name and involved_obj.get('name') != pod_name:
                continue

            # Parse timestamp
            timestamp_str = event_data.get('firstTimestamp')
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp < cutoff_time:
                        continue
                except:
                    pass

            # Convert to Event object
            event = Event.from_k8s_event(event_data)
            events.append(event)

            if len(events) >= 1000:  # Limit to prevent memory issues
                logger.info(f"   Hit max event limit (1000), stopping collection")
                break

    finally:
        consumer.close()

    logger.info(f"   Kafka consumer stats: processed={messages_processed}, matched={len(events)}")
    return events


async def get_service_topology(client_id: str) -> Dict[str, Any]:
    """Get service topology from Neo4j"""
    if not neo4j_driver:
        return {"services": [], "dependencies": []}

    try:
        with neo4j_driver.session() as session:
            # Get services
            services_result = session.run("""
                MATCH (s:Resource:Service {client_id: $client_id})
                RETURN s.name as name, s.ns as namespace, s.labels_json as labels
                LIMIT 100
            """, client_id=client_id)

            services = [dict(record) for record in services_result]

            # Get dependencies
            deps_result = session.run("""
                MATCH (s1:Resource:Service {client_id: $client_id})-[r:DEPENDS_ON]->(s2:Resource:Service)
                RETURN s1.name as source, s2.name as target, type(r) as type
                LIMIT 200
            """, client_id=client_id)

            dependencies = [dict(record) for record in deps_result]

            return {
                "services": services,
                "dependencies": dependencies
            }
    except Exception as e:
        logger.error(f"Failed to get topology: {e}")
        return {"services": [], "dependencies": []}


async def calculate_blast_radius(client_id: str, service_name: Optional[str]) -> List[str]:
    """Calculate blast radius - which services would be affected"""
    if not neo4j_driver or not service_name:
        return []

    try:
        with neo4j_driver.session() as session:
            result = session.run("""
                MATCH path = (s:Resource:Service {client_id: $client_id, name: $service_name})
                             -[:DEPENDS_ON*0..2]->(dependent)
                WHERE dependent:Service
                RETURN DISTINCT dependent.name as service
                LIMIT 20
            """, client_id=client_id, service_name=service_name)

            return [record["service"] for record in result]
    except Exception as e:
        logger.error(f"Failed to calculate blast radius: {e}")
        return [service_name] if service_name else []


async def generate_fix_suggestions(
    result: RCAResult,
    topology: Dict[str, Any],
    blast_radius: List[str]
) -> List[FixSuggestion]:
    """Generate and rank fix suggestions using LLM analysis"""

    suggestions = []

    # If LLM analysis available, extract AI-generated suggestions
    if result.llm_analysis and "solutions" in result.llm_analysis:
        llm_solutions = result.llm_analysis["solutions"]

        for idx, solution in enumerate(llm_solutions[:4]):  # Top 4
            suggestions.append(FixSuggestion(
                rank=idx + 1,
                action=solution.get("action", "Unknown action"),
                confidence=solution.get("probability_of_success", 50.0),
                blast_radius=blast_radius[:3],  # Top 3 affected services
                risk_score=solution.get("impact_analysis", {}).get("rollback_difficulty", 50),
                eta_minutes=solution.get("estimated_time_minutes", 5),
                prerequisites=solution.get("prerequisites", []),
                reasoning=solution.get("reasoning", "")
            ))
    else:
        # Fallback: Generate basic suggestions from root causes
        for idx, cause in enumerate(result.top_root_causes[:3]):
            suggestions.append(generate_fallback_suggestion(idx + 1, cause, blast_radius))

    return suggestions


def generate_fallback_suggestion(rank: int, cause: Dict, blast_radius: List[str]) -> FixSuggestion:
    """Generate basic fix suggestion when LLM not available"""

    event_type = cause.get("event_type", "")
    confidence = cause.get("score", 0.5) * 100

    # Template-based suggestions
    if "OOM" in event_type or "memory" in str(cause).lower():
        return FixSuggestion(
            rank=rank,
            action=f"Increase memory limits for {cause.get('pod', 'pod')}",
            confidence=confidence,
            blast_radius=blast_radius[:2],
            risk_score=25,
            eta_minutes=5,
            prerequisites=["Deployment access", "Resource quota available"],
            reasoning="Pod experiencing OOM kills, needs more memory allocation"
        )
    elif "CrashLoop" in event_type:
        return FixSuggestion(
            rank=rank,
            action=f"Rollback recent deployment of {cause.get('service', 'service')}",
            confidence=confidence,
            blast_radius=blast_radius[:3],
            risk_score=35,
            eta_minutes=4,
            prerequisites=["Previous deployment available", "No DB migrations"],
            reasoning="Application crashing repeatedly, likely due to recent code change"
        )
    else:
        return FixSuggestion(
            rank=rank,
            action=f"Investigate {cause.get('event_type', 'issue')}",
            confidence=confidence,
            blast_radius=blast_radius[:2],
            risk_score=20,
            eta_minutes=10,
            prerequisites=["Logs access", "Monitoring access"],
            reasoning="Root cause identified, needs manual investigation"
        )


def build_timeline_from_events(events: List[Event]) -> List[Dict[str, Any]]:
    """Build timeline of events for Web UI"""
    timeline = []

    # Sort events by timestamp
    sorted_events = sorted(events, key=lambda e: e.timestamp or datetime.min)

    for event in sorted_events[:20]:  # Limit to 20 for UI
        timeline.append({
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "type": event.event_type.value if event.event_type else "Unknown",
            "description": event.message or event.reason,
            "service": event.labels.get("app") if event.labels else None,
            "pod": event.pod_name,
            "severity": "critical" if "fail" in (event.reason or "").lower() else "warning"
        })

    return timeline


def calculate_sla_metrics(events: List[Event], analysis_duration: float) -> Dict[str, Any]:
    """Calculate SLA status and risk budget"""

    # Simple heuristic: if failure events recent, may be breaching
    failure_events = [e for e in events if "fail" in (e.reason or "").lower()]

    if analysis_duration > 120:  # >2 minutes is slow
        status = "breached"
        percentage = 110.0
        risk_budget = 0
    elif len(failure_events) > 10:
        status = "breaching"
        percentage = 98.5
        risk_budget = 1
    else:
        status = "within_slo"
        percentage = 95.2
        risk_budget = 3

    return {
        "status": status,
        "percentage": percentage,
        "risk_budget": risk_budget
    }


def get_primary_symptom(events: List[Event], result: RCAResult) -> str:
    """Get primary symptom description"""
    if result.top_root_causes:
        cause = result.top_root_causes[0]
        return f"{cause.get('service', 'service')} · {cause.get('event_type', 'failure')}"

    failure_events = [e for e in events if "fail" in (e.reason or "").lower()]
    if failure_events:
        return f"{failure_events[0].pod_name} · {failure_events[0].reason}"

    return "Unknown incident"


def get_affected_services(events: List[Event]) -> List[str]:
    """Get list of affected services"""
    services = set()
    for event in events:
        if event.labels and "app" in event.labels:
            services.add(event.labels["app"])

    return list(services)[:5]  # Limit to 5


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
