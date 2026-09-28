"""应用统一日志配置与请求关联上下文。"""

import json
import logging
import os
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_standard_record_fields = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
_ignored_record_fields = {"color_message", "message", "asctime"}
_level_colors = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[41;97m",
}
_color_reset = "\033[0m"


def bind_request_id(request_id: str) -> Any:
    """绑定当前执行上下文的请求关联标识。"""

    return _request_id.set(request_id)


def reset_request_id(token: Any) -> None:
    """恢复请求关联标识的上一个上下文值。"""

    _request_id.reset(token)


def get_log_request_id() -> str | None:
    """返回日志上下文中的请求关联标识。"""

    return _request_id.get()


class JsonFormatter(logging.Formatter):
    """将标准日志记录转换为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := getattr(record, "request_id", None):
            payload["request_id"] = request_id
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _standard_record_fields | _ignored_record_fields | {"request_id"}
            }
        )
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleColorFormatter(logging.Formatter):
    """为控制台日志添加 ANSI 颜色，并追加结构化扩展字段。"""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _standard_record_fields | _ignored_record_fields | {"request_id"}
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            extras["request_id"] = request_id
        if extras:
            rendered = " ".join(f"{key}={value}" for key, value in extras.items())
            message = f"{message} {rendered}"
        color = _level_colors.get(record.levelno)
        return f"{color}{message}{_color_reset}" if color else message


class RequestContextFilter(logging.Filter):
    """将当前上下文的请求关联标识写入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_log_request_id()
        return True


def configure_logging() -> None:
    """按环境变量初始化应用控制台日志。"""

    log_format = os.getenv("LOG_FORMAT", "text").lower()
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = ConsoleColorFormatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())
    logging.basicConfig(level=level, handlers=[handler])
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "starlette"):
        managed_logger = logging.getLogger(logger_name)
        managed_logger.propagate = True
        managed_logger.setLevel(level)
