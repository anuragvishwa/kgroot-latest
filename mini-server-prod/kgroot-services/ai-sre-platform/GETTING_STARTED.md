# Getting Started - AI SRE Platform

> **Quick start guide** for developers joining the project

---

## 🎯 What You Need to Know

This platform builds a **multi-agent AI SRE system** for automated root cause analysis. Think of it as:

```
Production Incident
    ↓
AI SRE investigates autonomously
    ├─> Queries causality graphs (Neo4j)
    ├─> Checks metrics (Datadog)
    ├─> Searches logs (Argo/OpenSearch)
    ├─> Reviews code changes (GitHub)
    └─> Searches past incidents (Slack)
    ↓
Returns: Root cause + remediation steps
(in 30 seconds, not 30 minutes)
```

---

## 📚 Required Reading (30 minutes)

**Read these documents in order**:

1. **[README.md](./README.md)** (15 min)
   - System overview
   - Architecture diagram
   - Key concepts

2. **[CANONICAL_EVENT_ENVELOPE.md](./CANONICAL_EVENT_ENVELOPE.md)** (10 min)
   - Event schema standard
   - Why it matters
   - Examples

3. **[IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)** (5 min)
   - Implementation phases
   - What we're building next

---

## 🛠️ Local Development Setup

### Prerequisites

```bash
# macOS
brew install python@3.11
brew install kafka
brew install neo4j
brew install redis
brew install postgresql

# Or use Docker (recommended)
docker --version  # Ensure Docker is installed
```

### Step 1: Clone and Setup

```bash
# Navigate to project
cd /Users/anuragvishwa/Anurag/kgroot_latest/mini-server-prod/kgroot-services/ai-sre-platform

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies (once requirements.txt is created)
pip install -r requirements.txt
```

### Step 2: Start Infrastructure

```bash
# Start all services via Docker Compose
docker-compose up -d

# Verify services are running
docker-compose ps

# Expected output:
# NAME                STATUS
# kafka               running
# neo4j               running
# opensearch          running
# redis               running
```

### Step 3: Initialize Database

```bash
# Run existing Neo4j setup scripts
# (Use your existing COMPLETE-RCA-SYSTEM-GUIDE.md scripts)

# Connect to Neo4j
open http://localhost:7474

# Run index creation queries from Phase 1.2
```

### Step 4: Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit with your credentials
nano .env
```

**.env contents**:
```bash
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# OpenAI (for LLM)
OPENAI_API_KEY=sk-...

# Datadog (optional for now)
DATADOG_API_KEY=
DATADOG_APP_KEY=

# GitHub (optional for now)
GITHUB_TOKEN=

# Slack (optional for now)
SLACK_TOKEN=
```

### Step 5: Verify Setup

```bash
# Test Neo4j connection
python -c "from neo4j import GraphDatabase; \
  driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password')); \
  driver.verify_connectivity(); \
  print('✅ Neo4j connected')"

# Test Kafka
kafka-topics --list --bootstrap-server localhost:9092

# Test Redis
redis-cli ping  # Should return "PONG"
```

---

## 🏗️ Project Structure

```
ai-sre-platform/
│
├── docs/                          # Documentation
│   ├── README.md                  # Overview
│   ├── ARCHITECTURE.md            # Detailed architecture
│   ├── CANONICAL_EVENT_ENVELOPE.md # Event schema
│   └── IMPLEMENTATION_ROADMAP.md  # Build phases
│
├── config/                        # Configuration files
│   ├── schemas/                   # Event schemas (Avro/JSON)
│   ├── tools/                     # Tool configs
│   └── agents/                    # Agent configs
│
├── src/                           # Source code
│   ├── core/                      # Core abstractions
│   │   ├── tool_registry.py       # Tool plugin system
│   │   ├── agent_registry.py      # Agent management
│   │   └── schemas.py             # Pydantic models
│   │
│   ├── orchestrator/              # Investigation orchestration
│   │   ├── orchestrator.py        # Main orchestrator
│   │   ├── router.py              # Rule-based routing
│   │   └── planner.py             # LLM planning
│   │
│   ├── agents/                    # Specialist agents
│   │   ├── base.py                # Base agent class
│   │   ├── graph_agent.py         # Neo4j RCA
│   │   ├── metrics_agent.py       # Datadog/Prometheus
│   │   └── ...                    # Other agents
│   │
│   ├── tools/                     # Tool implementations
│   │   ├── base.py                # Base tool class
│   │   ├── graph_tools.py         # Neo4j tools
│   │   └── ...                    # Other tools
│   │
│   ├── ingestion/                 # Kafka ingestion
│   │   ├── kafka_consumer.py      # Multi-tenant consumer
│   │   └── processors/            # Event processors
│   │
│   └── api/                       # REST API
│       └── routes/                # API endpoints
│
├── tests/                         # Tests
├── scripts/                       # Utility scripts
└── docker/                        # Docker configs
```

---

## 🔨 Development Workflow

### Creating a New Tool

1. **Create tool file**: `src/tools/my_tool.py`

```python
from src.core.tool_registry import BaseTool, ToolMetadata, tool_registry

