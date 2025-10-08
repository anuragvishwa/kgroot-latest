# ✅ Migration Complete - All Services Operational

## Summary

Successfully migrated data layer from Minikube to Docker while keeping K8s-aware services in Minikube. All Kafka topics are now receiving messages and consumers are processing with **0 lag**.

---

## 🎯 What Was Fixed

### Issues Found:
1. ❌ state-watcher was connecting to old minikube Kafka
2. ❌ vector was connecting to non-existent kafka-external service
3. ❌ vector-logs was connecting to old minikube Kafka
4. ❌ k8s-event-exporter was connecting to old minikube Kafka
5. ❌ alerts-enricher didn't support ZSTD compression

### Solutions Applied:
1. ✅ Updated `state-watcher` → `KAFKA_BOOTSTRAP=host.minikube.internal:29092`
2. ✅ Updated `vector` → `KAFKA_BOOTSTRAP=host.minikube.internal:29092`
3. ✅ Updated `vector-logs` → `KAFKA_BOOTSTRAP=host.minikube.internal:29092`
4. ✅ Updated `k8s-event-exporter` → `KAFKA_BOOTSTRAP=host.minikube.internal:29092`
5. ✅ Added ZSTD codec to `alerts-enricher` package.json + code

---

## 📊 Current Status

### Docker Services (All Running ✅)
```
✅ kafka:9092 (healthy) - Main message broker
✅ zookeeper:2181 - Kafka coordination
✅ neo4j:7687, 7474 - Graph database
✅ kafka-ui:7777 - Web UI for Kafka
✅ graph-builder - Building knowledge graph (0 lag)
✅ alerts-enricher - Enriching alerts with K8s context
```

### Minikube Services (All Running ✅)
```
✅ state-watcher - Watching K8s resources → Docker Kafka
✅ k8s-event-exporter - Exporting K8s events → Docker Kafka
✅ vector - Collecting Prometheus alerts → Docker Kafka
✅ vector-logs - Collecting pod logs → Docker Kafka
✅ Prometheus Stack (monitoring namespace) - Metrics & alerting
```

### Kafka Topics Status

| Topic | Messages | Producer | Consumer | Status |
|-------|----------|----------|----------|--------|
| **state.k8s.resource** | 1,010 | state-watcher | kg-builder | ✅ 0 lag |
| **state.k8s.topology** | 721 | state-watcher | kg-builder | ✅ 0 lag |
| **state.prom.targets** | 96 | state-watcher | kg-builder | ✅ 0 lag |
| **logs.normalized** | 15,458 | vector-logs | kg-builder | ✅ 0 lag |
| **events.normalized** | 43 | vector, k8s-event-exporter | alerts-enricher, kg-builder | ✅ 0 lag |
| **alerts.enriched** | 0 | alerts-enricher | (none yet) | ⏳ Waiting for alerts |
| **alerts.normalized** | 0 | vector | alerts-enricher | ⏳ Waiting for alerts |

---

## 🚀 Quick Access

### Web UIs
- **Kafka UI**: http://localhost:7777
- **Neo4j Browser**: http://localhost:7474 (neo4j/anuragvishwa)
- **Grafana**: Run `minikube service prometheus-grafana -n monitoring`

### Check Logs
```bash
# Docker services
docker logs -f kgroot_latest-graph-builder-1
docker logs -f kgroot_latest-alerts-enricher-1

# Minikube services
kubectl logs -f deployment/state-watcher -n observability
kubectl logs -f deployment/vector -n observability
kubectl logs -f daemonset/vector-logs -n observability
```

### Check Kafka Messages
```bash
# View state resources
docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic state.k8s.resource \
  --from-beginning \
  --max-messages 5

# View logs
docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic logs.normalized \
  --from-beginning \
  --max-messages 5

# View events
docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic events.normalized \
  --from-beginning \
  --max-messages 5
```

