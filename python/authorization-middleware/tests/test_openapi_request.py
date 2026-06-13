"""OpenAPI request parsing and validation."""

import json
from pathlib import Path

import pytest

from flask import Flask

from authorization_in_the_middle.openapi_request import (
    bind_openapi_spec,
    flask_rule_to_openapi_path,
    load_openapi_spec,
    operation_for_request,
    request_body_schema,
    reset_openapi_spec_cache,
    resolve_openapi_spec,
    validate_request_body,
)

pytestmark = pytest.mark.unit

_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "test", "version": "0.0.0"},
    "paths": {
        "/api/v1/users": {
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "first_name": {"type": "string"},
                                    "email": {"type": "string"},
                                },
                                "required": ["first_name", "email"],
                                "additionalProperties": False,
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}


def test_flask_rule_to_openapi_path():
    assert flask_rule_to_openapi_path("/api/v1/users/<user_uuid>") == "/api/v1/users/{user_uuid}"


def test_validate_request_body_rejects_extra_fields():
    operation = operation_for_request(_SPEC, rule="/api/v1/users", method="post")
    schema = request_body_schema(operation)
    with pytest.raises(ValueError, match="roles"):
        validate_request_body(
            {"first_name": "A", "email": "a@b.com", "roles": ["x"]},
            schema,
            _SPEC,
        )


def test_load_openapi_spec_from_fixture(tmp_path: Path):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    loaded = load_openapi_spec(path)
    assert loaded["openapi"] == "3.0.3"


def test_bind_openapi_spec_caches_at_startup(tmp_path: Path):
    reset_openapi_spec_cache()
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    app = Flask(__name__)
    app.config["OPENAPI_SPEC_PATH"] = str(path)
    bound = bind_openapi_spec(app)
    assert bound["openapi"] == "3.0.3"
    assert resolve_openapi_spec() is bound
    reset_openapi_spec_cache()


def test_resolve_openapi_spec_requires_startup_bind():
    reset_openapi_spec_cache()
    with pytest.raises(RuntimeError, match="bind_openapi_spec"):
        resolve_openapi_spec()
    reset_openapi_spec_cache()
