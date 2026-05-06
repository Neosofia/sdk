from typing import Any

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
