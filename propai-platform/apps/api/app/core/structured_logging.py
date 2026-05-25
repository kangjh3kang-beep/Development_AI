"""구조화 로깅(Structured Logging).

JSON 포맷으로 request_id, tenant_id를 바인딩하며,
레벨별 필터링과 요청/응답 로깅을 지원한다.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional


class StructuredLogger:
    """구조화 JSON 로거."""

    def __init__(self, service_name: str = "propai-api",
                 min_level: str = "INFO"):
        self.service_name = service_name
        self._min_level = min_level.upper()
        self._context: dict[str, str] = {}
        self._entries: list[dict] = []
        self._level_order = {
            "DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4,
        }

    def bind(self, **kwargs: str) -> "StructuredLogger":
        """컨텍스트 변수를 바인딩한다."""
        self._context.update(kwargs)
        return self

    def unbind(self, *keys: str) -> "StructuredLogger":
        """컨텍스트 변수를 제거한다."""
        for key in keys:
            self._context.pop(key, None)
        return self

    def _should_log(self, level: str) -> bool:
        return self._level_order.get(level.upper(), 1) >= self._level_order.get(
            self._min_level, 1
        )

    def _make_entry(self, level: str, message: str, **extra) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "service": self.service_name,
            "message": message,
            **self._context,
            **extra,
        }
        return entry

    def _log(self, level: str, message: str, **extra) -> Optional[dict]:
        if not self._should_log(level):
            return None
        entry = self._make_entry(level, message, **extra)
        self._entries.append(entry)
        return entry

    def debug(self, message: str, **extra) -> Optional[dict]:
        return self._log("DEBUG", message, **extra)

    def info(self, message: str, **extra) -> Optional[dict]:
        return self._log("INFO", message, **extra)

    def warning(self, message: str, **extra) -> Optional[dict]:
        return self._log("WARNING", message, **extra)

    def error(self, message: str, **extra) -> Optional[dict]:
        return self._log("ERROR", message, **extra)

    def critical(self, message: str, **extra) -> Optional[dict]:
        return self._log("CRITICAL", message, **extra)

    def log_request(self, method: str, path: str, status_code: int,
                    duration_ms: float, **extra) -> dict:
        """HTTP 요청/응답 로깅."""
        return self._log(
            "INFO",
            f"{method} {path} {status_code}",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            **extra,
        )

    def to_json(self, entry: dict) -> str:
        """로그 엔트리를 JSON 문자열로 변환."""
        return json.dumps(entry, ensure_ascii=False)

    @property
    def entries(self) -> list[dict]:
        """기록된 로그 엔트리 목록."""
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def get_entries_by_level(self, level: str) -> list[dict]:
        """특정 레벨의 로그 엔트리를 반환."""
        level = level.upper()
        return [e for e in self._entries if e["level"] == level]

    def clear(self) -> None:
        """모든 로그 엔트리를 삭제."""
        self._entries.clear()

    @staticmethod
    def generate_request_id() -> str:
        """고유 요청 ID 생성."""
        return f"req-{uuid.uuid4().hex[:12]}"


def get_structured_logger(service_name: str = "propai-api") -> StructuredLogger:
    """구조화 로거 팩토리."""
    return StructuredLogger(service_name=service_name)
