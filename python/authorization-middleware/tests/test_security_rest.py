from flask import Flask

from authorization_in_the_middle.route_inference import (
    infer_catalog_scope,
    infer_crud_action,
    infer_id_arg,
    infer_resource,
    infer_scope_bindings,
)
from authorization_in_the_middle.security import (
    _action_parts,
    _catalog_constant_name,
    _catalog_resource_type,
    _find_catalog_builder,
    _is_catalog_collection,
    _is_catalog_singleton,
    _resolve_id_arg,
    _resource_uid_for_action,
    _type_to_snake,
    _uses_catalog_scope,
)


def test_infer_roles_collection_list():
    app = Flask(__name__)

    @app.route("/api/v1/roles")
    def list_roles():
        return ""

    with _bind_request(app, "/api/v1/roles"):
        assert infer_resource() == "role"
        assert infer_crud_action() == 'Action::"role:list"'


def test_action_parts():
    assert _action_parts('Action::"user:read"') == ("user", "read")
    assert _action_parts('Action::"user:list"') == ("user", "list")
    assert _action_parts('Action::"role_catalog:read"') == ("role_catalog", "read")
    assert _action_parts('Action::"care-episode:list"') == ("care_episode", "list")


def test_catalog_detection():
    assert _is_catalog_collection("list")
    assert _is_catalog_collection("create")
    assert not _is_catalog_collection("read")
    assert _is_catalog_singleton("role_catalog", "read")
    assert not _is_catalog_singleton("user", "read")


def test_catalog_resource_types():
    assert _catalog_resource_type("user", "list") == "UserCatalog"
    assert _catalog_resource_type("role_catalog", "read") == "RoleCatalog"
    assert _catalog_resource_type("care_episode", "list") == "CareEpisodeCatalog"
    assert _catalog_resource_type("care_episode", "create") == "CareEpisodeCatalog"


def test_catalog_constant_name():
    assert _catalog_constant_name("user") == "USER_CATALOG_ID"
    assert _catalog_constant_name("role_catalog") == "ROLE_CATALOG_ID"


def test_type_to_snake():
    assert _type_to_snake("UserCatalog") == "user_catalog"
    assert _type_to_snake("RoleCatalog") == "role_catalog"
    assert _type_to_snake("CareEpisodeCatalog") == "care_episode_catalog"


def _bind_request(app: Flask, path: str, method: str = "GET"):
    from flask import request

    adapter = app.url_map.bind("")
    endpoint, view_args = adapter.match(path, method=method)
    rule = app.url_map._rules_by_endpoint[endpoint][0]
    ctx = app.test_request_context(path, method=method)
    ctx.request.url_rule = rule
    ctx.request.view_args = view_args
    return ctx


def test_infer_resource():
    app = Flask(__name__)

    @app.route("/api/services")
    def services():
        return ""

    @app.route("/api/v1/tenants/<tenant_uuid>")
    def tenant(tenant_uuid: str):
        return tenant_uuid

    @app.route("/api/idp/failed-authentications")
    def idp_failed():
        return ""

    @app.route("/api/people/<person_id>")
    def people(person_id: str):
        return person_id

    with _bind_request(app, "/api/services"):
        assert infer_resource() == "service"
    @app.route("/api/v2/tenants/<tenant_uuid>")
    def tenant_v2(tenant_uuid: str):
        return tenant_uuid

    with _bind_request(app, "/api/v1/tenants/t1"):
        assert infer_resource() == "tenant"
    with _bind_request(app, "/api/v2/tenants/t1"):
        assert infer_resource() == "tenant"
    with _bind_request(app, "/api/idp/failed-authentications"):
        assert infer_resource() == "idp"
    with _bind_request(app, "/api/people/p1"):
        assert infer_resource() == "person"


def test_infer_nested_tenant_users_collection():
    app = Flask(__name__)

    @app.route("/api/v1/tenants/<tenant_uuid>/users")
    def tenant_users(tenant_uuid: str):
        return tenant_uuid

    with _bind_request(app, "/api/v1/tenants/t1/users"):
        assert infer_resource() == "user"
        assert infer_crud_action() == 'Action::"user:list"'
        assert infer_id_arg() is None
        assert infer_scope_bindings() == [("tenant_uuid", "tenantId")]
        assert infer_catalog_scope() == ("tenant_uuid", {"tenantId": "t1"})


def test_infer_nested_tenant_users_member():
    app = Flask(__name__)

    @app.route("/api/v1/tenants/<tenant_uuid>/users/<user_uuid>")
    def tenant_user(tenant_uuid: str, user_uuid: str):
        return user_uuid

    with _bind_request(app, "/api/v1/tenants/t1/users/u1"):
        assert infer_resource() == "user"
        assert infer_crud_action() == 'Action::"user:read"'
        assert infer_id_arg() == "user_uuid"


