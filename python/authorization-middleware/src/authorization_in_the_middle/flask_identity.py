import os
from collections.abc import Sequence
from typing import Any, Optional

from flask import current_app, g, request
from werkzeug.exceptions import BadRequest

from authorization_in_the_middle.cedar_attrs import tier1_actor_flags
from authorization_in_the_middle.entities import build_entity_payload, entity_uid

_CEDAR_ATTR_ALIASES = {
    "tenant_type": "tenantType",
    "tenant_uuid": "tenantId",
    "session_actors": "sessionActors",
    "service_uuid": "serviceUuid",
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


def _jwt_token_type(jwt_attrs: dict[str, Any], claims: dict[str, Any]) -> str:
    return str(
        jwt_attrs.get("tokenType")
        or jwt_attrs.get("token_type")
        or claims.get("token_type")
        or "human"
    )


def _normalize_roles(jwt_attrs: dict[str, Any]) -> list[str]:
    jwt_roles = jwt_attrs.get("roles")
    if not isinstance(jwt_roles, list):
        return []
    return [str(role) for role in jwt_roles if str(role).strip()]


def _resolve_actor_classes(actor_classes: frozenset[str] | None) -> frozenset[str]:
    if actor_classes is not None:
        return actor_classes
    try:
        from authentication_in_the_middle.actors import ensure_tier1_actor_classes
        from flask import has_app_context

        if has_app_context():
            return ensure_tier1_actor_classes(current_app)
    except ImportError:
        pass
    return frozenset()


def principal_cedar_attrs(
    claims: dict[str, Any],
    *,
    actor_classes: frozenset[str] | None = None,
    default_type: str = "User",
) -> dict[str, Any]:
    """Map platform JWT claims to Cedar principal attrs for policy evaluation."""
    _, _, jwt_attrs = jwt_claim_principal_attributes(claims, default_type=default_type)
    actors = jwt_attrs.get("actors")
    jwt_actors = actors if isinstance(actors, list) else []
    attrs: dict[str, Any] = {
        "uuid": str(jwt_attrs.get("uuid") or claims.get("sub", "")),
        "tenantId": str(jwt_attrs.get("tenantId") or ""),
        "tenantType": str(jwt_attrs.get("tenantType") or ""),
        "roles": _normalize_roles(jwt_attrs),
        "tokenType": _jwt_token_type(jwt_attrs, claims),
    }
    if jwt_actors:
        attrs["actors"] = list(jwt_actors)
    resolved_classes = _resolve_actor_classes(actor_classes)
    if resolved_classes:
        attrs.update(tier1_actor_flags(jwt_actors, resolved_classes))
    return attrs


def build_service_principal_entity(
    namespace: str,
    service_slug: str,
    claims: dict[str, Any],
) -> dict[str, Any]:
    _, _, jwt_attrs = jwt_claim_principal_attributes(claims)
    return build_entity_payload(
        f"{namespace}::Service",
        service_slug,
        {
            "serviceSlug": service_slug,
            "tokenType": _jwt_token_type(jwt_attrs, claims),
        },
    )


def build_jwt_principal_entity(
    namespace: str,
    claims: dict[str, Any],
    *,
    actor_classes: frozenset[str] | None = None,
    default_type: str = "User",
) -> dict[str, Any]:
    """Build a Cedar principal entity from platform JWT claims."""
    sub, ptype, jwt_attrs = jwt_claim_principal_attributes(claims, default_type=default_type)
    if _jwt_token_type(jwt_attrs, claims) == "service":
        return build_service_principal_entity(namespace, sub, claims)
    return build_entity_payload(
        f"{namespace}::{ptype}",
        sub,
        principal_cedar_attrs(
            claims,
            actor_classes=actor_classes,
            default_type=default_type,
        ),
    )


def resolve_jwt_principal(
    namespace: str,
    *,
    actor_classes: frozenset[str] | None = None,
    default_type: str = "User",
    require_claims: bool = False,
    extra_attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Cedar principal entity from ``g.jwt_claims`` (standard service pattern)."""
    claims = getattr(g, "jwt_claims", None)
    if require_claims and not claims:
        raise BadRequest("No JWT claims available on request context")
    entity = build_jwt_principal_entity(
        namespace,
        claims or {},
        actor_classes=actor_classes,
        default_type=default_type,
    )
    if extra_attrs:
        attrs = dict(entity.get("attrs") or {})
        attrs.update(extra_attrs)
        entity = {**entity, "attrs": attrs}
    return entity


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
    Parses g.jwt_claims to construct the principal's Cedar entity model payload.

    Prefer ``resolve_jwt_principal()`` in service ``entities`` modules; this helper
    remains for callers that already pass an explicit namespace at the call site.
    """
    claims = getattr(g, "jwt_claims", None)
    if not claims:
        raise BadRequest("No JWT claims available on request context")

    return build_jwt_principal_entity(
        _get_namespace(namespace),
        claims,
        default_type=default_type,
    )


def request_scoped_uuid(
    param_name: str,
    *,
    self_for_actors: Sequence[str] = (),
) -> str:
    """Resolve a subject UUID from the request or the authenticated principal.

    Resolution order: Flask path args, query string, JSON body, then principal
    ``uuid`` when any ``self_for_actors`` entry is on JWT actors. By default
    self-scope is disabled; pass actor names (e.g. ``("patient",)``) when the
  service policy allows implicit self binding.
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
