"""Map Cedar Actions to Catalog vs Member scope, types, and resource UIDs."""
from __future__ import annotations

import re
from typing import Any

from flask import has_request_context, request

from authorization_in_the_middle.entities import entity_uid
from authorization_in_the_middle.flask_request import request_view_arg
from authorization_in_the_middle.route_inference import infer_id_arg

_CATALOG_COLLECTION_VERBS = frozenset({"list", "create"})


def _action_parts(action: str) -> tuple[str, str]:
    action_key = action[len('Action::"'):-1] if action.startswith('Action::"') else action
    model_name, verb = action_key.split(":", 1)
    return model_name.replace("-", "_").lower(), verb.lower()


def _pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _catalog_constant_name(model_name: str) -> str:
    if model_name.endswith("_catalog"):
        return f"{model_name.upper()}_ID"
    return f"{model_name.upper()}_CATALOG_ID"


def _is_catalog_collection(verb: str) -> bool:
    """``user:list`` / ``user:create`` — README collection verbs."""
    return verb in _CATALOG_COLLECTION_VERBS


def _is_catalog_singleton(model_name: str, verb: str) -> bool:
    """``role_catalog:read`` on a fixed catalog id."""
    return verb == "read" and model_name.endswith("_catalog")


def _resolve_id_arg(id_arg: str | None, model_name: str) -> str:
    """Member path param: explicit ``id_arg`` → route rule → ``{model}_uuid`` fallback."""
    if id_arg:
        return id_arg
    inferred = infer_id_arg() if has_request_context() else None
    if inferred:
        return inferred
    return f"{model_name}_uuid"


def _uses_catalog_scope(model_name: str, verb: str, id_arg: str | None) -> bool:
    """True when the Cedar **Resource** is a **Catalog**, not a **Member**.

    - ``list`` / ``create`` → Catalog (e.g. ``GET /api/services`` → ``ServiceCatalog``)
    - ``audit:list`` (and similar) with no member id in the path → Catalog
      (e.g. ``GET /api/services/audits`` — ``audits`` is not an id)
    - Same action with a member id present → Member (e.g. ``GET .../<slug>/audits``)
    """
    if _is_catalog_collection(verb) or _is_catalog_singleton(model_name, verb):
        return True
    if not has_request_context():
        return False
    member_arg = _resolve_id_arg(id_arg, model_name)
    view_args = request.view_args or {}
    return member_arg not in view_args and ":list" in verb


def _scope_resource_name(
    model_name: str,
    verb: str,
    resource_type: str | None,
    *,
    catalog: bool,
) -> str:
    """Cedar **Resource** type name: ``UserCatalog`` (Catalog) or ``User`` (Member)."""
    if catalog:
        catalog_verb = verb if _is_catalog_collection(verb) else "list"
        return resource_type or _catalog_resource_type(model_name, catalog_verb)
    return _item_resource_type(model_name, resource_type)


def _catalog_resource_type(model_name: str, verb: str) -> str:
    base = _pascal_case(model_name)
    if not _is_catalog_collection(verb):
        return base
    if model_name.endswith("_catalog"):
        return base
    if "_" not in model_name:
        return f"{_pascal_case(model_name.split('_')[0])}Catalog"
    return f"{base}Catalog"


def _item_resource_type(model_name: str, resource_type: str | None) -> str:
    if resource_type:
        return resource_type
    return _pascal_case(model_name)


def _resource_uid_from_view_arg(
    namespace: str,
    resource_name: str,
    id_arg: str,
) -> str:
    resource_id = request_view_arg(id_arg)
    return entity_uid(f"{namespace}::{resource_name}", resource_id)


def _resource_uid_for_catalog(namespace: str, resource_name: str, catalog_id: str) -> str:
    return entity_uid(f"{namespace}::{resource_name}", catalog_id)


def _catalog_id(model_name: str, verb: str, entities_mod: Any, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    if entities_mod is not None:
        const = _catalog_constant_name(model_name)
        if hasattr(entities_mod, const):
            return str(getattr(entities_mod, const))
    return f"{model_name.replace('_', '-')}-catalog"


def _resource_uid_for_action(
    *,
    namespace: str,
    model_name: str,
    verb: str,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    entities_mod: Any,
) -> str:
    """Cedar **Resource** UID for one **Action** (Catalog constant or Member path id)."""
    catalog = _uses_catalog_scope(model_name, verb, id_arg)
    resource_name = _scope_resource_name(model_name, verb, resource_type, catalog=catalog)
    if catalog:
        catalog_verb = verb if _is_catalog_collection(verb) else "list"
        return _resource_uid_for_catalog(
            namespace,
            resource_name,
            _catalog_id(model_name, catalog_verb, entities_mod, catalog_id),
        )
    return _resource_uid_from_view_arg(
        namespace,
        resource_name,
        _resolve_id_arg(id_arg, model_name),
    )


def _type_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
