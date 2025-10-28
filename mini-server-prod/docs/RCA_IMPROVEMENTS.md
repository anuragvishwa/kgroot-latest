# RCA System Improvements Roadmap

## Phase 1: MVP Enhancements (No ML Required)

### 1.1 Event Graph Construction
**Goal**: Build temporal event graphs similar to KGroot's FPGs

**Implementation**:
```python
# services/event_graph_builder.py
class EventGraphBuilder:
    def __init__(self, time_window=300):  # 5 minutes
        self.time_window = time_window

    def build_online_graph(self, events):
        """
        Construct directed graph of events within time window
        Similar to Algorithm 1 in KGroot paper
        """
        graph = nx.DiGraph()
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        for i, event in enumerate(sorted_events):
            graph.add_node(event.id, **event.attributes)

            # Look back for potential causal predecessors
            for j in range(max(0, i-5), i):  # Check last 5 events
                prev_event = sorted_events[j]
                if self._are_related(prev_event, event):
                    relation_type = self._classify_relation(prev_event, event)
                    graph.add_edge(prev_event.id, event.id, type=relation_type)

        return graph

    def _are_related(self, e1, e2):
        """Check if events are causally related"""
        # Same service/pod
        if e1.service == e2.service:
            return True
        # Dependency chain
        if self._has_dependency(e1.service, e2.service):
            return True
        # Time proximity
        if abs(e2.timestamp - e1.timestamp) < 60:  # 1 min
            return True
        return False

    def _classify_relation(self, e1, e2):
        """Classify relationship type"""
        # Rule-based classification (can upgrade to ML later)
        if e1.type == 'resource_spike' and e2.type == 'pod_restart':
            return 'CAUSES'
        if e1.service == e2.service:
            return 'SEQUENTIAL'
        if self._has_dependency(e1.service, e2.service):
            return 'PROPAGATES_TO'
        return 'CORRELATES_WITH'
```

### 1.2 Pattern Database in Neo4j
**Goal**: Store and match failure patterns

```cypher
// Neo4j Schema Extensions

// Failure Pattern node
CREATE CONSTRAINT failure_pattern_id IF NOT EXISTS
FOR (fp:FailurePattern) REQUIRE fp.pattern_id IS UNIQUE;

// Store pattern
CREATE (fp:FailurePattern {
  pattern_id: 'PAT_001',
  name: 'CPU Exhaustion Cascade',
  root_cause_type: 'resource_limit_exceeded',
  event_sequence: ['cpu_80_percent', 'memory_pressure', 'oom_kill', 'pod_restart'],
  affected_services: ['api-gateway', 'auth-service'],
  frequency: 12,
  avg_resolution_time: 180,  // seconds
  resolution_steps: ['Scale up replicas', 'Increase resource limits'],
  created_at: datetime(),
  last_matched: datetime()
})

// Link events to patterns
CREATE (e:Event)-[:MATCHES_PATTERN]->(fp:FailurePattern)

// Pattern evolution tracking
CREATE (fp_v1:FailurePattern)-[:EVOLVED_TO]->(fp_v2:FailurePattern)
```

### 1.3 Enhanced Matching Algorithm
```python
# services/pattern_matcher.py
class PatternMatcher:
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver

    def find_similar_patterns(self, online_graph, top_k=3):
        """
        Find top-k similar historical patterns
        Simplified version of KGroot's GCN similarity
        """
        patterns = self._fetch_all_patterns()
        similarities = []

        for pattern in patterns:
            score = self._compute_similarity(online_graph, pattern)
            similarities.append((pattern, score))

        # Return top-k matches
        return sorted(similarities, key=lambda x: x[1], reverse=True)[:top_k]

    def _compute_similarity(self, online_graph, pattern):
        """
        Multi-factor similarity scoring
        """
        # Factor 1: Event type overlap (Jaccard)
        online_events = set([n['type'] for n in online_graph.nodes(data=True)])
        pattern_events = set(pattern['event_sequence'])
        jaccard = len(online_events & pattern_events) / len(online_events | pattern_events)

        # Factor 2: Service overlap
        online_services = set([n['service'] for n in online_graph.nodes(data=True)])
        pattern_services = set(pattern['affected_services'])
        service_overlap = len(online_services & pattern_services) / len(online_services | pattern_services) if pattern_services else 0

        # Factor 3: Sequence similarity (longest common subsequence)
        online_seq = [n['type'] for n in nx.topological_sort(online_graph)]
        pattern_seq = pattern['event_sequence']
        sequence_sim = self._lcs_ratio(online_seq, pattern_seq)

        # Factor 4: Graph structure similarity (edge count ratio)
        edge_ratio = min(online_graph.number_of_edges(), len(pattern.get('edges', []))) / \
                     max(online_graph.number_of_edges(), len(pattern.get('edges', [])), 1)

        # Weighted combination
        return (0.35 * jaccard +
                0.25 * service_overlap +
                0.30 * sequence_sim +
                0.10 * edge_ratio)

    def _lcs_ratio(self, seq1, seq2):
        """Longest common subsequence ratio"""
        lcs_length = self._lcs_length(seq1, seq2)
        return 2 * lcs_length / (len(seq1) + len(seq2)) if (len(seq1) + len(seq2)) > 0 else 0
```

