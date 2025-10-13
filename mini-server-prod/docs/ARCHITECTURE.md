# KG RCA Architecture

## System Overview

The KG RCA (Knowledge Graph Root Cause Analysis) platform is a distributed system that collects observability data from Kubernetes clusters, processes it through multiple stages, and builds a knowledge graph for intelligent incident analysis and root cause determination.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Client Clusters (K8s)                           │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐           │
│  │ Event Exporter │  │  Log Exporter  │  │ Prom Exporter  │           │
│  └────────┬───────┘  └────────┬───────┘  └────────┬───────┘           │
└───────────┼──────────────────┼──────────────────┼─────────────────────┘
            │                   │                   │
            │ SSL (9093)        │ SSL (9093)        │ SSL (9093)
            └───────────────────┴───────────────────┘
                                 │
┌────────────────────────────────┼─────────────────────────────────────────┐
│                    KG RCA Mini Server (Ubuntu)                          │
│                                 │                                         │
│                         ┌───────▼────────┐                               │
│                         │     Kafka      │                               │
│                         │  (Message Bus) │                               │
│                         └───┬────┬───┬───┘                               │
│                             │    │   │                                   │
│          ┌──────────────────┘    │   └──────────────────┐               │
│          │                       │                       │               │
│    ┌─────▼──────┐         ┌─────▼──────┐        ┌──────▼──────┐        │
│    │  Alerts    │         │   Graph    │        │   KG API    │        │
│    │  Enricher  │         │  Builder   │        │ (REST API)  │        │
│    └─────┬──────┘         └─────┬──────┘        └──────┬──────┘        │
│          │                      │                       │               │
│          │            ┌─────────▼─────────┐            │               │
│          │            │      Neo4j        │◄───────────┘               │
│          │            │  (Knowledge Graph)│                             │
│          │            └───────────────────┘                             │
│          │                                                               │
│          └──────────────────────┐                                       │
│                                  │                                       │
│                     ┌────────────▼──────────┐                           │
│                     │    Kafka (enriched)   │                           │
│                     └────────────┬──────────┘                           │
│                                  │                                       │
│                                  └────────────────┐                      │
│                                                   │                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────▼────┐                │
│  │  Prometheus  │  │   Grafana    │  │   Kafka UI    │                │
│  │  (Metrics)   │  │ (Dashboards) │  │  (Management) │                │
│  └──────────────┘  └──────────────┘  └───────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Data Ingestion Layer

#### Event Exporter (Client-side)
- **Purpose**: Collects Kubernetes events from API server
- **Location**: Runs in each monitored cluster
- **Output**: Sends events to `raw.k8s.events` topic
- **Format**: JSON with metadata (namespace, resource type, etc.)

#### Log Exporter (Client-side)
- **Purpose**: Collects container logs
- **Location**: Runs as DaemonSet in each cluster
- **Output**: Sends logs to `raw.k8s.logs` topic
- **Format**: JSON with pod metadata and log lines

#### Prometheus Exporter (Client-side)
- **Purpose**: Forwards Prometheus alerts
- **Location**: Configured in Prometheus AlertManager
- **Output**: Sends alerts to `raw.prom.alerts` topic
- **Format**: Prometheus alert JSON format

### 2. Message Broker

#### Apache Kafka
- **Purpose**: Distributed message queue for all data streams
- **Image**: `wurstmeister/kafka:latest`
- **Ports**:
  - `9092`: Internal (Docker network) - PLAINTEXT
  - `9093`: External (clients) - SSL
- **Topics**:
  - `raw.k8s.events`: Raw Kubernetes events
  - `raw.k8s.logs`: Raw container logs
  - `raw.prom.alerts`: Raw Prometheus alerts
  - `events.normalized`: Normalized events
  - `logs.normalized`: Normalized logs
  - `alerts.enriched`: Enriched alerts with context
  - `state.k8s.resource`: Resource state snapshots
  - `state.k8s.topology`: Topology state snapshots
  - `dlq.*`: Dead letter queues
