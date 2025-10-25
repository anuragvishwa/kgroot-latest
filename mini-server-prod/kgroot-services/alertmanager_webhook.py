#!/usr/bin/env python3
"""
KGroot RCA - Alertmanager Webhook Receiver

Receives alerts from Prometheus Alertmanager and triggers RCA analysis.
Integrates with existing kg-alert-receiver and adds RCA capabilities.

Features:
- Receives Alertmanager webhook POST requests
- Converts alerts to KGroot Events
- Groups related alerts
- Triggers RCA when multiple related alerts fire
- Can co-exist with existing alert-receiver
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.event import Event, EventType, EventSeverity
from rca_orchestrator import RCAOrchestrator

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="KGroot RCA Webhook Receiver")

# Global state
rca_orchestrator: Optional[RCAOrchestrator] = None
alert_buffer: List[Event] = []
RCA_TRIGGER_THRESHOLD = 3  # Number of alerts to trigger RCA
RCA_TIME_WINDOW = 300  # 5 minutes


# ═══════════════════════════════════════════════════════════════════════════
# Alert Type Mapping
# ═══════════════════════════════════════════════════════════════════════════

ALERT_TYPE_MAPPING = {
    # Common Prometheus alerts
    "KubePodCrashLooping": EventType.POD_RESTART,
    "KubePodNotReady": EventType.POD_FAILED,
    "KubeNodeNotReady": EventType.SERVICE_DOWN,
    "KubeNodeUnreachable": EventType.SERVICE_DOWN,
    "KubeMemoryOvercommit": EventType.MEMORY_HIGH,
    "KubeCPUOvercommit": EventType.CPU_HIGH,
    "KubePersistentVolumeFillingUp": EventType.DISK_HIGH,
    "KubeDeploymentReplicasMismatch": EventType.DEPLOYMENT,
    "KubeJobFailed": EventType.POD_FAILED,
    "KubeContainerOOMKilled": EventType.OOM_KILL,

    # Custom alerts
    "HighErrorRate": EventType.ERROR_RATE_HIGH,
    "HighLatency": EventType.LATENCY_HIGH,
    "ServiceDown": EventType.SERVICE_DOWN,
    "DatabaseConnectionFailed": EventType.NETWORK_ERROR,
}


def map_alert_to_event_type(alert_name: str) -> EventType:
    """Map Alertmanager alert name to KGroot EventType"""
    # Check exact match
    if alert_name in ALERT_TYPE_MAPPING:
        return ALERT_TYPE_MAPPING[alert_name]

    # Fuzzy matching
    alert_lower = alert_name.lower()
    if "crash" in alert_lower or "restart" in alert_lower:
        return EventType.POD_RESTART
    elif "memory" in alert_lower or "oom" in alert_lower:
        return EventType.MEMORY_HIGH
    elif "cpu" in alert_lower:
        return EventType.CPU_HIGH
    elif "disk" in alert_lower or "volume" in alert_lower:
        return EventType.DISK_HIGH
    elif "network" in alert_lower or "connection" in alert_lower:
        return EventType.NETWORK_ERROR
    elif "error" in alert_lower:
        return EventType.ERROR_RATE_HIGH
    elif "latency" in alert_lower or "slow" in alert_lower:
        return EventType.LATENCY_HIGH
    elif "node" in alert_lower or "service" in alert_lower:
        return EventType.SERVICE_DOWN

    return EventType.CUSTOM


def map_severity(severity: str) -> EventSeverity:
    """Map Alertmanager severity to KGroot EventSeverity"""
    severity_lower = severity.lower()
    if severity_lower == "critical":
        return EventSeverity.CRITICAL
    elif severity_lower == "warning":
        return EventSeverity.WARNING
    elif severity_lower == "info":
        return EventSeverity.INFO
    else:
        return EventSeverity.WARNING


# ═══════════════════════════════════════════════════════════════════════════
# Alert Processing
# ═══════════════════════════════════════════════════════════════════════════

def convert_alert_to_event(alert: Dict) -> Event:
    """Convert Alertmanager alert to KGroot Event"""

    # Extract basic info
    labels = alert.get('labels', {})
    annotations = alert.get('annotations', {})

    alert_name = labels.get('alertname', 'Unknown')
    severity = labels.get('severity', 'warning')
    namespace = labels.get('namespace', labels.get('exported_namespace', 'default'))
    service = labels.get('service', labels.get('pod', labels.get('job', 'unknown')))

    # Map to KGroot types
    event_type = map_alert_to_event_type(alert_name)
    event_severity = map_severity(severity)

    # Extract timestamp
    starts_at = alert.get('startsAt', datetime.now(timezone.utc).isoformat())
    timestamp = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))

    # Build message
    summary = annotations.get('summary', annotations.get('message', alert_name))
    description = annotations.get('description', '')
    message = f"{summary}\n{description}".strip()

    # Extract pod/node/container from labels
    pod_name = labels.get('pod')
    node_name = labels.get('node')
    container_name = labels.get('container')

    # Create event
    event_id = f"alert-{alert.get('fingerprint', hash(json.dumps(alert)))}"

    # Store full alert data in details field
    event_details = {
        'alert_source': 'alertmanager',
        'alert_fingerprint': alert.get('fingerprint'),
        'instance': labels.get('instance'),
        'raw_alert': alert
    }

    return Event(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        service=service,
        namespace=namespace,
        severity=event_severity,
        message=message,
        pod_name=pod_name,
        node=node_name,
        container=container_name,
        labels=labels,
        annotations=annotations,
        details=event_details
    )


async def trigger_rca(events: List[Event]):
    """Trigger RCA analysis for grouped alerts"""
    if not rca_orchestrator or len(events) == 0:
        return

    try:
        logger.info(f"🔍 Triggering RCA for {len(events)} alerts")

        # Generate fault ID
        fault_id = f"alert-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # Run RCA
        result = await rca_orchestrator.analyze_failure(
            events=events,
            fault_id=fault_id,
            time_window_seconds=RCA_TIME_WINDOW
        )

        # Log results
        if result and result.get("ranked_root_causes"):
            top_causes = result["ranked_root_causes"][:3]
            logger.info("🎯 Top Root Causes:")
            for i, cause in enumerate(top_causes, 1):
                logger.info(f"  {i}. {cause['event_type']} in {cause['service']} (confidence: {cause['rank_score']:.2f})")
                logger.info(f"     Explanation: {cause['explanation'][:100]}...")

            if result.get("llm_analysis"):
                logger.info(f"💡 LLM Insight: {result['llm_analysis'].get('summary', 'N/A')}")

        return result

    except Exception as e:
        logger.error(f"Error in RCA analysis: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/webhook")
async def alertmanager_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive Alertmanager webhook POST

    Expected format:
    {
      "version": "4",
      "groupKey": "...",
      "status": "firing",
      "alerts": [
        {
          "labels": {...},
          "annotations": {...},
          "startsAt": "...",
          "endsAt": "..."
        }
      ]
    }
    """
    try:
        payload = await request.json()

        status = payload.get('status', 'firing')
        alerts = payload.get('alerts', [])

        logger.info(f"📥 Received webhook: {len(alerts)} alerts, status={status}")

        # Process firing alerts
        if status == "firing" and alerts:
            events = []

            for alert in alerts:
                try:
                    event = convert_alert_to_event(alert)
                    events.append(event)
                    alert_buffer.append(event)

                    logger.info(f"  Alert: {event.event_type.value} - {event.service} - {event.message[:50]}")

                except Exception as e:
                    logger.error(f"Error converting alert: {e}")

            # Trigger RCA if threshold reached
            if len(alert_buffer) >= RCA_TRIGGER_THRESHOLD:
                # Run RCA in background
                background_tasks.add_task(trigger_rca, alert_buffer.copy())

                # Clear buffer (keep last few for context)
                alert_buffer.clear()
                alert_buffer.extend(events[-2:])

        # Handle resolved alerts
        elif status == "resolved":
            logger.info(f"✓ Alerts resolved: {len(alerts)}")

        return JSONResponse(
            status_code=200,
            content={"status": "ok", "processed": len(alerts)}
        )

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "rca_enabled": rca_orchestrator is not None,
        "buffer_size": len(alert_buffer)
    }


