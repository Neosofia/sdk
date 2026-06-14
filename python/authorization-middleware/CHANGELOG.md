# Changelog

Changes for consumers of the `authorization-in-the-middle` Python package.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.7.0] - 2026-06-14

### Added

- Synthesized REST Cedar builders when services omit named hooks: catalog, member, and write entities are composed from `NAMESPACE`, action inference, and optional `registry_{model}_cedar_attrs` / `member_attrs`.
- `@with_security(catalog_id_from=…, catalog_attrs=…)` for tenant-scoped or attributed catalogs without `entities_fn` / `resource_fn` pairs.
- `@with_security(resource_type=…, catalog_id=…)` forces fixed catalog/singleton resources for custom actions (e.g. `user:provision` on `UserProvisioning`).

### Changed

- Route inference uses the **last** noun for nested scoped collections and member routes; earlier nouns with matching path params become catalog scope (`tenant_uuid` → `tenantId`). Compound subpaths without scope (e.g. `/idp/failed-authentications`) still use the first noun.
- `@with_security` auto-applies inferred `catalog_id_from` / `catalog_attrs` on nested collection routes when not explicitly overridden.
- Named `build_{model}_catalog_entity` / `build_write_{model}_entity` hooks are optional overrides; standard CRUD routes need only `NAMESPACE`, `resolve_principal()`, and a member attrs mapper.

## [0.6.0] - 2026-06-14

### Added

- Shared JWT principal builders in `flask_identity`: `principal_cedar_attrs`, `build_jwt_principal_entity`, `build_service_principal_entity`, and `resolve_jwt_principal` — standard Cedar principal attrs (tier-1 flags, roles, tenant scope) without per-service duplication.
- `resolve_jwt_principal(..., extra_attrs=…)` for service-specific principal attrs (e.g. care-episode demo template UUID).

### Changed

- `extract_jwt_principal_entity` delegates to `build_jwt_principal_entity` for consistent principal attrs across services.

## [0.5.0] - 2026-06-13

### Added

- OpenAPI-backed request validation for inferred REST writes (`openapi_request`) — validates create/update bodies against the service `openapi.json`, derives Cedar `presentFields` from raw JSON keys, and exposes `bind_openapi_spec` / `init_openapi_spec`.
- REST authorization wiring modules: `action_scope`, `route_inference`, `rest_entities`, and `service_conventions` — infer CRUD **Action**, **Catalog** vs **Member** scope, path id resolution, and default `resource_fn` / `entities_fn` for standard Flask routes.
- Write payload helpers in `payload`: `present_field_names`, `align_shared_uid_entity_attrs`, `canonical_string_set`, `write_exact_set_field_attrs`, and `write_role_namespace_attrs` — attach `presentFields`, `rolesExact`, and `roleNamespaces` to Cedar write entities.
- `cedar_attrs.tier1_actor_flags` — maps JWT actor lists to Cedar `isOperator`, `isClinician`, `isStudy`, etc.
- `flask_request.request_view_arg` — shared Flask view-arg access for entity builders.
- Catalog entity builders in `entities`: `build_catalog_entity`, `catalog_resource_uid`, and `catalog_entities`.
- Public exports on the package root for OpenAPI init, payload helpers, catalog builders, and JWT identity utilities used by service `entities` modules.

### Changed

- `with_security` automatically validates OpenAPI on inferred create/update, sets `g.validated_body`, `g.present_fields`, and `g.write_resource`, and authorizes writes via service `plan_*_from_openapi` hooks before the route handler runs.
- Self-update authorization merges principal and resource attrs when UIDs match so Cedar forbid rules see tier-1 flags alongside write `presentFields`.
- README expanded with REST ↔ Cedar glossary, route table, and write-entity attribute reference.

## [0.4.23] - 2026-06-10

### Fixed

- Catalog type inference for hyphenated Cedar actions (e.g. `care-episode:list` → `CareEpisodeCatalog`, not `CareEpisode`). Models whose names end in `_catalog` (e.g. `role_catalog`) are unchanged.

### Changed

- README and decorator docs: drop stale `Capabilities.*` examples; document inline `action='Action::"…"'` and bare `@with_security()` inference.

## [0.4.22] - 2026-06-10

### Added

- `with_security` infers CRUD **Action** from HTTP method and route when `action` is omitted.
- Automatic **Catalog** vs **Member** scope for `resource_fn` / `entities_fn` (list/create and catalog-style paths such as `/audits` without a path id).
- Path id resolution: explicit `id_arg`, first route parameter, then `{model}_uuid` fallback.
- `inflect` dependency for singularizing resource names from URL segments.

### Changed

- Removed `rest` parameter from `with_security`; pass only overrides (`action`, `id_arg`, `resource_fn`, `entities_fn`, etc.).
- Reorganized `security.py` with glossary-aligned module docstring and section comments (no new naming patterns).
- Entity records for inferred routes are built from path parameters only (no DB loader during authz).

### Removed

- `rest=False` toggle and related manual catalog/member wiring for standard REST routes.

[0.7.0]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.7.0
[0.6.0]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.6.0
[0.5.0]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.5.0
[0.4.23]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.23
[0.4.22]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.22
