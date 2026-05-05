# authorization-in-the-middle

Shared Cedar authorization middleware for Neosofia platform services.

## Usage

```python
from authorization_in_the_middle import CedarEvaluator, PolicySetClient, with_authorization
from flask import request

_evaluator = CedarEvaluator(
    policy_client=PolicySetClient(base_url="http://authorization:8006")
)

@app.route("/patients/<patient_id>")
@with_authorization(
    _evaluator,
    principal_fn=lambda: request.headers["X-Principal"],
    action='Action::"patient:view"',
    resource_fn=lambda: f'cdp::PatientRecord::"{request.view_args["patient_id"]}"',
    entities_fn=lambda: resolve_entities(request),
)
def get_patient(patient_id):
    ...
```

## Architecture

```
Your Service (Python)
  ├── with_authorization decorator
  │     └── CedarEvaluator
  │           ├── PolicySetClient  →  GET /api/policies/version  (cheap poll)
  │           │                   →  GET /api/policies           (full fetch on change)
  │           └── cedarpy (Rust)  →  evaluates policies in-process
  └── Authorization Service       →  serves Cedar policy files
```

`cedarpy` ships a pre-compiled Rust wheel — no sidecar, no subprocess.  Each service
must include `cedarpy` in its Dockerfile (it is a runtime dependency of this package).

## Evaluators

| Class | When to use |
|---|---|
| `CedarEvaluator` | Production — in-process via cedarpy + PolicySetClient |
| `StubEvaluator` | Tests — configurable allow/deny via a callable |
