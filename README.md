# Neosofia SDK

Polyglot collection of shared packages for the Neosofia platform.

## Layout

```
python/
  logenvelope/           # Structured JSON logger (conforms to Neosofia/schemas log-v1.0.0.json)
```

Each package is independently versioned and published. Languages are
top-level directories; packages live under their language.

## Packages

| Package | Language | Distribution name | Purpose |
|---|---|---|---|
| [`logenvelope`](python/logenvelope) | Python | `logenvelope` | Structured JSON logger conforming to the platform log schema |

## Development

This repo is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) for the Python packages.

```
uv sync                                    # install all workspace deps
uv run --package logenvelope pytest    # test a single package
```

## Releasing a Python package

Wheels and GitHub Release assets are **CI-only** (`.github/workflows/publish.yml`). Do not upload `dist/*` manually.

1. Bump `version` in the package `pyproject.toml` and run `uv lock` at the repo root.
2. Commit and push to `main`.
3. Create the tag **on that commit** (tag name must match package version):
   ```bash
   git tag authentication-in-the-middle/v0.9.4
   git push origin refs/tags/authentication-in-the-middle/v0.9.4
   ```
4. Confirm the `publish` workflow succeeds. The tag must point at the commit that contains the version bump; otherwise validation fails with a version mismatch.

Supported tag prefixes: `logenvelope/v*`, `authentication-in-the-middle/v*`, `authorization-in-the-middle/v*`.

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Security

See [SECURITY.md](SECURITY.md).
