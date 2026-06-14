"""Tests for synthesized REST entity builders."""
from __future__ import annotations

from authorization_in_the_middle.entities import ID_PLACEHOLDER
from authorization_in_the_middle.rest_defaults import (
    find_member_attrs,
    synthesize_catalog_builder,
    synthesize_member_builder,
    synthesize_write_builder,
)


class UserEntities:
    NAMESPACE = "users"

    @staticmethod
    def registry_user_cedar_attrs(row: dict) -> dict:
        return {
            "uuid": str(row.get("uuid") or ""),
            "tenantId": str(row.get("tenant_uuid") or ""),
            "roles": list(row.get("roles") or []),
            "tokenType": "human",
        }


def test_find_member_attrs_discovers_registry_hook():
    assert find_member_attrs(UserEntities, "user") is UserEntities.registry_user_cedar_attrs


def test_synthesize_catalog_builder():
    builder = synthesize_catalog_builder(
        namespace="users",
        catalog_resource_type="UserCatalog",
        catalog_id="user-catalog",
    )
    entity = builder()
    assert entity["uid"]["__entity"]["type"] == "users::UserCatalog"
    assert entity["uid"]["__entity"]["id"] == "user-catalog"


def test_synthesize_catalog_builder_with_attrs():
    builder = synthesize_catalog_builder(
        namespace="users",
        catalog_resource_type="UserCatalog",
        catalog_id="tenant-1",
        catalog_attrs={"tenantId": "tenant-1"},
    )
    entity = builder()
    assert entity["attrs"]["tenantId"] == "tenant-1"


def test_synthesize_member_builder():
    builder = synthesize_member_builder(
        namespace="users",
        model_name="user",
        id_arg="user_uuid",
        entities_mod=UserEntities,
    )
    entity = builder(
        "user-1",
        {"uuid": "user-1", "tenant_uuid": "tenant-1", "roles": ["patient.self"]},
    )
    assert entity["uid"]["__entity"]["id"] == "user-1"
    assert entity["attrs"]["roles"] == ["patient.self"]


def test_synthesize_write_builder_resolves_placeholder():
    builder = synthesize_write_builder(
        namespace="users",
        model_name="user",
        id_arg="user_uuid",
        entities_mod=UserEntities,
    )
    entity = builder(
        {
            "uuid": ID_PLACEHOLDER,
            "tenant_uuid": "tenant-1",
            "roles": ["patient.self"],
        }
    )
    assert entity["uid"]["__entity"]["id"] == ID_PLACEHOLDER
    assert entity["attrs"]["roles"] == ["patient.self"]