- **Configuration**:
  - Compression: gzip
  - Replication: 1 (single broker)
  - Partitions: 3-6 (topic-dependent)
  - Retention: 3-30 days (topic-dependent)

#### Zookeeper
- **Purpose**: Kafka coordination service
- **Image**: `wurstmeister/zookeeper:latest`
- **Port**: `2181`

### 3. Processing Layer

#### Alerts Enricher
- **Purpose**: Enriches raw events with Kubernetes state information
- **Language**: Go/Python
- **Input Topics**:
  - `events.normalized`: Incoming events
  - `state.k8s.resource`: Resource state
  - `state.k8s.topology`: Topology state
- **Output Topic**: `alerts.enriched`
- **Processing**:
  1. Reads normalized events
  2. Looks up current resource state
  3. Looks up topology relationships
  4. Enriches event with context
  5. Publishes to enriched topic

**Enrichment Example:**
```json
// Input (normalized)
{
  "severity": "ERROR",
  "message": "Pod crashed",
  "resource_name": "my-app-xyz"
}

// Output (enriched)
{
  "severity": "ERROR",
  "message": "Pod crashed",
  "resource": {
    "name": "my-app-xyz",
    "type": "Pod",
    "namespace": "production",
    "labels": {"app": "my-app"},
    "node": "worker-node-1"
  },
  "topology": {
    "deployment": "my-app",
    "service": "my-app-svc",
    "depends_on": ["database-svc", "cache-svc"]
  }
}
```

#### Graph Builder
- **Purpose**: Builds and maintains the knowledge graph in Neo4j
- **Language**: Go
- **Input Topics**:
  - `logs.normalized`
  - `events.normalized`
  - `alerts.enriched`
- **Output**: Neo4j graph database
- **Ports**:
  - `9090`: Prometheus metrics endpoint
  - `/healthz`: Health check endpoint
- **Processing Flow**:
  1. Consumes events from Kafka
  2. Extracts entities (pods, nodes, services, etc.)
  3. Identifies relationships
  4. Creates/updates graph nodes and edges
  5. Detects patterns and anomalies
  6. Triggers incident clustering
  7. Exposes metrics

**Graph Schema:**
```
(Resource)-[:BELONGS_TO]->(Namespace)
(Pod)-[:RUNS_ON]->(Node)
(Pod)-[:PART_OF]->(Deployment)
(Service)-[:ROUTES_TO]->(Pod)
(Event)-[:AFFECTS]->(Resource)
(Incident)-[:CAUSED_BY]->(Event)
(Incident)-[:RELATED_TO]->(Resource)
```

**Features:**
- **Severity Escalation**: Tracks recurring errors and escalates severity
- **Incident Clustering**: Groups related events into incidents
- **Anomaly Detection**: Identifies unusual patterns
- **Temporal Analysis**: Analyzes time-based relationships

### 4. Storage Layer

#### Neo4j
- **Purpose**: Graph database for knowledge graph
- **Image**: `neo4j:5.20`
- **Ports**:
  - `7474`: HTTP (Browser UI)
  - `7687`: Bolt protocol (native)
- **Plugins**: APOC (Advanced Procedures and Functions)
- **Memory Configuration** (default):
  - Heap: 2GB initial, 4GB max
  - Page cache: 2GB
  - Transaction memory: 2GB max
- **Indexes**:
  - Resource ID
  - Event timestamp
  - Incident ID
  - Namespace
- **Data Model**:
  - **Nodes**: Resource, Pod, Node, Service, Deployment, Event, Incident, Alert
  - **Relationships**: BELONGS_TO, RUNS_ON, PART_OF, ROUTES_TO, AFFECTS, CAUSED_BY, RELATED_TO

### 5. API Layer

