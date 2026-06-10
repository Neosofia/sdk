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
- **Action** — what they want, e.g. `Action::"user:list"`. Inferred from HTTP method + path, or passed explicitly on `@with_security`.
- **Resource** — what they act on: one `User`, the `UserCatalog` for “list users,” a `Service`, etc.

Policies only see those three UIDs plus **entity records** (attributes for principal and resource). They do not see HTTP or JWT directly.

### Glossary

| Term | Meaning |
|------|---------|
| **Principal** | The actor (`users::User` / `authentication::User`). |
| **Action** | The verb (`user:read`, `user:list`, …). |
| **Resource** | The target of the action (`User`, `UserCatalog`, `Service`, …). |
| **Entity** | [Cedar](https://docs.cedarpolicy.com/overview/terminology.html) name for a typed object with an id and **attributes** (`uid`, `attrs`, `parents`). In our code: the JSON from `build_entity_payload()`. |
| **Member** | One record — id from the path (`user_uuid`, `slug`). |
| **Catalog** | REST **collection** (list/create) — Cedar type `*Catalog`, fixed id (`user-catalog`). Same as “the list endpoint,” not a product catalog. |

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
| **Get** one user | `GET /api/v1/users/{user_uuid}` | `user:read` | `users::User` | Path `user_uuid` |
| **Replace** one user (full body) | `PUT /api/v1/users/{user_uuid}` | `user:update` | `users::User` | Path `user_uuid` |
| **Update** one user (partial) | `PATCH /api/v1/users/{user_uuid}` | `user:update` | `users::User` | Path `user_uuid` |
| **Delete** one user | `DELETE /api/v1/users/{user_uuid}` | `user:delete` | `users::User` | Path `user_uuid` |
| **Get** a user’s audit history | `GET /api/v1/users/{user_uuid}/audits` | `user:read` | `users::User` | Path `user_uuid` |
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
              (typically ``extract_jwt_principal_entity`` — sets ``attrs.uuid`` from ``sub`` for human User principals)
                    ↓
         path id or catalog constant        →  resource entity
                    ↓
         CedarEvaluator.is_authorized(...)
                    ↓
              allow → handler              deny → 403
```

Authn stays in `authentication-in-the-middle`; authz is this package + your `entities` + policies.

### Scoped catalog entities

Some catalog routes scope authorization to a subject that is not in the path — e.g. list messages for a user via `?user_uuid=` or JSON body. Use `request_scoped_uuid()` in `build_*_catalog_resource()`:

```python
from authorization_in_the_middle import extract_jwt_principal_entity, request_scoped_uuid
from authorization_in_the_middle.entities import build_entity_payload

def build_message_catalog_resource():
    attrs = {}
    if user_uuid := request_scoped_uuid("user_uuid"):
        attrs["userUuid"] = user_uuid
        if tenant := _tenant_for(user_uuid):
            attrs["tenantId"] = tenant
    return build_entity_payload(f"{NAMESPACE}::MessageCatalog", MESSAGE_CATALOG_ID, attrs)
```

Resolution order: Flask path arg → query param → JSON body → principal `attrs.uuid` when the JWT includes a matching actor (default: `patient`). On nested REST routes, the path value wins even when query or body also carry the param. Clinicians and other actors must supply scope explicitly when it is not in the path. Pass `self_for_actors=()` to disable self-scope.

### `@with_security`

Omit ``action`` to infer CRUD from HTTP method + path. Pass any parameter explicitly to override; omitted ``resource_fn`` / ``entities_fn`` are inferred from ``action`` + path:

| Action shape | Infers |
|--------------|--------|
| `user:read`, `profile:read`, … | Member — `{Model}` + path arg `{model}_uuid` (or inferred from route rule) |
| `user:list`, `user:create`, … | Collection — `{Model}Catalog` + `{MODEL}_CATALOG_ID` |
| `role_catalog:read`, … | Catalog singleton — `RoleCatalog` + `ROLE_CATALOG_ID` |

**Path argument name** is inferred from the route rule (`/<tenant_uuid>` → `tenant_uuid`). When that fails, the fallback is `{model}_uuid`. Pass `id_arg` only for non-uuid keys such as `slug`.

Requires `src.authorization.entities`: `NAMESPACE`, `resolve_principal()` (or `load_principal_entity()`), and builders/loaders per conventions. Override `entities_fn` / `resource_fn` when layout does not match `src.services.{model}_service.get_{model}_or_404`.

## Usage

Typical platform route (REST inference — see Rosetta stone):

```python
from authorization_in_the_middle.security import with_security

@bp.route("", methods=["GET"])
@with_security(rate_limit="60 per minute")
def list_users():
    ...

@bp.route("/<user_uuid>", methods=["GET"])
@with_security(rate_limit="60 per minute", resource_loader=get_user_or_404)
def get_user(user_uuid: str):
    ...

@bp.route("/<slug>/rotate", methods=["POST"])
@with_security(action='Action::"service:rotate"', id_arg="slug")
def rotate_service(slug: str):
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
    action='Action::"document:read"',
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

Cedar policies reason over principal, action, and resource — not HTTP details. Prefer
bare `@with_security()` where inference matches your policy vocabulary; pass
`action='Action::"…"'` only when the route noun or verb does not match Cedar.

## Sources and Evaluators

| Class | When to use |
|---|---|
| `FilesystemPolicySetSource` | Default — policy lives in the service repo and is loaded from disk |
| `HttpPolicySetSource` | Optional — fetch a shared bundle from a central control-plane service |
| `PolicySetClient` | Backwards-compatible alias for `HttpPolicySetSource` |
| `CedarEvaluator` | Production — in-process via cedarpy + a policy source |
| `StubEvaluator` | Tests — configurable allow/deny via a callable |

See the example service template at `templates/python/service` for a concrete
service-owned bundle layout, env-driven policy directory configuration, and
`@with_security` route bindings.
