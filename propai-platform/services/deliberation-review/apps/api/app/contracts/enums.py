"""R0 — 계약 공용 enum(단위/추출방법/원장상태/관할출처/축척출처).

단위·방법은 고정 enum으로 강제(INV-4). 미정의 단위/방법 참조는 pydantic 검증에서 거부.
순환 import 방지를 위해 계약 모듈들이 공유하는 enum을 여기에 모은다.
"""
from __future__ import annotations

from enum import Enum


class Unit(str, Enum):
    """정량 변수 단위(고정). 단위 불일치는 거부한다."""

    M = "m"
    M2 = "m2"
    PERCENT = "percent"
    COUNT = "count"
    M_ABOVE_GROUND = "m_above_ground"
    RATIO = "ratio"
    NONE = "none"


class Method(str, Enum):
    """수량 추출 방법(명기 우선 > 벡터 > VLLM > OCR)."""

    TABLE = "TABLE"
    VECTOR = "VECTOR"
    VLLM = "VLLM"
    OCR = "OCR"


class RecordStatus(str, Enum):
    """원장 해소 상태. MISSING은 '데이터 미충족'의 명시적 표면화(무음 skip 금지, INV-2)."""

    AGREED = "AGREED"
    HELD = "HELD"
    MISSING = "MISSING"


class JurisdictionSource(str, Enum):
    """관할 해석 출처(fallback chain: 외부API > 공부 > 수기입력)."""

    EXTERNAL = "EXTERNAL"
    CADASTRAL = "CADASTRAL"
    MANUAL = "MANUAL"


class ScaleSource(str, Enum):
    """축척 확정 출처(fallback chain: 치수역산 > 축척표기 > 사용자입력 > 공부역검증)."""

    DIMENSION = "DIMENSION"
    NOTATION = "NOTATION"
    USER = "USER"
    CADASTRAL_CROSSCHECK = "CADASTRAL_CROSSCHECK"
