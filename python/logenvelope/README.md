# logenvelope

Structured JSON logger for web service platforms. Output conforms
to the [log envelope schema](https://github.com/Neosofia/schemas/blob/main/log-v1.0.0.json).

## Install

### With `uv` (recommended)

Add to your `pyproject.toml`:

```toml
dependencies = [
    "logenvelope @ git+https://github.com/Neosofia/sdk.git#subdirectory=python/logenvelope",
]
```

Then sync:

```bash
uv sync
```

Or in one command:

```bash
uv add "logenvelope @ git+https://github.com/Neosofia/sdk.git#subdirectory=python/logenvelope"
```

### With pip

```bash
pip install "logenvelope @ git+https://github.com/Neosofia/sdk.git#subdirectory=python/logenvelope"
```

## Usage

```python
from logenvelope import setup_logging, log_event, emits

# At service startup:
setup_logging("authentication")  # service name

# Declare events a route may emit (introspection only):
@emits("platform_token_issued", "platform_token_denied")
def issue_token():
    ...

# Emit a structured event:
log_event(
    "platform_token_issued",
    actor="clinician:usr_abc123",
    trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
)
```

## Gunicorn integration

If your service uses Gunicorn, use the package helper to emit structured
access logs with discrete HTTP fields instead of raw text.

```python
from logenvelope.gunicorn import JSONLogger

logger_class = JSONLogger
```

Gunicorn access log records are enriched with fields like `client.ip`, 
`http.method`, `http.target`, `http.status_code`, and `http.response_time_ms`.

Each `log_event` call produces a single JSON line with `timestamp`,
`level`, `message`, `event_type`, and any keyword arguments merged in.
The output validates against the [`log-v1.0.0.json`](https://github.com/Neosofia/schemas/blob/main/log-v1.0.0.json)
schema published in the [Neosofia/schemas](https://github.com/Neosofia/schemas) repository.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Minimum log level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

## License

Apache-2.0
