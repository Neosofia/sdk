"""
Flask route decorator for Cedar-based authorization.

with_authorization wraps a Flask view function and:
  1. Resolves the principal and resource from the current request via callables.
  2. Delegates the is_authorized decision to the supplied evaluator.
  3. Returns 403 Forbidden if the evaluator denies the request.
  4. Returns 503 Service Unavailable if the evaluator raises (fail-closed).
"""

from functools import wraps
from typing import Any, Callable

from flask import jsonify, make_response
from werkzeug.exceptions import BadRequest, NotFound


def with_authorization(
    evaluator,
    principal_fn: Callable[[], str],
    action: str,
    resource_fn: Callable[[], str],
    entities_fn: Callable[[], list[dict[str, Any]]] | None = None,
    context_fn: Callable[[], dict[str, Any]] | None = None,
    log_event: Callable = lambda *a, **k: None,
) -> Callable:
    """
    Decorator factory that enforces Cedar authorization on a Flask route.

    Args:
        evaluator:     An object with is_authorized(principal, action, resource,
                   entities, context) -> bool. Use CedarEvaluator in
                   production and StubEvaluator in tests. Create the
                   evaluator once at module level — its policy source may
                   cache bundles between requests.
        principal_fn:  Zero-argument callable invoked at request time to return
                       the Cedar principal UID string, e.g.
                       ``lambda: request.headers["X-Principal"]``.
        action:        Cedar action UID string, fixed at decoration time, e.g.
                   ``Capabilities.PATIENT_RECORD_READ``.
        resource_fn:   Zero-argument callable invoked at request time to return
                       the Cedar resource UID string, e.g.
                       ``lambda: f'cdp::PatientRecord::"{request.view_args["id"]}"'``.
        entities_fn:   Optional zero-argument callable that returns the list of
                       Cedar entity dicts needed for evaluation.  Defaults to an
                       empty list (sufficient when the evaluator resolves entities
                       itself, e.g. cedar-agent with pre-loaded data).
        context_fn:    Optional zero-argument callable that returns Cedar
                   request context derived from the current request.
        log_event:     Optional structured-logging callable with the same signature
                       as logenvelope's log_event(event_type, **kwargs).

    Returns:
        A decorator suitable for use with @with_authorization(...).

    Example::

        _evaluator = CedarEvaluator(policy_source=policy_source)

        @app.route("/patients/<patient_id>")
        @with_authorization(
            _evaluator,
            principal_fn=lambda: request.headers["X-Principal"],
            action='Action::"patient:view"',
            resource_fn=lambda: f'cdp::PatientRecord::"{request.view_args["patient_id"]}"',
        )
        def get_patient(patient_id):
            return jsonify({"patient_id": patient_id})
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs) -> Any:
            try:
                principal = principal_fn()
                resource = resource_fn()
                entities = entities_fn() if entities_fn else []
                context = context_fn() if context_fn else {}
                allowed = evaluator.is_authorized(principal, action, resource, entities, context)
            except BadRequest as exc:
                log_event(
                    "authorization.invalid_request",
                    route=f.__name__,
                    action=action,
                    error_type=type(exc).__name__,
                )
                return make_response(jsonify({"error": "invalid_request"}), 400)
            except NotFound as exc:
                log_event(
                    "authorization.resource_not_found",
                    route=f.__name__,
                    action=action,
                    error_type=type(exc).__name__,
                )
                return make_response(jsonify({"error": "not_found"}), 404)
            except Exception as exc:
                log_event(
                    "authorization.evaluation_error",
                    route=f.__name__,
                    action=action,
                    error_type=type(exc).__name__,
                )
                return make_response(
                    jsonify({"error": "authorization_unavailable"}), 503
                )

            if not allowed:
                log_event(
                    "authorization.denied",
                    route=f.__name__,
                    principal=principal,
                    action=action,
                    resource=resource,
                )
                return make_response(jsonify({"error": "forbidden"}), 403)

            log_event(
                "authorization.allowed",
                route=f.__name__,
                principal=principal,
                action=action,
                resource=resource,
            )
            return f(*args, **kwargs)

        return decorated

    return decorator
