import json
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def timed_step(step: str, **context):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "perf_step",
            "step": step,
            "duration_ms": duration_ms,
            **context,
        }))
