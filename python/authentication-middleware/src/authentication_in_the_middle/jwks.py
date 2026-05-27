from functools import lru_cache

import jwt as pyjwt


@lru_cache(maxsize=8)
def get_jwks_client(jwks_uri: str) -> pyjwt.PyJWKClient:
    """Process-wide JWKS client; PyJWT defaults cache the JWK set for 5 minutes."""
    return pyjwt.PyJWKClient(jwks_uri)
