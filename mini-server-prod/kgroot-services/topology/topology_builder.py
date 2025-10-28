"""
Topology Builder Service
Constructs service dependency graph from K8s resource state

Based on KGroot Paper:
- Section 3: Dependencies Complexity - service interdependencies form complex networks
- Section 4.2: FEKG Construction - topology relationships for blast radius
- Critical for Web UI visualization and impact analysis
"""

import json
import logging
from typing import Dict, List, Set, Optional
from datetime import datetime
from kafka import KafkaConsumer, KafkaProducer
from collections import defaultdict
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ServiceNode:
    """Service node in topology graph"""
    name: str
    namespace: str
    type: str  # service, deployment, statefulset, daemonset
    replicas: int
    pods: List[str]
    labels: Dict


@dataclass
class ServiceEdge:
    """Dependency edge between services"""
    source: str  # Calling service
    target: str  # Called service
    edge_type: str  # http, grpc, tcp, database
    confidence: float  # 0-1, based on evidence strength


@dataclass
class TopologySnapshot:
    """Complete topology graph snapshot"""
    client_id: str
    cluster_name: str
    timestamp: str

    nodes: List[Dict]  # ServiceNode dicts
    edges: List[Dict]  # ServiceEdge dicts

    # Metadata
    namespace: str
    total_services: int
    total_connections: int

    def to_dict(self) -> Dict:
        return asdict(self)


