#!/usr/bin/env python3
"""
Slow Startup Test App - Takes long to become ready
Generates: Readiness probe failures, warnings
"""
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    ready = False

    def do_GET(self):
        if self.path == '/healthz':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path == '/ready':
            if HealthHandler.ready:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Ready')
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'Not Ready')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress default logging

print("INFO: Starting slow-startup application...")
print("WARNING: This application takes 90 seconds to initialize")

# Start health check server in background
server = HTTPServer(('0.0.0.0', 8080), HealthHandler)

# Simulate slow initialization
for i in range(9):
    print(f"INFO: Initialization step {i+1}/9...")
    time.sleep(10)

print("INFO: Application is now ready!")
HealthHandler.ready = True

# Keep running
print("INFO: Serving health checks on port 8080")
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("INFO: Shutting down...")
