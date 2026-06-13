import pytest

from authorization_in_the_middle.entities import (
    ID_PLACEHOLDER,
    build_catalog_entity,
    catalog_entities,
    catalog_resource_uid,
    is_id_placeholder,
    resolve_entity_id,
)

pytestmark = pytest.mark.unit


def test_id_placeholder_constant():
    assert ID_PLACEHOLDER == "proposed"


def test_is_id_placeholder():
    assert is_id_placeholder(ID_PLACEHOLDER)
    assert is_id_placeholder("proposed")
    assert not is_id_placeholder(None)
    assert not is_id_placeholder("00000000-0000-7000-8000-000000000001")


def test_resolve_entity_id_uses_placeholder_when_missing():
    assert resolve_entity_id({}) == ID_PLACEHOLDER
    assert resolve_entity_id({"uuid": ID_PLACEHOLDER}) == ID_PLACEHOLDER


def test_resolve_entity_id_returns_assigned_id():
    uid = "00000000-0000-7000-8000-000000000002"
    assert resolve_entity_id({"uuid": uid}) == uid


def test_build_catalog_entity():
    entity = build_catalog_entity("users", "UserCatalog", "user-catalog")
    assert entity["uid"]["__entity"] == {"type": "users::UserCatalog", "id": "user-catalog"}
    assert entity["attrs"] == {}


def test_build_catalog_entity_with_attrs():
    tenant = "00000000-0000-7000-8000-000000000001"
    entity = build_catalog_entity(
        "users",
        "UserCatalog",
        tenant,
        {"tenantId": tenant},
    )
    assert entity["attrs"]["tenantId"] == tenant


def test_catalog_resource_uid():
    uid = catalog_resource_uid("users", "RoleCatalog", "role-catalog")
    assert uid == 'users::RoleCatalog::"role-catalog"'


def test_catalog_entities():
    principal = {"uid": {"__entity": {"type": "users::User", "id": "u1"}}, "attrs": {}}
    catalog = build_catalog_entity("users", "UserCatalog", "user-catalog")
    entities = catalog_entities(lambda: principal, lambda: catalog)
    assert len(entities) == 2
    assert entities[0] == principal
    assert entities[1] == catalog
