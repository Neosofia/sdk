from functools import wraps
from typing import Any, Callable

import jwt as pyjwt
from flask import g, jsonify, make_response, request, current_app
import re

from authentication_in_the_middle.jwks import get_jwks_client

SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
_DEFAULT_CLAIM_NAMESPACE = "neosofia"


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
    enforce_active_role: bool = True,
    require_role: bool = False,
) -> Callable:
    """
    Decorator that validates a Bearer JWT using the provided public key or JWKS URI and audience.
    Stores the decoded JWT claims in flask.g.jwt_claims.
    If args are not provided, it falls back to current_app.config (e.g. JWT_PUBLIC_KEY, JWT_CLAIM_NAMESPACE)
    """
    if algorithms is None:
        algorithms = ["RS256"]

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            
            # Resolve config at request time if not explicitly provided
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
                    options={"require": ["exp", "iat", "sub", "aud"]}
                )

                ns = _jwt_claim_namespace()
                roles_key = _claim_key("roles", ns)
                session_roles_key = _claim_key("session_roles", ns)
                token_type_key = _claim_key("token_type", ns)

                auth_roles = claims.get(roles_key, claims.get("roles", []))
                if not isinstance(auth_roles, list):
                    auth_roles = []

                token_type = claims.get(token_type_key) or claims.get("token_type")
                if token_type == "service":
                    # Service tokens are service-to-service credentials and should
                    # not carry any user role information. Strip role claims
                    # entirely for downstream handlers.
                    claims.pop(roles_key, None)
                    claims.pop(session_roles_key, None)
                    claims.pop("roles", None)
                else:
                    if auth_roles:
                        # Full JWT role list for assignment / catalog scoping (UI may switch active role).
                        claims[session_roles_key] = list(auth_roles)
                    if enforce_active_role:
                        requested_role = request.headers.get("X-Active-Role")
                        if requested_role:
                            if not SLUG_PATTERN.match(requested_role):
                                return make_response(jsonify({"error": "bad_request", "detail": "Invalid role format"}), 400)
                            if requested_role not in auth_roles:
                                return make_response(jsonify({"error": "forbidden", "detail": "Active role not authorized for this session"}), 403)
                            active_roles = [requested_role]
                        else:
                            if len(auth_roles) > 1:
                                return make_response(jsonify({"error": "bad_request", "detail": "Multiple roles present but X-Active-Role header is missing"}), 400)
                            active_roles = auth_roles

                        claims[roles_key] = active_roles

                    if require_role:
                        if not claims.get(roles_key):
                            return make_response(jsonify({"error": "forbidden", "detail": "Token must have at least one role"}), 403)

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
