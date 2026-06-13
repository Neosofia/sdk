from collections.abc import Callable
from typing import Any

# Cedar entity id / OpenAPI default before a real id is assigned on create.
ID_PLACEHOLDER = "proposed"


def is_id_placeholder(value: object) -> bool:
    return value is not None and str(value) == ID_PLACEHOLDER


def resolve_entity_id(
    record: dict[str, Any],
    field: str = "uuid",
    fallback: str | None = None,
) -> str:
    """Entity id from a planned record; ``ID_PLACEHOLDER`` when not yet assigned."""
    raw = record.get(field)
    if raw is None:
        return str(fallback or ID_PLACEHOLDER)
    text = str(raw)
    if is_id_placeholder(text):
        return ID_PLACEHOLDER
    return text


def entity_uid(type_name: str, entity_id: str) -> str:
    """
    Format an entity UID as a Cedar string for principal/action/resource arguments.
    Example: entity_uid("demo::Patient", "p1") -> 'demo::Patient::"p1"'
    """
    return f'{type_name}::"{entity_id}"'

def build_entity_payload(type_name: str, entity_id: str, attrs: dict[str, Any] | None = None, parents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """
    Build the standard Cedar JSON entity payload shape expected by the evaluator.
    """
    return {
        "uid": {"__entity": {"type": type_name, "id": entity_id}},
        "attrs": attrs or {},
        "parents": parents or [],
    }

def build_entity_ref(type_name: str, entity_id: str) -> dict[str, dict[str, str]]:
    """
    Build the standard Cedar JSON entity reference for attributes that point to other entities.
    """
    return {"__entity": {"type": type_name, "id": entity_id}}


def build_catalog_entity(
    namespace: str,
    cedar_type: str,
    catalog_id: str,
    attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Cedar **Catalog** entity for list/create or singleton catalog reads."""
    return build_entity_payload(f"{namespace}::{cedar_type}", catalog_id, attrs or {})


def catalog_resource_uid(namespace: str, cedar_type: str, catalog_id: str) -> str:
    """Cedar resource UID for a catalog entity (``Action`` resource argument)."""
    return entity_uid(f"{namespace}::{cedar_type}", catalog_id)


def catalog_entities(
    resolve_principal: Callable[[], dict[str, Any]],
    build_catalog: Callable[[], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Principal + catalog entity pair for ``entities_fn`` on catalog-scoped routes."""
    return [resolve_principal(), build_catalog()]
