from flask import Flask, jsonify
from werkzeug.exceptions import BadRequest, NotFound

from authorization_in_the_middle import StubEvaluator, with_authorization


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