def test_infer_member_subresource_audits():
    app = Flask(__name__)

    @app.route("/api/v1/users/<user_uuid>/audits")
    def user_audits(user_uuid: str):
        return user_uuid

    with _bind_request(app, "/api/v1/users/u1/audits"):
        assert infer_resource() == "user"
        assert infer_crud_action() == 'Action::"user:read"'
        assert infer_id_arg() == "user_uuid"
        assert infer_scope_bindings() == []


def test_infer_crud_action_collection():
    app = Flask(__name__)

    @app.route("/api/services", methods=["GET", "POST"])
    def services():
        return ""

    with _bind_request(app, "/api/services", "GET"):
        assert infer_crud_action() == 'Action::"service:list"'
    with _bind_request(app, "/api/services", "POST"):
        assert infer_crud_action() == 'Action::"service:create"'


def test_infer_crud_action_member():
    app = Flask(__name__)

    @app.route("/api/services/<slug>", methods=["GET", "PUT"])
    def service(slug: str):
        return slug

    @app.route("/api/v1/tenants/<tenant_uuid>", methods=["GET", "PUT"])
    def tenant(tenant_uuid: str):
        return tenant_uuid

    with _bind_request(app, "/api/services/chat", "GET"):
        assert infer_crud_action() == 'Action::"service:read"'

    with _bind_request(app, "/api/v1/tenants/t1", "PUT"):
        assert infer_crud_action() == 'Action::"tenant:update"'


def test_infer_id_arg():
    app = Flask(__name__)

    @app.route("/api/services/<slug>")
    def service(slug: str):
        return slug

    with _bind_request(app, "/api/services/chat"):
        assert infer_id_arg() == "slug"


def test_resolve_id_arg_prefers_explicit():
    app = Flask(__name__)

    @app.route("/api/services/<slug>")
    def service(slug: str):
        return slug

    with _bind_request(app, "/api/services/chat"):
        assert _resolve_id_arg("slug", "service") == "slug"
        assert _resolve_id_arg(None, "service") == "slug"


def test_resolve_id_arg_falls_back_to_model_uuid():
    assert _resolve_id_arg(None, "user") == "user_uuid"


def test_uses_catalog_scope_member_list_when_id_in_path():
    app = Flask(__name__)

    @app.route("/api/v1/care-episodes/<patient_uuid>/records")
    def patient_records(patient_uuid: str):
        return patient_uuid

    with _bind_request(app, "/api/v1/care-episodes/u1/records"):
        assert _uses_catalog_scope("care_episode", "list", "patient_uuid") is False


def test_uses_catalog_scope_for_compound_list_without_member():
    app = Flask(__name__)

    @app.route("/api/services/audits")
    def catalog_audits():
        return ""

    @app.route("/api/services/<slug>/audits")
    def member_audits(slug: str):
        return slug

    with _bind_request(app, "/api/services/audits"):
        assert _uses_catalog_scope("service", "audit:list", None) is True

    with _bind_request(app, "/api/services/chat/audits"):
        assert _uses_catalog_scope("service", "audit:list", "slug") is False


def test_resource_uid_for_audit_list_catalog():
    app = Flask(__name__)

    class Entities:
        NAMESPACE = "authentication"
        SERVICE_CATALOG_ID = "service-catalog"

    @app.route("/api/services/audits")
    def catalog_audits():
        return ""

    with _bind_request(app, "/api/services/audits"):
        uid = _resource_uid_for_action(
            namespace="authentication",
            model_name="service",
            verb="audit:list",
            id_arg=None,
            resource_type=None,
            catalog_id=None,
            entities_mod=Entities,
        )
    assert uid == 'authentication::ServiceCatalog::"service-catalog"'


def test_find_catalog_builder_synthesizes_when_hook_missing():
    class Entities:
        NAMESPACE = "users"

    builder = _find_catalog_builder(Entities(), None, "UserCatalog")
    entity = builder()
    assert entity["uid"]["__entity"]["type"] == "users::UserCatalog"
    assert entity["uid"]["__entity"]["id"] == "user-catalog"


def test_find_catalog_builder_prefers_resource_name():
    class Entities:
        def build_message_catalog_resource(self):
            return {"kind": "resource"}

        def build_message_catalog_entity(self):
            return {"kind": "entity"}

    builder = _find_catalog_builder(Entities(), None, "MessageCatalog")
    assert builder() == {"kind": "resource"}


def test_find_catalog_builder_falls_back_to_entity_name():
    class Entities:
        def build_user_catalog_entity(self):
            return {"kind": "entity"}

    builder = _find_catalog_builder(Entities(), None, "UserCatalog")
    assert builder() == {"kind": "entity"}


