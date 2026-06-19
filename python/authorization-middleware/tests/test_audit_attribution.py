from flask import Flask, g

from authorization_in_the_middle.audit_attribution import (
    HUMAN_AUDIT_ACTOR_TYPE,
    SERVICE_AUDIT_ACTOR_TYPE,
    reject_client_audit_attribution,
    request_audit_actor,
)
import pytest
from werkzeug.exceptions import BadRequest


def test_request_audit_actor_human_token():
    app = Flask(__name__)
    with app.test_request_context():
        g.jwt_claims = {
            "sub": "user-uuid",
            "neosofia:token_type": "human",
            "neosofia:tenant_uuid": "tenant-uuid",
        }
        actor = request_audit_actor()

    assert actor.uuid == "user-uuid"
    assert actor.type == HUMAN_AUDIT_ACTOR_TYPE


def test_request_audit_actor_service_token():
    app = Flask(__name__)
    service_uuid = "00000000-0000-7000-8000-000000000099"
    with app.test_request_context():
        g.jwt_claims = {
            "sub": "care-episode",
            "neosofia:token_type": "service",
            "neosofia:service_uuid": service_uuid,
        }
        actor = request_audit_actor()

    assert actor.uuid == service_uuid
    assert actor.type == SERVICE_AUDIT_ACTOR_TYPE


def test_request_audit_actor_service_token_missing_uuid():
    app = Flask(__name__)
    with app.test_request_context():
        g.jwt_claims = {
            "sub": "care-episode",
            "neosofia:token_type": "service",
        }
        with pytest.raises(BadRequest, match="service uuid"):
            request_audit_actor()


def test_reject_client_audit_attribution():
    with pytest.raises(BadRequest, match="changed_by_uuid"):
        reject_client_audit_attribution({"changed_by_uuid": "forged"})


def test_reject_client_audit_attribution_allows_clean_payload():
    reject_client_audit_attribution({"status": "closed"})
