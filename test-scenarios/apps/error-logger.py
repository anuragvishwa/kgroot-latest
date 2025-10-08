#!/usr/bin/env python3
"""
Error Logger Test App - Logs various error levels periodically
Generates: ERROR, WARNING, FATAL logs at different intervals
"""
import time
import random
import traceback

errors = [
    ("ERROR", "Database connection timeout after 30 seconds"),
    ("ERROR", "Failed to process message: InvalidFormat"),
    ("ERROR", "HTTP request failed with status 500"),
    ("WARNING", "Retry attempt 3/5 for operation xyz"),
    ("WARNING", "High memory usage detected: 85%"),
    ("WARNING", "Slow query detected: took 2.5s"),
    ("ERROR", "Unable to write to cache: connection refused"),
    ("FATAL", "Unhandled exception in main loop"),
    ("ERROR", "Authentication failed for user: invalid token"),
]

def simulate_exception():
    """Simulate a real exception with traceback"""
    try:
        result = 1 / 0
    except Exception as e:
        print(f"ERROR: Caught exception: {type(e).__name__}")
        print(f"ERROR: {traceback.format_exc()}")

print("INFO: Starting error-logger test application...")
print("INFO: Will generate various error logs periodically")

counter = 0
while True:
    time.sleep(random.uniform(5, 15))

    level, message = random.choice(errors)
    print(f"{level}: {message} (event #{counter})")

    # Occasionally generate exception with traceback
    if counter % 7 == 0:
        simulate_exception()

    counter += 1

    # Occasional info logs
    if counter % 3 == 0:
        print(f"INFO: Processed {counter} operations so far")
