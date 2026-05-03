"""JSON-line log formatter + setup hook.

Why JSON: the moment logs go to a real backend (Loki, Cloudwatch, …)
text formatting becomes someone else's parsing problem. JSON gives every
field a dedicated key and lets us attach context (platform, query hash)
without grep gymnastics.

`setup_logging()` is idempotent — the scheduler and the API both call it
on startup; importing modules that log at import time work too because
we configure the root logger's handler in place rather than swapping it.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object.

    Anything passed via `logger.info("msg", extra={"k": v})` becomes a
    top-level field, which is the cheapest way to add structured context
    without a third-party logging library.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Pick up `extra=` fields without trampling the reserved LogRecord keys.
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = repr(value)
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger.

    `fmt="json"` is the default. `fmt="text"` falls back to a readable
    formatter for local development.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Drop existing handlers so repeat calls (uvicorn reloads, tests) are clean.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # uvicorn ships its own loggers with stickier handlers — propagate
    # everything to the root so structured formatting wins.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(noisy)
        lg.handlers.clear()
        lg.propagate = True
