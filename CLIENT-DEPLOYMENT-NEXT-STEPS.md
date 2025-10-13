# KG RCA Client - Deployment Next Steps

## ✅ What's Complete

### Client Package (v1.0.2)
- ✅ Helm chart created in `client-light/`
- ✅ Complete documentation (README, QUICK-START, installation guide)
- ✅ Example configuration files
- ✅ Test scripts for validation
- ✅ Committed to git
- ✅ Tagged as v1.0.2
- ✅ Released on GitHub: https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.2

### Server Infrastructure
- ✅ Mini-server running on EC2 (98.90.147.12)
- ✅ All services healthy (Kafka, Neo4j, Graph-builder, KG API, etc.)
- ✅ Neo4j credentials configured
- ✅ KG API bug fixed (OPTIONAL MATCH)
- ✅ Port 9092 accessible for client connections

## 🎯 Next Steps: Deploy Client to Test

### Option 1: Quick Test on Minikube (Recommended First)

```bash
# 1. Start Minikube
minikube start --cpus=4 --memory=8192

# 2. Download client package
cd /tmp
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# 3. Create test values
cat > test-values.yaml <<EOF
client:
  id: "test-minikube"
  kafka:
    bootstrapServers: "98.90.147.12:9092"

vector:
  enabled: true
eventExporter:
  enabled: true
stateWatcher:
  enabled: true
prometheusAgent:
  enabled: false
EOF

# 4. Install
helm install kg-rca-agent ./helm-chart \
  --values test-values.yaml \
  --namespace observability \
  --create-namespace

# 5. Watch pods start
kubectl get pods -n observability -w
```

### Option 2: Deploy to Real Kubernetes Cluster

```bash
# 1. Clone repo
git clone https://github.com/anuragvishwa/kgroot-latest.git
cd kgroot-latest/client-light

# 2. Configure for your cluster
cat > prod-values.yaml <<EOF
client:
  id: "prod-cluster-001"  # Unique name for your cluster
  kafka:
    bootstrapServers: "98.90.147.12:9092"

# Optional: Limit to specific namespaces
monitoredNamespaces: ["production", "staging"]
EOF

# 3. Install
helm install kg-rca-agent ./helm-chart \
  --values prod-values.yaml \
  --namespace observability \
  --create-namespace

# 4. Verify
kubectl get pods -n observability
kubectl logs -n observability -l app=vector --tail=50
```

## 📊 Verification Steps

### 1. Check Client Pods
```bash
kubectl get pods -n observability

# Expected:
# kg-rca-agent-vector-xxxxx          1/1  Running
# kg-rca-agent-event-exporter-xxx    1/1  Running
# kg-rca-agent-state-watcher-xxx     1/1  Running
```

### 2. Verify Data Flow to Server

SSH to mini-server and check:

```bash
ssh mini-server

# Check Kafka topics have data
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic events.normalized \
  --max-messages 5

# Check Neo4j has your cluster's pods
docker exec kg-neo4j cypher-shell -u neo4j -p Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA \
  "MATCH (n:Pod) RETURN n.name, n.namespace, n.uid LIMIT 20"

# Check KG API stats
curl -s http://localhost:8080/api/v1/graph/stats | python3 -m json.tool
```

### 3. View in Neo4j Browser

1. Open tunnel: `ssh -L 7474:localhost:7474 -L 7687:localhost:7687 mini-server`
2. Browser: http://localhost:7474
3. Login: neo4j / Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA
4. Query: `MATCH (n) RETURN n LIMIT 100`

You should see:
- Pod nodes from your cluster
- Episodic event nodes
- Relationships between them

## 🔧 Troubleshooting

### Pods Not Starting
```bash
kubectl describe pod -n observability <pod-name>
kubectl logs -n observability <pod-name>
```

### No Data on Server
```bash
# Test connectivity from client pod
kubectl exec -n observability -it \
  $(kubectl get pod -n observability -l app=vector -o name | head -1) \
  -- sh -c "nc -zv 98.90.147.12 9092"

# Check if firewall is blocking
# Make sure AWS Security Group allows port 9092 from your cluster's IPs
```

### Wrong Neo4j Password Error
The password is: `Kg9mN8pQ2vR5wX7jL4hF6sT3bD1nY0zA`

## 🔒 After Testing: Add SSL

Once basic connectivity works, set up SSL for production:

1. Configure domain: kafka.lumniverse.com → 98.90.147.12
2. Run SSL setup script on server
3. Update client values to use port 9093 with SSL
4. Test secure connection

See `mini-server-prod/scripts/setup-ssl.sh`

## 📈 What to Expect

After successful deployment, you'll see:

**In Neo4j:**
- Pod, Deployment, Service nodes from your cluster
- Event nodes (crashes, failures, etc.)
- Relationships (Pod → Deployment, Event → Pod)

**In KG API:**
- Resource count increasing
- Event count increasing
- Topology edges forming

**Capabilities:**
- Root cause analysis for incidents
- Resource dependency mapping
- Event correlation across time
- Automated incident detection

## 🎉 Success Criteria

- ✅ All 3 client pods running
- ✅ No errors in pod logs
- ✅ Network connectivity confirmed
- ✅ Events in Kafka topics
- ✅ Nodes visible in Neo4j
- ✅ KG API showing your cluster's data

## 📚 Resources

- Client README: `client-light/README.md`
- Quick Start: `client-light/QUICK-START.md`
- Test Guide: `client-light/INSTALL-TEST-GUIDE.md`
- GitHub Release: https://github.com/anuragvishwa/kgroot-latest/releases/tag/v1.0.2

## Need Help?

- Check logs: `kubectl logs -n observability <pod-name>`
- Verify server health: `ssh mini-server "cd kgroot-latest/mini-server-prod && ./scripts/test-services.sh"`
- Contact: support@lumniverse.com
