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

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

## Security

See [SECURITY.md](SECURITY.md).
