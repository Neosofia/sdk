from functools import wraps
from typing import Any, Callable

import jwt as pyjwt
from flask import g, jsonify, make_response, request, current_app
import re
import os

SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

def with_authentication(
    public_key: str | None = None,
    issuer: str | None = None,
    audience: str | None = None,
    algorithms: list[str] | None = None,
    jwks_uri: str | None = None,
    enforce_active_role: bool = True
) -> Callable:
    """
    Decorator that validates a Bearer JWT using the provided public key or JWKS URI, issuer, and audience.
    Stores the decoded JWT claims in flask.g.jwt_claims.
    If args are not provided, it falls back to current_app.config (e.g. JWT_PUBLIC_KEY)
    """
    if algorithms is None:
        algorithms = ["RS256"]

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            
            # Resolve config at request time if not explicitly provided
            resolved_public_key = public_key or current_app.config.get("JWT_PUBLIC_KEY")
            resolved_issuer = issuer or current_app.config.get("JWT_ISSUER")
            
            resolved_audience = audience
            if resolved_audience is None:
                resolved_audience = current_app.config.get("SERVICE_NAME")
            
            resolved_jwks_uri = jwks_uri or current_app.config.get("JWT_JWKS_URI")
            
            if not resolved_issuer or not resolved_audience:
                return make_response(jsonify({"error": "server_error", "detail": f"Missing config. issuer={resolved_issuer}, audience={resolved_audience}"}), 500)

            jwks_client = pyjwt.PyJWKClient(resolved_jwks_uri) if resolved_jwks_uri else None
            
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
                    issuer=resolved_issuer,
                    audience=resolved_audience,
                    options={"require": ["exp", "iat", "iss", "sub", "aud"]}
                )
                
                if enforce_active_role:
                    auth_roles = claims.get("neosofia:roles", claims.get("roles", []))
                    if not isinstance(auth_roles, list):
                        auth_roles = []
                        
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
                        
                    claims["neosofia:roles"] = active_roles

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
