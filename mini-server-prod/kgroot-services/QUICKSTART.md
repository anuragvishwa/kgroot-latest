# KGroot RCA - Quick Start Guide

## 🚀 How to Run This

### Prerequisites

- Python 3.8+ installed
- OpenAI API key (optional, for LLM features)
- Neo4j database (optional, for pattern storage)

---

## Option 1: Run Without Any Setup (Demo Mode)

The fastest way to see it in action:

```bash
# Navigate to kgroot-services
cd kgroot-services

# Install dependencies
pip install -r requirements.txt

# Run the example (works without Neo4j or OpenAI)
python example_usage.py
```

This will:
- Create sample failure events
- Build a fault propagation graph
- Analyze root causes
- Display results in terminal

**Expected output:**
```
============================================================
ROOT CAUSE ANALYSIS: fault_sample_001
============================================================

TOP ROOT CAUSE (Confidence: 87.3%):
  Event Type: cpu_high
  Service: api-gateway
  Pod: api-gateway-abc123
  ...
```

---

## Option 2: Run With OpenAI (GPT-4o Enhanced Analysis)

For AI-powered insights and recommendations:

### Step 1: Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create new API key
3. Copy it (starts with `sk-...`)

### Step 2: Configure

```bash
# Create config file
cp config.yaml.example config.yaml

# Edit config.yaml and add your API key
nano config.yaml
```

Update this section:
```yaml
openai:
  api_key: "sk-your-actual-api-key-here"  # ← Paste your key
  embedding_model: "text-embedding-3-small"
  chat_model: "gpt-4o"  # Latest GPT-4o model
  enable_llm_analysis: true  # Set to true
```

### Step 3: Run with LLM

```bash
python example_usage.py
```

Now you'll get:
- ✅ Natural language explanations
- ✅ Contextual recommendations
- ✅ Automated runbooks
- ✅ Enhanced confidence scoring

**Example output:**
```
LLM ENHANCED ANALYSIS
═══════════════════════════════════════
Diagnosis: The root cause is a CPU resource exhaustion in the
api-gateway service, triggered by increased load. The failure
cascaded through memory pressure, OOM kill, and pod restart.

Immediate Actions:
  - Scale horizontally: kubectl scale deployment api-gateway --replicas=5
  - Investigate traffic spike source
  - Review recent deployments
```

---

## Option 3: Run With Neo4j (Pattern Storage)

For persistent pattern learning:

### Step 1: Start Neo4j

**Option A: Docker (Easiest)**
```bash
docker run -d \
  --name kgroot-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5.23-community
```

**Option B: Local Installation**
```bash
# macOS
brew install neo4j
neo4j start

# Ubuntu
sudo apt install neo4j
sudo systemctl start neo4j
```

Access Neo4j Browser: http://localhost:7474
- Username: `neo4j`
- Password: `your_password`

### Step 2: Configure

Edit `config.yaml`:
```yaml
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "your_password"  # ← Your password
```

### Step 3: Initialize Schema

```python
from utils.neo4j_pattern_store import Neo4jPatternStore

store = Neo4jPatternStore(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="your_password"
)

# Initialize schema (run once)
store.initialize_schema()
print("Neo4j schema initialized!")
```

### Step 4: Run

```bash
python example_usage.py
```

Now patterns are stored in Neo4j and will be reused for future failures!

---

## Option 4: Full Setup (Neo4j + OpenAI)

Combine both for maximum capability:

```bash
# 1. Start Neo4j
docker run -d --name kgroot-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 neo4j:5.23-community

# 2. Create config
cp config.yaml.example config.yaml

# 3. Edit config with both Neo4j and OpenAI credentials
nano config.yaml

# 4. Run
python example_usage.py
```

---

## 🎯 Using in Your Code

### Basic Usage

```python
import asyncio
from rca_orchestrator import RCAOrchestrator
from models.event import Event, EventType, EventSeverity
from datetime import datetime

async def analyze_my_failure():
    # Initialize
    orchestrator = RCAOrchestrator(
        openai_api_key="sk-...",  # Optional
        enable_llm=True  # Set False for rule-based only
    )

    # Set your service topology
    orchestrator.set_service_dependencies({
        'api-gateway': ['auth-service', 'user-service'],
        'auth-service': ['database-service'],
        'user-service': ['database-service', 'cache-service']
    })

    # Create events from your monitoring system
    events = [
        Event(
            event_id="evt_001",
            event_type=EventType.CPU_HIGH,
            timestamp=datetime.now(),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.CRITICAL,
            pod_name="api-gateway-abc123",
            metric_value=95.0,
            metric_unit="percent",
            message="CPU usage critical"
        ),
        # ... more events
    ]

    # Analyze
    result = await orchestrator.analyze_failure(
        fault_id="my_fault_001",
        events=events,
        context={
            'recent_deployments': 'api-gateway v1.2.3 deployed 1h ago',
            'config_changes': 'None',
            'cluster_load': 'CPU: 75%, Memory: 68%'
        }
    )

    # Get results
    print(orchestrator.get_summary(result))

    # Access structured data
    if result.top_root_causes:
        top_cause = result.top_root_causes[0]
        print(f"Root cause: {top_cause['event_type']}")
        print(f"Service: {top_cause['service']}")
        print(f"Confidence: {top_cause['confidence']}")

    # Get recommendations
    for action in result.recommended_actions:
        print(f"Action: {action}")

# Run
asyncio.run(analyze_my_failure())
```

