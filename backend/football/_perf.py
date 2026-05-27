import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone


def _emit(event: dict) -> None:
    """Emit a structured JSON event to stdout.

    Bypasses the logging framework (which Uvicorn suppresses in
    Docker containers) and writes directly to stdout where EB / Docker
    log collection picks it up natively.
    """
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(event), flush=True)


@contextmanager
def timed_step(step: str, **context):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        _emit({
            "event": "perf_step",
            "step": step,
            "duration_ms": duration_ms,
            **context,
        })
