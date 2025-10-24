#!/bin/bash
# Quick demo script for KGroot RCA

set -e

echo "=================================="
echo "KGroot RCA - Demo Runner"
echo "=================================="
echo ""

# Check if we're in the right directory
if [ ! -f "example_usage.py" ]; then
    echo "❌ Error: Please run this from the kgroot-services directory"
    echo "   cd kgroot-services && ./run_demo.sh"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"
echo ""

# Check if dependencies are installed
echo "Checking dependencies..."
if ! python3 -c "import networkx" 2>/dev/null; then
    echo "⚠️  Dependencies not installed. Installing now..."
    pip3 install -r requirements.txt
    echo "✓ Dependencies installed"
else
    echo "✓ Dependencies already installed"
fi
echo ""

# Check for config
if [ ! -f "config.yaml" ]; then
    echo "⚠️  No config.yaml found. Running in demo mode (no LLM)..."
    echo "   To enable GPT-4o: cp config.yaml.example config.yaml"
    echo "   Then add your OpenAI API key"
    echo ""
fi

# Check for OpenAI key
if [ -f "config.yaml" ]; then
    if grep -q "sk-proj" config.yaml || grep -q "sk-[a-zA-Z0-9]" config.yaml; then
        echo "✓ OpenAI API key found in config.yaml"
        echo "✓ Will use GPT-4o for enhanced analysis"
    else
        echo "ℹ️  No OpenAI key in config.yaml"
        echo "   Running in rule-based mode (still works great!)"
    fi
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "✓ OpenAI API key found in environment"
    echo "✓ Will use GPT-4o for enhanced analysis"
else
    echo "ℹ️  No OpenAI API key found"
    echo "   Running in rule-based mode"
fi
echo ""

# Check Neo4j
echo "Checking Neo4j connection..."
if command -v docker &> /dev/null; then
    if docker ps | grep -q neo4j; then
        echo "✓ Neo4j container is running"
    else
        echo "ℹ️  Neo4j not running (optional)"
        echo "   To start: docker run -d --name kgroot-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5.23-community"
    fi
else
    echo "ℹ️  Docker not found (Neo4j is optional)"
fi
echo ""

# Run the demo
echo "=================================="
echo "Starting RCA Demo..."
echo "=================================="
echo ""

python3 example_usage.py

echo ""
echo "=================================="
echo "Demo Complete!"
echo "=================================="
echo ""
echo "📊 Results saved to: rca_result_sample.json"
echo "📝 Logs saved to: kgroot_rca.log"
echo ""
echo "Next steps:"
echo "  1. Review the analysis above"
echo "  2. Try with your own events (modify example_usage.py)"
echo "  3. Enable GPT-4o: Add OpenAI key to config.yaml"
echo "  4. Add Neo4j for pattern storage"
echo ""
echo "Full docs: See QUICKSTART.md and README.md"
