import os
from typing import Any, Optional
from flask import request, g, current_app
from werkzeug.exceptions import BadRequest
from authorization_in_the_middle.entities import build_entity_payload, entity_uid

def _get_namespace(namespace: Optional[str] = None) -> str:
    if namespace:
        return namespace
    if current_app and "CEDAR_NAMESPACE" in current_app.config:
        return current_app.config["CEDAR_NAMESPACE"]
    return os.environ.get("CEDAR_NAMESPACE", "cdp")

def extract_jwt_principal_uid(namespace: Optional[str] = None, default_type: str = "User") -> str:
    """
    Extracts the Cedar principal UID from g.jwt_claims.
    Must be used in conjunction with the authentication-in-the-middle @with_authentication decorator.
    """
    claims = getattr(g, "jwt_claims", None)
    if not claims:
        raise BadRequest("No JWT claims available on request context")
        
    sub = claims.get("sub", "")
    # Dynamically extract principal type if provided in claims, else use default
    ptype = claims.get("neosofia:principal_type", default_type)
    resolved_namespace = _get_namespace(namespace)
        
    return entity_uid(f"{resolved_namespace}::{ptype}", sub)

def extract_jwt_principal_entity(namespace: Optional[str] = None, default_type: str = "User") -> dict[str, Any]:
    """
    Parses g.jwt_claims to construct the principal's Cedar entity model payload flexibly.
    Must be used in conjunction with the authentication-in-the-middle @with_authentication decorator.
    """
    claims = getattr(g, "jwt_claims", None)
    if not claims:
        raise BadRequest("No JWT claims available on request context")
        
    sub = claims.get("sub", "")
    ptype = claims.get("neosofia:principal_type", default_type)
    
    # Pack dynamic attributes from claims
    attributes = {}
    for key, value in claims.items():
        if key.startswith("neosofia:"):
            attr_name = key.replace("neosofia:", "")
            if attr_name != "principal_type":
                attributes[attr_name] = value
                
    resolved_namespace = _get_namespace(namespace)
    return build_entity_payload(f"{resolved_namespace}::{ptype}", sub, attributes)
