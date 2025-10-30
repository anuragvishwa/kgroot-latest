"""
System test for AI SRE Platform

Tests:
1. Tool registry
2. GraphAgent
3. Router
4. Orchestrator
5. API endpoints
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from src.core.neo4j_service import Neo4jService
from src.core.tool_registry import tool_registry
from src.tools.graph_tools import (
    Neo4jRootCauseTool,
    Neo4jCausalChainTool,
    Neo4jBlastRadiusTool
)
from src.agents.graph_agent import GraphAgent
from src.orchestrator.router import RuleRouter
from src.orchestrator.orchestrator import AIRCAOrchestrator
from src.core.schemas import IncidentScope
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment
load_dotenv()


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


async def test_neo4j_connection():
    """Test 1: Neo4j Connection"""
    print_header("Test 1: Neo4j Connection")

    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

    print_info(f"Connecting to Neo4j at {neo4j_uri}...")

    try:
        neo4j = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
        if neo4j.verify_connectivity():
            print_success("Neo4j connected")
            return neo4j
        else:
            print_error("Neo4j connection failed")
            return None
    except Exception as e:
        print_error(f"Neo4j connection error: {e}")
        return None


async def test_tool_registry(neo4j):
    """Test 2: Tool Registry"""
    print_header("Test 2: Tool Registry")

    try:
        # Clear registry for clean test
        tool_registry.clear()

        # Register tools
        Neo4jRootCauseTool(neo4j)
        Neo4jCausalChainTool(neo4j)
        Neo4jBlastRadiusTool(neo4j)

        # Verify registration
        tools = tool_registry.get_tool_names()
        print_info(f"Registered tools: {tools}")

        assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"
        print_success(f"Tool registry working: {len(tools)} tools registered")

        return True
    except Exception as e:
        print_error(f"Tool registry test failed: {e}")
        return False


async def test_graph_agent(neo4j):
    """Test 3: GraphAgent"""
    print_header("Test 3: GraphAgent")

    try:
        # Initialize agent
        graph_tools = tool_registry.get_tools_by_category('graph')
        agent = GraphAgent(tools=graph_tools)

        print_info(f"Agent: {agent.capability.name}")
        print_info(f"Tools: {agent.capability.tools}")

        # Test investigation
        scope = {
            'tenant_id': 'test-01',
            'time_window_start': datetime.utcnow() - timedelta(hours=24),
            'time_window_end': datetime.utcnow()
        }

        print_info("Running investigation...")
        result = await agent.investigate("Test query", scope)

        print_info(f"Success: {result.success}")
        print_info(f"Findings: {len(result.findings)}")
        print_info(f"Latency: {result.latency_ms}ms")

        print_success(f"GraphAgent executed successfully")
        return True

    except Exception as e:
        print_error(f"GraphAgent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_router():
    """Test 4: Router"""
    print_header("Test 4: Rule Router")

    try:
        router = RuleRouter()

        # Test event-type routing
        scope = IncidentScope(
            tenant_id='test-01',
            time_window_start=datetime.utcnow() - timedelta(hours=24),
            time_window_end=datetime.utcnow()
        )

        decision = router.route(scope, {'event_type': 'OOMKilled'})

        print_info(f"Event type: OOMKilled")
        print_info(f"Selected agents: {decision.agents}")
        print_info(f"Confidence: {decision.confidence}")
        print_info(f"LLM used: {decision.llm_used}")

        assert 'GraphAgent' in decision.agents, "Expected GraphAgent in decision"
        assert decision.llm_used == False, "Should not use LLM for known patterns"

        print_success("Router working correctly")
        return True

    except Exception as e:
        print_error(f"Router test failed: {e}")
        return False


async def test_orchestrator(neo4j):
    """Test 5: Orchestrator"""
    print_header("Test 5: Orchestrator (Full Integration)")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print_error("OPENAI_API_KEY not set, skipping orchestrator test")
        return False

    try:
        orchestrator = AIRCAOrchestrator(
            neo4j_service=neo4j,
            openai_api_key=openai_api_key,
            model=os.getenv("LLM_MODEL", "gpt-4o")  # Use cheaper model for testing
        )

        print_info(f"Model: {orchestrator.model}")
        print_info(f"Agents: {list(orchestrator.agents.keys())}")

        # Run investigation
        print_info("Running full investigation...")

        result = await orchestrator.investigate(
            query="Test investigation for system check",
            tenant_id="test-01",
            event_type="OOMKilled"
        )

        print_info(f"Incident ID: {result.incident_id}")
        print_info(f"Agents executed: {list(result.agent_results.keys())}")
        print_info(f"Synthesis confidence: {result.synthesis.confidence}")
        print_info(f"Total cost: ${result.total_cost_usd:.4f}")
        print_info(f"Total latency: {result.total_latency_ms}ms")

        print_success("Orchestrator working correctly")
        return True

    except Exception as e:
        print_error(f"Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print_header("AI SRE Platform - System Test")

    results = {}

    # Test 1: Neo4j
    neo4j = await test_neo4j_connection()
    results['neo4j'] = neo4j is not None

    if not neo4j:
        print_error("Cannot proceed without Neo4j connection")
        return

    # Test 2: Tool Registry
    results['tool_registry'] = await test_tool_registry(neo4j)

    # Test 3: GraphAgent
    results['graph_agent'] = await test_graph_agent(neo4j)

    # Test 4: Router
    results['router'] = await test_router()

    # Test 5: Orchestrator (full integration)
    results['orchestrator'] = await test_orchestrator(neo4j)

    # Summary
    print_header("Test Summary")

    for test_name, passed in results.items():
        if passed:
            print_success(f"{test_name}: PASSED")
        else:
            print_error(f"{test_name}: FAILED")

    total = len(results)
    passed = sum(results.values())

    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}\n")

    if passed == total:
        print(f"{Colors.OKGREEN}{Colors.BOLD}🎉 All tests passed! System ready to deploy.{Colors.ENDC}\n")
    else:
        print(f"{Colors.WARNING}{Colors.BOLD}⚠️  Some tests failed. Review errors above.{Colors.ENDC}\n")

    # Cleanup
    neo4j.close()


if __name__ == "__main__":
    asyncio.run(main())
