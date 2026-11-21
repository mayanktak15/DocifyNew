"""Production request metrics, omitting identifiers, bodies and query parameters."""
from datetime import datetime, timezone
import json
from time import monotonic
from flask import g, request


def configure(app):
    @app.before_request
    def start_timer():
        g.request_started = monotonic()

    @app.after_request
    def log_response(response):
        print(json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'endpoint': request.endpoint, 'status': response.status_code,
            'method': request.method,
            'duration_ms': round((monotonic() - g.request_started) * 1000, 2)
            if 'request_started' in g else None,
        }), flush=True)
        return response
