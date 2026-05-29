from authorization_in_the_middle.security import (
    _action_parts,
    _catalog_constant_name,
    _catalog_resource_type,
    _is_catalog_collection,
    _is_catalog_singleton,
    _type_to_snake,
)


def test_action_parts():
    assert _action_parts('Action::"user:read"') == ("user", "read")
    assert _action_parts('Action::"user:list"') == ("user", "list")
    assert _action_parts('Action::"role_catalog:read"') == ("role_catalog", "read")
    assert _action_parts('Action::"service:audit:read"') == ("service", "audit:read")  # sub-resource verb


def test_catalog_detection():
    assert _is_catalog_collection("list")
    assert _is_catalog_collection("create")
    assert not _is_catalog_collection("read")
    assert _is_catalog_singleton("role_catalog", "read")
    assert not _is_catalog_singleton("user", "read")


def test_catalog_resource_types():
    assert _catalog_resource_type("user", "list") == "UserCatalog"
    assert _catalog_resource_type("role_catalog", "read") == "RoleCatalog"


def test_catalog_constant_name():
    assert _catalog_constant_name("user") == "USER_CATALOG_ID"
    assert _catalog_constant_name("role_catalog") == "ROLE_CATALOG_ID"


def test_type_to_snake():
    assert _type_to_snake("UserCatalog") == "user_catalog"
    assert _type_to_snake("RoleCatalog") == "role_catalog"
