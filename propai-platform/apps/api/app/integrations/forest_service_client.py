"""산림청 임목축적 데이터 커넥터 (T3 — pluggable, 무날조·정직 게이트 보존).

특정 공공 API 스펙을 하드코딩으로 확신할 수 없으므로(무날조 원칙),
엔드포인트·인증·응답 매핑 전부를 **설정 주입**으로 받는 어댑터 계약만 정의한다.

계약:
    get_forest_facts(pnu) -> {
        "입목축적_per_ha": float | None,          # 해당 필지 ha당 입목축적(㎥)
        "관할평균_입목축적_per_ha": float | None,   # 관할 시군구 평균(별표4 150% 비교 분모)
        "산지구분": str | None,                    # 보전/준보전 등
        "source": str,                             # 출처(설명가능성 기본화)
    } | None

동작 원칙:
- env `FOREST_API_KEY`/`FOREST_API_BASE` 가 **둘 다** 설정된 경우에만 조회를 시도한다.
  하나라도 미설정(또는 공백)이면 **네트워크 시도 없이 즉시 None** — 데이터 미확보를
  정직하게 반환하여 현행 NEEDS_OFFICIAL_SURVEY 게이트를 완전 보존한다.
- 응답 매핑은 설정가능 필드맵: env `FOREST_API_FIELD_MAP` (JSON, 표준키→dot-path).
  미설정 시 표준키 동일명 매핑(DEFAULT_FIELD_MAP). dot-path 는 dict 키와 리스트
  숫자 인덱스를 지원한다 (예: "response.body.items.0.frstStck").
- 요청 파라미터명도 설정가능: `FOREST_API_KEY_PARAM`(기본 "serviceKey" — data.go.kr
  관례), `FOREST_API_PNU_PARAM`(기본 "pnu").
- 모든 실패(HTTP 오류·네트워크 예외·JSON 파싱 실패)는 None + warning 로그 —
  호출부(special_parcel 게이트)로 예외를 전파하지 않는다.
- 수치 파싱 불가 값은 날조하지 않고 None 으로 강등한다.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ENV_API_KEY = "FOREST_API_KEY"
ENV_API_BASE = "FOREST_API_BASE"
ENV_FIELD_MAP = "FOREST_API_FIELD_MAP"
ENV_KEY_PARAM = "FOREST_API_KEY_PARAM"
ENV_PNU_PARAM = "FOREST_API_PNU_PARAM"

REQUEST_TIMEOUT_SECONDS = 10.0

# 표준 계약 키 (special_parcel 별표4 150% 비교가 소비)
FIELD_STOCK = "입목축적_per_ha"
FIELD_DISTRICT_AVG = "관할평균_입목축적_per_ha"
FIELD_FOREST_CLASS = "산지구분"

_NUMERIC_FIELDS = frozenset({FIELD_STOCK, FIELD_DISTRICT_AVG})

# 기본 필드맵: 표준키 동일명 매핑(특정 API 응답 구조를 가정하지 않음).
DEFAULT_FIELD_MAP: dict[str, str] = {
    FIELD_STOCK: FIELD_STOCK,
    FIELD_DISTRICT_AVG: FIELD_DISTRICT_AVG,
    FIELD_FOREST_CLASS: FIELD_FOREST_CLASS,
}


def _env(name: str) -> str | None:
    """공백-트림 env 조회. 빈 문자열은 미설정으로 간주(정직 게이트)."""
    value = os.environ.get(name, "").strip()
    return value or None


def _load_field_map() -> dict[str, str]:
    """env 필드맵(JSON) 로드. 손상 시 warning 후 기본맵 폴백."""
    raw = _env(ENV_FIELD_MAP)
    if not raw:
        return dict(DEFAULT_FIELD_MAP)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("필드맵은 JSON 객체여야 함")
        field_map = {
            str(k): str(v)
            for k, v in parsed.items()
            if k in DEFAULT_FIELD_MAP and isinstance(v, str) and v.strip()
        }
        if not field_map:
            raise ValueError("유효한 표준키 매핑이 없음")
        return field_map
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "%s 파싱 실패(%s) — 기본 필드맵으로 폴백", ENV_FIELD_MAP, exc
        )
        return dict(DEFAULT_FIELD_MAP)


def _resolve_path(data: Any, dot_path: str) -> Any:
    """dot-path 로 중첩 JSON 값을 조회. 불일치는 None (무날조)."""
    current = data
    for segment in dot_path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, list):
            try:
                index = int(segment)
            except ValueError:
                return None
            if not (0 <= index < len(current)):
                return None
            current = current[index]
        else:
            return None
    return current


def _coerce_float(value: Any) -> float | None:
    """수치 강제변환 — 파싱 불가 값은 날조 없이 None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def get_forest_facts(pnu: str) -> dict[str, Any] | None:
    """필지(PNU)의 임목축적 관련 사실을 조회한다.

    env 미설정·조회 실패·유효 필드 전무 시 None — 호출부는 None 을
    '데이터 미확보(정직)'로 다루며 확정판정을 완화하지 않는다.
    """
    api_key = _env(ENV_API_KEY)
    api_base = _env(ENV_API_BASE)
    if not api_key or not api_base:
        # 네트워크 시도 금지 — 미설정은 즉시 정직 None.
        return None
    if not pnu or not str(pnu).strip():
        return None

    key_param = _env(ENV_KEY_PARAM) or "serviceKey"
    pnu_param = _env(ENV_PNU_PARAM) or "pnu"
    params = {key_param: api_key, pnu_param: str(pnu).strip()}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(api_base, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — 커넥터 실패는 호출부로 전파 금지.
        logger.warning("산림청 임목축적 API 조회 실패(pnu=%s): %s", pnu, exc)
        return None

    field_map = _load_field_map()
    facts: dict[str, Any] = {}
    for canonical_key in (FIELD_STOCK, FIELD_DISTRICT_AVG, FIELD_FOREST_CLASS):
        dot_path = field_map.get(canonical_key)
        raw = _resolve_path(payload, dot_path) if dot_path else None
        if canonical_key in _NUMERIC_FIELDS:
            facts[canonical_key] = _coerce_float(raw)
        else:
            facts[canonical_key] = str(raw).strip() if raw not in (None, "") else None

    if all(facts[k] is None for k in (FIELD_STOCK, FIELD_DISTRICT_AVG, FIELD_FOREST_CLASS)):
        logger.warning(
            "산림청 임목축적 API 응답에서 유효 필드를 찾지 못함(pnu=%s) — "
            "%s 필드맵 확인 필요", pnu, ENV_FIELD_MAP,
        )
        return None

    facts["source"] = urlparse(api_base).netloc or api_base
    return facts
