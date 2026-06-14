from flask import Flask, g

from authorization_in_the_middle.flask_identity import (
    build_jwt_principal_entity,
    principal_cedar_attrs,
    resolve_jwt_principal,
)


def test_principal_cedar_attrs_maps_jwt_claims_and_tier1_flags():
    claims = {
        "sub": "user-uuid",
        "neosofia:actors": ["operator"],
        "neosofia:roles": ["admin"],
        "neosofia:tenant_type": "platform",
        "neosofia:tenant_uuid": "tenant-uuid",
        "neosofia:token_type": "human",
    }
    attrs = principal_cedar_attrs(
        claims,
        actor_classes=frozenset({"operator", "study", "clinician"}),
    )

    assert attrs["uuid"] == "user-uuid"
    assert attrs["tenantId"] == "tenant-uuid"
    assert attrs["tenantType"] == "platform"
    assert attrs["roles"] == ["admin"]
    assert attrs["tokenType"] == "human"
    assert attrs["actors"] == ["operator"]
    assert attrs["isOperator"] is True
    assert attrs["isClinician"] is False


def test_build_jwt_principal_entity_service_token():
    entity = build_jwt_principal_entity(
        "users",
        {"sub": "authentication", "neosofia:token_type": "service"},
    )

    assert entity["uid"]["__entity"]["type"] == "users::Service"
    assert entity["attrs"]["serviceSlug"] == "authentication"
    assert entity["attrs"]["tokenType"] == "service"


def test_resolve_jwt_principal_reads_flask_claims():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.jwt_claims = {
            "sub": "user-uuid",
            "neosofia:actors": ["clinician"],
            "neosofia:tenant_uuid": "tenant-uuid",
            "neosofia:token_type": "human",
        }
        entity = resolve_jwt_principal(
            "chat",
            actor_classes=frozenset({"clinician", "patient"}),
        )

    assert entity["uid"]["__entity"]["type"] == "chat::User"
    assert entity["attrs"]["isClinician"] is True
    assert entity["attrs"]["tenantId"] == "tenant-uuid"


def test_resolve_jwt_principal_merges_extra_attrs():
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.jwt_claims = {
            "sub": "user-uuid",
            "neosofia:token_type": "human",
        }
        entity = resolve_jwt_principal(
            "care_episode",
            extra_attrs={"demoTemplatePatientUuid": "template-uuid"},
        )

    assert entity["attrs"]["demoTemplatePatientUuid"] == "template-uuid"
    assert entity["attrs"]["uuid"] == "user-uuid"
