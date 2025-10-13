# Quick Start - 5 Minutes

Install KG RCA Agent in your Kubernetes cluster in 5 minutes.

## Step 1: Get Server Details

Contact your KG RCA Server administrator for:

- Kafka server address (e.g., `98.90.147.12:9092`)
- Your unique client ID

## Step 2: Create Configuration

```bash
cat > values.yaml <<EOF
client:
  id: "my-cluster"
  kafka:
    bootstrapServers: "98.90.147.12:9092"
EOF
```

Replace:

- `my-cluster` with your cluster name (e.g., `prod-us-west`)
- `98.90.147.12:9092` with your server's Kafka endpoint

## Step 3: Install

```bash
helm install kg-rca-agent ./helm-chart/kg-rca-agent \
  --values values.yaml \
  --namespace observability \
  --create-namespace
```

## Step 4: Verify

```bash
kubectl get pods -n observability
```

You should see 3 pods running:

- `kg-rca-agent-vector-xxxxx`
- `kg-rca-agent-event-exporter-xxxxx`
- `kg-rca-agent-state-watcher-xxxxx`

## Step 5: Check Server

Ask your administrator to verify data is arriving, or if you have access:

```bash
# On server
docker exec kg-neo4j cypher-shell -u neo4j -p <password> \
  "MATCH (n:Pod) RETURN n.name LIMIT 10"
```

## Done! 🎉

Your cluster is now streaming data to the KG RCA Server for real-time root cause analysis.

## Next Steps

- View your cluster's topology in Neo4j Browser
- Query for root causes using the KG API
- Set up alerts in Grafana

## Troubleshooting

**Pods not starting?**

```bash
kubectl describe pod -n observability <pod-name>
kubectl logs -n observability <pod-name>
```

**No data on server?**
Check network connectivity:

```bash
kubectl exec -n observability -it <vector-pod> -- nc -zv 98.90.147.12 9092
```

**Need help?** Email support@lumniverse.com
