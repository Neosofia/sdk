from flask import Flask, g, request

from authorization_in_the_middle.flask_identity import (
    extract_jwt_principal_entity,
    jwt_claim_principal_attributes,
    request_scoped_uuid,
)


def test_extract_jwt_principal_entity_maps_actors_and_roles():
    app = Flask(__name__)
    with app.app_context():
        g.jwt_claims = {
            "sub": "user-uuid",
            "neosofia:actors": ["operator"],
            "neosofia:roles": ["admin"],
            "neosofia:tenant_type": "platform",
            "neosofia:token_type": "human",
        }
        entity = extract_jwt_principal_entity("demo", default_type="User")

    assert entity["uid"]["__entity"]["id"] == "user-uuid"
    assert entity["attrs"]["uuid"] == "user-uuid"
    assert entity["attrs"]["actors"] == ["operator"]
    assert entity["attrs"]["roles"] == ["admin"]
    assert entity["attrs"]["tenantType"] == "platform"


def test_jwt_claim_principal_attributes_sets_uuid_without_flask():
    sub, ptype, attrs = jwt_claim_principal_attributes(
        {
            "sub": "user-uuid",
            "neosofia:token_type": "human",
            "neosofia:tenant_uuid": "tenant-uuid",
        }
    )

    assert sub == "user-uuid"
    assert ptype == "User"
    assert attrs["uuid"] == "user-uuid"
    assert attrs["tenantId"] == "tenant-uuid"


def test_extract_jwt_principal_entity_omits_uuid_for_service_tokens():
    app = Flask(__name__)
    with app.app_context():
        g.jwt_claims = {
            "sub": "chat",
            "neosofia:token_type": "service",
        }
        entity = extract_jwt_principal_entity("demo", default_type="User")

    assert entity["uid"]["__entity"]["id"] == "chat"
    assert "uuid" not in entity["attrs"]


def test_request_scoped_uuid_prefers_path_over_query():
    app = Flask(__name__)
    with app.test_request_context("/users/path-uuid/interactions?user_uuid=query-uuid"):
        g.jwt_claims = {
            "sub": "self-uuid",
            "neosofia:actors": ["clinician"],
            "neosofia:token_type": "human",
        }
        request.view_args = {"user_uuid": "path-uuid"}
        assert request_scoped_uuid("user_uuid") == "path-uuid"


def test_request_scoped_uuid_prefers_query_param():
    app = Flask(__name__)
    with app.test_request_context("/?user_uuid=explicit-uuid"):
        g.jwt_claims = {
            "sub": "self-uuid",
            "neosofia:actors": ["patient"],
            "neosofia:token_type": "human",
        }
        assert request_scoped_uuid("user_uuid") == "explicit-uuid"


def test_request_scoped_uuid_prefers_body_over_self_scope():
    app = Flask(__name__)
    with app.test_request_context(
        "/",
        method="POST",
        json={"user_uuid": "body-uuid"},
    ):
        g.jwt_claims = {
            "sub": "self-uuid",
            "neosofia:actors": ["patient"],
            "neosofia:token_type": "human",
        }
        assert request_scoped_uuid("user_uuid") == "body-uuid"


def test_request_scoped_uuid_self_scopes_when_configured():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.jwt_claims = {
            "sub": "self-uuid",
            "neosofia:actors": ["patient"],
            "neosofia:token_type": "human",
        }
        assert request_scoped_uuid("user_uuid", self_for_actors=("patient",)) == "self-uuid"


def test_request_scoped_uuid_requires_explicit_for_clinician():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.jwt_claims = {
            "sub": "clinician-uuid",
            "neosofia:actors": ["clinician"],
            "neosofia:token_type": "human",
        }
        assert request_scoped_uuid("user_uuid") == ""


def test_request_scoped_uuid_disables_self_scope_when_empty_actors():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.jwt_claims = {
            "sub": "self-uuid",
            "neosofia:actors": ["patient"],
            "neosofia:token_type": "human",
        }
        assert request_scoped_uuid("user_uuid", self_for_actors=()) == ""
