from flask import Flask, g

from authorization_in_the_middle.service_conventions import resolve_write_plan_fn
from authorization_in_the_middle.write_planners import default_plan_create_from_openapi


def test_default_plan_create_merges_scope_bindings():
    app = Flask(__name__)

    @app.route("/api/v1/users/<user_uuid>/interactions/<chat_interaction_uuid>/messages", methods=["POST"])
    def post_message(user_uuid: str, chat_interaction_uuid: str):
        return ""

    with app.test_request_context(
        "/api/v1/users/u1/interactions/i1/messages",
        method="POST",
        json={"sender_type": "patient", "content": "hi"},
    ):
        g.planned_body = {"sender_type": "patient", "content": "hi"}
        planned = default_plan_create_from_openapi()

    assert planned == {
        "sender_type": "patient",
        "content": "hi",
        "user_uuid": "u1",
        "chat_interaction_uuid": "i1",
    }


def test_resolve_write_plan_fn_uses_default_for_post_without_service_hook():
    assert resolve_write_plan_fn("nonexistent_model_xyz", "POST") is default_plan_create_from_openapi


def test_resolve_write_plan_fn_requires_custom_planner_for_patch():
    assert resolve_write_plan_fn("nonexistent_model_xyz", "PATCH") is None
