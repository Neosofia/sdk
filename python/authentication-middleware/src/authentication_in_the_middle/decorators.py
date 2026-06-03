from functools import wraps
from typing import Any, Callable

import jwt as pyjwt
from flask import current_app, g, jsonify, make_response, request
import re

from authentication_in_the_middle.jwks import get_jwks_client

SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_DEFAULT_CLAIM_NAMESPACE = "neosofia"


def _tier1_actor_classes() -> frozenset[str]:
    """Tier-1 allow-list set at app startup (see ``TIER1_ACTOR_CLASSES`` in Flask config)."""
    configured = current_app.config.get("TIER1_ACTOR_CLASSES")
    if isinstance(configured, frozenset):
        return configured
    if isinstance(configured, (set, list, tuple)):
        return frozenset(configured)
    return frozenset()


def _jwt_claim_namespace() -> str:
    ns = current_app.config.get("JWT_CLAIM_NAMESPACE", _DEFAULT_CLAIM_NAMESPACE)
    return str(ns).strip() or _DEFAULT_CLAIM_NAMESPACE


def _claim_key(name: str, namespace: str | None = None) -> str:
    return f"{namespace or _jwt_claim_namespace()}:{name}"


def with_authentication(
    public_key: str | None = None,
    audience: str | None = None,
    algorithms: list[str] | None = None,
    jwks_uri: str | None = None,
    enforce_active_actor: bool = True,
    require_actor: bool = False,
) -> Callable:
    """
    Decorator that validates a Bearer JWT using the provided public key or JWKS URI and audience.
    Stores the decoded JWT claims in flask.g.jwt_claims.

    Tier-1 (actors): ``{ns}:actors`` on the JWT; narrowed per request via ``X-Active-Actor``.
    Full session actor list is copied to ``{ns}:session_actors`` when narrowing applies.
    Tier-2 (roles): ``{ns}:roles`` is left untouched (registry roles within tenant_type).

    Services must set ``TIER1_ACTOR_CLASSES`` (frozenset) in Flask config at startup, typically
    from Pydantic ``valid_actors`` / env ``VALID_ACTORS``. Also supports ``JWT_PUBLIC_KEY``,
    ``JWT_AUDIENCE``, ``JWT_JWKS_URI``, and ``JWT_CLAIM_NAMESPACE`` via ``current_app.config``.
    """
    if algorithms is None:
        algorithms = ["RS256"]

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:

            resolved_public_key = public_key or current_app.config.get("JWT_PUBLIC_KEY")

            resolved_audience = audience
            if resolved_audience is None:
                resolved_audience = current_app.config.get("JWT_AUDIENCE")

            resolved_jwks_uri = jwks_uri or current_app.config.get("JWT_JWKS_URI")

            if not resolved_audience:
                return make_response(jsonify({"error": "server_error", "detail": "Missing config: JWT_AUDIENCE"}), 500)

            jwks_client = (
                get_jwks_client(resolved_jwks_uri)
                if resolved_jwks_uri and not resolved_public_key
                else None
            )

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return make_response(jsonify({"error": "unauthenticated", "detail": "Missing or invalid Bearer token"}), 401)

            token = auth_header[7:]
            try:
                if jwks_client:
                    signing_key = jwks_client.get_signing_key_from_jwt(token).key
                elif resolved_public_key:
                    signing_key = resolved_public_key
                else:
                    return make_response(jsonify({"error": "unauthenticated", "detail": "No public key or JWKS URI configured"}), 500)

                claims = pyjwt.decode(
                    token,
                    key=signing_key,
                    algorithms=algorithms,
                    audience=resolved_audience,
                    options={"require": ["exp", "iat", "sub", "aud"]},
                )

                ns = _jwt_claim_namespace()
                actors_key = _claim_key("actors", ns)
                session_actors_key = _claim_key("session_actors", ns)
                roles_key = _claim_key("roles", ns)
                token_type_key = _claim_key("token_type", ns)

                auth_actors = claims.get(actors_key, [])
                if not isinstance(auth_actors, list):
                    auth_actors = []

                token_type = claims.get(token_type_key) or claims.get("token_type")
                if token_type == "service":
                    claims.pop(actors_key, None)
                    claims.pop(session_actors_key, None)
                    claims.pop(roles_key, None)
                else:
                    existing_session = claims.get(session_actors_key, [])
                    if not isinstance(existing_session, list):
                        existing_session = []
                    session_actors: list[str] = []
                    seen_session: set[str] = set()
                    allowed = _tier1_actor_classes()
                    for actor in [*existing_session, *auth_actors]:
                        if (
                            isinstance(actor, str)
                            and actor in allowed
                            and actor not in seen_session
                        ):
                            seen_session.add(actor)
                            session_actors.append(actor)
                    if session_actors:
                        claims[session_actors_key] = session_actors
                    actor_eligibility = session_actors if session_actors else auth_actors
                    if enforce_active_actor:
                        requested_actor = request.headers.get("X-Active-Actor")
                        if requested_actor:
                            if not SLUG_PATTERN.match(requested_actor):
                                return make_response(jsonify({"error": "bad_request", "detail": "Invalid actor format"}), 400)
                            if requested_actor not in actor_eligibility:
                                return make_response(jsonify({"error": "forbidden", "detail": "Active actor not authorized for this session"}), 403)
                            active_actors = [requested_actor]
                        else:
                            if len(auth_actors) > 1:
                                return make_response(
                                    jsonify({
                                        "error": "bad_request",
                                        "detail": "Multiple actors present but X-Active-Actor header is missing",
                                    }),
                                    400,
                                )
                            active_actors = auth_actors

                        claims[actors_key] = active_actors

                    if require_actor:
                        if not claims.get(actors_key):
                            return make_response(jsonify({"error": "forbidden", "detail": "Token must have at least one actor"}), 403)

                g.jwt_claims = claims
            except pyjwt.ExpiredSignatureError:
                return make_response(jsonify({"error": "unauthenticated", "detail": "Token expired"}), 401)
            except pyjwt.PyJWKClientError as e:
                return make_response(jsonify({"error": "unauthenticated", "detail": f"JWKS Error: {str(e)}"}), 500)
            except pyjwt.InvalidTokenError:
                return make_response(jsonify({"error": "unauthenticated", "detail": "Invalid token"}), 401)

            return f(*args, **kwargs)

        return decorated

    return decorator
