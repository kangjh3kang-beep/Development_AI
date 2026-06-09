"""설계 의도 파싱 AI 서비스 (CAD Phase 2).

비전문가가 자연어로 적은 설계 의도("원룸 위주 50세대 수익 최대")를
LLM(Claude)이 해석하여 구조화된 설계 파라미터로 변환한다.

기존 9개 interpreter(avm/cost/design/...)와 동일하게 BaseInterpreter를 상속해
토큰 계측·캐시·그라운딩을 공유한다. LLM 실패 시 규칙기반(키워드) 폴백으로
무중단 동작한다(가짜 설계가 아니라 정직한 키워드 추출).
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 시스템 프롬프트 ──
SYSTEM_PROMPT = """\
당신은 한국 부동산 개발 기획 전문가입니다.

역할:
비전문가(토지주·소규모 시행자)가 일상 언어로 적은 건축 설계 희망사항을
구조화된 설계 파라미터로 변환합니다. 사용자는 건축 용어를 모를 수 있으므로
의도를 추론하되, 데이터에 없는 수치를 지어내지 않습니다.

판단 기준:
- "원룸/소형/1인" → 소형 평형(원룸) 비중 ↑
- "투룸/신혼/2인" → 투룸 비중 ↑
- "쓰리룸/가족/넓은" → 쓰리룸 비중 ↑
- "수익/최대/임대/분양" → priority=yield
- "거주/쾌적/넓은/조망" → priority=livability
- "균형/적당" 또는 불명확 → priority=balanced
- "N세대/N호" → target_units=N
- "상가/근생/사무실" → building_use 변경

출력 규칙:
1. 사용자가 명시하지 않은 값은 null로 둔다(추측 강제 금지).
2. unit_mix는 비율 합이 1.0이 되도록 하되, 명시 없으면 null.
3. notes는 비전문가가 이해할 쉬운 한국어 한두 문장.
4. 반드시 JSON 형식으로만 응답(마크다운·설명문 금지).
"""

# ── 유저 프롬프트 템플릿 ──
USER_PROMPT_TEMPLATE = """\
아래 사용자의 자연어 설계 희망을 구조화된 파라미터로 변환하세요.

## 사용자 입력
"{text}"

## 참고 정보
- 대지면적: {site_area}
- 용도지역: {zone_code}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체만 반환하세요:

