# authorization-in-the-middle

Shared Cedar authorization middleware for Neosofia platform services.

## Rosetta stone — REST, Cedar, and our words

Maps how we talk about APIs to what Cedar evaluates. Read top to bottom once; use the route table as the cheat sheet afterward.

### The authorization question

Every protected route answers one question:

```text
principal  +  action  +  resource
   who         what      on what
```

- **Principal** — who is acting. Almost always JWT **`sub`**, built in `resolve_principal()` (your service decides how: JWT claims, DB row, etc.). Not taken from the path.
- **Action** — what they want, e.g. `Action::"user:list"`. Bound via `Capabilities.*` on the route.
- **Resource** — what they act on: one `User`, the `UserCatalog` for “list users,” a `Service`, etc.

Policies only see those three UIDs plus **entity records** (attributes for principal and resource). They do not see HTTP or JWT directly.

### Glossary

| Term | Meaning |
|------|---------|
| **Principal** | The actor (`users::User` / `authentication::User`). |
| **Action** | The verb (`user:read`, `user:list`, …). |
| **Resource** | The target of the action (`User`, `UserCatalog`, `Service`, …). |
| **Entity** | [Cedar](https://docs.cedarpolicy.com/overview/terminology.html) name for a typed object with an id and **attributes** (`uid`, `attrs`, `parents`). In our code: the JSON from `build_entity_payload()`. |
| **Member** | One record — id from the path (`user_id`, `slug`). |
| **Catalog** | REST **collection** (list/create) — Cedar type `*Catalog`, fixed id (`user-catalog`). Same as “the list endpoint,” not a product catalog. |
| **Capability** | Service constant for an action string. |

`entities_fn` returns **`[principal_entity, resource_entity]`** — attribute data for who and what. The action is separate.

### Cedar entity record (brief)

UID in policies: `users::User::"aaa-111"` (type + id).

Record passed to the evaluator ([syntax](https://docs.cedarpolicy.com/auth/entities-syntax.html)):

```json
{
  "uid": { "__entity": { "type": "users::User", "id": "aaa-111" } },
  "attrs": { "uuid": "aaa-111", "tenantId": "tenant-xyz", "isOperator": true },
  "parents": []
}
```

“Entity” in code means this object — principal and resource each get one; the action does not.

### REST routes → Cedar

Principal on every row = JWT **`sub`**.

| You say | Example HTTP | Cedar **action** | Cedar **resource** | Resource entity id |
|---------|--------------|------------------|-------------------|-------------------|
| **List** users (paginate, search) | `GET /api/v1/users` | `user:list` | `users::UserCatalog` | Fixed `user-catalog` |
| **Create** a user | `POST /api/v1/users` | `user:create` | `users::UserCatalog` | Fixed `user-catalog` |
| **Get** one user | `GET /api/v1/users/{user_id}` | `user:read` | `users::User` | Path `user_id` |
| **Replace** one user (full body) | `PUT /api/v1/users/{user_id}` | `user:update` | `users::User` | Path `user_id` |
| **Update** one user (partial) | `PATCH /api/v1/users/{user_id}` | `user:update` | `users::User` | Path `user_id` |
| **Delete** one user | `DELETE /api/v1/users/{user_id}` | `user:delete` | `users::User` | Path `user_id` |
| **Get** a user’s audit history | `GET /api/v1/users/{user_id}/audits` | `user:read` | `users::User` | Path `user_id` |
| **Read** role picklists | `GET /api/v1/roles` | `role_catalog:read` | `users::RoleCatalog` | Fixed `role-catalog` |
| **Rotate** a service credential | `POST /api/services/{slug}/rotate` | `service:rotate` | `authentication::Service` | Path `slug` |

**Notes:** List/create target **`UserCatalog`** because the URL has no member id. **PUT** and **PATCH** often share `user:update`. **DELETE** is the usual REST shape — add `user:delete` to policy when you ship it (not on user v1). **Read role picklists** — `/roles` is the API path; Cedar uses `role_catalog:read` on a singleton catalog (static picklists), not `role:list`.

Example — list users:

```text
principal  = users::User::"aaa-111"                 ← JWT sub
action     = Action::"user:list"
resource   = users::UserCatalog::"user-catalog"
```

### Request flow

```text
Bearer JWT  →  authentication-in-the-middle  →  g.jwt_claims
                    ↓
         entities.resolve_principal()       →  principal entity
                    ↓
         path id or catalog constant        →  resource entity
                    ↓
         CedarEvaluator.is_authorized(...)
                    ↓
              allow → handler              deny → 403
```

Authn stays in `authentication-in-the-middle`; authz is this package + your `entities` + policies.

### `@with_security` (`rest=True`, default)

Infers `resource_fn` and `entities_fn` from `action` + path:

| Action shape | Infers |
|--------------|--------|
| `user:read`, `profile:read`, … | Member — `{Model}` + path arg `{model}_id` |
| `user:list`, `user:create`, … | Collection — `{Model}Catalog` + `{MODEL}_CATALOG_ID` |
| `role_catalog:read`, … | Catalog singleton — `RoleCatalog` + `ROLE_CATALOG_ID` |

**Path argument name** comes from the **action** (`user:read` → `user_id`), not by parsing your `@bp.route`. It must match `request.view_args` — if your route uses `/<slug>` or `/<tenant_uuid>`, pass `id_arg="slug"` or `id_arg="tenant_uuid"`. When the path is `/<user_id>`, omit `id_arg`.

Requires `src.authorization.entities`: `NAMESPACE`, `resolve_principal()` (or `load_principal_entity()`), and builders/loaders per conventions. Override `entities_fn` / `resource_fn` when layout does not match `src.services.{model}_service.get_{model}_or_404`.

## Usage

Typical platform route (REST inference — see Rosetta stone):

```python
from authorization_in_the_middle.security import with_security
from src.bootstrap.capabilities import Capabilities

@bp.route("/<user_id>", methods=["GET"])
@with_security(action=Capabilities.USER_READ, rate_limit="60 per minute")
def get_user(user_id: str):
    ...
```

Lower-level Cedar hook when you need full control:

```python
from authorization_in_the_middle import CedarEvaluator, FilesystemPolicySetSource, with_authorization
from flask import request

_evaluator = CedarEvaluator(
    policy_source=FilesystemPolicySetSource(settings.authorization_policies_dir),
)

@app.route("/patients/<patient_id>")
@with_authorization(
    _evaluator,
    principal_fn=lambda: ...,
    action=Capabilities.PATIENT_RECORD_READ,
    resource_fn=lambda: f'cdp::PatientRecord::"{request.view_args["patient_id"]}"',
    entities_fn=lambda: [...],
    context_fn=lambda: {"http_method": request.method},
)
def get_patient(patient_id):
    ...
```

## Architecture

```
Your Service (Python)
    ├── service-owned Cedar bundle
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
