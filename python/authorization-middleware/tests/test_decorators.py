import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, NotFound

from authorization_in_the_middle import StubEvaluator, with_authorization
from authorization_in_the_middle.logging_context import set_authz_outcome_log_extra


def test_with_authorization_passes_context_to_evaluator():
    calls: list[dict] = []

    def decide(principal, action, resource, entities, context):
        calls.append(
            {
                "principal": principal,
                "action": action,
                "resource": resource,
                "entities": entities,
                "context": context,
            }
        )
        return True

    app = Flask(__name__)
    evaluator = StubEvaluator(decide_fn=decide)

    @app.get("/documents/<document_id>")
    @with_authorization(
        evaluator,
        principal_fn=lambda: 'demo::User::"u1"',
        action='Action::"document:read"',
        resource_fn=lambda: 'demo::Document::"d1"',
        entities_fn=lambda: [{"uid": {"__entity": {"type": "demo::User", "id": "u1"}}, "attrs": {}, "parents": []}],
        context_fn=lambda: {"request_id": "req-123"},
    )
    def get_document(document_id: str):
        return jsonify({"document_id": document_id})

    with app.test_client() as client:
        response = client.get("/documents/d1")

    assert response.status_code == 200
    assert calls == [
        {
            "principal": 'demo::User::"u1"',
            "action": 'Action::"document:read"',
            "resource": 'demo::Document::"d1"',
            "entities": [{"uid": {"__entity": {"type": "demo::User", "id": "u1"}}, "attrs": {}, "parents": []}],
            "context": {"request_id": "req-123"},
        }
    ]


def test_with_authorization_returns_400_for_bad_request_inputs():
    app = Flask(__name__)
    evaluator = StubEvaluator(decide_fn=lambda *args: True)

    @app.get("/documents/<document_id>")
    @with_authorization(
        evaluator,
        principal_fn=lambda: (_ for _ in ()).throw(BadRequest()),
        action='Action::"document:read"',
        resource_fn=lambda: 'demo::Document::"d1"',
    )
    def get_document(document_id: str):
        return jsonify({"document_id": document_id})

    with app.test_client() as client:
        response = client.get("/documents/d1")

    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_request"}


def test_with_authorization_returns_404_for_missing_resource_inputs():
    app = Flask(__name__)
    evaluator = StubEvaluator(decide_fn=lambda *args: True)

    @app.get("/documents/<document_id>")
    @with_authorization(
        evaluator,
        principal_fn=lambda: 'demo::User::"u1"',
        action='Action::"document:read"',
        resource_fn=lambda: (_ for _ in ()).throw(NotFound()),
    )
    def get_document(document_id: str):
        return jsonify({"document_id": document_id})

    with app.test_client() as client:
        response = client.get("/documents/d9")

    assert response.status_code == 404
    assert response.get_json() == {"error": "not_found"}


def test_with_authorization_returns_503_for_unexpected_evaluation_errors():
    app = Flask(__name__)
    evaluator = StubEvaluator(decide_fn=lambda *args: True)

    @app.get("/documents/<document_id>")
    @with_authorization(
        evaluator,
        principal_fn=lambda: (_ for _ in ()).throw(RuntimeError()),
        action='Action::"document:read"',
        resource_fn=lambda: 'demo::Document::"d1"',
    )
    def get_document(document_id: str):
        return jsonify({"document_id": document_id})

    with app.test_client() as client:
        response = client.get("/documents/d1")

    assert response.status_code == 503
    assert response.get_json() == {"error": "authorization_unavailable"}


