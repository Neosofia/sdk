from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import g, has_request_context
from werkzeug.exceptions import BadRequest

from authorization_in_the_middle.flask_identity import (
    _jwt_token_type,
    jwt_claim_principal_attributes,
)

HUMAN_AUDIT_ACTOR_TYPE = 1
SERVICE_AUDIT_ACTOR_TYPE = 2

CLIENT_AUDIT_ATTRIBUTION_FIELDS = frozenset({"changed_by_uuid", "changed_by_type"})


@dataclass(frozen=True, slots=True)
class AuditActor:
    uuid: str
    type: int


def reject_client_audit_attribution(payload: dict[str, Any] | None) -> None:
    """Reject forged audit attribution supplied by API consumers."""
    if not isinstance(payload, dict):
        return
    forbidden = CLIENT_AUDIT_ATTRIBUTION_FIELDS & payload.keys()
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise BadRequest(f"client-supplied audit attribution is not permitted: {names}")


def request_audit_actor(*, claims: dict[str, Any] | None = None) -> AuditActor:
    """Derive audit actor UUID and type from the authenticated platform JWT."""
    if claims is None:
        if not has_request_context():
            raise BadRequest("No request context for audit actor")
        claims = getattr(g, "jwt_claims", None) or {}
    if not claims.get("sub"):
        raise BadRequest("No JWT claims available for audit actor")

    sub, _, attrs = jwt_claim_principal_attributes(claims)
    token_type = _jwt_token_type(attrs, claims)

    if token_type == "service":
        service_uuid = str(
            attrs.get("serviceUuid")
            or attrs.get("service_uuid")
            or ""
        ).strip()
        if not service_uuid:
            raise BadRequest("Service token missing service uuid for audit attribution")
        return AuditActor(uuid=service_uuid, type=SERVICE_AUDIT_ACTOR_TYPE)

    actor_uuid = str(attrs.get("uuid") or sub).strip()
    if not actor_uuid:
        raise BadRequest("Human token missing principal uuid for audit attribution")
    return AuditActor(uuid=actor_uuid, type=HUMAN_AUDIT_ACTOR_TYPE)
