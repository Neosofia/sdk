# Changelog

Changes for consumers of the `authorization-in-the-middle` Python package.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

[0.5.0]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.5.0
[0.4.23]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.23
[0.4.22]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.22