class MyNewTool(BaseTool):
    def __init__(self, api_client):
        self.client = api_client
        tool_registry.register(self)  # Auto-register

    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_new_tool",
            description="Does something useful",
            category="metrics"  # graph|metrics|logs|code|context
        )

    async def execute(self, params: dict) -> dict:
        # Your implementation
        result = await self.client.query(params)
        return {"success": True, "data": result}

    def get_schema(self) -> dict:
        # JSON schema for LLM function calling
        return {
            "type": "function",
            "function": {
                "name": self.metadata.name,
                "description": self.metadata.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string"}
                    },
                    "required": ["param1"]
                }
            }
        }
```

2. **Write tests**: `tests/unit/tools/test_my_tool.py`

```python
import pytest
from src.tools.my_tool import MyNewTool

@pytest.mark.asyncio
async def test_my_tool_execute():
    tool = MyNewTool(mock_client)
    result = await tool.execute({"param1": "test"})
    assert result["success"] == True
```

3. **Enable in config**: `config/tools/tools.yaml`

```yaml
tools:
  my_new_tool:
    enabled: true
    api_key: ${MY_TOOL_API_KEY}
```

4. **Use in agent**: Tool now available to all agents!

### Running Tests

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Specific test file
pytest tests/unit/tools/test_graph_tools.py -v

# With coverage
pytest --cov=src tests/
```

### Code Quality

```bash
# Format code
ruff format src/

# Lint
ruff check src/

# Type checking
mypy src/
```

---

## 🐛 Debugging Tips

### Neo4j Queries Not Working

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check logs
docker logs neo4j

# Test connection
cypher-shell -u neo4j -p password
```

### Kafka Issues

```bash
# Check topics
kafka-topics --list --bootstrap-server localhost:9092

# Check consumer groups
kafka-consumer-groups --list --bootstrap-server localhost:9092

# Tail a topic
kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic k8s-events-acme-01 \
  --from-beginning
```

### Agent Not Executing

```python
# Add debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check tool registry
from src.core.tool_registry import tool_registry
print(tool_registry._tools.keys())

# Check agent has tools
agent = GraphAgent(...)
print(agent.tools.keys())
```

---

## 📖 Common Tasks

### Add a New Data Source

1. **Define event transformation** in `src/ingestion/envelope.py`
2. **Create Kafka topic**: `kafka-topics --create ...`
3. **Create processor** in `src/ingestion/processors/`
4. **Add to consumer** in `src/ingestion/kafka_consumer.py`

### Add a New Agent

1. **Create agent file**: `src/agents/my_agent.py`
2. **Inherit from BaseAgent**
3. **Define capability** (name, tools, expertise)
4. **Implement `investigate()` method**
5. **Write tests**

### Query Neo4j from Code

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

def find_root_causes(client_id: str):
    with driver.session() as session:
        result = session.run("""
            MATCH (e:Episodic {client_id: $client_id})
            WHERE NOT EXISTS {
                MATCH (:Episodic {client_id: $client_id})-[:POTENTIAL_CAUSE]->(e)
            }
            RETURN e
            LIMIT 10
        """, client_id=client_id)
        return [record["e"] for record in result]
```

---

## 🚀 Next Steps

### For New Developers

1. ✅ Complete local setup (above)
2. ✅ Read all documentation
3. ✅ Run existing tests
4. ✅ Pick a Phase 1 task from [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)
5. ✅ Create feature branch: `git checkout -b feature/your-task`
6. ✅ Implement, test, and submit PR

### Current Sprint (Example)

**Phase 1: Foundation** (Weeks 1-2)

Tasks available:
- [ ] `#1` - Create core schemas (src/core/schemas.py)
- [ ] `#2` - Implement tool registry (src/core/tool_registry.py)
- [ ] `#3` - Create base agent class (src/agents/base.py)
- [ ] `#4` - Wrap Neo4j as GraphAgent (src/agents/graph_agent.py)
- [ ] `#5` - Build simple orchestrator (src/orchestrator/orchestrator.py)

**Pick a task and let's build! 🎯**

---

## 💬 Getting Help

- **Slack**: `#ai-sre-platform`
- **Team Lead**: [Your Name]
- **Architecture Questions**: Review [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Implementation Questions**: Check [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)

---

## 📚 Additional Resources

### Internal Docs
- Existing RCA system: `../COMPLETE-RCA-SYSTEM-GUIDE.md`
- Existing orchestrator: `../rca_orchestrator.py`
- Existing API: `../rca-api/src/api/rca.py`

### External Docs
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Kafka Python](https://docs.confluent.io/kafka-clients/python/current/overview.html)
- [OpenAI API](https://platform.openai.com/docs/)

---

**Welcome to the team! Let's build an AI SRE that actually works. 🚀**