def test_with_authorization_merges_outcome_log_extra_on_allow_and_deny():
    events: list[dict] = []

    def capture(event_type: str, **kwargs):
        events.append({"event_type": event_type, **kwargs})

    app = Flask(__name__)
    allow_evaluator = StubEvaluator(decide_fn=lambda *args: True)
    deny_evaluator = StubEvaluator(decide_fn=lambda *args: False)

    @app.get("/allowed")
    @with_authorization(
        allow_evaluator,
        principal_fn=lambda: 'demo::User::"u1"',
        action='Action::"document:read"',
        resource_fn=lambda: 'demo::Document::"d1"',
        log_event=capture,
    )
    def allowed_handler():
        return jsonify({"ok": True})

    @app.get("/denied")
    @with_authorization(
        deny_evaluator,
        principal_fn=lambda: 'demo::User::"u1"',
        action='Action::"document:read"',
        resource_fn=lambda: 'demo::Document::"d1"',
        log_event=capture,
    )
    def denied_handler():
        return jsonify({"ok": True})

    @app.before_request
    def stash_outcome_fields():
        if request.path == "/allowed":
            set_authz_outcome_log_extra(
                rate_limit="60 per minute",
                resource_name="Document",
                resource_id="d1",
                tenant_uuid="tenant-1",
                tenant_type="cro",
            )
        elif request.path == "/denied":
            set_authz_outcome_log_extra(
                rate_limit="30 per minute",
                resource_name="Document",
                resource_id="d1",
                tenant_uuid="tenant-2",
            )

    with app.test_client() as client:
        assert client.get("/allowed").status_code == 200
        assert client.get("/denied").status_code == 403

    assert events[0]["event_type"] == "authorization.allowed"
    assert events[0]["rate_limit"] == "60 per minute"
    assert events[0]["resource_name"] == "Document"
    assert events[0]["resource_id"] == "d1"
    assert events[0]["tenant_uuid"] == "tenant-1"
    assert events[0]["tenant_type"] == "cro"

    assert events[1]["event_type"] == "authorization.denied"
    assert events[1]["rate_limit"] == "30 per minute"
    assert events[1]["tenant_uuid"] == "tenant-2"
    assert events[1].get("tenant_type") is None


def test_with_security_does_not_emit_security_evaluation_started(monkeypatch):
    events: list[dict] = []
    principal_entity = {
        "uid": {"__entity": {"type": "demo::User", "id": "u1"}},
        "attrs": {"tenantId": "tenant-1", "tenantType": "cro"},
        "parents": [],
    }

    def capture(event_type: str, *, level: int = logging.INFO, **kwargs):
        events.append({"event_type": event_type, "level": level, **kwargs})

    from types import SimpleNamespace

    entities_mod = SimpleNamespace(
        resolve_principal=lambda: principal_entity,
        NAMESPACE="demo",
    )

    monkeypatch.setattr(
        "authorization_in_the_middle.security.log_request_event",
        capture,
    )
    monkeypatch.setattr(
        "authorization_in_the_middle.security._import_entities_module",
        lambda: entities_mod,
    )
    monkeypatch.setattr(
        "authorization_in_the_middle.security._resolve_principal",
        lambda _entities_mod: principal_entity,
    )
    monkeypatch.setattr(
        "authorization_in_the_middle.security.with_authentication",
        lambda **_kwargs: lambda handler: handler,
    )

    app = Flask(__name__)
    app.extensions["cedar_evaluator"] = StubEvaluator(decide_fn=lambda *args: True)

    from authorization_in_the_middle.security import with_security

    @app.get("/items")
    @with_security(
        action='Action::"item:list"',
        rate_limit="60 per minute",
        resource_fn=lambda: 'demo::ItemCatalog::"catalog"',
        entities_fn=lambda: [principal_entity],
        namespace="demo",
        catalog_id="catalog",
    )
    def list_items():
        return jsonify({"items": []})

    with app.test_client() as client:
        response = client.get("/items")

    assert response.status_code == 200
    assert [event for event in events if event["event_type"] == "security_evaluation_started"] == []

    allowed = [event for event in events if event["event_type"] == "authorization.allowed"]
    assert len(allowed) == 1
    assert allowed[0]["tenant_uuid"] == "tenant-1"
    assert allowed[0]["tenant_type"] == "cro"
    assert allowed[0]["rate_limit"] == "60 per minute"