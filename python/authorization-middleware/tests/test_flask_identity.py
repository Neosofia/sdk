from flask import Flask, g

from authorization_in_the_middle.flask_identity import extract_jwt_principal_entity


def test_extract_jwt_principal_entity_maps_actors_and_roles():
    app = Flask(__name__)
    with app.app_context():
        g.jwt_claims = {
            "sub": "user-uuid",
            "neosofia:actors": ["operator"],
            "neosofia:roles": ["admin"],
            "neosofia:tenant_type": "platform",
        }
        entity = extract_jwt_principal_entity("demo", default_type="User")

    assert entity["uid"]["__entity"]["id"] == "user-uuid"
    assert entity["attrs"]["actors"] == ["operator"]
    assert entity["attrs"]["roles"] == ["admin"]
    assert entity["attrs"]["tenantType"] == "platform"
