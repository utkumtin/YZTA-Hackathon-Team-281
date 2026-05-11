"""
app/logging.py — JSON formatter ve logger fabrikası

Tüm uygulama bu modül üzerinden logger alır:
    from app.logging import get_logger
    logger = get_logger(__name__)
"""

import json
import logging
import sys
from datetime import datetime, timezone

from app.config import settings


class _JsonFormatter(logging.Formatter):
    """Yapılandırılmış JSON log satırları üretir.

    Çıktı örneği:
        {"time":"2026-05-11T18:00:00Z","level":"INFO","logger":"app.api.webhook",
         "msg":"webhook_received","chat_id":987654321}
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        base = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Extra field'lar (logger.info("x", extra={"key": "val"}))
        skip = {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "id",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                base[key] = value

        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)

        return json.dumps(base, ensure_ascii=False, default=str)


def _configure_root_logger() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    # Mevcut handler yoksa ekle; import iki kez olursa duplicate önle
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers = [handler]


_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Modül logger'ı döndürür.

    Kullanım:
        logger = get_logger(__name__)
        logger.info("tool_call", extra={"tool": "get_order", "order_id": 1024})
    """
    return logging.getLogger(name)