class TopologyBuilder:
    """
    Builds service dependency graph from K8s state snapshots

    Inference strategies:
    1. Service-to-Service: K8s Service -> Endpoints -> Pods
    2. Network policies: Explicit allow rules
    3. ConfigMap/Secret references: Database connections, API URLs
    4. Environment variables: Service discovery URLs
    """

    def __init__(self, kafka_brokers: str):
        self.kafka_brokers = kafka_brokers

        # Consume resource state snapshots
        self.consumer = KafkaConsumer(
            'state.k8s.resource',
            bootstrap_servers=kafka_brokers,
            group_id='topology-builder',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
        )

        self.producer = KafkaProducer(
            bootstrap_servers=kafka_brokers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8'),
        )

        # In-memory state (per client)
        self.client_state: Dict[str, Dict] = defaultdict(lambda: {
            'services': {},
            'deployments': {},
            'pods': {},
            'endpoints': {},
            'configmaps': {},
        })

        logger.info("Topology Builder initialized")

    def _extract_dependencies_from_env(self, env_vars: List[Dict]) -> Set[str]:
        """Extract service dependencies from environment variables"""
        dependencies = set()

        for env in env_vars:
            name = env.get('name', '')
            value = env.get('value', '')

            # Common patterns for service references
            if any(keyword in name.upper() for keyword in ['URL', 'HOST', 'ENDPOINT', 'SERVICE']):
                # Extract service name from URLs like "http://api-service:8080"
                if 'http://' in value or 'https://' in value:
                    parts = value.split('//')
                    if len(parts) > 1:
                        host = parts[1].split(':')[0].split('/')[0]
                        if host and not host.startswith('localhost'):
                            dependencies.add(host)

                # Direct service names
                elif value and '.' in value and not value.startswith('$'):
                    dependencies.add(value.split('.')[0])

        return dependencies

    def _infer_dependencies_from_service(self, service_name: str, endpoints: Dict, client_state: Dict) -> List[ServiceEdge]:
        """Infer dependencies from Service -> Endpoints -> Pods"""
        edges = []

        # Get pods backing this service
        if service_name in endpoints:
            endpoint_pods = endpoints[service_name].get('pods', [])

            # For each pod, check its environment and config for outgoing calls
            for pod_name in endpoint_pods:
                if pod_name in client_state['pods']:
                    pod_spec = client_state['pods'][pod_name]

                    # Check containers for environment variables
                    containers = pod_spec.get('spec', {}).get('containers', [])
                    for container in containers:
                        env_vars = container.get('env', [])
                        dependencies = self._extract_dependencies_from_env(env_vars)

                        for dep_service in dependencies:
                            if dep_service != service_name and dep_service in client_state['services']:
                                edges.append(ServiceEdge(
                                    source=service_name,
                                    target=dep_service,
                                    edge_type='http',  # Assume HTTP by default
                                    confidence=0.7  # Medium confidence from env vars
                                ))

        return edges

    def _build_topology_for_client(self, client_id: str) -> Optional[TopologySnapshot]:
        """Build complete topology graph for a client"""
        client_state = self.client_state[client_id]

        if not client_state['services']:
            return None

        # Build nodes
        nodes = []
        for svc_name, svc_data in client_state['services'].items():
            node = ServiceNode(
                name=svc_name,
                namespace=svc_data.get('metadata', {}).get('namespace', 'default'),
                type='service',
                replicas=len(client_state['endpoints'].get(svc_name, {}).get('pods', [])),
                pods=client_state['endpoints'].get(svc_name, {}).get('pods', []),
                labels=svc_data.get('metadata', {}).get('labels', {})
            )
            nodes.append(asdict(node))

        # Build edges (infer dependencies)
        edges = []
        seen_edges = set()

        for svc_name in client_state['services'].keys():
            inferred_edges = self._infer_dependencies_from_service(
                svc_name,
                client_state['endpoints'],
                client_state
            )

            for edge in inferred_edges:
                edge_key = f"{edge.source}->{edge.target}"
                if edge_key not in seen_edges:
                    edges.append(asdict(edge))
                    seen_edges.add(edge_key)

        topology = TopologySnapshot(
            client_id=client_id,
            cluster_name=client_state.get('cluster_name', 'unknown'),
            timestamp=datetime.utcnow().isoformat(),
            nodes=nodes,
            edges=edges,
            namespace='all',  # Can be filtered per namespace
            total_services=len(nodes),
            total_connections=len(edges)
        )

        return topology

    def _process_resource_update(self, resource: Dict):
        """Process incoming resource state update"""
        client_id = resource.get('client_id', 'unknown')
        resource_kind = resource.get('kind', '').lower()
        resource_name = resource.get('metadata', {}).get('name', '')
        namespace = resource.get('metadata', {}).get('namespace', 'default')

        client_state = self.client_state[client_id]

        if not client_state.get('cluster_name'):
            client_state['cluster_name'] = resource.get('cluster_name', 'unknown')

        # Store resource in appropriate bucket
        if resource_kind == 'service':
            client_state['services'][resource_name] = resource

        elif resource_kind in ['deployment', 'statefulset', 'daemonset']:
            client_state['deployments'][resource_name] = resource

        elif resource_kind == 'pod':
            client_state['pods'][resource_name] = resource

        elif resource_kind == 'endpoints':
            # Endpoints link services to pods
            pods = []
            for subset in resource.get('subsets', []):
                for address in subset.get('addresses', []):
                    target_ref = address.get('targetRef', {})
                    if target_ref.get('kind') == 'Pod':
                        pods.append(target_ref.get('name'))

            client_state['endpoints'][resource_name] = {'pods': pods}

        elif resource_kind == 'configmap':
            client_state['configmaps'][resource_name] = resource

    def run(self):
        """Main processing loop"""
        logger.info("🚀 Topology Builder started. Consuming from 'state.k8s.resource'...")

        message_count = 0
        topology_publish_interval = 100  # Rebuild topology every 100 messages

        try:
            for message in self.consumer:
                resource = message.value

                # Update client state
                self._process_resource_update(resource)

                message_count += 1

                # Periodically rebuild and publish topology
                if message_count % topology_publish_interval == 0:
                    for client_id in list(self.client_state.keys()):
                        topology = self._build_topology_for_client(client_id)

                        if topology:
                            kafka_key = f"{client_id}::topology"

                            self.producer.send(
                                'state.k8s.topology',
                                key=kafka_key,
                                value=topology.to_dict()
                            )

                            logger.info(f"📊 Published topology for {client_id}: "
                                        f"{topology.total_services} services, {topology.total_connections} connections")

        except KeyboardInterrupt:
            logger.info("Shutting down Topology Builder...")

        finally:
            self.consumer.close()
            self.producer.close()
            logger.info(f"Final stats - Processed: {message_count} resources")


if __name__ == "__main__":
    import os

    kafka_brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
    builder = TopologyBuilder(kafka_brokers)
    builder.run()
