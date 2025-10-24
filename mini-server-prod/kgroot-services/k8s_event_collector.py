#!/usr/bin/env python3
"""
KGroot RCA - Kubernetes Event Collector

Connects to remote K8s cluster and collects events for RCA analysis.
Runs in Docker Compose alongside other services.

Features:
- Watches K8s events in real-time
- Converts K8s events to KGroot Event objects
- Enriches with pod/node/deployment context
- Sends to RCA orchestrator for analysis
- Handles multiple namespaces
- Automatic reconnection on failures
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import yaml

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Add parent directory to path for imports
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


@dataclass
class K8sEventCollectorConfig:
    """Configuration for K8s event collector"""
    kubeconfig_path: str = "/config/kubeconfig.yaml"
    namespaces: List[str] = None  # None = all namespaces
    event_resync_seconds: int = 300
    enable_rca: bool = True
    rca_trigger_threshold: int = 3  # Number of related events to trigger RCA
    rca_time_window_seconds: int = 300  # 5 minutes


# ═══════════════════════════════════════════════════════════════════════════
# Event Type Mapping
# ═══════════════════════════════════════════════════════════════════════════

K8S_EVENT_TYPE_MAPPING = {
    # Pod events
    "BackOff": EventType.POD_RESTART,
    "Failed": EventType.POD_FAILED,
    "Killing": EventType.POD_KILLED,
    "Unhealthy": EventType.HEALTH_CHECK_FAILED,
    "FailedScheduling": EventType.DEPLOYMENT_UPDATE,
    "FailedMount": EventType.DISK_PRESSURE,

    # Resource events
    "OOMKilling": EventType.MEMORY_HIGH,
    "Evicted": EventType.POD_EVICTED,
    "FailedKillPod": EventType.POD_FAILED,

    # Node events
    "NodeNotReady": EventType.NODE_DOWN,
    "NodeReady": EventType.NODE_RECOVERED,
    "RegisteredNode": EventType.NODE_RECOVERED,

    # Network events
    "FailedCreateEndpoint": EventType.NETWORK_ERROR,
    "FailedAttachVolume": EventType.DISK_PRESSURE,

    # Default
    "Warning": EventType.ERROR_RATE_HIGH,
}


def map_k8s_event_type(reason: str, event_type: str) -> EventType:
    """Map K8s event reason to KGroot EventType"""
    if reason in K8S_EVENT_TYPE_MAPPING:
        return K8S_EVENT_TYPE_MAPPING[reason]

    # Fallback based on event type
    if event_type == "Warning":
        return EventType.ERROR_RATE_HIGH

    return EventType.CUSTOM


def map_k8s_severity(event_type: str) -> EventSeverity:
    """Map K8s event type to severity"""
    if event_type == "Warning":
        return EventSeverity.WARNING
    elif event_type == "Error":
        return EventSeverity.CRITICAL
    else:
        return EventSeverity.INFO


# ═══════════════════════════════════════════════════════════════════════════
# K8s Event Collector
# ═══════════════════════════════════════════════════════════════════════════

class K8sEventCollector:
    """Collects events from remote Kubernetes cluster"""

    def __init__(self, config: K8sEventCollectorConfig, rca_orchestrator: Optional[RCAOrchestrator] = None):
        self.config = config
        self.rca_orchestrator = rca_orchestrator

        # Event buffering for RCA trigger detection
        self.event_buffer: List[Event] = []
        self.processed_event_ids: Set[str] = set()

        # K8s clients (initialized in connect())
        self.core_v1 = None
        self.apps_v1 = None
        self.api_client = None

        # Caches for enrichment
        self.pod_cache: Dict[str, Dict] = {}
        self.node_cache: Dict[str, Dict] = {}
        self.deployment_cache: Dict[str, Dict] = {}

    async def connect(self):
        """Connect to K8s cluster using kubeconfig"""
        try:
            logger.info(f"Loading kubeconfig from {self.config.kubeconfig_path}")

            # Load kubeconfig
            config.load_kube_config(config_file=self.config.kubeconfig_path)

            # Initialize clients
            self.api_client = client.ApiClient()
            self.core_v1 = client.CoreV1Api(self.api_client)
            self.apps_v1 = client.AppsV1Api(self.api_client)

            # Test connection
            version = await asyncio.to_thread(self.core_v1.get_api_resources)
            logger.info("✓ Successfully connected to Kubernetes cluster")

            # Warm up caches
            await self._warm_caches()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to K8s cluster: {e}")
            raise

    async def _warm_caches(self):
        """Pre-populate caches with current state"""
        try:
            logger.info("Warming up caches...")

            # Cache pods
            if self.config.namespaces:
                for ns in self.config.namespaces:
                    pods = await asyncio.to_thread(
                        self.core_v1.list_namespaced_pod, namespace=ns
                    )
                    for pod in pods.items:
                        self.pod_cache[f"{pod.metadata.namespace}/{pod.metadata.name}"] = {
                            "node": pod.spec.node_name,
                            "labels": pod.metadata.labels or {},
                            "phase": pod.status.phase,
                        }
            else:
                pods = await asyncio.to_thread(self.core_v1.list_pod_for_all_namespaces)
                for pod in pods.items:
                    self.pod_cache[f"{pod.metadata.namespace}/{pod.metadata.name}"] = {
                        "node": pod.spec.node_name,
                        "labels": pod.metadata.labels or {},
                        "phase": pod.status.phase,
                    }

            # Cache nodes
            nodes = await asyncio.to_thread(self.core_v1.list_node)
            for node in nodes.items:
                self.node_cache[node.metadata.name] = {
                    "labels": node.metadata.labels or {},
                    "conditions": {c.type: c.status for c in node.status.conditions} if node.status.conditions else {},
                }

            logger.info(f"✓ Cached {len(self.pod_cache)} pods, {len(self.node_cache)} nodes")

        except Exception as e:
            logger.warning(f"Failed to warm caches: {e}")

    async def watch_events(self):
        """Watch K8s events and convert to KGroot events"""
        logger.info("Starting event watcher...")

        w = watch.Watch()

        while True:
            try:
                # Watch events
                if self.config.namespaces:
                    # Watch specific namespaces
                    for namespace in self.config.namespaces:
                        await self._watch_namespace_events(w, namespace)
                else:
                    # Watch all namespaces
                    await self._watch_all_events(w)

            except ApiException as e:
                logger.error(f"K8s API error: {e}")
                await asyncio.sleep(10)  # Wait before retry

            except Exception as e:
                logger.error(f"Unexpected error in event watcher: {e}")
                await asyncio.sleep(10)

    async def _watch_namespace_events(self, w: watch.Watch, namespace: str):
        """Watch events in a specific namespace"""
        logger.info(f"Watching events in namespace: {namespace}")

        async for event in asyncio.to_thread(
            w.stream,
            self.core_v1.list_namespaced_event,
            namespace=namespace,
            timeout_seconds=self.config.event_resync_seconds
        ):
            await self._process_k8s_event(event)

    async def _watch_all_events(self, w: watch.Watch):
        """Watch events across all namespaces"""
        logger.info("Watching events in all namespaces")

        try:
            for event in w.stream(
                self.core_v1.list_event_for_all_namespaces,
                timeout_seconds=self.config.event_resync_seconds
            ):
                await self._process_k8s_event(event)
        except Exception as e:
            logger.error(f"Error watching events: {e}")

    async def _process_k8s_event(self, k8s_event: Dict):
        """Process a K8s event and convert to KGroot Event"""
        try:
            event_obj = k8s_event['object']
            event_type = k8s_event['type']  # ADDED, MODIFIED, DELETED

            # Skip if already processed
            event_id = f"{event_obj.metadata.namespace}/{event_obj.metadata.name}"
            if event_id in self.processed_event_ids:
                return

            # Convert to KGroot Event
            kg_event = await self._convert_k8s_event(event_obj)

            if kg_event:
                logger.info(f"📥 Event: {kg_event.event_type.value} - {kg_event.service} - {kg_event.message}")

                # Add to buffer
                self.event_buffer.append(kg_event)
                self.processed_event_ids.add(event_id)

                # Trigger RCA if threshold reached
                if self.config.enable_rca and len(self.event_buffer) >= self.config.rca_trigger_threshold:
                    await self._trigger_rca()

        except Exception as e:
            logger.error(f"Error processing K8s event: {e}")

    async def _convert_k8s_event(self, k8s_event) -> Optional[Event]:
        """Convert K8s Event to KGroot Event"""
        try:
            # Extract basic info
            namespace = k8s_event.metadata.namespace
            reason = k8s_event.reason
            message = k8s_event.message
            event_time = k8s_event.last_timestamp or k8s_event.event_time or datetime.now(timezone.utc)

            # Map event type
            kg_event_type = map_k8s_event_type(reason, k8s_event.type)
            kg_severity = map_k8s_severity(k8s_event.type)

            # Extract involved object
            involved_obj = k8s_event.involved_object
            service_name = involved_obj.name if involved_obj else "unknown"

            # Enrich with context
            labels = {}
            annotations = {}
            metrics = {}

            if involved_obj and involved_obj.kind == "Pod":
                pod_key = f"{namespace}/{involved_obj.name}"
                if pod_key in self.pod_cache:
                    pod_info = self.pod_cache[pod_key]
                    labels = pod_info.get("labels", {})
                    metrics["node"] = pod_info.get("node")
                    metrics["phase"] = pod_info.get("phase")

            # Create KGroot Event
            return Event(
                event_id=f"k8s-{namespace}-{k8s_event.metadata.name}-{int(event_time.timestamp())}",
                event_type=kg_event_type,
                timestamp=event_time,
                service=service_name,
                namespace=namespace,
                severity=kg_severity,
                message=message,
                source="kubernetes",
                labels=labels,
                annotations=annotations,
                metrics=metrics,
                raw_data={
                    "reason": reason,
                    "kind": involved_obj.kind if involved_obj else None,
                    "count": k8s_event.count,
                }
            )

        except Exception as e:
            logger.error(f"Error converting K8s event: {e}")
            return None

    async def _trigger_rca(self):
        """Trigger RCA analysis when threshold is reached"""
        if not self.rca_orchestrator or len(self.event_buffer) == 0:
            return

        try:
            logger.info(f"🔍 Triggering RCA analysis for {len(self.event_buffer)} events")

            # Get events from buffer
            events = self.event_buffer[-self.config.rca_trigger_threshold:]

            # Generate fault ID
            fault_id = f"k8s-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

            # Run RCA
            result = await self.rca_orchestrator.analyze_failure(
                events=events,
                fault_id=fault_id,
                time_window_seconds=self.config.rca_time_window_seconds
            )

            # Log results
            if result and result.get("ranked_root_causes"):
                top_cause = result["ranked_root_causes"][0]
                logger.info(f"🎯 Top Root Cause: {top_cause['event_type']} in {top_cause['service']} (confidence: {top_cause['rank_score']:.2f})")

            # Clear buffer (keep last few for overlap)
            self.event_buffer = self.event_buffer[-5:]

        except Exception as e:
            logger.error(f"Error triggering RCA: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Main entry point"""

    # Load configuration
    config_path = os.getenv("KGROOT_CONFIG", "config.yaml")
    kubeconfig_path = os.getenv("KUBECONFIG_PATH", "/config/kubeconfig.yaml")

    logger.info("════════════════════════════════════════════════════════════════")
    logger.info("KGroot RCA - Kubernetes Event Collector")
    logger.info("════════════════════════════════════════════════════════════════")
    logger.info(f"Config: {config_path}")
    logger.info(f"Kubeconfig: {kubeconfig_path}")
    logger.info("")

    # Load KGroot config
    with open(config_path, 'r') as f:
        kg_config = yaml.safe_load(f)

    # Initialize RCA orchestrator (optional)
    rca_orchestrator = None
    if kg_config.get('openai', {}).get('enable_llm_analysis', False):
        try:
            rca_orchestrator = RCAOrchestrator(
                openai_api_key=kg_config['openai']['api_key'],
                enable_llm=True,
                llm_model=kg_config['openai'].get('chat_model', 'gpt-4o'),
                neo4j_uri=kg_config.get('neo4j', {}).get('uri'),
                neo4j_user=kg_config.get('neo4j', {}).get('user'),
                neo4j_password=kg_config.get('neo4j', {}).get('password'),
            )
            logger.info("✓ RCA Orchestrator initialized")
        except Exception as e:
            logger.warning(f"Could not initialize RCA orchestrator: {e}")

    # Initialize collector
    collector_config = K8sEventCollectorConfig(
        kubeconfig_path=kubeconfig_path,
        namespaces=os.getenv("WATCH_NAMESPACES", "").split(",") if os.getenv("WATCH_NAMESPACES") else None,
        enable_rca=os.getenv("ENABLE_RCA", "true").lower() == "true",
    )

    collector = K8sEventCollector(collector_config, rca_orchestrator)

    # Connect to K8s
    await collector.connect()

    # Start watching
    logger.info("✓ Starting event collection...")
    await collector.watch_events()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
