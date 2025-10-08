#!/usr/bin/env python3
"""
CrashLoop Test App - Crashes immediately after startup
Generates: CrashLoopBackOff events, ERROR logs
"""
import sys
import time

print("INFO: Starting crashloop test application...")
print("INFO: Initializing components...")
time.sleep(2)

print("ERROR: Critical initialization failure!")
print("ERROR: Unable to connect to non-existent database at db.example.com:5432")
print("FATAL: Application cannot continue, exiting with code 1")

sys.exit(1)
