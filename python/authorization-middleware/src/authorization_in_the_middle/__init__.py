"""
authorization-in-the-middle

Shared Cedar authorization middleware for Neosofia platform services.
Provides a Flask route decorator that loads Cedar policies from a policy
source, evaluates them locally, and enforces allow/deny before the route
handler is invoked.

Typical usage
-------------
from authorization_in_the_middle import CedarEvaluator, FilesystemPolicySetSource, with_authorization

_evaluator = CedarEvaluator(
    policy_source=FilesystemPolicySetSource("./policies")
)

@app.route("/patients/<patient_id>")
@with_authorization(
    _evaluator,
    principal_fn=lambda: request.headers["X-Principal"],
    action='Action::"patient:view"',
    resource_fn=lambda: f'cdp::PatientRecord::"{request.view_args["patient_id"]}"',
    entities_fn=lambda: _resolve_entities(request),
)
def get_patient(patient_id):
    ...
"""

from authorization_in_the_middle.decorators import with_authorization
from authorization_in_the_middle.evaluator import CedarEvaluator, StubEvaluator
from authorization_in_the_middle.entities import (
    ID_PLACEHOLDER,
    build_catalog_entity,
    build_entity_payload,
    build_entity_ref,
    catalog_entities,
    catalog_resource_uid,
    entity_uid,
    is_id_placeholder,
    resolve_entity_id,
)
from authorization_in_the_middle.openapi_request import bind_openapi_spec, init_openapi_spec
from authorization_in_the_middle.audit_attribution import (
    AuditActor,
    CLIENT_AUDIT_ATTRIBUTION_FIELDS,
    HUMAN_AUDIT_ACTOR_TYPE,
    SERVICE_AUDIT_ACTOR_TYPE,
    reject_client_audit_attribution,
    request_audit_actor,
)
from authorization_in_the_middle.flask_identity import (
    build_jwt_principal_entity,
    build_service_principal_entity,
    extract_jwt_principal_uid,
    extract_jwt_principal_entity,
    jwt_claim_principal_attributes,
    principal_cedar_attrs,
    request_scoped_uuid,
    resolve_jwt_principal,
)
from authorization_in_the_middle.payload import (
    align_shared_uid_entity_attrs,
    canonical_string_set,
    present_field_names,
    write_exact_set_field_attrs,
)
from authorization_in_the_middle.policy_sources import (
    FilesystemPolicySetSource,
    StaticPolicySetSource,
)

version = "0.7.7"
__all__ = [
    "AuditActor",
    "CLIENT_AUDIT_ATTRIBUTION_FIELDS",
    "HUMAN_AUDIT_ACTOR_TYPE",
    "SERVICE_AUDIT_ACTOR_TYPE",
    "reject_client_audit_attribution",
    "request_audit_actor",
    "CedarEvaluator",
    "FilesystemPolicySetSource",
    "StaticPolicySetSource",
    "StubEvaluator",
    "bind_openapi_spec",
    "init_openapi_spec",
    "with_authorization",
    "ID_PLACEHOLDER",
    "build_catalog_entity",
    "build_entity_payload",
    "build_entity_ref",
    "catalog_entities",
    "catalog_resource_uid",
    "entity_uid",
    "is_id_placeholder",
    "resolve_entity_id",
    "extract_jwt_principal_uid",
    "extract_jwt_principal_entity",
    "jwt_claim_principal_attributes",
    "principal_cedar_attrs",
    "build_jwt_principal_entity",
    "build_service_principal_entity",
    "resolve_jwt_principal",
    "request_scoped_uuid",
    "align_shared_uid_entity_attrs",
    "canonical_string_set",
    "present_field_names",
    "write_exact_set_field_attrs",
]
