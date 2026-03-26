"""구조화 로깅 설정.

structlog 기반. request_id, tenant_id, user_id를 자동 바인딩한다.
JSON 형식으로 출력하여 ELK/Grafana Loki와 연동 가능하다.
"""

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

# PII 패턴 목록 (정규식, 대체 문자열)
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d{6}-[1-4]\d{6}"), "******-*******"),  # 주민등록번호
    (re.compile(r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}"), "****-****-****-****"),  # 카드번호
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***@***.***"),  # 이메일
    (re.compile(r"\d{2,3}-\d{3,4}-\d{4}"), "***-****-****"),  # 전화번호
]


def mask_pii(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """로그 이벤트에서 PII를 자동 마스킹한다."""
    for key, val in event_dict.items():
        if isinstance(val, str):
            for pattern, replacement in _PII_PATTERNS:
                val = pattern.sub(replacement, val)
            event_dict[key] = val
    return event_dict


def setup_logging(*, json_output: bool = True, log_level: str = "INFO") -> None:
    """앱 시작 시 로깅을 초기화한다."""

    # structlog 프로세서 체인
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        mask_pii,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 표준 logging 연동
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # SQLAlchemy, uvicorn 로그 레벨 조정
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """모듈별 로거를 반환한다."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