### 1.4 Root Cause Ranking
```python
# services/root_cause_ranker.py
class RootCauseRanker:
    def __init__(self):
        self.time_weight = 0.6
        self.distance_weight = 0.4

    def rank_candidates(self, candidates, alarm_event, service_graph):
        """
        Implement KGroot's ranking strategy (Equation 3)
        """
        scored_candidates = []

        for candidate in candidates:
            # Temporal score (Nt in paper)
            time_diff = abs(candidate.timestamp - alarm_event.timestamp)
            time_score = 1.0 / (1.0 + time_diff / 60.0)  # Normalize by minutes
            time_rank = self._rank_in_list(time_score, [c.timestamp for c in candidates])

            # Distance score (Nd in paper)
            graph_distance = self._calculate_service_distance(
                candidate.service,
                alarm_event.service,
                service_graph
            )
            distance_score = 1.0 / (1.0 + graph_distance)
            distance_rank = self._rank_in_list(distance_score, [c.service for c in candidates])

            # Combined score (Equation 3)
            final_score = (self.time_weight * time_rank +
                          self.distance_weight * distance_rank)

            scored_candidates.append({
                'event': candidate,
                'score': final_score,
                'time_score': time_score,
                'distance_score': distance_score,
                'explanation': self._generate_explanation(candidate, alarm_event)
            })

        return sorted(scored_candidates, key=lambda x: x['score'], reverse=True)

    def _calculate_service_distance(self, service1, service2, service_graph):
        """Calculate shortest path in service dependency graph"""
        try:
            return nx.shortest_path_length(service_graph, service1, service2)
        except nx.NetworkXNoPath:
            return float('inf')

    def _generate_explanation(self, candidate, alarm):
        """Generate human-readable explanation"""
        return {
            'root_cause': candidate.type,
            'affected_service': candidate.service,
            'propagation_path': self._trace_propagation_path(candidate, alarm),
            'recommendation': self._get_resolution_steps(candidate.type)
        }
```

## Phase 2: AI Agent Integration

### 2.1 GraphRAG for Enhanced Context
```python
# services/graph_rag.py
class GraphRAGAnalyzer:
    """
    Use GraphRAG to enhance RCA with contextual understanding
    """
    def __init__(self, neo4j_driver, llm_client):
        self.driver = neo4j_driver
        self.llm = llm_client

    async def analyze_failure(self, online_graph, matched_patterns):
        """
        Enhance pattern matching with LLM reasoning
        """
        # 1. Extract relevant subgraph from Neo4j
        context_graph = self._extract_context_graph(online_graph)

        # 2. Build prompt with graph context
        prompt = self._build_analysis_prompt(
            online_graph=online_graph,
            matched_patterns=matched_patterns,
            context_graph=context_graph
        )

        # 3. Get LLM analysis
        analysis = await self.llm.analyze(prompt)

        # 4. Store insights back to graph
        self._store_analysis(analysis)

        return analysis

    def _build_analysis_prompt(self, online_graph, matched_patterns, context_graph):
        return f"""
        # Root Cause Analysis Task

        ## Current Failure Events:
        {self._format_events(online_graph)}

        ## Historical Similar Patterns:
        {self._format_patterns(matched_patterns)}

        ## System Context:
        - Service Dependencies: {self._format_dependencies(context_graph)}
        - Recent Changes: {self._get_recent_changes()}
        - Resource Utilization: {self._get_resource_metrics()}

        ## Analysis Required:
        1. Identify the most likely root cause
        2. Explain the failure propagation path
        3. Assess confidence level (high/medium/low)
        4. Suggest immediate mitigation steps
        5. Recommend preventive measures

        Provide analysis in structured JSON format.
        """
```