### Without Async (Simpler)

```python
from rca_orchestrator import RCAOrchestrator

# Initialize without LLM (synchronous)
orchestrator = RCAOrchestrator(enable_llm=False)

# Set dependencies
orchestrator.set_service_dependencies(your_dependencies)

# For sync usage, just call directly (won't use LLM)
result = orchestrator.analyze_failure_sync(fault_id, events)
```

---

## 🔧 Configuration Options

### Minimal (No External Services)

```yaml
# config.yaml
openai:
  enable_llm_analysis: false  # Disable LLM

# No neo4j section needed
```

### Rule-Based + Pattern Storage

```yaml
# config.yaml
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "password"

openai:
  enable_llm_analysis: false  # Use rules only
```

### Full AI-Powered

```yaml
# config.yaml
neo4j:
  uri: "bolt://localhost:7687"
  username: "neo4j"
  password: "password"

openai:
  api_key: "sk-..."
  embedding_model: "text-embedding-3-small"
  chat_model: "gpt-4o"  # Latest and most powerful
  enable_llm_analysis: true
```

---

## 📊 What Models Are Used?

### OpenAI Models

| Model | Purpose | Cost | Speed |
|-------|---------|------|-------|
| **gpt-4o** | Main analysis, recommendations | $$$ | Fast |
| **text-embedding-3-small** | Semantic similarity | $ | Fast |

**Note**: OpenAI pricing (as of 2024):
- GPT-4o: ~$2.50 per 1M input tokens, ~$10 per 1M output tokens
- Embeddings: ~$0.02 per 1M tokens

Typical RCA analysis costs: **$0.01 - $0.05 per incident**

### Why GPT-4o?

GPT-4o is OpenAI's latest and most powerful model:
- ✅ Better reasoning than GPT-4 Turbo
- ✅ Faster response times
- ✅ More accurate technical analysis
- ✅ Better structured output

---

## 🐛 Troubleshooting

### "Module not found" errors

```bash
# Make sure you're in the right directory
cd kgroot-services

# Reinstall dependencies
pip install -r requirements.txt
```

### "OpenAI API key not found"

```bash
# Option 1: Set environment variable
export OPENAI_API_KEY="sk-..."
python example_usage.py

# Option 2: Update config.yaml
nano config.yaml  # Add your key
```

### "Cannot connect to Neo4j"

```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Or check local service
neo4j status

# Restart if needed
docker restart kgroot-neo4j
```

### "No patterns found"

This is normal on first run! The system needs to learn patterns:

```python
# Store some patterns first
from utils.neo4j_pattern_store import Neo4jPatternStore

store = Neo4jPatternStore(...)
store.initialize_schema()

# Run analysis multiple times - patterns will accumulate
```

### Running without Neo4j or OpenAI

It works! Just set in config:
```yaml
openai:
  enable_llm_analysis: false
```

And don't configure Neo4j. The system will run in rule-based mode.

---

## 📈 Performance Tips

### For Fastest Analysis (< 500ms)

```yaml
openai:
  enable_llm_analysis: false  # Skip LLM
```

### For Best Accuracy

```yaml
openai:
  enable_llm_analysis: true
  chat_model: "gpt-4o"  # Use latest model
```

### For Cost Optimization

```yaml
openai:
  enable_llm_analysis: true
  chat_model: "gpt-4o-mini"  # Cheaper, still good
```

---

## 🎓 Next Steps

1. **Run the example**: `python example_usage.py`
2. **Try with your events**: Modify `example_usage.py`
3. **Enable OpenAI**: Add API key to config
4. **Set up Neo4j**: For pattern storage
5. **Integrate**: Connect to your alerting system
6. **Deploy**: See [Integration Guide](README.md#integration)

---

## 💡 Tips

- **Start simple**: Run without Neo4j/OpenAI first
- **Add OpenAI**: For better explanations
- **Add Neo4j**: When you have recurring failures
- **Tune weights**: Adjust in config.yaml for your environment
- **Monitor costs**: OpenAI API costs ~$0.01-0.05 per analysis

---

## 📞 Need Help?

- **Full docs**: See [README.md](README.md)
- **Configuration**: See [config.yaml.example](config.yaml.example)
- **Issues**: Check logs in `kgroot_rca.log`
- **Examples**: See [example_usage.py](example_usage.py)

---

## ⚡ TL;DR

**Absolute quickest start:**

```bash
cd kgroot-services
pip install -r requirements.txt
python example_usage.py
```

**With AI (recommended):**

```bash
cp config.yaml.example config.yaml
# Add OpenAI key to config.yaml
python example_usage.py
```

Done! 🎉
