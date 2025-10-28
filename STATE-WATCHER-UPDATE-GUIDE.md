# State-Watcher Multi-Tenant Update Guide

## Summary

The state-watcher needs to be updated to include `client_id` in all Kafka messages it produces. This guide outlines the changes needed.

## Current Status

✅ **Completed:**
- Added `ClientID` field to `ResourceRecord` struct
- Added `ClientID` field to `EdgeRecord` struct
- Added `CLIENT_ID` environment variable reading in `main()`

⏳ **Remaining Work:**
- Update all function signatures to pass `clientID` parameter
- Update all record creation to include `ClientID` field

## Changes Required

### 1. Function Signature Updates

Update these function signatures to include `clientID string` parameter:

```go
// In state-watcher/main.go

func runWatchers(ctx context.Context, cluster, clientID string, client *kubernetes.Clientset, producer sarama.AsyncProducer, topicRes, topicTopo string)

func pushPod(cluster, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, pod *corev1.Pod)

func deletePod(cluster, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, pod *corev1.Pod)

func pushService(cluster, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicRes, topicTopo string, svc *corev1.Service)

func deleteService(clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, svc *corev1.Service)

func pushDeployment(cluster, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, d *appsv1.Deployment)

func pushReplicaSet(cluster, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, rs *appsv1.ReplicaSet)

func pushDaemonSet(cluster, clientID string, p sarama.AsyncProducer, topicRes string, ds *appsv1.DaemonSet)

func pushJob(cluster, clientID string, p sarama.AsyncProducer, topicRes, topicTopo string, j *batchv1.Job)

func pushCronJob(cluster, clientID string, p sarama.AsyncProducer, topicRes string, cj *batchv1.CronJob)

func pushNode(cluster, clientID string, p sarama.AsyncProducer, topicRes string, n *corev1.Node)

func reconcileServiceEdges(cluster, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicTopo string, svc *corev1.Service)

func reconcilePodServiceMembership(cluster, clientID string, client *kubernetes.Clientset, p sarama.AsyncProducer, topicTopo string, pod *corev1.Pod)
```

### 2. Record Creation Updates

Update all `ResourceRecord` and `EdgeRecord` creation to include `ClientID`:

#### Example: pushPod function

**Before:**
```go
rec := ResourceRecord{
    Op:        "UPSERT",
    At:        time.Now().UTC(),
    Cluster:   cluster,
    Kind:      "Pod",
    // ...
}
```

**After:**
```go
rec := ResourceRecord{
    Op:        "UPSERT",
    At:        time.Now().UTC(),
    ClientID:  clientID,  // ADD THIS LINE
    Cluster:   cluster,
    Kind:      "Pod",
    // ...
}
```

Apply this pattern to:
- `pushPod` (line ~413)
- `deletePod` (updates needed for edge records)
- `pushService` (line ~501)
- `pushDeployment` (line ~536)
- `pushReplicaSet` (line ~557)
- `pushDaemonSet` (line ~586)
- `pushJob` (line ~612)
- `pushCronJob` (line ~648)
- `pushNode` (line ~672)

#### Example: Edge Record Updates

**Before:**
```go
e := EdgeRecord{
    Op: "UPSERT", At: rec.At, Cluster: cluster,
    ID:   edgeID("pod", pod.Namespace, pod.Name, "node", "", pod.Spec.NodeName),
    From: idFor("pod", pod.Namespace, pod.Name),
    To: idFor("node", "", pod.Spec.NodeName),
    Type: "RUNS_ON",
}
```

**After:**
```go
e := EdgeRecord{
    Op: "UPSERT", At: rec.At,
    ClientID: clientID,  // ADD THIS LINE
    Cluster: cluster,
    ID:   edgeID("pod", pod.Namespace, pod.Name, "node", "", pod.Spec.NodeName),
    From: idFor("pod", pod.Namespace, pod.Name),
    To: idFor("node", "", pod.Spec.NodeName),
    Type: "RUNS_ON",
}
```

### 3. Main Function Update

