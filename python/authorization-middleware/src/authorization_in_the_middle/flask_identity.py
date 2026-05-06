from typing import Any
from flask import request
from werkzeug.exceptions import BadRequest
from authorization_in_the_middle.entities import build_entity_payload, entity_uid

def _required_header(name: str) -> str:
    value = request.headers.get(name, "").strip()
    if not value:
        raise BadRequest()
    return value

def extract_platform_principal_uid(namespace: str) -> str:
    """
    Extracts the Neosofia standard X-Principal-Id and X-Principal-Type HTTP headers
    and returns a formatted Cedar principal UID.
    """
    ptype = _required_header("X-Principal-Type").lower()
    pid = _required_header("X-Principal-Id")
    if ptype not in {"patient", "clinician"}:
        raise BadRequest()
    
    entity_name = {"patient": "Patient", "clinician": "Clinician"}[ptype]
    return entity_uid(f"{namespace}::{entity_name}", pid)

def extract_platform_principal_entity(namespace: str) -> dict[str, Any]:
    """
    Parses Neosofia identity headers to construct the principal's Cedar entity model payload.
    Provides standard mapped attributes like roles and clinic_id for clinicians.
    """
    ptype = _required_header("X-Principal-Type").lower()
    pid = _required_header("X-Principal-Id")
    
    if ptype == "patient":
        return build_entity_payload(f"{namespace}::Patient", pid, {})
    
    if ptype == "clinician":
        roles = [r.strip() for r in request.headers.get("X-Roles", "").split(",") if r.strip()]
        if not roles:
            raise BadRequest()
        
        clinic_id = _required_header("X-Clinic-Id")
        return build_entity_payload(
            f"{namespace}::Clinician",
            pid,
            {"role": roles[0], "clinic_id": clinic_id},
        )
    
    raise BadRequest()
