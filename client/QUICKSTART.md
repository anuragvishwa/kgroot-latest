# KGroot Client - 5 Minute Quickstart

Get your Kubernetes cluster sending data to KGroot in 5 minutes.

## Prerequisites Checklist

- [ ] Kubernetes cluster access (`kubectl` configured)
- [ ] Helm 3 installed
- [ ] KGroot mini-server running
- [ ] Server's public IP/hostname
- [ ] Port 9092 accessible from cluster

## Step 1: Get Server Information (1 min)

```bash
# Get server public IP
ssh mini-server "curl -s http://169.254.169.254/latest/meta-data/public-ipv4"

# Save this IP, you'll need it next
# Example: 54.123.45.67
```

## Step 2: Test Connectivity (1 min)

```bash
# Replace with your server IP
SERVER_IP="54.123.45.67"

# Test from your cluster
kubectl run kafka-test --rm -it --image=busybox --restart=Never -- \
  nc -zv $SERVER_IP 9092

# You should see: "open" or "succeeded"
```

If this fails, check:
- Server security group allows port 9092
- Server firewall allows inbound on 9092
- Your cluster can reach external IPs

## Step 3: Install Client (2 min)

```bash
# Navigate to client directory
cd /path/to/kgroot_latest/client

# Install with Helm
helm install kgroot-client ./helm-chart/kg-client \
  --set global.clusterName="my-cluster" \
  --set server.kafka.brokers="$SERVER_IP:9092" \
  --create-namespace

# Wait for pods to be ready
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=kg-client \
  -n kgroot-client \
  --timeout=120s
```

## Step 4: Verify (1 min)

```bash
# Check pods are running
kubectl get pods -n kgroot-client

# Check event exporter logs
kubectl logs -n kgroot-client deployment/kg-client-event-exporter --tail 20

# Generate a test event
kubectl run test-crash --image=busybox --restart=Never -- /bin/sh -c "exit 1"

# Wait 10 seconds, then check on server
ssh mini-server "
docker exec kgroot-latest-kafka-1 \
  kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group kg-builder --describe | grep -E 'TOPIC|events|logs'
"

# Look for LAG column - should be 0 or low (messages being consumed!)

# Clean up test pod
kubectl delete pod test-crash
```

## Success! 🎉

Your cluster is now sending data to KGroot.

### What's Happening Now?

1. **Event Exporter** watches all K8s events → sends to `raw.k8s.events` topic
2. **Vector DaemonSets** collect pod logs → sends to `raw.k8s.logs` topic
3. **Server processes** data through alerts-enricher and graph-builder
4. **Neo4j stores** knowledge graph for RCA queries

### Next Steps

1. **Configure Prometheus Alerts**: See "Prometheus Integration" below
2. **Query the Graph**: See `/validation/interactive-query-test.sh`
3. **View in Neo4j**: Browse to `http://YOUR_SERVER:7474`
4. **Customize Collection**: See [README.md](README.md#configuration)

---

## Prometheus Integration (Optional)

Send alerts to KGroot:

```bash
# Get Vector webhook service URL
kubectl get svc -n kgroot-client kg-client-vector -o jsonpath='{.spec.clusterIP}'

# Add to Alertmanager config
kubectl edit configmap -n monitoring alertmanager-config
```

Add this receiver:

```yaml
receivers:
  - name: 'kgroot'
    webhook_configs:
      - url: 'http://kg-client-vector.kgroot-client.svc:9090/alerts'
        send_resolved: true

route:
  routes:
    - receiver: 'kgroot'
      continue: true
```

---

## Troubleshooting

### Pods stuck in Pending

```bash
kubectl describe pod -n kgroot-client <pod-name>

# Common fixes:
# - Check node resources: kubectl top nodes
# - Check RBAC: kubectl get clusterrolebinding | grep kg-client
```

### No data on server

```bash
# Check pod logs for Kafka errors
kubectl logs -n kgroot-client deployment/kg-client-event-exporter | grep -i error
kubectl logs -n kgroot-client ds/kg-client-vector | grep -i error

# Test Kafka from pod
kubectl run kafka-debug --rm -it --image=confluentinc/cp-kafka:7.0.0 --restart=Never -- \
  kafka-console-producer --broker-list $SERVER_IP:9092 --topic test

# Type a message, press Ctrl+C

# Check on server
ssh mini-server "
docker exec kgroot-latest-kafka-1 \
  kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic test --from-beginning --max-messages 1
"
```

### High resource usage

```bash
# Reduce log collection scope
helm upgrade kgroot-client ./helm-chart/kg-client \
  --reuse-values \
  --set vector.logCollection.levels="{ERROR,FATAL}"
```

---

## Quick Commands Reference

```bash
# Check status
kubectl get all -n kgroot-client

# View logs
kubectl logs -n kgroot-client deployment/kg-client-event-exporter -f
kubectl logs -n kgroot-client ds/kg-client-vector -f

# Restart components
kubectl rollout restart deployment -n kgroot-client kg-client-event-exporter
kubectl rollout restart daemonset -n kgroot-client kg-client-vector

# Upgrade configuration
helm upgrade kgroot-client ./helm-chart/kg-client \
  --reuse-values \
  --set KEY=VALUE

# Uninstall
helm uninstall kgroot-client -n kgroot-client
kubectl delete namespace kgroot-client
```

---

## Example: Production Setup

For production with authentication:

```bash
# Create secrets
kubectl create secret generic kafka-credentials \
  --from-literal=username=kgroot-user \
  --from-literal=password=secure-password \
  -n kgroot-client

# Install with SASL
helm install kgroot-client ./helm-chart/kg-client \
  --set global.clusterName="production" \
  --set server.kafka.brokers="kafka.prod.company.com:9092" \
  --set server.kafka.sasl.enabled=true \
  --set server.kafka.sasl.mechanism="PLAIN" \
  --set server.kafka.sasl.username="kgroot-user" \
  --set server.kafka.sasl.password="secure-password" \
  --set vector.logCollection.levels="{ERROR,FATAL,WARN}"
```

---

**Time to complete**: ~5 minutes

**Difficulty**: Beginner

**Support**: Check [README.md](README.md#troubleshooting) for detailed troubleshooting
