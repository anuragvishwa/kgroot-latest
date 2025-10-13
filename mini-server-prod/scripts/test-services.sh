#!/bin/bash

# ============================================================================
# KG RCA Mini Server - Service Health Check
# ============================================================================
# This script tests all services and reports their status
# Run after deploying services
# ============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}KG RCA Mini Server - Service Health Check${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""

# ============================================================================
# Configuration
# ============================================================================
HOST="localhost"
TIMEOUT=5

# ============================================================================
# Helper functions
# ============================================================================
check_port() {
    local service=$1
    local port=$2
    local protocol=${3:-tcp}

    echo -n "  Port $port: "
    if timeout $TIMEOUT bash -c "cat < /dev/null > /dev/$protocol/$HOST/$port" 2>/dev/null; then
        echo -e "${GREEN}✓ Open${NC}"
        return 0
    else
        echo -e "${RED}✗ Closed${NC}"
        return 1
    fi
}

check_http() {
    local service=$1
    local url=$2

    echo -n "  HTTP: "
    local status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT "$url" 2>/dev/null)

    if [ "$status" -eq 200 ] || [ "$status" -eq 401 ] || [ "$status" -eq 302 ]; then
        echo -e "${GREEN}✓ Responding (HTTP $status)${NC}"
        return 0
    else
        echo -e "${RED}✗ Not responding (HTTP $status)${NC}"
        return 1
    fi
}

check_container() {
    local container=$1

    echo -n "  Container: "
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        local status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null)
        if [ "$status" == "running" ]; then
            echo -e "${GREEN}✓ Running${NC}"
            return 0
        else
            echo -e "${RED}✗ $status${NC}"
            return 1
        fi
    else
        echo -e "${RED}✗ Not found${NC}"
        return 1
    fi
}

check_docker_health() {
    local container=$1

    local health=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)
    if [ ! -z "$health" ]; then
        echo -n "  Health: "
        if [ "$health" == "healthy" ]; then
            echo -e "${GREEN}✓ Healthy${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠ $health${NC}"
            return 1
        fi
    fi
    return 0
}

# ============================================================================
# Check Docker
# ============================================================================
echo -e "${BLUE}[Docker]${NC}"
if command -v docker &> /dev/null; then
    echo -e "  Version: ${GREEN}$(docker --version)${NC}"
    echo -e "  Compose: ${GREEN}$(docker compose version)${NC}"
else
    echo -e "  ${RED}✗ Docker not installed${NC}"
    exit 1
fi
echo ""

# ============================================================================
# Check Zookeeper
# ============================================================================
echo -e "${BLUE}[Zookeeper]${NC}"
check_container "kg-zookeeper"
check_port "zookeeper" 2181
echo ""

# ============================================================================
# Check Kafka
# ============================================================================
echo -e "${BLUE}[Kafka]${NC}"
check_container "kg-kafka"
check_docker_health "kg-kafka"
check_port "kafka" 9092
check_port "kafka-ssl" 9093

# Test topic listing
echo -n "  Topics: "
if docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list &>/dev/null; then
    TOPIC_COUNT=$(docker exec kg-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null | wc -l)
    echo -e "${GREEN}✓ $TOPIC_COUNT topics${NC}"
else
    echo -e "${RED}✗ Cannot list topics${NC}"
fi
echo ""

# ============================================================================
# Check Kafka UI
# ============================================================================
echo -e "${BLUE}[Kafka UI]${NC}"
check_container "kg-kafka-ui"
check_port "kafka-ui" 7777
check_http "kafka-ui" "http://$HOST:7777"
echo ""

# ============================================================================
# Check Neo4j
# ============================================================================
echo -e "${BLUE}[Neo4j]${NC}"
check_container "kg-neo4j"
check_docker_health "kg-neo4j"
check_port "neo4j-http" 7474
check_port "neo4j-bolt" 7687
check_http "neo4j" "http://$HOST:7474"
echo ""

# ============================================================================
# Check Graph Builder
# ============================================================================
echo -e "${BLUE}[Graph Builder]${NC}"
check_container "kg-graph-builder"
check_docker_health "kg-graph-builder"
check_port "graph-builder-metrics" 9090
check_http "graph-builder" "http://$HOST:9090/healthz"
echo ""

# ============================================================================
# Check Alerts Enricher
# ============================================================================
echo -e "${BLUE}[Alerts Enricher]${NC}"
check_container "kg-alerts-enricher"
echo -n "  Status: "
if docker ps --format '{{.Names}}' --filter "status=running" | grep -q "kg-alerts-enricher"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
fi
echo ""

# ============================================================================
# Check KG API
# ============================================================================
echo -e "${BLUE}[KG API]${NC}"
check_container "kg-api"
check_docker_health "kg-api"
check_port "kg-api" 8080
check_http "kg-api" "http://$HOST:8080/healthz"
echo ""

# ============================================================================
# Check Prometheus
# ============================================================================
echo -e "${BLUE}[Prometheus]${NC}"
check_container "kg-prometheus"
check_port "prometheus" 9091
check_http "prometheus" "http://$HOST:9091/-/healthy"
echo ""

# ============================================================================
# Check Grafana
# ============================================================================
echo -e "${BLUE}[Grafana]${NC}"
check_container "kg-grafana"
check_port "grafana" 3000
check_http "grafana" "http://$HOST:3000/api/health"
echo ""

# ============================================================================
# System Resources
# ============================================================================
echo -e "${BLUE}[System Resources]${NC}"
echo "  Memory usage:"
docker stats --no-stream --format "    {{.Name}}: {{.MemUsage}}" 2>/dev/null | head -n 10

echo ""
echo "  Disk usage:"
df -h / | awk 'NR==2 {printf "    Root: %s / %s (%s used)\n", $3, $2, $5}'
docker system df --format "    Docker: {{.Size}}" 2>/dev/null | head -n 1

echo ""

# ============================================================================
# Service URLs
# ============================================================================
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Service URLs${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo -e "${BLUE}External Access (replace 'localhost' with your server IP):${NC}"
echo "  Kafka UI:    http://localhost:7777"
echo "  Neo4j:       http://localhost:7474 (user: neo4j)"
echo "  KG API:      http://localhost:8080"
echo "  Prometheus:  http://localhost:9091"
echo "  Grafana:     http://localhost:3000 (user: admin)"
echo ""
echo -e "${BLUE}Internal Access (from other containers):${NC}"
echo "  Kafka:       kafka:9092"
echo "  Zookeeper:   zookeeper:2181"
echo "  Neo4j:       neo4j://neo4j:7687"
echo "  KG API:      http://kg-api:8080"
echo ""
echo -e "${BLUE}SSL Access (if configured):${NC}"
echo "  Kafka SSL:   your-server:9093"
echo ""

# ============================================================================
# Quick Tips
# ============================================================================
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN}Quick Tips${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "View logs:"
echo "  All services: docker compose logs -f"
echo "  Specific service: docker compose logs -f <service-name>"
echo ""
echo "Restart a service:"
echo "  docker compose restart <service-name>"
echo ""
echo "Check container health:"
echo "  docker ps"
echo ""
echo "Create Kafka topics:"
echo "  ./scripts/create-topics.sh"
echo ""
echo "Access Neo4j shell:"
echo "  docker exec -it kg-neo4j cypher-shell -u neo4j -p <password>"
echo ""
echo "Access Kafka console:"
echo "  docker exec -it kg-kafka kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic <topic-name>"
echo ""
