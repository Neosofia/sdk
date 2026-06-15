"""Assemble ``resource_fn`` and ``entities_fn`` for Cedar evaluation."""
from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from authorization_in_the_middle.action_scope import (
    _action_parts,
    _is_catalog_collection,
    _is_catalog_singleton,
    _resolve_id_arg,
    _resource_uid_for_action,
    _scope_resource_name,
    _type_to_snake,
    _uses_catalog_scope,
)
from authorization_in_the_middle.entities import catalog_entities, catalog_resource_uid, entity_uid
from authorization_in_the_middle.flask_request import request_view_arg
from authorization_in_the_middle.payload import (
    _entity_record_id,
    align_shared_uid_entity_attrs,
    write_exact_set_field_attrs,
    write_role_namespace_attrs,
)
from authorization_in_the_middle.rest_defaults import default_catalog_id
from authorization_in_the_middle.service_conventions import (
    _find_catalog_builder,
    _find_resource_builder,
    _find_write_entity_builder,
    _resolve_principal,
)


def _resource_uid_from_entity(entity: dict[str, Any]) -> str:
    ref = entity["uid"]["__entity"]
    return entity_uid(ref["type"], ref["id"])


def _uses_catalog_for_action(
    *,
    model_name: str,
    verb: str,
    id_arg: str | None,
    catalog_id: str | None,
    resource_type: str | None,
    catalog_id_from: str | None = None,
) -> bool:
    if catalog_id_from:
        return True
    if catalog_id and resource_type and verb not in ("read", "update", "delete"):
        return True
    return _uses_catalog_scope(model_name, verb, id_arg)


def _rest_entities_for_item(
    service_model: str,
    builder_module_name: str,
    id_arg: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
    *,
    namespace: str | None = None,
) -> list[dict[str, Any]]:
    """Principal + **Member** resource entity (id from path; no DB load unless ``resource_loader``)."""
    member_arg = _resolve_id_arg(id_arg, service_model)
    resource_id = request_view_arg(member_arg)
    try:
        model_mod = importlib.import_module(f"src.models.{builder_module_name}")
    except ImportError:
        model_mod = None
    build_resource_entity = _find_resource_builder(
        entities_mod,
        model_mod,
        service_model,
        builder_module_name,
        namespace=namespace,
        id_arg=member_arg,
    )
    loaded = resource_loader(resource_id) if resource_loader else None
    principal = _resolve_principal(entities_mod)
    resource = build_resource_entity(resource_id, loaded)
    principal, resource = align_shared_uid_entity_attrs(
        principal,
        resource,
        source="principal",
    )
    return [principal, resource]


def _rest_entities_for_catalog(
    build_catalog_resource: Callable[[], dict[str, Any]],
    entities_mod: Any,
) -> list[dict[str, Any]]:
    """Principal + **Catalog** resource record (fixed catalog id)."""
    return catalog_entities(
        lambda: _resolve_principal(entities_mod),
        build_catalog_resource,
    )


def _entities_for_write_member(
    entities_mod: Any,
    model_name: str,
    write_record: dict[str, Any],
    *,
    present_fields: list[str] | None = None,
    namespace: str | None = None,
    id_arg: str | None = None,
    builder_module_name: str | None = None,
) -> list[dict[str, Any]]:
    build_write = _find_write_entity_builder(
        entities_mod,
        model_name,
        namespace=namespace,
        id_arg=id_arg,
        builder_module_name=builder_module_name,
    )
    if build_write is None:
        raise ValueError(
            f"REST write authorization requires member attrs on src.authorization.entities "
            f"(registry_{model_name}_cedar_attrs / member_attrs) or "
            f"build_write_{model_name}_entity(record)"
        )
    principal = _resolve_principal(entities_mod)
    resource = build_write(write_record)
    presence = {"presentFields": sorted(present_fields or [])}
    namespace_attrs = write_role_namespace_attrs(
        write_record,
        resource,
        present_fields or [],
    )
    exact_set_attrs = write_exact_set_field_attrs(
        write_record,
        resource,
        present_fields or [],
        "roles",
    )
    if _entity_record_id(principal) == _entity_record_id(resource):
        merged_attrs = {
            **(principal.get("attrs") or {}),
            **(resource.get("attrs") or {}),
            **namespace_attrs,
            **exact_set_attrs,
            **presence,
        }
        principal = {**principal, "attrs": merged_attrs}
        resource = {**resource, "attrs": merged_attrs}
    else:
        resource_attrs = dict(resource.get("attrs") or {})
        resource_attrs.update(namespace_attrs)
        resource_attrs.update(exact_set_attrs)
        resource_attrs.update(presence)
        resource = {**resource, "attrs": resource_attrs}
    return [principal, resource]


