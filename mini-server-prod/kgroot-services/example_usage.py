"""
Example usage of KGroot RCA system
Demonstrates how to use the orchestrator for root cause analysis
"""

import asyncio
from datetime import datetime, timedelta
import os
import yaml
import logging

from models.event import Event, EventType, EventSeverity
from rca_orchestrator import RCAOrchestrator
from utils.neo4j_pattern_store import Neo4jPatternStore

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path='config.yaml'):
    """Load configuration from YAML file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def create_sample_events() -> list[Event]:
    """
    Create sample failure events for demonstration
    Simulates a CPU overload cascading failure
    """
    base_time = datetime.now() - timedelta(minutes=10)

    events = [
        # Root cause: CPU spike in api-gateway
        Event(
            event_id="evt_001",
            event_type=EventType.CPU_HIGH,
            timestamp=base_time,
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.WARNING,
            pod_name="api-gateway-abc123",
            metric_value=85.0,
            metric_unit="percent",
            threshold=80.0,
            message="CPU usage above threshold"
        ),

        # Propagation: High latency due to CPU
        Event(
            event_id="evt_002",
            event_type=EventType.LATENCY_HIGH,
            timestamp=base_time + timedelta(seconds=30),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.WARNING,
            pod_name="api-gateway-abc123",
            metric_value=1200.0,
            metric_unit="ms",
            threshold=500.0,
            message="Response latency increased"
        ),

        # Propagation: Memory pressure
        Event(
            event_id="evt_003",
            event_type=EventType.MEMORY_HIGH,
            timestamp=base_time + timedelta(seconds=60),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.CRITICAL,
            pod_name="api-gateway-abc123",
            metric_value=90.0,
            metric_unit="percent",
            threshold=85.0,
            message="Memory usage critical"
        ),

        # Propagation: OOM Kill
        Event(
            event_id="evt_004",
            event_type=EventType.OOM_KILL,
            timestamp=base_time + timedelta(seconds=90),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.CRITICAL,
            pod_name="api-gateway-abc123",
            message="Container killed due to OOM"
        ),

        # Symptom: Pod restart
        Event(
            event_id="evt_005",
            event_type=EventType.POD_RESTART,
            timestamp=base_time + timedelta(seconds=95),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.CRITICAL,
            pod_name="api-gateway-abc123",
            message="Pod restarted after OOM kill"
        ),

        # Symptom: Service degradation
        Event(
            event_id="evt_006",
            event_type=EventType.ERROR_RATE_HIGH,
            timestamp=base_time + timedelta(seconds=100),
            service="api-gateway",
            namespace="production",
            severity=EventSeverity.CRITICAL,
            metric_value=25.0,
            metric_unit="percent",
            threshold=5.0,
            message="Error rate spiked"
        ),

        # Downstream impact: Auth service
        Event(
            event_id="evt_007",
            event_type=EventType.LATENCY_HIGH,
            timestamp=base_time + timedelta(seconds=110),
            service="auth-service",
            namespace="production",
            severity=EventSeverity.WARNING,
            pod_name="auth-service-def456",
            metric_value=800.0,
            metric_unit="ms",
            threshold=300.0,
            message="Timeout calling upstream api-gateway"
        ),
    ]

    return events


async def main():
    """Main example function"""
    logger.info("=" * 60)
    logger.info("KGroot RCA System - Example Usage")
    logger.info("=" * 60)

    # Load configuration
    try:
        config = load_config('config.yaml')
    except FileNotFoundError:
        logger.warning("config.yaml not found, using defaults")
        config = {
            'openai': {'api_key': os.getenv('OPENAI_API_KEY'), 'enable_llm_analysis': False},
            'service_dependencies': {
                'api-gateway': ['auth-service', 'user-service'],
                'auth-service': ['database-service'],
                'user-service': ['database-service']
            }
        }

    # Initialize RCA Orchestrator
    openai_key = config.get('openai', {}).get('api_key')
    enable_llm = config.get('openai', {}).get('enable_llm_analysis', False) and openai_key

    orchestrator = RCAOrchestrator(
        openai_api_key=openai_key,
        enable_llm=enable_llm
    )

    # Set service dependencies
    service_deps = config.get('service_dependencies', {})
    orchestrator.set_service_dependencies(service_deps)

    # Load pattern library from Neo4j (if available)
    try:
        neo4j_config = config.get('neo4j', {})
        if neo4j_config:
            pattern_store = Neo4jPatternStore(
                uri=neo4j_config.get('uri', 'bolt://localhost:7687'),
                username=neo4j_config.get('username', 'neo4j'),
                password=neo4j_config.get('password', 'password')
            )

            patterns = pattern_store.get_all_patterns()
            orchestrator.load_pattern_library(patterns)
            logger.info(f"Loaded {len(patterns)} patterns from Neo4j")

            # Print statistics
            stats = pattern_store.get_statistics()
            logger.info(f"Pattern library stats: {stats}")

            pattern_store.close()
    except Exception as e:
        logger.warning(f"Could not connect to Neo4j: {e}")
        logger.info("Running without historical patterns")

    # Create sample failure events
    logger.info("\nCreating sample failure scenario...")
    events = create_sample_events()
    logger.info(f"Created {len(events)} events spanning "
               f"{(events[-1].timestamp - events[0].timestamp).total_seconds():.0f} seconds")

    # Perform RCA
    logger.info("\nPerforming Root Cause Analysis...")
    result = await orchestrator.analyze_failure(
        fault_id="fault_sample_001",
        events=events,
        context={
            'recent_deployments': 'api-gateway deployed 2 hours ago',
            'config_changes': 'No recent config changes',
            'resource_metrics': 'Cluster CPU: 75%, Memory: 68%'
        }
    )

    # Display results
    print("\n")
    print(orchestrator.get_summary(result))

    # Export to JSON
    logger.info("\nExporting results to JSON...")
    import json
    with open('rca_result_sample.json', 'w') as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    logger.info("Results saved to rca_result_sample.json")

    # Display detailed breakdown
    if result.top_root_causes:
        print("\n" + "=" * 60)
        print("DETAILED ROOT CAUSE BREAKDOWN")
        print("=" * 60)

        for i, cause in enumerate(result.top_root_causes[:3], 1):
            print(f"\n#{i} Root Cause Candidate:")
            print(f"  Event Type: {cause['event_type']}")
            print(f"  Service: {cause['service']}")
            print(f"  Pod: {cause.get('pod', 'N/A')}")
            print(f"  Timestamp: {cause['timestamp']}")
            print(f"  Confidence: {cause['confidence']}")
            print(f"  Explanation: {cause['explanation']}")
            if cause.get('propagation_path'):
                print(f"  Propagation: {' -> '.join(cause['propagation_path'][:5])}")

    if result.matched_patterns:
        print("\n" + "=" * 60)
        print("MATCHED HISTORICAL PATTERNS")
        print("=" * 60)

        for i, pattern_match in enumerate(result.matched_patterns, 1):
            pattern = pattern_match.pattern
            print(f"\n#{i} {pattern.name}")
            print(f"  Root Cause Type: {pattern.root_cause_type}")
            print(f"  Similarity: {pattern_match.similarity_score:.1%}")
            print(f"  Confidence: {pattern_match.confidence:.1%}")
            print(f"  Frequency: {pattern.frequency} occurrences")
            if pattern.resolution_steps:
                print(f"  Resolution Steps:")
                for step in pattern.resolution_steps:
                    print(f"    - {step}")

    if result.llm_analysis:
        print("\n" + "=" * 60)
        print("LLM ENHANCED ANALYSIS")
        print("=" * 60)

        analysis = result.llm_analysis
        if 'root_cause_diagnosis' in analysis:
            print(f"\nDiagnosis: {analysis['root_cause_diagnosis']}")
        if 'confidence_level' in analysis:
            print(f"Confidence Level: {analysis['confidence_level']}")
        if 'immediate_actions' in analysis:
            print("\nImmediate Actions:")
            for action in analysis['immediate_actions']:
                print(f"  - {action}")

    logger.info("\n" + "=" * 60)
    logger.info("Example completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
