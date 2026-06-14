"""Synthesize standard REST Cedar entity builders when services omit named hooks."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from authorization_in_the_middle.action_scope import _catalog_id, _pascal_case, _type_to_snake
from authorization_in_the_middle.entities import (
    build_catalog_entity,
    build_entity_payload,
    resolve_entity_id,
)


def _resolve_catalog_attrs(
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None,
) -> dict[str, Any]:
    if catalog_attrs is None:
        return {}
    if callable(catalog_attrs):
        resolved = catalog_attrs()
        return dict(resolved) if isinstance(resolved, dict) else {}
    return dict(catalog_attrs)


def find_member_attrs(
    entities_mod: Any,
    model_name: str,
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Discover ``member_attrs`` / ``registry_{model}_cedar_attrs`` on entities."""
    if entities_mod is None:
        return None
    for name in (
        "member_attrs",
        f"{model_name}_attrs",
        f"registry_{model_name}_cedar_attrs",
    ):
        fn = getattr(entities_mod, name, None)
        if callable(fn):
            return fn
    return None


def member_id_field(entities_mod: Any, model_name: str, id_arg: str | None) -> str:
    """Row key for member entity id (``uuid``, ``slug``, ``tenant_uuid``, …)."""
    if entities_mod is not None:
        field = getattr(entities_mod, "MEMBER_ID_FIELD", None)
        if isinstance(field, str) and field.strip():
            return field.strip()
        per_model = getattr(entities_mod, f"{model_name.upper()}_ID_FIELD", None)
        if isinstance(per_model, str) and per_model.strip():
            return per_model.strip()
    if id_arg:
        return id_arg
    return "uuid"


def synthesize_catalog_builder(
    *,
    namespace: str,
    catalog_resource_type: str,
    catalog_id: str,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
) -> Callable[[], dict[str, Any]]:
    def build() -> dict[str, Any]:
        return build_catalog_entity(
            namespace,
            catalog_resource_type,
            catalog_id,
            _resolve_catalog_attrs(catalog_attrs),
        )

    return build


def synthesize_member_builder(
    *,
    namespace: str,
    model_name: str,
    id_arg: str | None,
    entities_mod: Any,
) -> Callable[[str, dict[str, Any] | None], dict[str, Any]]:
    pascal = _pascal_case(model_name)
    cedar_type = f"{namespace}::{pascal}"
    attrs_fn = find_member_attrs(entities_mod, model_name)
    id_field = member_id_field(entities_mod, model_name, id_arg)

    def build(resource_id: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(row or {})
        if id_field not in merged:
            merged[id_field] = resource_id
        entity_id = str(merged.get(id_field) or merged.get("uuid") or resource_id)
        if attrs_fn is not None:
            attrs = attrs_fn(merged)
        else:
            attrs = {id_field: entity_id}
        return build_entity_payload(cedar_type, entity_id, attrs)

    return build


def synthesize_write_builder(
    *,
    namespace: str,
    model_name: str,
    id_arg: str | None,
    entities_mod: Any,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    member_builder = synthesize_member_builder(
        namespace=namespace,
        model_name=model_name,
        id_arg=id_arg,
        entities_mod=entities_mod,
    )
    id_field = member_id_field(entities_mod, model_name, id_arg)

    def build(record: dict[str, Any]) -> dict[str, Any]:
        entity_id = resolve_entity_id(record, id_field)
        row = {**record, id_field: entity_id}
        if "uuid" not in row and id_field == "uuid":
            row["uuid"] = entity_id
        return member_builder(entity_id, row)

    return build


def default_catalog_id(
    model_name: str,
    verb: str,
    entities_mod: Any,
    *,
    explicit: str | None = None,
    catalog_id_from: str | None = None,
) -> str:
    if explicit is not None:
        return explicit
    if catalog_id_from:
        from authorization_in_the_middle.flask_request import request_view_arg

        return str(request_view_arg(catalog_id_from))
    return _catalog_id(model_name, verb, entities_mod, None)


def namespace_from_entities(entities_mod: Any, model_name: str, builder_module_name: str) -> str:
    if entities_mod is not None and hasattr(entities_mod, "NAMESPACE"):
        return str(entities_mod.NAMESPACE)
    try:
        model_mod = importlib.import_module(f"src.models.{builder_module_name}")
    except ImportError as exc:
        raise ValueError(
            f"Could not infer Cedar namespace for '{model_name}'. "
            f"Set NAMESPACE on src.authorization.entities."
        ) from exc
    namespace = getattr(model_mod, "NAMESPACE", None)
    if namespace is None:
        raise ValueError(
            f"Could not infer Cedar namespace for '{model_name}'. "
            f"Set NAMESPACE on src.authorization.entities."
        )
    return str(namespace)
