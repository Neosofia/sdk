import os
from collections.abc import Sequence
from typing import Any, Optional

from flask import current_app, g, request
from werkzeug.exceptions import BadRequest

from authorization_in_the_middle.entities import build_entity_payload, entity_uid

_CEDAR_ATTR_ALIASES = {
    "tenant_type": "tenantType",
    "tenant_uuid": "tenantId",
    "session_actors": "sessionActors",
}


def _get_namespace(namespace: Optional[str] = None) -> str:
    if namespace:
        return namespace
    if current_app and "CEDAR_NAMESPACE" in current_app.config:
        return current_app.config["CEDAR_NAMESPACE"]
    return os.environ.get("CEDAR_NAMESPACE", "cdp")


def jwt_claim_principal_attributes(
    claims: dict[str, Any],
    *,
    default_type: str = "User",
) -> tuple[str, str, dict[str, Any]]:
    """Map platform JWT claims to Cedar principal attrs (``sub``, type, attrs)."""
    sub = str(claims.get("sub", ""))
    ptype = str(claims.get("neosofia:principal_type", default_type))
    attributes: dict[str, Any] = {}
    for key, value in claims.items():
        if key.startswith("neosofia:"):
            attr_name = key.replace("neosofia:", "")
            if attr_name == "principal_type":
                continue
            cedar_name = _CEDAR_ATTR_ALIASES.get(attr_name, attr_name)
            attributes[cedar_name] = value

    token_type = attributes.get("token_type")
    if ptype == "User" and token_type != "service":
        attributes.setdefault("uuid", sub)

    return sub, ptype, attributes


def extract_jwt_principal_uid(namespace: Optional[str] = None, default_type: str = "User") -> str:
    """
    Extracts the Cedar principal UID from g.jwt_claims.
    Must be used in conjunction with the authentication-in-the-middle @with_authentication decorator.
    """
    claims = getattr(g, "jwt_claims", None)
    if not claims:
        raise BadRequest("No JWT claims available on request context")

    sub, ptype, _ = jwt_claim_principal_attributes(claims, default_type=default_type)
    resolved_namespace = _get_namespace(namespace)

    return entity_uid(f"{resolved_namespace}::{ptype}", sub)


def extract_jwt_principal_entity(namespace: Optional[str] = None, default_type: str = "User") -> dict[str, Any]:
    """
    Parses g.jwt_claims to construct the principal's Cedar entity model payload flexibly.
    Must be used in conjunction with the authentication-in-the-middle @with_authentication decorator.

    Maps ``neosofia:actors`` → ``actors`` (Tier-1, narrowed by ``X-Active-Actor``) and
    ``neosofia:roles`` → ``roles`` (Tier-2 short names within ``tenant_type``).
    User principals also get ``uuid`` from ``sub`` unless ``token_type`` is ``service``.
    """
    claims = getattr(g, "jwt_claims", None)
    if not claims:
        raise BadRequest("No JWT claims available on request context")

    sub, ptype, attributes = jwt_claim_principal_attributes(claims, default_type=default_type)
    resolved_namespace = _get_namespace(namespace)
    return build_entity_payload(f"{resolved_namespace}::{ptype}", sub, attributes)


def request_scoped_uuid(
    param_name: str,
    *,
    self_for_actors: Sequence[str] = ("patient",),
) -> str:
    """Resolve a subject UUID from the request or the authenticated principal.

    Resolution order: Flask path args, query string, JSON body, then principal
    ``uuid`` when any ``self_for_actors`` entry is on JWT actors (default: patient
    self-scope). Pass ``self_for_actors=()`` to require an explicit request value.
    Intended for ``build_*_catalog_resource`` scoping in Cedar policies.
    """
    view_args = request.view_args or {}
    if param_name in view_args:
        path_value = str(view_args[param_name]).strip()
        if path_value:
            return path_value

    body = request.get_json(silent=True) or {}
    explicit = str(request.args.get(param_name) or body.get(param_name) or "").strip()
    if explicit:
        return explicit

    if not self_for_actors:
        return ""

    claims = getattr(g, "jwt_claims", None) or {}
    _, _, attrs = jwt_claim_principal_attributes(claims)
    actors = attrs.get("actors", [])
    if not isinstance(actors, list):
        return ""
    if any(actor in actors for actor in self_for_actors):
        return str(attrs.get("uuid", "")).strip()
    return ""
