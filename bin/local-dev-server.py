#!/usr/bin/env python3
"""Local backend runner for machines without Docker/Terraform/LocalStack.

Executes each backend service's actual `handler()` in-process, translating
plain HTTP requests into the Lambda Function URL payload-format-2.0 event
shape that backend/_shared/http.py expects, and translating the returned
{statusCode, headers, body} dict back into an HTTP response. It stands in
for the AWS Lambda / LocalStack layer only — every service's business logic
runs completely unmodified.

Usage:
    python bin/local-dev-server.py

Configure the database via the same env vars the Lambdas use in the cloud
(POSTGRES_HOST / _PORT / _USER / _PASS / _NAME); sensible localhost
defaults are set below for bin/local-dev-server.py's own throwaway Postgres
instance.
"""

import importlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
PORT = int(os.environ.get("LOCAL_BACKEND_PORT", "3001"))

os.environ.setdefault("IS_LOCAL", "true")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASS", "test")
os.environ.setdefault("POSTGRES_NAME", "test")


def discover_services():
    """Same convention infra/locals.tf uses: one level under backend/,
    a function.py present, folder name not prefixed with `_`."""
    services = {}
    for entry in BACKEND.iterdir():
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if (entry / "function.py").exists():
            services[entry.name] = entry
    return services


SERVICES = discover_services()

# Every service defines its own top-level `function`/`repository`/`schema`
# modules and imports the `_shared` package. Purging these from sys.modules
# on every service switch stops e.g. teams-service's `repository` module
# from leaking into a later projects-service request.
_PER_SERVICE_MODULES = ("function", "repository", "schema")

_loaded_service = None
_loaded_handler = None


def get_handler(service_name):
    """Import (or reuse) the given service's handler.

    Reusing the handler when consecutive requests hit the same service keeps
    that service's module-level Postgres connection (backend/_shared/db.py)
    warm, mirroring how a warm Lambda container behaves.
    """
    global _loaded_service, _loaded_handler

    if service_name == _loaded_service:
        return _loaded_handler

    service_dir = SERVICES[service_name]
    for name in list(sys.modules):
        if name in _PER_SERVICE_MODULES or name == "_shared" or name.startswith("_shared."):
            del sys.modules[name]

    sys.path.insert(0, str(service_dir))
    try:
        module = importlib.import_module("function")
    finally:
        sys.path.remove(str(service_dir))

    _loaded_service = service_name
    _loaded_handler = module.handler
    return _loaded_handler


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0: every response closes the connection. This server handles
    # one connection at a time (see main()); with HTTP/1.1 keep-alive, a
    # second concurrent request — e.g. React StrictMode double-invoking an
    # effect in dev — would open a second connection that sits unaccepted
    # forever while the first stays open waiting for a request that never
    # comes.
    protocol_version = "HTTP/1.0"

    def _handle(self):
        parts = urlsplit(self.path)
        segments = [s for s in parts.path.split("/") if s]

        if len(segments) < 2 or segments[0] != "api":
            self._send_json(200, {
                "message": "Local backend runner (bin/local-dev-server.py)",
                "usage": f"http://localhost:{PORT}/api/{{service-name}}/...",
                "available": sorted(SERVICES),
            })
            return

        service_name = segments[1]
        if service_name not in SERVICES:
            self._send_json(404, {"error": {
                "code": "unknown_service",
                "message": f"No such service: {service_name}",
                "details": {"available": sorted(SERVICES)},
            }})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) if length else b""

        event = {
            "version": "2.0",
            "rawPath": parts.path,
            "rawQueryString": parts.query,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "queryStringParameters": dict(parse_qsl(parts.query)) if parts.query else None,
            "requestContext": {"http": {"method": self.command}},
            "body": raw_body.decode("utf-8") if raw_body else None,
            "isBase64Encoded": False,
        }

        try:
            handler = get_handler(service_name)
            result = handler(event, {})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": {"code": "local_runner_error", "message": str(exc)}})
            return

        status = result.get("statusCode", 500)
        headers = result.get("headers") or {}
        body = (result.get("body") or "").encode("utf-8")

        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, status, obj):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = _handle


def main():
    if not SERVICES:
        raise SystemExit(f"No backend services found under {BACKEND}")
    print(f"Discovered services: {', '.join(sorted(SERVICES))}")
    print(
        f"POSTGRES_HOST={os.environ['POSTGRES_HOST']} "
        f"POSTGRES_PORT={os.environ['POSTGRES_PORT']} "
        f"POSTGRES_NAME={os.environ['POSTGRES_NAME']}"
    )
    print(f"Listening on http://localhost:{PORT}  (Ctrl+C to stop)")
    HTTPServer(("localhost", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
