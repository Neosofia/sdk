from authorization_in_the_middle import CedarEvaluator, FilesystemPolicySetSource


def test_filesystem_policy_source_loads_and_versions_bundle(tmp_path):
    (tmp_path / "schema.cedar.json").write_text(
        '{"demo": {"entityTypes": {}, "actions": {"document:read": {"appliesTo": {"principalTypes": ["User"], "resourceTypes": ["Document"], "context": {"type": "Record", "attributes": {}}}}}}}',
        encoding="utf-8",
    )
    (tmp_path / "read.cedar").write_text(
        'permit (principal, action == Action::"document:read", resource);',
        encoding="utf-8",
    )

    source = FilesystemPolicySetSource(tmp_path, cache_ttl=60)
    policy_set = source.get_policy_set()

    assert policy_set["version"].startswith("sha256:")
    assert policy_set["schema_content"]
    assert [policy["name"] for policy in policy_set["policies"]] == ["read"]


def test_cedar_evaluator_uses_filesystem_policy_source(tmp_path):
    (tmp_path / "schema.cedar.json").write_text(
        '{"demo": {"entityTypes": {"User": {"shape": {"type": "Record", "attributes": {}}}, "Document": {"shape": {"type": "Record", "attributes": {}}}}, "actions": {"document:read": {"appliesTo": {"principalTypes": ["User"], "resourceTypes": ["Document"], "context": {"type": "Record", "attributes": {}}}}}}}',
        encoding="utf-8",
    )
    (tmp_path / "read.cedar").write_text(
        'permit (principal is demo::User, action == Action::"document:read", resource is demo::Document);',
        encoding="utf-8",
    )

    evaluator = CedarEvaluator(policy_source=FilesystemPolicySetSource(tmp_path))

    assert evaluator.is_authorized(
        'demo::User::"u1"',
        'Action::"document:read"',
        'demo::Document::"d1"',
        [],
    )