@app.get("/status")
async def status():
    """Status endpoint with more details"""
    return {
        "service": "KGroot RCA Webhook Receiver",
        "rca_enabled": rca_orchestrator is not None,
        "buffer_size": len(alert_buffer),
        "trigger_threshold": RCA_TRIGGER_THRESHOLD,
        "time_window": RCA_TIME_WINDOW,
        "recent_alerts": [
            {
                "event_type": e.event_type.value,
                "service": e.service,
                "timestamp": e.timestamp.isoformat()
            }
            for e in alert_buffer[-5:]
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    global rca_orchestrator

    logger.info("════════════════════════════════════════════════════════════════")
    logger.info("KGroot RCA - Alertmanager Webhook Receiver")
    logger.info("════════════════════════════════════════════════════════════════")

    # Load config
    config_path = os.getenv("KGROOT_CONFIG", "config.yaml")
    enable_rca = os.getenv("ENABLE_RCA", "true").lower() == "true"

    if enable_rca and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Initialize RCA orchestrator
            if config.get('openai', {}).get('enable_llm_analysis', False):
                rca_orchestrator = RCAOrchestrator(
                    openai_api_key=config['openai']['api_key'],
                    enable_llm=True,
                    llm_model=config['openai'].get('chat_model', 'gpt-4o'),
                    reasoning_effort=config['openai'].get('reasoning_effort', 'medium'),
                    verbosity=config['openai'].get('verbosity', 'medium'),
                )
                logger.info("✓ RCA Orchestrator initialized")
            else:
                logger.info("⚠️  LLM analysis disabled in config")

        except Exception as e:
            logger.warning(f"Could not initialize RCA: {e}")
            logger.info("Running in webhook-only mode (no RCA)")
    else:
        logger.info("Running in webhook-only mode (RCA disabled)")

    logger.info(f"✓ Listening for Alertmanager webhooks on port {os.getenv('PORT', 8081)}")
    logger.info("")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Run the webhook receiver"""
    port = int(os.getenv("PORT", 8081))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
