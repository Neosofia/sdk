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

from authorization_in_the_middle.client import PolicySetClient
from authorization_in_the_middle.decorators import with_authorization
from authorization_in_the_middle.evaluator import CedarEvaluator, StubEvaluator
from authorization_in_the_middle.policy_sources import (
    FilesystemPolicySetSource,
    HttpPolicySetSource,
    StaticPolicySetSource,
)

__version__ = "0.1.0"
__all__ = [
    "CedarEvaluator",
    "FilesystemPolicySetSource",
    "HttpPolicySetSource",
    "PolicySetClient",
    "StaticPolicySetSource",
    "StubEvaluator",
    "with_authorization",
]
