# RCA Enhancements - Documentation

Complete documentation for the enhanced RCA system has been moved to a dedicated folder.

## 📂 Documentation Location

All RCA enhancement documentation is now in:
```
docs/rca-enhancements/
```

## 📚 Available Documents

1. **[docs/rca-enhancements/INDEX.md](docs/rca-enhancements/INDEX.md)**
   - Documentation index and navigation guide
   - Quick links to all sections
   - Feature lookup table

2. **[docs/rca-enhancements/README.md](docs/rca-enhancements/README.md)**
   - Complete implementation guide
   - What was enhanced (5 production gaps + bonus features)
   - Deployment instructions (new cluster + existing)
   - Testing and verification
   - Neo4j queries
   - Troubleshooting

3. **[docs/rca-enhancements/TESTING_GUIDE.md](docs/rca-enhancements/TESTING_GUIDE.md)**
   - Detailed testing procedures
   - 8 test categories with examples
   - End-to-end RCA scenarios
   - Performance testing

4. **[docs/rca-enhancements/QUICK_REFERENCE.md](docs/rca-enhancements/QUICK_REFERENCE.md)**
   - Quick deploy commands
   - Essential Neo4j queries
   - Common kubectl commands
   - Troubleshooting quick fixes

## 🚀 Quick Start

### View Documentation
```bash
# Start with the index
cat docs/rca-enhancements/INDEX.md

# Or open in your editor
code docs/rca-enhancements/INDEX.md
```

### Quick Deploy
```bash
# Build enhanced image
docker build -t kg-builder:enhanced -f kg/Dockerfile .
minikube image load kg-builder:enhanced

# Apply configs
kubectl apply -f k8s/vector-configmap.yaml
kubectl set image deployment/kg-builder kg-builder=kg-builder:enhanced -n observability

# Restart components
kubectl rollout restart deployment/vector -n observability
kubectl rollout restart daemonset/vector-logs -n observability
```

### Access Neo4j
```bash
kubectl port-forward -n observability pod/neo4j-0 7474:7474 7687:7687 &
# Open: http://localhost:7474/browser/
# Username: neo4j
# Password: anuragvishwa
```

## ✅ What Was Enhanced

1. **Multi-format Log Parsing** - JSON, glog, plain text
2. **K8s Event Severity Mapping** - 15+ intelligent mappings
3. **Expanded Error Patterns** - 40+ patterns across 10 categories
4. **Severity Escalation** - WARNING→ERROR→FATAL after repeats
5. **Incident Clustering** - Groups related ERROR/FATAL events
6. **RCA Confidence Scoring** - 0.40-0.95 based on domain heuristics

## 📊 Current System State

- **7,879+ RCA links** in knowledge graph
- **2,712+ high-severity events** detected
- **90%+ target accuracy** (all enhancements deployed)

## 📖 For More Information

See [docs/rca-enhancements/INDEX.md](docs/rca-enhancements/INDEX.md) for complete documentation navigation.
