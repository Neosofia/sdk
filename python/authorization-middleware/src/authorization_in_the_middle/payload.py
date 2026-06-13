"""
Helpers for Cedar ``presentFields`` and shared-UID entity bundles.

``present_field_names`` supplies sorted JSON keys for field allowlists in Cedar
``when`` clauses (e.g. ``!resource.presentFields.contains("roles")``). Used with
REST write authz — values are assembled in the service, not copied from raw JSON.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def present_field_names(payload: dict[str, Any] | None) -> list[str]:
    """Sorted field names present in a request payload (Cedar Set of String)."""
    if not payload:
        return []
    return sorted(str(key) for key in payload.keys())


def canonical_string_set(values: Sequence[str] | None) -> list[str]:
    """Sorted unique non-empty strings for Cedar Set comparisons."""
    if not values:
        return []
    seen: set[str] = set()
    canonical: list[str] = []
    for raw in values:
        item = str(raw).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        canonical.append(item)
    return sorted(canonical)


def _proposed_field_values(
    write_record: dict[str, Any],
    resource: dict[str, Any],
    field: str,
) -> list[str]:
    proposed = write_record.get(field)
    if proposed is None:
        proposed = resource.get("attrs", {}).get(field)
    if not isinstance(proposed, list):
        return []
    return [str(item) for item in proposed]


def write_exact_set_field_attrs(
    write_record: dict[str, Any],
    resource: dict[str, Any],
    present_fields: Sequence[str],
    field: str,
    allowed: Sequence[str] | None = None,
    *,
    attr_name: str | None = None,
) -> dict[str, Any]:
    """
    Cedar exact-set helper for write payloads.

    When ``field`` is in ``present_fields``, derive ``{field}Exact`` (or ``attr_name``)
    with the canonical proposed set. When ``allowed`` is given, omit the attribute unless
    the proposed set equals ``allowed`` exactly (order-independent, no duplicates).

    Policy examples::

        resource.rolesExact == ["patient.self"]
        resource has rolesExact   // when ``allowed`` was passed at entity build time
    """
    if field not in present_fields:
        return {}
    canonical_proposed = canonical_string_set(_proposed_field_values(write_record, resource, field))
    cedar_name = attr_name or f"{field}Exact"
    if allowed is not None:
        canonical_allowed = canonical_string_set(allowed)
        if canonical_proposed != canonical_allowed:
            return {}
        return {cedar_name: canonical_allowed}
    if not canonical_proposed:
        return {}
    return {cedar_name: canonical_proposed}


def role_namespaces(roles: Sequence[str]) -> list[str]:
    """Sorted unique slug namespaces (``cro`` from ``cro.admin``) for Cedar ``roleNamespaces``."""
    seen: set[str] = set()
    namespaces: list[str] = []
    for raw in roles:
        slug = str(raw).strip()
        if not slug or "." not in slug:
            continue
        namespace = slug.split(".", 1)[0]
        if namespace not in seen:
            seen.add(namespace)
            namespaces.append(namespace)
    return sorted(namespaces)


def write_role_namespace_attrs(
    write_record: dict[str, Any],
    resource: dict[str, Any],
    present_fields: Sequence[str],
) -> dict[str, Any]:
    """``roleNamespaces`` when the client sent ``roles`` (mechanical; policy uses Set.contains)."""
    if "roles" not in present_fields:
        return {}
    proposed = write_record.get("roles") or resource.get("attrs", {}).get("roles") or []
    if not isinstance(proposed, list):
        return {}
    namespaces = role_namespaces(proposed)
    if not namespaces:
        return {}
    return {"roleNamespaces": namespaces}


def _entity_record_id(entity: dict[str, Any]) -> tuple[str, str]:
    ref = entity["uid"]["__entity"]
    return str(ref["type"]), str(ref["id"])


def align_shared_uid_entity_attrs(
    principal: dict[str, Any],
    resource: dict[str, Any],
    *,
    source: str = "principal",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    When principal and member share a Cedar UID, cedarpy requires identical attrs.

    ``source`` chooses which record supplies the canonical attribute map
    (``principal`` for reads, ``resource`` for planned writes).
    """
    if _entity_record_id(principal) != _entity_record_id(resource):
        return principal, resource
    pick = principal if source == "principal" else resource
    attrs = dict(pick.get("attrs") or {})
    return (
        {**principal, "attrs": attrs},
        {**resource, "attrs": attrs},
    )
