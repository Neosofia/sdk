# Neosofia SDK

Polyglot collection of shared packages for the Neosofia platform.

## Layout

```
python/
  logger/                # Structured JSON logger (conforms to neosofia/schemas log-v1.0.0.json)
```

Each package is independently versioned and published. Languages are
top-level directories; packages live under their language.

## Packages

| Package | Language | Distribution name | Purpose |
|---|---|---|---|
| [`logger`](python/logger) | Python | `neosofia-logger` | Structured JSON logger conforming to the platform log schema |

## Development

This repo is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) for the Python packages.

```
uv sync                                    # install all workspace deps
uv run --package neosofia-logger pytest    # test a single package
```

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Security

See [SECURITY.md](SECURITY.md).
