from authorization_in_the_middle.entities import build_entity_payload
from authorization_in_the_middle.payload import (
    align_shared_uid_entity_attrs,
    canonical_string_set,
    present_field_names,
    role_namespaces,
    write_exact_set_field_attrs,
)


def test_present_field_names_sorted():
    assert present_field_names({"roles": [], "email": "a", "first_name": "x"}) == [
        "email",
        "first_name",
        "roles",
    ]


def test_align_shared_uid_entity_attrs_uses_principal_for_reads():
    principal = build_entity_payload("users::User", "u1", {"isClinician": True, "uuid": "u1"})
    resource = build_entity_payload("users::User", "u1", {"roles": ["self"]})
    aligned_principal, aligned_resource = align_shared_uid_entity_attrs(
        principal,
        resource,
        source="principal",
    )
    assert aligned_principal["attrs"]["isClinician"] is True
    assert aligned_resource["attrs"]["isClinician"] is True


def test_align_shared_uid_entity_attrs_uses_resource_for_planned_writes():
    principal = build_entity_payload("users::User", "u1", {"isClinician": True})
    resource = build_entity_payload("users::User", "u1", {"roles": ["patient.self"]})
    aligned_principal, aligned_resource = align_shared_uid_entity_attrs(
        principal,
        resource,
        source="resource",
    )
    assert aligned_resource["attrs"]["roles"] == ["patient.self"]


def test_role_namespaces_from_slugs():
    assert role_namespaces(["cro.admin", "patient.self", "cro.monitor"]) == [
        "cro",
        "patient",
    ]


def test_canonical_string_set_dedupes_and_sorts():
    assert canonical_string_set(["b", "a", "b", ""]) == ["a", "b"]


def test_write_exact_set_field_attrs_canonical_proposed():
    resource = build_entity_payload("users::User", "u1", {"roles": ["patient.self"]})
    attrs = write_exact_set_field_attrs(
        {"roles": ["patient.self", "patient.self"]},
        resource,
        ["roles"],
        "roles",
    )
    assert attrs == {"rolesExact": ["patient.self"]}


def test_write_exact_set_field_attrs_omits_when_field_not_sent():
    resource = build_entity_payload("users::User", "u1", {"roles": ["patient.self"]})
    assert write_exact_set_field_attrs({"roles": ["patient.self"]}, resource, [], "roles") == {}


def test_write_exact_set_field_attrs_allowed_match_only():
    resource = build_entity_payload("users::User", "u1", {"roles": ["patient.self"]})
    assert write_exact_set_field_attrs(
        {"roles": ["patient.self"]},
        resource,
        ["roles"],
        "roles",
        ["patient.self"],
    ) == {"rolesExact": ["patient.self"]}


def test_write_exact_set_field_attrs_allowed_mismatch_omits():
    resource = build_entity_payload("users::User", "u1", {"roles": ["site.clinical"]})
    assert write_exact_set_field_attrs(
        {"roles": ["patient.self", "site.clinical"]},
        resource,
        ["roles"],
        "roles",
        ["patient.self"],
    ) == {}
