"""Discover Neosofia service entity builders and write planners by convention."""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from authorization_in_the_middle.action_scope import _type_to_snake
from authorization_in_the_middle.entities import entity_uid
from authorization_in_the_middle.rest_defaults import (
    default_catalog_id,
    namespace_from_entities,
    synthesize_catalog_builder,
    synthesize_member_builder,
    synthesize_write_builder,
)
from authorization_in_the_middle.write_planners import default_plan_create_from_openapi


def _import_entities_module():
    try:
        return importlib.import_module("src.authorization.entities")
    except ImportError:
        return None


def _resolve_principal(entities_mod: Any) -> dict[str, Any]:
    if entities_mod is not None:
        if hasattr(entities_mod, "resolve_principal"):
            return entities_mod.resolve_principal()
        if hasattr(entities_mod, "load_principal_entity"):
            return entities_mod.load_principal_entity()
    raise ValueError(
        "src.authorization.entities must define resolve_principal() or load_principal_entity()"
    )


def _principal_uid(entities_mod: Any) -> str:
    entity = _resolve_principal(entities_mod)
    ref = entity["uid"]["__entity"]
    return entity_uid(ref["type"], ref["id"])


def _find_resource_builder(
    entities_mod: Any,
    model_mod: Any,
    model_name: str,
    builder_module_name: str,
    *,
    namespace: str | None = None,
    id_arg: str | None = None,
) -> Callable[[str, dict[str, Any] | None], dict[str, Any]]:
    candidates: list[tuple[Any, str]] = []
    if entities_mod is not None:
        candidates.extend(
            (
                (entities_mod, f"build_{model_name}_resource_entity"),
                (entities_mod, f"build_{builder_module_name}_resource_entity"),
            )
        )
    if model_mod is not None:
        candidates.extend(
            (
                (model_mod, f"build_{builder_module_name}_entity"),
                (model_mod, f"build_{model_name}_entity"),
            )
        )
    for mod, attr in candidates:
        if mod is not None and hasattr(mod, attr):
            return getattr(mod, attr)
    resolved_namespace = namespace or namespace_from_entities(
        entities_mod,
        model_name,
        builder_module_name,
    )
    return synthesize_member_builder(
        namespace=resolved_namespace,
        model_name=model_name,
        id_arg=id_arg,
        entities_mod=entities_mod,
    )


def _find_catalog_builder(
    entities_mod: Any,
    model_mod: Any,
    catalog_resource_type: str,
    *,
    namespace: str | None = None,
    model_name: str | None = None,
    verb: str = "list",
    catalog_id: str | None = None,
    catalog_id_from: str | None = None,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
) -> Callable[[], dict[str, Any]]:
    snake = _type_to_snake(catalog_resource_type)
    for mod in (entities_mod, model_mod):
        if mod is None:
            continue
        for attr in (f"build_{snake}_resource", f"build_{snake}_entity"):
            if hasattr(mod, attr):
                fn = getattr(mod, attr)
                return lambda fn=fn: fn()
    resolved_namespace = namespace
    if resolved_namespace is None and entities_mod is not None:
        resolved_namespace = getattr(entities_mod, "NAMESPACE", None)
    if resolved_namespace is None:
        raise AttributeError(f"No catalog builder found for '{catalog_resource_type}'")
    resolved_model = model_name or snake.replace("_catalog", "")
    resolved_catalog_id = default_catalog_id(
        resolved_model,
        verb,
        entities_mod,
        explicit=catalog_id,
        catalog_id_from=catalog_id_from,
    )
    return synthesize_catalog_builder(
        namespace=str(resolved_namespace),
        catalog_resource_type=catalog_resource_type,
        catalog_id=resolved_catalog_id,
        catalog_attrs=catalog_attrs,
    )


def _find_write_entity_builder(
    entities_mod: Any,
    model_name: str,
    *,
    namespace: str | None = None,
    id_arg: str | None = None,
    builder_module_name: str | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    if entities_mod is not None:
        for attr in (f"build_write_{model_name}_entity", f"build_planned_{model_name}_entity"):
            if hasattr(entities_mod, attr):
                return getattr(entities_mod, attr)
        resource_attr = f"build_{model_name}_resource_entity"
        if hasattr(entities_mod, resource_attr):
            build_resource = getattr(entities_mod, resource_attr)

            def _from_resource(record: dict[str, Any], fn=build_resource) -> dict[str, Any]:
                return fn(str(record.get("uuid") or ""), record)

            return _from_resource
    resolved_namespace = namespace
    if resolved_namespace is None and entities_mod is not None:
        resolved_namespace = getattr(entities_mod, "NAMESPACE", None)
    if resolved_namespace is None and builder_module_name:
        try:
            resolved_namespace = namespace_from_entities(
                entities_mod,
                model_name,
                builder_module_name,
            )
        except (ImportError, AttributeError, ValueError):
            return None
    if resolved_namespace is None:
        return None
    return synthesize_write_builder(
        namespace=resolved_namespace,
        model_name=model_name,
        id_arg=id_arg,
        entities_mod=entities_mod,
    )


def _find_write_plan_fn(builder_module_name: str, http_method: str) -> Callable[[], dict[str, Any]] | None:
    """Convention: ``src.services.{module}_service.plan_*_from_openapi`` for REST writes."""
    method = http_method.upper()
    candidates: list[str] = []
    if method == "POST":
        candidates.append("plan_create_from_openapi")
    elif method == "PATCH":
        candidates.extend(["plan_patch_from_openapi", "plan_update_from_openapi"])
    elif method == "PUT":
        candidates.extend(["plan_put_from_openapi", "plan_update_from_openapi"])
    try:
        service_mod = importlib.import_module(f"src.services.{builder_module_name}_service")
    except ImportError:
        return None
    for attr in candidates:
        fn = getattr(service_mod, attr, None)
        if callable(fn):
            return fn
    return None


def resolve_write_plan_fn(
    builder_module_name: str,
    http_method: str,
) -> Callable[[], dict[str, Any]] | None:
    """Service planner when present; otherwise SDK default for ``POST`` create only."""
    custom = _find_write_plan_fn(builder_module_name, http_method)
    if custom is not None:
        return custom
    if http_method.upper() == "POST":
        return default_plan_create_from_openapi
    return None