def _resource_uid_for_write_member(
    entities_mod: Any,
    model_name: str,
    write_record: dict[str, Any],
    *,
    namespace: str | None = None,
    id_arg: str | None = None,
    builder_module_name: str | None = None,
) -> str:
    entity = _entities_for_write_member(
        entities_mod,
        model_name,
        write_record,
        namespace=namespace,
        id_arg=id_arg,
        builder_module_name=builder_module_name,
    )[1]
    return _resource_uid_from_entity(entity)


def _entities_for_action(
    *,
    model_name: str,
    verb: str,
    builder_module_name: str,
    id_arg: str | None,
    resource_type: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None,
    namespace: str | None = None,
    catalog_id: str | None = None,
    catalog_id_from: str | None = None,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """``[principal_entity, resource_entity]`` for one **Action**."""
    catalog = _uses_catalog_for_action(
        model_name=model_name,
        verb=verb,
        id_arg=id_arg,
        catalog_id=catalog_id,
        resource_type=resource_type,
        catalog_id_from=catalog_id_from,
    )
    if catalog:
        try:
            model_mod = importlib.import_module(f"src.models.{builder_module_name}")
        except ImportError:
            model_mod = None
        resource_name = resource_type or _scope_resource_name(
            model_name,
            verb,
            resource_type,
            catalog=True,
        )
        build_catalog = _find_catalog_builder(
            entities_mod,
            model_mod,
            resource_name,
            namespace=namespace,
            model_name=model_name,
            verb=verb if _is_catalog_collection(verb) else "list",
            catalog_id=catalog_id,
            catalog_id_from=catalog_id_from,
            catalog_attrs=catalog_attrs,
        )
        return _rest_entities_for_catalog(build_catalog, entities_mod)
    return _rest_entities_for_item(
        model_name,
        builder_module_name,
        id_arg,
        entities_mod,
        resource_loader,
        namespace=namespace,
    )


def _resource_uid_for_action_with_overrides(
    *,
    namespace: str,
    model_name: str,
    verb: str,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    catalog_id_from: str | None,
    entities_mod: Any,
) -> str:
    if _uses_catalog_for_action(
        model_name=model_name,
        verb=verb,
        id_arg=id_arg,
        catalog_id=catalog_id,
        resource_type=resource_type,
        catalog_id_from=catalog_id_from,
    ):
        resource_name = resource_type or _scope_resource_name(
            model_name,
            verb,
            resource_type,
            catalog=True,
        )
        snake = _type_to_snake(resource_name)
        if entities_mod is not None and hasattr(entities_mod, f"build_{snake}_resource"):
            try:
                model_mod = importlib.import_module(f"src.models.{model_name}")
            except ImportError:
                model_mod = None
            build_catalog = _find_catalog_builder(
                entities_mod,
                model_mod,
                resource_name,
                namespace=namespace,
                model_name=model_name,
                verb=verb if _is_catalog_collection(verb) else "list",
                catalog_id=catalog_id,
                catalog_id_from=catalog_id_from,
            )
            return _resource_uid_from_entity(build_catalog())
        resolved_catalog_id = default_catalog_id(
            model_name,
            verb if _is_catalog_collection(verb) else "list",
            entities_mod,
            explicit=catalog_id,
            catalog_id_from=catalog_id_from,
        )
        return catalog_resource_uid(namespace, resource_name, resolved_catalog_id)
    return _resource_uid_for_action(
        namespace=namespace,
        model_name=model_name,
        verb=verb,
        id_arg=id_arg,
        resource_type=resource_type,
        catalog_id=catalog_id,
        entities_mod=entities_mod,
    )


def _infer_rest_fns(
    action: str,
    *,
    resource_fn: Callable[[], str] | None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None,
    namespace: str | None,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    catalog_id_from: str | None,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None,
    entity_module: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[Callable[[], str], Callable[[], list[dict[str, Any]]], str, str]:
    """Fill in omitted ``resource_fn`` / ``entities_fn`` for a resolved Cedar **Action**."""
    resource_fn_local = resource_fn
    entities_fn_local = entities_fn

    model_name, verb = _action_parts(action)
    builder_module_name = entity_module or model_name
    resolved_resource_name = _scope_resource_name(
        model_name,
        verb,
        resource_type,
        catalog=_is_catalog_collection(verb) or _is_catalog_singleton(model_name, verb) or bool(catalog_id and resource_type),
    )

    inferred_namespace = namespace
    if inferred_namespace is None:
        if entities_mod is not None and hasattr(entities_mod, "NAMESPACE"):
            inferred_namespace = entities_mod.NAMESPACE
        else:
            try:
                model_mod = importlib.import_module(f"src.models.{builder_module_name}")
                inferred_namespace = getattr(model_mod, "NAMESPACE")
            except (ImportError, AttributeError) as exc:
                raise ValueError(
                    f"Could not infer Cedar namespace for '{model_name}'. "
                    f"Set namespace= or add NAMESPACE to src.authorization.entities. Error: {exc}"
                ) from exc

    if resource_fn_local is None:
        resource_fn_local = lambda ns=inferred_namespace, mn=model_name, v=verb, explicit=id_arg, rt=resource_type, cid=catalog_id, cid_from=catalog_id_from, em=entities_mod: (
            _resource_uid_for_action_with_overrides(
                namespace=ns,
                model_name=mn,
                verb=v,
                id_arg=explicit,
                resource_type=rt,
                catalog_id=cid,
                catalog_id_from=cid_from,
                entities_mod=em,
            )
        )

    if entities_fn_local is None:
        entities_fn_local = lambda mn=model_name, v=verb, bm=builder_module_name, explicit=id_arg, rt=resource_type, em=entities_mod, rl=resource_loader, ns=inferred_namespace, cid=catalog_id, cid_from=catalog_id_from, cattrs=catalog_attrs: (
            _entities_for_action(
                model_name=mn,
                verb=v,
                builder_module_name=bm,
                id_arg=explicit,
                resource_type=rt,
                entities_mod=em,
                resource_loader=rl,
                namespace=ns,
                catalog_id=cid,
                catalog_id_from=cid_from,
                catalog_attrs=cattrs,
            )
        )

    return resource_fn_local, entities_fn_local, resolved_resource_name, id_arg or f"{model_name}_uuid"


def _infer_kwargs(
    *,
    resource_fn: Callable[[], str] | None,
    entities_fn: Callable[[], list[dict[str, Any]]] | None,
    namespace: str | None,
    id_arg: str | None,
    resource_type: str | None,
    catalog_id: str | None,
    catalog_id_from: str | None,
    catalog_attrs: dict[str, Any] | Callable[[], dict[str, Any]] | None,
    entity_module: str | None,
    entities_mod: Any,
    resource_loader: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    """Shared kwargs for ``_infer_rest_fns`` (decorator + logging)."""
    return {
        "resource_fn": resource_fn,
        "entities_fn": entities_fn,
        "namespace": namespace,
        "id_arg": id_arg,
        "resource_type": resource_type,
        "catalog_id": catalog_id,
        "catalog_id_from": catalog_id_from,
        "catalog_attrs": catalog_attrs,
        "entity_module": entity_module,
        "entities_mod": entities_mod,
        "resource_loader": resource_loader,
    }