{{
  "target_units": "희망 세대수(정수) 또는 null",
  "unit_mix": "{{\\"원룸\\": 0.0~1.0, \\"투룸\\": 0.0~1.0, \\"쓰리룸\\": 0.0~1.0}} 또는 null (합 1.0)",
  "building_use": "건축물 용도(예: 공동주택/근린생활시설/업무시설) 또는 null",
  "priority": "yield | livability | balanced 중 하나",
  "target_margin_pct": "목표 수익률(%) 숫자 또는 null",
  "notes": "사용자 의도 요약 — 쉬운 한국어 한두 문장"
}}
"""


class DesignIntentInterpreter(BaseInterpreter):
    """자연어 설계 의도를 구조화 파라미터로 변환하는 인터프리터."""

    name = "design_intent"
    # 파싱 후 후처리(타입 캐스팅)하므로 원시 키를 모두 받는다.
    expected_keys = [
        "target_units",
        "unit_mix",
        "building_use",
        "priority",
        "target_margin_pct",
        "notes",
    ]
    fallback_key = "notes"
    max_tokens = 1024
    system_prompt = SYSTEM_PROMPT

    def __init__(self) -> None:
        # 짧은 작업이라 타임아웃을 줄여 응답성을 높인다.
        super().__init__(timeout_sec=20.0)

    async def parse(
        self,
        text: str,
        site_area_sqm: float | None = None,
        zone_code: str | None = None,
    ) -> dict[str, Any]:
        """자연어 의도를 구조화한다. LLM 실패 시 규칙기반 폴백."""
        text = (text or "").strip()
        if not text:
            # 입력이 비면 정직하게 빈 결과(가짜 설계 금지).
            return _empty_intent("입력된 설계 의도가 없습니다.")

        prompt = USER_PROMPT_TEMPLATE.format(
            text=text[:1000],
            site_area=f"{site_area_sqm:.0f}㎡" if site_area_sqm else "미지정",
            zone_code=zone_code or "미지정",
        )

        raw: dict[str, str] = {}
        try:
            raw = await self._invoke(prompt, cache_data={"t": text, "a": site_area_sqm, "z": zone_code})
        except Exception as e:  # noqa: BLE001 — LLM 실패는 폴백으로 흡수
            logger.warning("설계 의도 LLM 파싱 실패, 규칙기반 폴백", error=str(e)[:120])

        structured = _normalize_llm_intent(raw) if raw else None
        if structured is not None:
            structured["source"] = "llm"
            return structured

        # LLM 미응답/파싱 실패 → 규칙기반 폴백
        fallback = parse_intent_rule_based(text)
        fallback["source"] = "rule"
        return fallback


# ── 규칙기반 폴백(키워드 매칭) ──

_ROOM_KEYWORDS = {
    "원룸": ("원룸", "소형", "1인", "스튜디오", "도시형생활주택", "도생"),
    "투룸": ("투룸", "신혼", "2인", "다세대"),
    "쓰리룸": ("쓰리룸", "쓰리룸", "가족", "넓은", "대형", "3룸", "방3"),
}
_YIELD_KEYWORDS = ("수익", "최대", "임대", "분양", "수익률", "이익")
_LIVABILITY_KEYWORDS = ("거주", "쾌적", "조망", "넓게", "여유")
_USE_KEYWORDS = {
    "근린생활시설": ("상가", "근생", "근린", "점포"),
    "업무시설": ("사무실", "오피스", "업무"),
}


def parse_intent_rule_based(text: str) -> dict[str, Any]:
    """LLM 없이 키워드로 설계 의도를 추출(폴백)."""
    t = text or ""

    # 세대수: 숫자 + "세대/호"
    target_units: int | None = None
    m = re.search(r"(\d[\d,]*)\s*(?:세대|호|가구)", t)
    if m:
        try:
            target_units = int(m.group(1).replace(",", ""))
        except ValueError:
            target_units = None

    # 평형 믹스: 언급된 룸 타입에 가중치 부여
    weights: dict[str, float] = {}
    for room, kws in _ROOM_KEYWORDS.items():
        if any(kw in t for kw in kws):
            # "위주/위주로/대부분" 강조면 가중치 ↑
            emphasis = 2.0 if any(e in t for e in ("위주", "대부분", "주로", "중심")) else 1.0
            weights[room] = emphasis
    unit_mix: dict[str, float] | None = None
    if weights:
        total = sum(weights.values())
        unit_mix = {k: round(v / total, 2) for k, v in weights.items()}

    # 우선순위
    if any(kw in t for kw in _YIELD_KEYWORDS):
        priority = "yield"
    elif any(kw in t for kw in _LIVABILITY_KEYWORDS):
        priority = "livability"
    else:
        priority = "balanced"

    # 목표 수익률: 숫자 + "%"
    target_margin_pct: float | None = None
    mm = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if mm:
        try:
            target_margin_pct = float(mm.group(1))
        except ValueError:
            target_margin_pct = None

    # 용도
    building_use: str | None = None
    for use, kws in _USE_KEYWORDS.items():
        if any(kw in t for kw in kws):
            building_use = use
            break

    # 쉬운 한국어 요약
    parts: list[str] = []
    if unit_mix:
        top = max(unit_mix, key=unit_mix.get)
        parts.append(f"{top} 위주")
    if target_units:
        parts.append(f"약 {target_units}세대")
    parts.append({"yield": "수익 우선", "livability": "거주성 우선", "balanced": "균형"}[priority])
    notes = "키워드 분석: " + ", ".join(parts) + " 의도로 보입니다." if parts else "의도를 명확히 추출하지 못했습니다."

    return {
        "target_units": target_units,
        "unit_mix": unit_mix,
        "building_use": building_use,
        "priority": priority,
        "target_margin_pct": target_margin_pct,
        "notes": notes,
    }


def _empty_intent(notes: str) -> dict[str, Any]:
    return {
        "target_units": None,
        "unit_mix": None,
        "building_use": None,
        "priority": "balanced",
        "target_margin_pct": None,
        "notes": notes,
        "source": "empty",
    }


def _normalize_llm_intent(raw: dict[str, str]) -> dict[str, Any] | None:
    """LLM 문자열 응답을 타입 캐스팅한다. 핵심 키 없으면 None(폴백 신호)."""
    if not raw:
        return None

    def _to_int(v: Any) -> int | None:
        try:
            s = str(v).strip()
            if s.lower() in ("null", "none", ""):
                return None
            digits = re.sub(r"[^\d]", "", s)
            return int(digits) if digits else None
        except (ValueError, TypeError):
            return None

    def _to_float(v: Any) -> float | None:
        try:
            s = str(v).strip()
            if s.lower() in ("null", "none", ""):
                return None
            m = re.search(r"\d+(?:\.\d+)?", s)
            return float(m.group(0)) if m else None
        except (ValueError, TypeError):
            return None

    def _to_mix(v: Any) -> dict[str, float] | None:
        if isinstance(v, dict):
            out = {k: float(val) for k, val in v.items() if _is_num(val)}
            return out or None
        s = str(v).strip()
        if s.lower() in ("null", "none", ""):
            return None
        # "원룸:0.6, 투룸:0.4" 형태 파싱 시도
        pairs = re.findall(r"(원룸|투룸|쓰리룸)\D*(\d*\.?\d+)", s)
        out = {k: float(val) for k, val in pairs}
        return out or None

    priority = str(raw.get("priority", "")).strip().lower()
    if priority not in ("yield", "livability", "balanced"):
        priority = "balanced"

    building_use = str(raw.get("building_use", "")).strip()
    if building_use.lower() in ("null", "none", ""):
        building_use = None

    return {
        "target_units": _to_int(raw.get("target_units")),
        "unit_mix": _to_mix(raw.get("unit_mix")),
        "building_use": building_use,
        "priority": priority,
        "target_margin_pct": _to_float(raw.get("target_margin_pct")),
        "notes": str(raw.get("notes", "")).strip() or "설계 의도를 분석했습니다.",
    }


def _is_num(v: Any) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False
