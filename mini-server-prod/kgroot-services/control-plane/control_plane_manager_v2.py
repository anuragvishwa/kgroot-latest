"""
Control Plane Manager V2 - Pure Control Plane Model

Responsibilities:
1. Monitor cluster.registry for new client registrations
2. Monitor cluster.heartbeat for client health
3. Dynamically spawn per-client containers:
   - kg-event-normalizer-{client-id}
   - kg-log-normalizer-{client-id}
   - kg-graph-builder-{client-id}
4. Clean up stale clients (no heartbeat for 2 minutes)
5. Manage Neo4j graph isolation per client

Architecture:
  Client "af-9" publishes to cluster.registry
    ↓
  Control Plane detects new client
    ↓
  Spawns containers:
    - kg-event-normalizer-af-9 (consumer group: "event-normalizer-af-9")
    - kg-log-normalizer-af-9 (consumer group: "log-normalizer-af-9")
    - kg-graph-builder-af-9 (consumer group: "graph-builder-af-9")
    ↓
  Each container reads from SHARED topics but isolated via consumer groups
"""

import json
import logging
import docker
import time
from typing import Dict, Optional, Set
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from collections import defaultdict
import threading

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ControlPlaneManagerV2:
    """
    Manages per-client container lifecycle based on registry and heartbeat
    """

    def __init__(self, kafka_brokers: str, docker_network: str = "mini-server-prod_kg-network"):
        import os

        self.kafka_brokers = kafka_brokers
        self.docker_network = docker_network
        self.docker_client = docker.from_env()

        # Container images (from environment variables)
        self.event_normalizer_image = os.getenv("EVENT_NORMALIZER_IMAGE", "anuragvishwa/kg-event-normalizer:1.0.0")
        self.log_normalizer_image = os.getenv("LOG_NORMALIZER_IMAGE", "anuragvishwa/kg-log-normalizer:1.0.0")
        self.graph_builder_image = os.getenv("GRAPH_BUILDER_IMAGE", "anuragvishwa/kg-graph-builder:1.0.20")

        # Neo4j connection (from environment variables)
        self.neo4j_uri = os.getenv("NEO4J_URI", "bolt://kg-neo4j:7687")
        self.neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD", "Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA")

        # Track client state
        self.registered_clients: Dict[str, Dict] = {}  # client_id → registration data
        self.last_heartbeat: Dict[str, datetime] = {}  # client_id → last heartbeat time
        self.spawned_containers: Dict[str, Set[str]] = defaultdict(set)  # client_id → {container_ids}

        # Safe JSON deserializer that handles malformed messages
        def safe_json_deserializer(m):
            if not m:
                return None
            try:
                decoded = m.decode('utf-8').strip()
                if not decoded:
                    return None

                # Try standard JSON parsing first
                try:
                    return json.loads(decoded)
                except json.JSONDecodeError as e:
                    # If "Extra data" error, try to extract first valid JSON object
                    if "Extra data" in str(e):
                        decoder = json.JSONDecoder()
                        obj, idx = decoder.raw_decode(decoded)
                        logger.debug(f"Extracted JSON from message with extra data (ignored {len(decoded)-idx} chars)")
                        return obj
                    raise

            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to deserialize message: {e} - skipping")
                return None

        # Kafka consumers
        self.registry_consumer = KafkaConsumer(
            'cluster.registry',
            bootstrap_servers=kafka_brokers,
            group_id='control-plane-registry',
            value_deserializer=safe_json_deserializer,
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest',  # Read all registrations from beginning
            enable_auto_commit=True,
        )

        self.heartbeat_consumer = KafkaConsumer(
            'cluster.heartbeat',
            bootstrap_servers=kafka_brokers,
            group_id='control-plane-heartbeat',
            value_deserializer=safe_json_deserializer,
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='latest',  # Only care about recent heartbeats
            enable_auto_commit=True,
        )

        logger.info("✅ Control Plane Manager V2 initialized")
        logger.info(f"   Kafka brokers: {kafka_brokers}")
        logger.info(f"   Docker network: {docker_network}")

    def _spawn_event_normalizer(self, client_id: str) -> Optional[str]:
        """Spawn event normalizer for specific client"""
        container_name = f"kg-event-normalizer-{client_id}"

        try:
            # Check if already exists
            existing = self.docker_client.containers.list(filters={"name": container_name})
            if existing:
                logger.info(f"   ✅ Event normalizer already exists: {container_name}")
                return existing[0].id

            # Spawn new container
            container = self.docker_client.containers.run(
                image=self.event_normalizer_image,
                name=container_name,
                environment={
                    "KAFKA_BROKERS": self.kafka_brokers,
                    "CLIENT_ID": client_id,  # ← KEY: Client ID passed as env var
                },
                network=self.docker_network,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                command=["python", "normalizers/event_normalizer_v2.py"]
            )

            logger.info(f"   ✅ Spawned event normalizer: {container_name} (ID: {container.short_id})")
            return container.id

        except Exception as e:
            logger.error(f"   ❌ Failed to spawn event normalizer for {client_id}: {e}")
            return None

    def _spawn_log_normalizer(self, client_id: str) -> Optional[str]:
        """Spawn log normalizer for specific client"""
        container_name = f"kg-log-normalizer-{client_id}"

        try:
            existing = self.docker_client.containers.list(filters={"name": container_name})
            if existing:
                logger.info(f"   ✅ Log normalizer already exists: {container_name}")
                return existing[0].id

            container = self.docker_client.containers.run(
                image=self.log_normalizer_image,
                name=container_name,
                environment={
                    "KAFKA_BROKERS": self.kafka_brokers,
                    "CLIENT_ID": client_id,
                },
                network=self.docker_network,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                command=["python", "normalizers/log_normalizer.py"]
            )

            logger.info(f"   ✅ Spawned log normalizer: {container_name} (ID: {container.short_id})")
            return container.id

        except Exception as e:
            logger.error(f"   ❌ Failed to spawn log normalizer for {client_id}: {e}")
            return None

    def _spawn_graph_builder(self, client_id: str) -> Optional[str]:
        """Spawn graph builder for specific client"""
        container_name = f"kg-graph-builder-{client_id}"

        try:
            existing = self.docker_client.containers.list(filters={"name": container_name})
            if existing:
                logger.info(f"   ✅ Graph builder already exists: {container_name}")
                return existing[0].id

            container = self.docker_client.containers.run(
                image=self.graph_builder_image,
                name=container_name,
                environment={
                    "KAFKA_BROKERS": self.kafka_brokers,
                    "CLIENT_ID": client_id,
                    "NEO4J_URI": self.neo4j_uri,
                    "NEO4J_USER": self.neo4j_user,
                    "NEO4J_PASS": self.neo4j_password,  # ← Go binary uses NEO4J_PASS not NEO4J_PASSWORD
                    "NEO4J_DATABASE": client_id,  # ← Separate database per client
                },
                network=self.docker_network,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
                command=["./graph-builder"]
            )

            logger.info(f"   ✅ Spawned graph builder: {container_name} (ID: {container.short_id})")
            return container.id

        except Exception as e:
            logger.error(f"   ❌ Failed to spawn graph builder for {client_id}: {e}")
            return None

    def _spawn_all_for_client(self, client_id: str, registration_data: Dict):
        """Spawn all required containers for a client"""
        logger.info(f"🚀 Spawning containers for client: {client_id}")
        logger.info(f"   Cluster: {registration_data.get('cluster_name', 'unknown')}")

        spawned_ids = set()

        # Spawn event normalizer
        event_norm_id = self._spawn_event_normalizer(client_id)
        if event_norm_id:
            spawned_ids.add(event_norm_id)

        # Spawn log normalizer
        log_norm_id = self._spawn_log_normalizer(client_id)
        if log_norm_id:
            spawned_ids.add(log_norm_id)

        # Spawn graph builder
        graph_id = self._spawn_graph_builder(client_id)
        if graph_id:
            spawned_ids.add(graph_id)

        self.spawned_containers[client_id] = spawned_ids

        logger.info(f"✅ Successfully spawned {len(spawned_ids)} containers for client {client_id}")

    def _cleanup_client(self, client_id: str):
        """Stop and remove all containers for a stale client"""
        logger.info(f"🧹 Cleaning up stale client: {client_id}")

        if client_id not in self.spawned_containers:
            logger.info(f"   No containers to clean up for {client_id}")
            return

        for container_id in self.spawned_containers[client_id]:
            try:
                container = self.docker_client.containers.get(container_id)
                container.stop(timeout=10)
                container.remove()
                logger.info(f"   ✅ Stopped and removed container: {container.name}")
            except Exception as e:
                logger.error(f"   ❌ Failed to remove container {container_id}: {e}")

        del self.spawned_containers[client_id]
        # NOTE: We keep registered_clients[client_id] so we can re-spawn if heartbeat resumes
        # Only delete last_heartbeat to mark as stale
        if client_id in self.last_heartbeat:
            del self.last_heartbeat[client_id]
        logger.info(f"✅ Cleanup complete for client {client_id} (registration preserved for auto-respawn)")

    def _process_registry_message(self, message):
        """Process client registration"""
        try:
            # Skip tombstone messages (None values)
            if message.value is None:
                logger.debug("Skipping tombstone message in cluster.registry")
                return

            # Debug: Check message type
            logger.debug(f"Registry message type: {type(message.value)}, value: {message.value}")

            # If message.value is a string, parse it as JSON
            if isinstance(message.value, str):
                # Skip empty strings
                if not message.value.strip():
                    logger.debug("Skipping empty string message in cluster.registry")
                    return
                try:
                    message_data = json.loads(message.value)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse registry message as JSON: {e}")
                    return
            else:
                message_data = message.value

            client_id = message_data.get('client_id')
            if not client_id:
                logger.warning("⚠️  Registry message missing client_id")
                return

            # Check if this is a new client
            if client_id not in self.registered_clients:
                logger.info(f"📋 New client registered: {client_id}")
                self.registered_clients[client_id] = message_data
                self.last_heartbeat[client_id] = datetime.utcnow()

                # Spawn containers for this client
                self._spawn_all_for_client(client_id, message_data)
            else:
                # Update registration data
                self.registered_clients[client_id] = message_data

        except Exception as e:
            logger.error(f"Error processing registry message: {e}", exc_info=True)

    def _process_heartbeat_message(self, message):
        """Process client heartbeat"""
        try:
            # Skip tombstone messages (None values)
            if message.value is None:
                logger.debug("Skipping tombstone message in cluster.heartbeat")
                return

            client_id = message.value.get('client_id')
            if not client_id:
                return

            # Update last heartbeat time
            self.last_heartbeat[client_id] = datetime.utcnow()

            # AUTO-RESPAWN: If client was previously stale and containers were killed,
            # but heartbeat resumed, re-spawn containers automatically
            if client_id in self.registered_clients and client_id not in self.spawned_containers:
                logger.info(f"🔄 Heartbeat resumed for stale client {client_id} - re-spawning containers")
                self._spawn_all_for_client(client_id, self.registered_clients[client_id])

        except Exception as e:
            logger.error(f"Error processing heartbeat message: {e}", exc_info=True)

    def _check_stale_clients(self):
        """Check for clients with no heartbeat for 2 minutes"""
        stale_threshold = datetime.utcnow() - timedelta(minutes=2)

        stale_clients = []
        for client_id, last_hb in self.last_heartbeat.items():
            if last_hb < stale_threshold:
                stale_clients.append(client_id)

        for client_id in stale_clients:
            logger.warning(f"⚠️  Client {client_id} is stale (no heartbeat for 2+ min)")
            self._cleanup_client(client_id)

    def _monitor_registry(self):
        """Background thread to monitor cluster.registry"""
        logger.info("🔍 Monitoring cluster.registry for new clients...")

        try:
            for message in self.registry_consumer:
                self._process_registry_message(message)
        except Exception as e:
            logger.error(f"Registry monitor crashed: {e}", exc_info=True)

    def _monitor_heartbeat(self):
        """Background thread to monitor cluster.heartbeat"""
        logger.info("💓 Monitoring cluster.heartbeat for client health...")

        try:
            for message in self.heartbeat_consumer:
                self._process_heartbeat_message(message)
        except Exception as e:
            logger.error(f"Heartbeat monitor crashed: {e}", exc_info=True)

    def _cleanup_loop(self):
        """Background thread to periodically check for stale clients"""
        logger.info("🧹 Starting cleanup loop (checks every 30 seconds)...")

        while True:
            try:
                time.sleep(30)
                self._check_stale_clients()
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}", exc_info=True)

    def run(self):
        """Start control plane manager"""
        logger.info("🚀 Control Plane Manager V2 starting...")
        logger.info("")
        logger.info("📋 Responsibilities:")
        logger.info("   1. Monitor cluster.registry for new clients")
        logger.info("   2. Monitor cluster.heartbeat for client health")
        logger.info("   3. Spawn per-client containers (normalizers, graph builders)")
        logger.info("   4. Clean up stale clients (no heartbeat for 2+ min)")
        logger.info("")

        # Start background threads
        registry_thread = threading.Thread(target=self._monitor_registry, daemon=True)
        heartbeat_thread = threading.Thread(target=self._monitor_heartbeat, daemon=True)
        cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)

        registry_thread.start()
        heartbeat_thread.start()
        cleanup_thread.start()

        logger.info("✅ All monitoring threads started")
        logger.info("")
        logger.info("📊 Current state:")
        logger.info(f"   Registered clients: {len(self.registered_clients)}")
        logger.info(f"   Active containers: {sum(len(c) for c in self.spawned_containers.values())}")
        logger.info("")

        # Keep main thread alive
        try:
            while True:
                time.sleep(60)

                # Periodic status report
                logger.info(f"📊 Status: {len(self.registered_clients)} clients, "
                            f"{sum(len(c) for c in self.spawned_containers.values())} containers")

        except KeyboardInterrupt:
            logger.info("🛑 Shutting down Control Plane Manager...")
            self.registry_consumer.close()
            self.heartbeat_consumer.close()


if __name__ == "__main__":
    import os

    kafka_brokers = os.getenv("KAFKA_BROKERS", "kg-kafka:29092")
    docker_network = os.getenv("DOCKER_NETWORK", "mini-server-prod_kg-network")

    manager = ControlPlaneManagerV2(kafka_brokers, docker_network)
    manager.run()
