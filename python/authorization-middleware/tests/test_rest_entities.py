from flask import Flask

from authorization_in_the_middle.rest_entities import _rest_entities_for_item


def _bind_request(app: Flask, path: str, method: str = "GET"):
    adapter = app.url_map.bind("")
    endpoint, view_args = adapter.match(path, method=method)
    rule = app.url_map._rules_by_endpoint[endpoint][0]
    ctx = app.test_request_context(path, method=method)
    ctx.request.url_rule = rule
    ctx.request.view_args = view_args
    return ctx


def test_rest_entities_for_item_uses_inferred_id_field_for_member_attrs():
    """Synthesized builders must key rows by inferred path param, not default uuid."""

    class Entities:
        NAMESPACE = "authentication"

        @staticmethod
        def resolve_principal():
            return {
                "uid": {"__entity": {"type": "authentication::User", "id": "u1"}},
                "attrs": {"tenantId": "t1"},
                "parents": [],
            }

        @staticmethod
        def registry_tenant_cedar_attrs(row: dict) -> dict:
            return {"tenantId": str(row.get("tenant_uuid") or "")}

    app = Flask(__name__)

    @app.route("/api/v1/tenants/<tenant_uuid>", methods=["GET"])
    def tenant(tenant_uuid: str):
        return tenant_uuid

    with _bind_request(app, "/api/v1/tenants/t1"):
        entities = _rest_entities_for_item(
            "tenant",
            "tenant",
            None,
            Entities,
            resource_loader=None,
            namespace="authentication",
        )

    assert entities[1]["attrs"]["tenantId"] == "t1"
