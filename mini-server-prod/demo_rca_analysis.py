#!/usr/bin/env python3
"""
Demo RCA Analysis Script
Analyzes events from Kafka to identify root causes of failures
"""

import json
from kafka import KafkaConsumer
from collections import defaultdict
from datetime import datetime, timedelta

def analyze_pod_failures(kafka_brokers='localhost:9092', client_id='mn-01'):
    """Analyze events for a specific client to identify pod failures and root causes"""

    print(f"🔍 Starting RCA Analysis for client: {client_id}")
    print(f"   Kafka brokers: {kafka_brokers}")
    print()

    # Create consumer for events.normalized topic
    consumer = KafkaConsumer(
        'events.normalized',
        bootstrap_servers=kafka_brokers,
        auto_offset_reset='earliest',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')) if m else None,
        key_deserializer=lambda k: k.decode('utf-8') if k else None,
        consumer_timeout_ms=5000  # Stop after 5 seconds of no messages
    )

    # Track events by pod
    pod_events = defaultdict(list)
    failure_events = []

    print("📥 Consuming events from Kafka...")
    event_count = 0

    for message in consumer:
        if message.value is None:
            continue

        event_count += 1
        event = message.value

        # Extract pod name from involvedObject
        involved_obj = event.get('involvedObject', {})
        pod_name = involved_obj.get('name', '')

        if not pod_name:
            continue

        # Collect all events for this pod
        pod_events[pod_name].append({
            'reason': event.get('reason', ''),
            'message': event.get('message', ''),
            'type': event.get('type', ''),
            'timestamp': event.get('firstTimestamp', ''),
            'count': event.get('count', 1)
        })

        # Identify failure events
        reason = event.get('reason', '').lower()
        message = event.get('message', '').lower()

        if any(keyword in reason or keyword in message for keyword in
               ['oom', 'killed', 'failed', 'error', 'backoff', 'crash']):
            failure_events.append({
                'pod': pod_name,
                'reason': event.get('reason'),
                'message': event.get('message'),
                'timestamp': event.get('firstTimestamp'),
                'type': event.get('type')
            })

    consumer.close()

    print(f"✅ Consumed {event_count} events total")
    print(f"   Tracked events for {len(pod_events)} pods")
    print(f"   Found {len(failure_events)} potential failure events")
    print()

    # Analyze failures
    if not failure_events:
        print("ℹ️  No obvious failure events found in recent history")
        print("   This could mean:")
        print("   - No failures occurred")
        print("   - Failures are older than Kafka retention")
        print("   - Events are being filtered out")
    else:
        print("🚨 FAILURE ANALYSIS")
        print("=" * 80)

        # Group failures by pod
        failures_by_pod = defaultdict(list)
        for failure in failure_events:
            failures_by_pod[failure['pod']].append(failure)

        for pod_name, failures in failures_by_pod.items():
            print(f"\n📍 Pod: {pod_name}")
            print(f"   Failure count: {len(failures)}")

            # Analyze failure pattern
            reasons = [f['reason'] for f in failures]
            reason_counts = defaultdict(int)
            for r in reasons:
                reason_counts[r] += 1

            print(f"   Failure reasons:")
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                print(f"      - {reason}: {count} occurrences")

            # Show latest failure details
            latest = failures[-1]
            print(f"\n   Latest failure:")
            print(f"      Reason: {latest['reason']}")
            print(f"      Message: {latest['message'][:100]}...")
            print(f"      Time: {latest['timestamp']}")

            # Root cause analysis
            print(f"\n   🎯 ROOT CAUSE ANALYSIS:")
            if any('oom' in r.lower() for r in reasons):
                print(f"      ⚠️  Out of Memory (OOM) Kill detected")
                print(f"      📊 Recommended actions:")
                print(f"         1. Increase memory limits in pod spec")
                print(f"         2. Investigate memory leaks in application")
                print(f"         3. Check if workload spike caused OOM")
                print(f"         4. Review memory request/limit ratio")
            elif any('crash' in r.lower() or 'backoff' in r.lower() for r in reasons):
                print(f"      ⚠️  Application crash detected (CrashLoopBackOff)")
                print(f"      📊 Recommended actions:")
                print(f"         1. Check application logs for errors")
                print(f"         2. Verify startup command is correct")
                print(f"         3. Check dependency availability (DB, services)")
                print(f"         4. Review liveness/readiness probe configuration")
            else:
                print(f"      ⚠️  Generic failure detected")
                print(f"      📊 Check logs and pod describe output for details")

    # Show event timeline for test pod
    test_pod_prefix = "test-memory-hog"
    test_pods = [p for p in pod_events.keys() if test_pod_prefix in p]

    if test_pods:
        print("\n" + "=" * 80)
        print("📊 EVENT TIMELINE FOR TEST POD")
        print("=" * 80)

        for test_pod in test_pods:
            events = sorted(pod_events[test_pod],
                          key=lambda x: x['timestamp'] if x['timestamp'] else '')

            print(f"\nPod: {test_pod}")
            print(f"Total events: {len(events)}")
            print("\nEvent sequence:")

            for i, evt in enumerate(events[-20:], 1):  # Show last 20 events
                emoji = "✅" if evt['type'] == 'Normal' else "❌"
                print(f"   {i:2d}. {emoji} [{evt['timestamp']}] {evt['reason']}: {evt['message'][:80]}")

if __name__ == "__main__":
    import sys

    kafka_brokers = sys.argv[1] if len(sys.argv) > 1 else 'localhost:9092'
    client_id = sys.argv[2] if len(sys.argv) > 2 else 'mn-01'

    analyze_pod_failures(kafka_brokers, client_id)