#### KG API
- **Purpose**: REST API for querying the knowledge graph
- **Language**: Go/Python
- **Port**: `8080`
- **Endpoints**:
  - `GET /healthz`: Health check
  - `GET /api/v1/graph/stats`: Graph statistics
  - `POST /api/v1/rca/{incident_id}`: Root cause analysis
  - `GET /api/v1/incidents`: List incidents
  - `GET /api/v1/resources/{id}`: Resource details
  - `GET /api/v1/topology`: Topology query
- **Authentication**: API key (Bearer token)
- **Security**: CORS enabled, rate limiting

**RCA Query Example:**
```bash
curl -X POST http://localhost:8080/api/v1/rca/incident-123 \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json"

# Response:
{
  "incident_id": "incident-123",
  "root_causes": [
    {
      "resource": "database-pod-xyz",
      "event": "OOMKilled",
      "confidence": 0.95,
      "path": [
        "app-pod -> database-svc -> database-pod"
      ]
    }
  ],
  "related_incidents": [...],
  "timeline": [...]
}
```

### 6. Monitoring Layer

#### Prometheus
- **Purpose**: Metrics collection and alerting
- **Image**: `prom/prometheus:latest`
- **Port**: `9091` (mapped from 9090)
- **Scrape Targets**:
  - Graph Builder: `graph-builder:9090/metrics`
  - Neo4j: `neo4j:2004/metrics`
  - KG API: `kg-api:8080/metrics`
- **Metrics Collected**:
  - Kafka consumer lag
  - Events processed/sec
  - Graph operations/sec
  - API latency
  - Neo4j query time
  - Memory/CPU usage
- **Retention**: 30 days

#### Grafana
- **Purpose**: Visualization and dashboards
- **Image**: `grafana/grafana:latest`
- **Port**: `3000`
- **Data Sources**:
  - Prometheus (metrics)
  - Neo4j (graph data)
- **Pre-configured Dashboards**:
  - System Overview
  - Kafka Throughput
  - Graph Builder Performance
  - Neo4j Metrics
  - API Performance
  - Incident Analytics

#### Kafka UI
- **Purpose**: Kafka management and monitoring
- **Image**: `provectuslabs/kafka-ui:latest`
- **Port**: `7777`
- **Features**:
  - Topic management
  - Message browsing
  - Consumer group monitoring
  - Broker metrics
  - Configuration management

## Data Flow

### 1. Event Ingestion Flow

```
Client Cluster → Event Exporter → Kafka (raw.k8s.events)
                                        ↓
                                   Normalizer
                                        ↓
                              Kafka (events.normalized)
                                        ↓
                                 Alerts Enricher
                                        ↓
                              Kafka (alerts.enriched)
                                        ↓
                                  Graph Builder
                                        ↓
                                      Neo4j
```

### 2. RCA Query Flow

```
Client Application → KG API → Neo4j (Cypher query)
                                  ↓
                        Graph traversal algorithm
                                  ↓
                           Analyze relationships
                                  ↓
                          Identify root causes
                                  ↓
                     ← Return RCA results ←
```

### 3. Monitoring Flow

```
Services → Prometheus metrics endpoint → Prometheus
                                              ↓
                                         Grafana
                                              ↓
                                    Visualization dashboards
```

## Scalability Considerations

### Current Setup (Single Server)
- **Capacity**:
  - 100-500 events/sec
  - 10-50 monitored clusters
  - 100K-1M graph nodes
- **Bottlenecks**:
  - Single Kafka broker
  - Neo4j single instance
  - No redundancy

### Scaling Options

#### Horizontal Scaling
1. **Kafka Cluster**: Add more brokers (3+ recommended)
   - Increase replication factor to 3
   - Distribute partitions
2. **Multiple Graph Builders**: Scale processing
3. **Neo4j Cluster** (Enterprise): Causal clustering
4. **Load Balancer**: For KG API instances

#### Vertical Scaling
1. **Increase Instance Size**: t3.large → t3.xlarge → t3.2xlarge
2. **Increase Memory**:
   - Neo4j heap: 8GB+
   - Kafka heap: 4GB+
