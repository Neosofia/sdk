from unittest.mock import MagicMock, patch

import jwt as pyjwt
from flask import Flask, jsonify

from authentication_in_the_middle.actors import parse_tier1_actor_classes
from authentication_in_the_middle.decorators import with_authentication

_TIER1 = parse_tier1_actor_classes("operator,study,clinician,patient")


def _test_app(**extra_config) -> Flask:
    app = Flask(__name__)
    app.config["TIER1_ACTOR_CLASSES"] = _TIER1
    app.config.update(extra_config)
    return app


def test_with_authentication_reuses_cached_jwks_client():
    app = _test_app(
        JWT_JWKS_URI="https://auth.example/.well-known/jwks.json",
        JWT_AUDIENCE="capabilities",
    )

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="public-key")

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    token = "header.payload.sig"

    with (
        patch("authentication_in_the_middle.decorators.get_jwks_client", return_value=mock_client) as get_client,
        patch(
            "authentication_in_the_middle.decorators.pyjwt.decode",
            return_value={
                "sub": "user-1",
                "aud": "capabilities",
                "exp": 9999999999,
                "iat": 1,
                "neosofia:actors": ["operator"],
            },
        ),
    ):
        with app.test_client() as client:
            headers = {"Authorization": f"Bearer {token}"}
            first = client.get("/protected", headers=headers)
            second = client.get("/protected", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert get_client.call_count == 2
    assert mock_client.get_signing_key_from_jwt.call_count == 2


def test_with_authentication_rejects_missing_bearer():
    app = _test_app(
        JWT_JWKS_URI="https://auth.example/.well-known/jwks.json",
        JWT_AUDIENCE="capabilities",
    )

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    with app.test_client() as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json == {"error": "unauthenticated", "detail": "Missing or invalid Bearer token"}


def test_with_authentication_requires_audience_config():
    app = _test_app(JWT_JWKS_URI="https://auth.example/.well-known/jwks.json")

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    with app.test_client() as client:
        response = client.get("/protected", headers={"Authorization": "Bearer token"})

    assert response.status_code == 500
    assert response.json == {"error": "server_error", "detail": "Missing config: JWT_AUDIENCE"}


def test_with_authentication_rejects_invalid_token():
    app = _test_app(
        JWT_JWKS_URI="https://auth.example/.well-known/jwks.json",
        JWT_AUDIENCE="capabilities",
    )

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="public-key")

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    with (
        patch("authentication_in_the_middle.decorators.get_jwks_client", return_value=mock_client),
        patch("authentication_in_the_middle.decorators.pyjwt.decode", side_effect=pyjwt.InvalidTokenError("bad")),
    ):
        with app.test_client() as client:
            response = client.get("/protected", headers={"Authorization": "Bearer token"})

    assert response.status_code == 401
    assert response.json == {"error": "unauthenticated", "detail": "Invalid token"}


def test_with_authentication_rejects_expired_token():
    app = _test_app(
        JWT_JWKS_URI="https://auth.example/.well-known/jwks.json",
        JWT_AUDIENCE="capabilities",
    )

    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="public-key")

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    with (
        patch("authentication_in_the_middle.decorators.get_jwks_client", return_value=mock_client),
        patch("authentication_in_the_middle.decorators.pyjwt.decode", side_effect=pyjwt.ExpiredSignatureError("expired")),
    ):
        with app.test_client() as client:
            response = client.get("/protected", headers={"Authorization": "Bearer token"})

    assert response.status_code == 401
    assert response.json == {"error": "unauthenticated", "detail": "Token expired"}


def test_with_authentication_accepts_static_public_key():
    app = _test_app(JWT_PUBLIC_KEY="public-key", JWT_AUDIENCE="capabilities")

    @app.get("/protected")
    @with_authentication()
    def protected():
        return jsonify({"ok": True})

    with patch(
        "authentication_in_the_middle.decorators.pyjwt.decode",
        return_value={
            "sub": "user-1",
            "aud": "capabilities",
            "exp": 9999999999,
            "iat": 1,
            "neosofia:actors": ["operator"],
        },
    ):
        with app.test_client() as client:
            response = client.get("/protected", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200


def test_with_authentication_uses_jwt_claim_namespace_from_config():
    app = _test_app(
        JWT_PUBLIC_KEY="public-key",
        JWT_AUDIENCE="capabilities",
        JWT_CLAIM_NAMESPACE="acme",
    )

    captured: dict = {}

    @app.get("/protected")
    @with_authentication()
    def protected():
        from flask import g

        captured["claims"] = dict(g.jwt_claims)
        return jsonify({"ok": True})

    with patch(
        "authentication_in_the_middle.decorators.pyjwt.decode",
        return_value={
            "sub": "user-1",
            "aud": "capabilities",
            "exp": 9999999999,
            "iat": 1,
            "acme:actors": ["operator", "clinician"],
        },
    ):
        with app.test_client() as client:
            response = client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer token",
                    "X-Active-Actor": "operator",
                },
            )

    assert response.status_code == 200
    assert captured["claims"]["acme:actors"] == ["operator"]
    assert captured["claims"]["acme:session_actors"] == ["operator", "clinician"]


def test_with_authentication_preserves_explicit_session_actors_claim():
    app = _test_app(
        JWT_PUBLIC_KEY="public-key",
        JWT_AUDIENCE="capabilities",
        JWT_CLAIM_NAMESPACE="acme",
    )

    captured: dict = {}

    @app.get("/protected")
    @with_authentication()
    def protected():
        from flask import g

        captured["claims"] = dict(g.jwt_claims)
        return jsonify({"ok": True})

    with patch(
        "authentication_in_the_middle.decorators.pyjwt.decode",
        return_value={
            "sub": "user-1",
            "aud": "capabilities",
            "exp": 9999999999,
            "iat": 1,
            "acme:actors": ["operator"],
            "acme:session_actors": ["operator", "clinician", "patient"],
        },
    ):
        with app.test_client() as client:
            response = client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer token",
                    "X-Active-Actor": "operator",
                },
            )

    assert response.status_code == 200
    assert captured["claims"]["acme:actors"] == ["operator"]
    assert captured["claims"]["acme:session_actors"] == [
        "operator",
        "clinician",
        "patient",
    ]


def test_parse_tier1_actor_classes():
    assert parse_tier1_actor_classes("operator,study,patient") == frozenset(
        {"operator", "study", "patient"}
    )
    assert parse_tier1_actor_classes("") == frozenset()


def test_session_actors_filtered_by_tier1_config():
    app = Flask(__name__)
    app.config["JWT_PUBLIC_KEY"] = "public-key"
    app.config["JWT_AUDIENCE"] = "capabilities"
    app.config["TIER1_ACTOR_CLASSES"] = frozenset({"operator", "study"})

    captured: dict = {}

    @app.get("/protected")
    @with_authentication()
    def protected():
        from flask import g

        captured["claims"] = dict(g.jwt_claims)
        return jsonify({"ok": True})

    with patch(
        "authentication_in_the_middle.decorators.pyjwt.decode",
        return_value={
            "sub": "user-1",
            "aud": "capabilities",
            "exp": 9999999999,
            "iat": 1,
            "neosofia:actors": ["operator", "study", "clinician"],
        },
    ):
        with app.test_client() as client:
            response = client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer token",
                    "X-Active-Actor": "study",
                },
            )

    assert response.status_code == 200
    assert captured["claims"]["neosofia:session_actors"] == ["operator", "study"]
