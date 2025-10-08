#!/bin/bash
# System health check script

echo "🔍 KGRoot Health Check"
echo "====================="
echo ""

# Check Docker services
echo "📦 Docker Services:"
echo "-------------------"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep kgroot || echo "⚠️  No Docker services found"
echo ""

# Check Minikube pods
echo "☸️  Minikube Pods (observability):"
echo "-----------------------------------"
kubectl get pods -n observability -o wide 2>/dev/null || echo "⚠️  Cannot connect to minikube"
echo ""

# Check Kafka consumer lag
echo "📊 Kafka Consumer Lag:"
echo "----------------------"
docker exec kgroot_latest-kafka-1 kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group kg-builder 2>/dev/null | \
  grep -E "TOPIC|state.k8s|logs.normalized|events.normalized" || echo "⚠️  Cannot connect to Kafka"
echo ""

# Check Neo4j
echo "🗄️  Neo4j Status:"
echo "-----------------"
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC" 2>/dev/null || echo "⚠️  Cannot connect to Neo4j"
echo ""

# Check recent errors
echo "⚠️  Recent Errors (last 15 min):"
echo "--------------------------------"
docker exec kgroot_latest-neo4j-1 cypher-shell -u neo4j -p anuragvishwa \
  "MATCH (e:Episodic) WHERE e.severity IN ['ERROR', 'FATAL'] AND e.eventTime > datetime() - duration('PT15M') RETURN count(e) as errorCount" 2>/dev/null || echo "⚠️  Cannot query Neo4j"
echo ""

# Overall health
echo "✅ Health Check Complete"
echo ""
echo "Quick Actions:"
echo "  - View Kafka UI: http://localhost:7777"
echo "  - View Neo4j: http://localhost:7474"
echo "  - Check logs: docker logs kgroot_latest-graph-builder-1"
