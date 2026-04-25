# neosofia-logger

Structured JSON logger for Neosofia platform services. Output conforms
to the [log envelope schema](https://github.com/Neosofia/schemas/blob/main/log-v1.0.0.json).

## Install

```
pip install "neosofia-logger @ git+https://github.com/Neosofia/sdk.git#subdirectory=python/logger"
```

## Usage

```python
from neosofia_logger import setup_logging, log_event, emits

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

Each `log_event` call produces a single JSON line with `timestamp`,
`level`, `message`, `event_type`, and any keyword arguments merged in.
The output validates against the platform `log-v1.0.0.json` schema.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Minimum log level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

## License

Apache-2.0