3. **SSD Storage**: NVMe for better I/O

#### Optimization
1. **Kafka Partitions**: Increase for parallelism
2. **Batch Processing**: Tune consumer batch sizes
3. **Neo4j Indexes**: Add for frequently queried properties
4. **Connection Pooling**: For database connections
5. **Caching**: Redis for frequently accessed data

## Security Architecture

### Network Security
- **Firewall**: UFW configured to allow only necessary ports
- **SSL/TLS**: Kafka uses SSL for external connections
- **Private Network**: Services communicate via Docker network

### Authentication
- **Neo4j**: Username/password authentication
- **KG API**: API key (Bearer token)
- **Grafana**: Username/password
- **Kafka**: SSL client certificates (optional mutual TLS)

### Data Security
- **Encryption in Transit**: SSL/TLS for Kafka
- **Encryption at Rest**: Docker volume encryption (optional)
- **Secrets Management**: Environment variables (production: use secrets manager)

## Deployment Models

### Current: Single Server
- **Pros**: Simple, cost-effective, easy to manage
- **Cons**: No redundancy, limited scale, single point of failure
- **Best For**: MVP, small deployments, testing

### Alternative: Multi-Server
- **Pros**: High availability, scalable, redundant
- **Cons**: Complex, expensive, requires orchestration
- **Best For**: Production, large deployments

### Future: Kubernetes
- **Pros**: Auto-scaling, self-healing, declarative
- **Cons**: Most complex, requires K8s expertise
- **Best For**: Enterprise, multi-tenant

## Performance Characteristics

### Latency
- **Event to Graph**: < 5 seconds (p95)
- **RCA Query**: < 2 seconds (p95)
- **API Response**: < 500ms (p95)

### Throughput
- **Events**: 100-500/sec (single server)
- **Logs**: 1000-5000/sec (single server)
- **API Queries**: 100-500 req/sec

### Resource Usage (t3.large)
- **CPU**: 40-60% average
- **Memory**: 6-7GB used (of 8GB)
- **Disk I/O**: 10-50 MB/sec
- **Network**: 5-20 Mbps

## Failure Modes and Recovery

### Service Failures

| Service | Impact | Recovery Time | Data Loss |
|---------|--------|---------------|-----------|
| Kafka | No new data ingested | 1-2 min | None (persisted) |
| Zookeeper | Kafka unavailable | 1-2 min | None |
| Neo4j | No RCA, no graph updates | 2-5 min | Recent events |
| Graph Builder | Events queued | 30 sec | None (will catch up) |
| KG API | No RCA queries | 30 sec | None |
| Alerts Enricher | Events not enriched | 30 sec | None (will catch up) |

### Recovery Procedures
- **Auto-restart**: Docker `restart: unless-stopped` policy
- **Health checks**: Docker health checks trigger restarts
- **Data recovery**: Kafka retention allows replay
- **Manual intervention**: `docker compose restart <service>`

## Monitoring and Observability

### Metrics to Monitor
1. **Kafka**: Consumer lag, message rate, disk usage
2. **Neo4j**: Query time, transaction rate, memory usage
3. **Graph Builder**: Events processed, errors, latency
4. **API**: Request rate, latency, error rate
5. **System**: CPU, memory, disk, network

### Alerts to Configure
1. Consumer lag > 10,000 messages
2. Disk usage > 85%
3. Memory usage > 90%
4. Service down > 5 minutes
5. Error rate > 1%

### Logs
- **Location**: Docker logs
- **Access**: `docker compose logs -f`
- **Retention**: Managed by Docker (default: unlimited)
- **Shipping**: Configure log driver for external storage

## Further Reading
- [Troubleshooting Guide](TROUBLESHOOTING.md)
- [Monitoring Guide](MONITORING.md)
- [Security Best Practices](SECURITY.md)
- [Backup and Restore](BACKUP-RESTORE.md)
