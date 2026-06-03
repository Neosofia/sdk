import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from authentication_in_the_middle.actors import (
    configure_tier1_actor_classes,
    fetch_tier1_actor_classes,
    platform_actors_uri_from_jwks,
)
from flask import Flask


def test_platform_actors_uri_from_jwks():
    assert (
        platform_actors_uri_from_jwks("http://auth:8014/.well-known/jwks.json")
        == "http://auth:8014/.well-known/platform-actors.json"
    )


def test_fetch_tier1_actor_classes_from_well_known():
    payload = {"tier1_actors": ["operator", "study", "clinician", "patient"]}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/.well-known/platform-actors.json":
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        jwks_uri = f"http://127.0.0.1:{port}/.well-known/jwks.json"
        fetch_tier1_actor_classes.cache_clear()
        actors = fetch_tier1_actor_classes(jwks_uri)
        assert actors == frozenset(payload["tier1_actors"])
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_configure_tier1_actor_classes_uses_jwks_uri():
    payload = {"tier1_actors": ["operator", "patient"]}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        app = Flask(__name__)
        app.config["JWT_JWKS_URI"] = f"http://127.0.0.1:{port}/.well-known/jwks.json"
        fetch_tier1_actor_classes.cache_clear()
        configure_tier1_actor_classes(app)
        assert app.config["TIER1_ACTOR_CLASSES"] == frozenset({"operator", "patient"})
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_configure_tier1_actor_classes_respects_explicit_config():
    app = Flask(__name__)
    app.config["TIER1_ACTOR_CLASSES"] = frozenset({"clinician"})
    app.config["JWT_JWKS_URI"] = "http://unused/.well-known/jwks.json"
    configure_tier1_actor_classes(app)
    assert app.config["TIER1_ACTOR_CLASSES"] == frozenset({"clinician"})
