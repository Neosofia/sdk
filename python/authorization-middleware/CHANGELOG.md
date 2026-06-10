# Changelog

Changes for consumers of the `authorization-in-the-middle` Python package.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

[0.4.23]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.23
[0.4.22]: https://github.com/Neosofia/sdk/releases/tag/authorization-in-the-middle/v0.4.22
