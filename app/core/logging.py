import json
import logging
import sys
from datetime import UTC, datetime

from app.core.types import JsonObject

_EXTRA_FIELDS = ("method", "path", "status_code", "duration_ms", "user_id")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: JsonObject = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _string_attr(record, "request_id"),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str | int | float | bool):
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def _string_attr(record: logging.LogRecord, name: str) -> str | None:
    value = getattr(record, name, None)
    return value if isinstance(value, str) else None


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
