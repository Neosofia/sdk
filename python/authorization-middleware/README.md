# authorization-in-the-middle

Shared Cedar authorization middleware for Neosofia platform services.

## Usage

```python
from authorization_in_the_middle import CedarEvaluator, FilesystemPolicySetSource, with_authorization
from flask import request

_evaluator = CedarEvaluator(
        policy_source=FilesystemPolicySetSource(settings.authorization_policies_dir)
)

@app.route("/patients/<patient_id>")
@with_authorization(
    _evaluator,
    principal_fn=lambda: request.headers["X-Principal"],
        action=Capabilities.PATIENT_RECORD_READ,
    resource_fn=lambda: f'cdp::PatientRecord::"{request.view_args["patient_id"]}"',
    entities_fn=lambda: resolve_entities(request),
        context_fn=lambda: {"http_method": request.method},
)
def get_patient(patient_id):
    ...
```

## Architecture

```
Your Service (Python)
    ├── service-owned Cedar bundle
    │     ├── schema.cedar.json
    │     └── *.cedar
  ├── with_authorization decorator
  │     └── CedarEvaluator
    │           ├── FilesystemPolicySetSource  →  local bundle
    │           ├── HttpPolicySetSource        →  optional shared bundle source
  │           └── cedarpy (Rust)  →  evaluates policies in-process
    └── Service route handler       →  owns resource/entity loading
```

`cedarpy` ships a pre-compiled Rust wheel — no sidecar, no subprocess.  Each service
must include `cedarpy` in its Dockerfile (it is a runtime dependency of this package).

Use capability constants in service code instead of encoding transport details into
the Cedar action vocabulary. A route binds to a capability; Cedar policies then reason
over resource facts, relationships, and request context.

## Sources and Evaluators

| Class | When to use |
|---|---|
| `FilesystemPolicySetSource` | Default — policy lives in the service repo and is loaded from disk |
| `HttpPolicySetSource` | Optional — fetch a shared bundle from a central control-plane service |
| `PolicySetClient` | Backwards-compatible alias for `HttpPolicySetSource` |
| `CedarEvaluator` | Production — in-process via cedarpy + a policy source |
| `StubEvaluator` | Tests — configurable allow/deny via a callable |

See the example service template at `templates/python/authorization` for a concrete
service-owned bundle layout, env-driven policy directory configuration, and
capability-to-route bindings.