**Current:**
```go
OnStartedLeading: func(ctx context.Context) {
    go runPromTargetSync(ctx, cluster, promURL, producer, topicProm, promTick)
    runWatchers(ctx, cluster, client, producer, topicRes, topicTopo)
},
```

**Update to:**
```go
OnStartedLeading: func(ctx context.Context) {
    go runPromTargetSync(ctx, cluster, promURL, producer, topicProm, promTick)
    runWatchers(ctx, cluster, tenantClientID, client, producer, topicRes, topicTopo)
},
```

### 4. PromTarget Records

Also update `PromTargetRecord` struct and `runPromTargetSync` function:

```go
type PromTargetRecord struct {
    Op         string            `json:"op"`
    At         time.Time         `json:"at"`
    ClientID   string            `json:"client_id,omitempty"` // ADD THIS
    Cluster    string            `json:"cluster"`
    // ...
}

func runPromTargetSync(ctx context.Context, cluster, clientID string, promURL string, p sarama.AsyncProducer, topic string, interval time.Duration) {
    // ...
    rec := PromTargetRecord{
        Op: "UPSERT", At: now,
        ClientID: clientID,  // ADD THIS
        Cluster: cluster,
        // ...
    }
    // ...
}
```

## Alternative: Simpler Approach

If you want to avoid updating all function signatures, you can use a package-level variable:

```go
// At package level
var globalClientID string

func main() {
    // ...
    globalClientID = getenv("CLIENT_ID", "")
    // ...
}

// Then in each function:
rec := ResourceRecord{
    Op:        "UPSERT",
    At:        time.Now().UTC(),
    ClientID:  globalClientID,  // Use package variable
    Cluster:   cluster,
    // ...
}
```

This is simpler but less explicit. Choose based on your preference.

## Testing

After making changes:

1. **Build and deploy:**
```bash
cd state-watcher
go build -o state-watcher .
```

2. **Test with CLIENT_ID:**
```bash
export CLIENT_ID=test-client
export CLUSTER_NAME=test-cluster
export KAFKA_BOOTSTRAP=localhost:9092
./state-watcher
```

3. **Verify messages have client_id:**
```bash
docker exec kg-kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic state.k8s.resource \
  --max-messages 5 \
  | jq '.client_id'
```

Expected output:
```json
"test-client"
"test-client"
"test-client"
```

## Impact

- **Breaking Change:** No - `client_id` is optional (`omitempty` tag)
- **Backward Compatible:** Yes - existing deployments work without CLIENT_ID
- **Performance:** Negligible - single string field per message
- **Storage:** ~10-20 bytes per message

## Deployment Strategy

1. **Phase 1:** Deploy updated graph-builder (already done ✅)
2. **Phase 2:** Deploy updated state-watcher with CLIENT_ID support
3. **Phase 3:** Configure CLIENT_ID in each cluster's state-watcher deployment
4. **Phase 4:** Deploy client-specific graph-builders using multi-client compose

## Configuration Example

### Kubernetes Deployment

```yaml
# state-watcher deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: state-watcher
spec:
  template:
    spec:
      containers:
      - name: state-watcher
        image: your-registry/state-watcher:latest
        env:
        - name: CLIENT_ID
          value: "prod-us-east-1"  # Unique per cluster
        - name: CLUSTER_NAME
          value: "prod-us-east-1"
        - name: KAFKA_BOOTSTRAP
          value: "your-kafka:9092"
```

### Docker Compose

```yaml
# In your docker-compose.yml
state-watcher:
  image: state-watcher:latest
  environment:
    CLIENT_ID: ${CLIENT_ID:-}
    CLUSTER_NAME: ${CLUSTER_NAME:-minikube}
    KAFKA_BOOTSTRAP: kafka:9092
```

## Summary

This update enables state-watcher to tag all K8s resource and topology messages with a `client_id`, allowing the graph-builder to create isolated knowledge graphs per client in a multi-tenant deployment.

**Estimated Effort:** 2-3 hours
**Priority:** High (required for multi-tenant support)
**Risk:** Low (backward compatible)