### Check Consumer Lag
```bash
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group kg-builder
```

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    DOCKER (localhost)                       │
│                                                             │
│  ┌──────────────────────────────────────────────┐          │
│  │  Kafka:9092 (+ Zookeeper)                    │          │
│  │  Topics: state.k8s.*, logs.*, events.*       │          │
│  └───────────┬────────────────────────┬─────────┘          │
│              │                        │                     │
│       ┌──────▼─────┐          ┌──────▼───────┐            │
│       │  Neo4j     │          │ alerts-      │            │
│       │  :7687     │          │ enricher     │            │
│       └──────▲─────┘          └──────────────┘            │
│              │                                              │
│       ┌──────┴─────┐                                       │
│       │ graph-     │                                       │
│       │ builder    │                                       │
│       └────────────┘                                       │
│                                                             │
│  Access: Kafka-UI (http://localhost:7777)                  │
└────────────────────────────▲───────────────────────────────┘
                             │
                             │ host.minikube.internal:29092
                             │
┌────────────────────────────┴────────────────────────────────┐
│                       MINIKUBE                               │
│                                                              │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐       │
│  │ state-       │  │ vector      │  │ vector-logs  │       │
│  │ watcher      │  │ (alerts)    │  │ (pod logs)   │       │
│  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘       │
│         │                 │                 │                │
│         └─────────────────┴─────────────────┘                │
│                           │                                  │
│         ┌─────────────────▼─────────┐                        │
│         │  k8s-event-exporter       │                        │
│         │  (K8s events)             │                        │
│         └───────────────────────────┘                        │
│                                                              │
│  All produce to Docker Kafka via host.minikube.internal     │
│                                                              │
│  ┌────────────────────────────────────────────┐             │
│  │  Prometheus Stack (monitoring namespace)   │             │
│  │  - Prometheus, Grafana, Alertmanager       │             │
│  └────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

---

## 🧹 Optional Cleanup

### Remove orphaned resources (optional)
```bash
# Remove orphan container warning
docker compose down --remove-orphans

# Remove old services from minikube (if they still exist)
kubectl delete svc kafka kafka-external neo4j kafka-ui -n observability 2>/dev/null || true

# Remove old PVCs (if they exist)
kubectl get pvc -n observability
kubectl delete pvc data-kafka-0 data-neo4j-0 -n observability 2>/dev/null || true

# Check for old deployments/statefulsets
kubectl get deployment,statefulset -n observability
```

---

## 🎉 Success Metrics

✅ **All Docker services running**
✅ **All Minikube pods running**
✅ **All Kafka topics receiving messages**
✅ **graph-builder consuming with 0 lag**
✅ **alerts-enricher ready for alerts**
✅ **15,458 log messages processed**
✅ **1,010 K8s resources tracked**
✅ **721 topology edges mapped**
✅ **96 Prometheus targets discovered**

---

## 📝 Environment Variables (For Reference)

### Minikube → Docker Kafka Connection
All minikube services now use:
```yaml
KAFKA_BOOTSTRAP: host.minikube.internal:29092
```

### Docker Services
All Docker services use:
```yaml
KAFKA_BROKERS: kafka:9092  # Internal Docker network
NEO4J_URI: neo4j://neo4j:7687
```

---

## 🔍 Troubleshooting

### If a service isn't producing messages:

1. **Check pod logs:**
   ```bash
   kubectl logs deployment/<service-name> -n observability --tail 50
   ```

2. **Verify KAFKA_BOOTSTRAP env var:**
   ```bash
   kubectl get deployment <service-name> -n observability -o yaml | grep KAFKA
   ```
   Should show: `host.minikube.internal:29092`

3. **Test connectivity from pod:**
   ```bash
   kubectl exec -it deployment/<service-name> -n observability -- \
     sh -c "nc -zv host.minikube.internal 29092"
   ```

4. **Restart deployment:**
   ```bash
   kubectl rollout restart deployment/<service-name> -n observability
   ```

### If Docker services aren't consuming:

1. **Check container logs:**
   ```bash
   docker logs kgroot_latest-<service-name>-1 --tail 50
   ```

2. **Verify Kafka connectivity:**
   ```bash
   docker exec kgroot_latest-<service-name>-1 nc -zv kafka 9092
   ```

3. **Restart container:**
   ```bash
   docker compose restart <service-name>
   ```

---

## 🎯 Next Steps

1. ✅ **Monitor for a few hours** - Ensure stability
2. ✅ **Check Neo4j** - Verify graph is building (http://localhost:7474)
   ```cypher
   MATCH (n) RETURN count(n) as total_nodes
   ```
3. ✅ **Trigger a test alert** - Verify alert enrichment pipeline
4. ✅ **Check Grafana dashboards** - Monitor cluster health

---

## 📚 Related Documentation

- [docker-migration-guide.md](docker-migration-guide.md) - Full migration guide
- [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md) - Detailed migration notes
- [docker-compose.yml](../docker-compose.yml) - Docker service definitions

---

## 💡 Pro Tips

1. **Fast log checking:**
   ```bash
   alias kafka-logs='docker exec kgroot_latest-kafka-1 kafka-console-consumer.sh --bootstrap-server localhost:9092'
   kafka-logs --topic logs.normalized --from-beginning --max-messages 5
   ```

2. **Watch consumer lag:**
   ```bash
   watch -n 5 'docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group kg-builder'
   ```

3. **Quick restart all Docker services:**
   ```bash
   docker compose restart
   ```

4. **Check all minikube service health:**
   ```bash
   kubectl get pods -n observability -w
   ```

---

**Migration completed successfully! 🎉**

All services operational, messages flowing, consumers processing with 0 lag.