### 2.2 Multi-Agent RCA System
```python
# services/multi_agent_rca.py
class MultiAgentRCA:
    """
    Coordinate multiple AI agents for comprehensive RCA
    """
    def __init__(self):
        self.pattern_agent = PatternMatchingAgent()
        self.causal_agent = CausalInferenceAgent()
        self.context_agent = ContextualAnalysisAgent()
        self.recommendation_agent = RecommendationAgent()

    async def perform_rca(self, failure_event):
        # Agent 1: Find similar patterns
        patterns = await self.pattern_agent.find_patterns(failure_event)

        # Agent 2: Infer causal relationships
        causal_graph = await self.causal_agent.build_causal_graph(
            failure_event,
            patterns
        )

        # Agent 3: Add business/operational context
        enriched_analysis = await self.context_agent.enrich(
            causal_graph,
            include_recent_deployments=True,
            include_config_changes=True,
            include_external_factors=True
        )

        # Agent 4: Generate actionable recommendations
        recommendations = await self.recommendation_agent.generate(
            enriched_analysis
        )

        return {
            'root_cause': enriched_analysis['root_cause'],
            'confidence': enriched_analysis['confidence'],
            'propagation_path': causal_graph,
            'recommendations': recommendations,
            'similar_incidents': patterns
        }
```

## Phase 3: Client K8s Integration

### 3.1 Read-Only K8s Access Setup
```yaml
# k8s-readonly-access.yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kgroot-readonly
  namespace: monitoring

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kgroot-readonly-role
rules:
  # Read pods
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/status"]
    verbs: ["get", "list", "watch"]

  # Read deployments
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]

  # Read services
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]

  # Read events
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]

  # Read metrics
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list"]

  # NO write permissions
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: []  # Explicitly no other verbs

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kgroot-readonly-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kgroot-readonly-role
subjects:
  - kind: ServiceAccount
    name: kgroot-readonly
    namespace: monitoring

---
# Generate token secret
apiVersion: v1
kind: Secret
metadata:
  name: kgroot-readonly-token
  namespace: monitoring
  annotations:
    kubernetes.io/service-account.name: kgroot-readonly
type: kubernetes.io/service-account-token
```

### 3.2 Client Onboarding Process
```bash
#!/bin/bash
# scripts/setup-client-access.sh

# 1. Create service account
kubectl apply -f k8s-readonly-access.yaml

# 2. Extract token
TOKEN=$(kubectl get secret kgroot-readonly-token -n monitoring -o jsonpath='{.data.token}' | base64 -d)

# 3. Get cluster info
CLUSTER_URL=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CA_CERT=$(kubectl get secret kgroot-readonly-token -n monitoring -o jsonpath='{.data.ca\.crt}')

# 4. Create kubeconfig for client
cat > client-kubeconfig.yaml <<EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ${CA_CERT}
    server: ${CLUSTER_URL}
  name: client-cluster
contexts:
- context:
    cluster: client-cluster
    user: kgroot-readonly
  name: kgroot-context
current-context: kgroot-context
users:
- name: kgroot-readonly
  user:
    token: ${TOKEN}
EOF

echo "Kubeconfig generated: client-kubeconfig.yaml"
echo "Provide this to the client securely"
```

## Expected Accuracy Improvements

### Current Baseline (Estimated):
- **Top-1 Accuracy**: ~40-50%
- **Top-3 Accuracy**: ~60-70%
- **False Positive Rate**: ~30%

### After Phase 1 (Rule-Based Improvements):
- **Top-1 Accuracy**: ~60-65%
- **Top-3 Accuracy**: ~75-80%
- **False Positive Rate**: ~20%

### After Phase 2 (AI Agent Integration):
- **Top-1 Accuracy**: ~70-75%
- **Top-3 Accuracy**: ~85-90%
- **False Positive Rate**: ~15%
- **Explanation Quality**: Significantly improved

### KGroot Paper Results (Full ML):
- **Top-3 Accuracy**: 93.5%
- **MAR**: 10.75

## Implementation Priority

1. **Immediate (Week 1-2)**:
   - Event graph construction
   - Pattern database in Neo4j
   - Basic similarity matching

2. **Short-term (Week 3-4)**:
   - Root cause ranking algorithm
   - K8s read-only access setup
   - Historical pattern learning

3. **Medium-term (Month 2)**:
   - GraphRAG integration
   - Multi-agent system
   - Client onboarding automation

4. **Long-term (Month 3+)**:
   - ML-based causal inference (if needed)
   - Automated resolution suggestions
   - Continuous learning from feedback