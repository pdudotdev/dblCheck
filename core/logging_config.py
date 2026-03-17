"""Structured logging configuration for dblCheck.

Provides a JSONFormatter and one setup function:
  setup_logging()  — configures the 'dblcheck' logger hierarchy for any process

Environment variables:
  LOG_LEVEL   DEBUG | INFO | WARNING | ERROR   (default: INFO)
  LOG_FORMAT  json | text                       (default: json)
"""
import json
import logging
import os
from datetime import datetime, timezone


# Standard LogRecord attributes that should NOT be forwarded as extra JSON fields.
_STANDARD_ATTRS = frozenset({
    "args", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg",
    "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "taskName", "thread", "threadName",
})


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record — friendly for log-aggregation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.fromtimestamp(record.created, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        )
        entry: dict = {
            "ts":     ts,
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        # Forward any extra fields added via logging.info("...", extra={...})
        for key, val in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                entry[key] = val
        return json.dumps(entry, default=str)


def _make_formatter() -> logging.Formatter:
    fmt = os.getenv("LOG_FORMAT", "text").lower()
    if fmt == "json":
        return JSONFormatter()
    return logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")


def setup_logging() -> None:
    """Configure the 'dblcheck' logger hierarchy with a stderr handler.

    Idempotent — safe to call multiple times; handlers are only added once.
    Respects LOG_LEVEL and LOG_FORMAT environment variables.
    """
    root = logging.getLogger("dblcheck")
    if root.handlers:
        return  # Already configured

    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    root.setLevel(level)
    root.propagate = False

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(_make_formatter())
    root.addHandler(sh)


