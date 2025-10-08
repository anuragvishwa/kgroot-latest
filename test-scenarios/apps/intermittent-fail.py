#!/usr/bin/env python3
"""
Intermittent Failure Test App - Works sometimes, fails randomly
Generates: Mixed ERROR and INFO logs, occasional crashes
"""
import time
import random
import sys

print("INFO: Starting intermittent-failure test application...")
print("INFO: This app randomly fails to simulate real-world issues")

failure_count = 0
success_count = 0
max_failures = 3

while True:
    time.sleep(random.uniform(10, 30))

    # 30% chance of failure
    if random.random() < 0.3:
        failure_count += 1
        print(f"ERROR: Operation failed! (failure #{failure_count})")
        print(f"ERROR: Unable to process request: connection timeout")

        if failure_count >= max_failures:
            print("FATAL: Too many consecutive failures, giving up!")
            print("FATAL: Application cannot recover, exiting...")
            sys.exit(1)
    else:
        success_count += 1
        failure_count = max(0, failure_count - 1)  # Recover one failure
        print(f"INFO: Operation completed successfully (success #{success_count})")

    if success_count % 5 == 0 and success_count > 0:
        print(f"INFO: Health check: {success_count} successful operations")
