"""
Cedar policy evaluators.

CedarEvaluator — in-process evaluator using the cedarpy library (PyO3 Rust bindings).
    Fetches the current policy set from the Authorization Service via PolicySetClient
    and evaluates requests locally — no sidecar process required.  Each service is
    responsible for installing cedarpy (which ships a pre-compiled Rust wheel) in its
    Dockerfile.

StubEvaluator — configurable evaluator for tests.  Calls an injected callable
    so tests can assert on the arguments and control the decision.
"""

from typing import Any, Callable

from cedarpy import is_authorized as _cedar_is_authorized


class CedarEvaluator:
    """
    In-process Cedar policy evaluator backed by cedarpy (PyO3 Rust bindings).

    Fetches the current policy set from the Authorization Service on each call;
    caching is handled transparently by the supplied PolicySetClient.

    Args:
        policy_client:  A PolicySetClient instance pointed at the Authorization
                        Service, e.g. PolicySetClient(base_url="http://authorization:8006").
    """

    def __init__(self, policy_client) -> None:
        self._policy_client = policy_client

    def is_authorized(
        self,
        principal: str,
        action: str,
        resource: str,
        entities: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate whether principal may perform action on resource.

        Retrieves the current (cached) policy set, concatenates all policy files
        into a single Cedar policy string, then calls the Cedar engine in-process
        via cedarpy.

        Args:
            principal:  Cedar entity UID string, e.g. 'cdp::Patient::"p1"'.
            action:     Cedar action UID string, e.g. 'Action::"patient:view"'.
            resource:   Cedar entity UID string, e.g. 'cdp::PatientRecord::"r1"'.
            entities:   List of Cedar entity dicts needed for evaluation.
            context:    Optional Cedar context dict.

        Returns:
            True if the decision is Allow, False for Deny (fail-closed on error).
        """
        policy_set = self._policy_client.get_policy_set()
        policies_text = "\n\n".join(p["content"] for p in policy_set["policies"])
        request = {
            "principal": principal,
            "action": action,
            "resource": resource,
            "context": context or {},
        }
        result = _cedar_is_authorized(request, policies_text, entities)
        return result.allowed


class StubEvaluator:
    """
    Configurable stub evaluator for tests and local development.

    The decision is delegated to a user-supplied callable so tests can:
      - Assert on the exact principal / action / resource values.
      - Control whether a request is allowed or denied.
      - Simulate evaluation failures.

    Args:
        decide_fn:  Callable(principal, action, resource, entities, context) -> bool.
                    Defaults to always-deny so tests must explicitly opt in.

    Example — always allow::

        evaluator = StubEvaluator(decide_fn=lambda *a, **k: True)

    Example — record calls and allow specific action::

        calls = []
        def decide(principal, action, resource, entities, context):
            calls.append((principal, action, resource))
            return action == 'Action::"patient:view"'

        evaluator = StubEvaluator(decide_fn=decide)
    """

    def __init__(self, decide_fn: Callable[..., bool] | None = None) -> None:
        self._decide = decide_fn or (lambda *a, **k: False)

    def is_authorized(
        self,
        principal: str,
        action: str,
        resource: str,
        entities: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> bool:
        return bool(self._decide(principal, action, resource, entities, context or {}))
