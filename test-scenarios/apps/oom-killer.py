#!/usr/bin/env python3
"""
OOM Killer Test App - Allocates excessive memory
Generates: OOMKilled events, memory pressure
"""
import time

print("INFO: Starting OOM test application...")
print("INFO: Application initialized successfully")

# Allocate memory in chunks
memory_hog = []
chunk_size = 10 * 1024 * 1024  # 10MB chunks

try:
    for i in range(1000):
        print(f"INFO: Allocating memory chunk {i+1} (approx {(i+1)*10}MB total)")
        memory_hog.append(' ' * chunk_size)
        time.sleep(0.5)
except MemoryError:
    print("ERROR: MemoryError caught!")
    print("FATAL: Out of memory, terminating")
    time.sleep(1)
