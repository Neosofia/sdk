from functools import wraps
from typing import Any, Callable

import jwt as pyjwt
from flask import g, jsonify, make_response, request

def with_authentication(public_key: str | None, issuer: str, audience: str, algorithms: list[str] | None = None, jwks_uri: str | None = None) -> Callable:
    """
    Decorator that validates a Bearer JWT using the provided public key or JWKS URI, issuer, and audience.
    Stores the decoded JWT claims in flask.g.jwt_claims.
    """
    if algorithms is None:
        algorithms = ["RS256"]
        
    jwks_client = pyjwt.PyJWKClient(jwks_uri) if jwks_uri else None

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return make_response(jsonify({"error": "unauthenticated", "detail": "Missing or invalid Bearer token"}), 401)
            
            token = auth_header[7:]
            try:
                if jwks_client:
                    signing_key = jwks_client.get_signing_key_from_jwt(token).key
                elif public_key:
                    signing_key = public_key
                else:
                    return make_response(jsonify({"error": "unauthenticated", "detail": "No public key or JWKS URI configured"}), 500)

                claims = pyjwt.decode(
                    token,
                    key=signing_key,
                    algorithms=algorithms,
                    issuer=issuer,
                    audience=audience,
                    options={"require": ["exp", "iat", "iss", "sub", "aud"]}
                )
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
