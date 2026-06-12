"""DA-1 — 설계개요서(brief) 추출기: PDF 텍스트 추출 + 필드 구조화.

- extract_text_from_pdf : PyMuPDF(fitz)로 PDF(바이트/경로)에서 텍스트 추출.
  미설치·열기실패·텍스트없음은 전부 정직한 빈 결과 + note(가짜 텍스트 생성 금지).
- DesignBriefInterpreter: BaseInterpreter 상속 LLM 추출기(name='design_brief').
  각 필드는 {value, quote, confidence} — 원문에 근거 없는 값은 null(날조 금지).
- parse_brief_rule_based : LLM 실패/미사용 시 한국어 라벨 정규식 폴백.
  매칭된 원문 라인을 quote로 동반하고, 매칭 실패 필드는 null.
- extract_brief          : 통합 진입점(LLM → 정규식 폴백, graceful).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.services.ai.base_interpreter import BaseInterpreter

logger = structlog.get_logger()

# ── 추출 대상 필드(키 → 한국어 라벨) ──
# geometry_adapter.merge_params의 파라미터 키와 1:1 정합(병합 시 그대로 사용).
BRIEF_FIELDS: dict[str, str] = {
    "zone_type": "용도지역",
    "land_area_sqm": "대지면적(㎡)",
    "building_area_sqm": "건축면적(㎡)",
    "total_floor_area_sqm": "연면적(㎡)",
    "bcr_pct": "건폐율(%)",
    "far_pct": "용적률(%)",
    "building_height_m": "건축물 높이(m)",
    "floors_above": "지상 층수",
    "floors_below": "지하 층수",
    "units": "세대수",
    "parking": "주차대수",
    "building_use": "주용도",
}

_FLOAT_FIELDS = {
    "land_area_sqm", "building_area_sqm", "total_floor_area_sqm",
    "bcr_pct", "far_pct", "building_height_m",
}
_INT_FIELDS = {"floors_above", "floors_below", "units", "parking"}
_STR_FIELDS = {"zone_type", "building_use"}

# 1평 = 3.3058㎡ (base_interpreter GROUNDING_RULE과 동일 환산계수)
_PYEONG_TO_SQM = 3.3058


# ─────────────────────────────────────────────────────────────────────────────
# PDF 텍스트 추출 (PyMuPDF)
# ─────────────────────────────────────────────────────────────────────────────
def extract_text_from_pdf(source: bytes | bytearray | str) -> dict[str, Any]:
    """PDF에서 텍스트를 추출한다(PyMuPDF fitz).

    Args:
        source: PDF 바이트(업로드 파일) 또는 파일 경로 문자열.

    Returns:
        {"text": str, "page_count": int, "source": "pymupdf", "note": str|None}
        — fitz 미설치/열기실패/텍스트없음 모두 빈 text + 정직한 note(예외 미전파).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {
            "text": "", "page_count": 0, "source": "pymupdf",
            "note": "PyMuPDF(fitz) 미설치 — PDF 텍스트 추출 불가(빈 결과 반환)",
        }

    try:
        if isinstance(source, (bytes, bytearray)):
            doc = fitz.open(stream=bytes(source), filetype="pdf")
        else:
            doc = fitz.open(str(source))
    except Exception as e:  # noqa: BLE001 — 손상 PDF 등은 정직한 빈 결과
        return {
            "text": "", "page_count": 0, "source": "pymupdf",
            "note": f"PDF 열기 실패 — {str(e)[:120]}",
        }

    pages: list[str] = []
    page_count = 0
    try:
        page_count = doc.page_count
        for page in doc:
            try:
                pages.append(page.get_text("text"))
            except Exception:  # noqa: BLE001 — 개별 페이지 실패는 건너뜀
                continue
    finally:
        try:
            doc.close()
        except Exception:  # noqa: BLE001
            pass

    text = "\n".join(pages).strip()
    note = None
    if not text:
        note = "추출된 텍스트 없음(스캔본/이미지 PDF 가능성) — OCR 미수행, 임의 텍스트 생성 금지"
    return {"text": text, "page_count": page_count, "source": "pymupdf", "note": note}


# ─────────────────────────────────────────────────────────────────────────────
# LLM 추출기 (BaseInterpreter 상속)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
당신은 한국 건축 설계개요서(설계개요·건축개요 표) 분석 전문가입니다.

역할:
설계개요서 원문 텍스트에서 핵심 설계 파라미터를 구조화 JSON으로 추출합니다.

출력 규칙(반드시 준수):
1. 각 필드는 {"value": 값, "quote": "원문 인용", "confidence": 0.0~1.0} 객체로 출력한다.
2. 원문에 근거가 없는 필드는 반드시 null로 둔다(추측·날조 절대 금지).
3. quote는 해당 값이 적힌 원문 구절을 그대로 짧게 인용한다(원문에 없으면 null).
4. 면적은 ㎡ 숫자로 출력한다. 평 표기는 1평=3.3058㎡로 환산하되 quote에는 원문 표기를 유지한다.
5. 건폐율·용적률은 % 숫자, 층수·세대수·주차대수는 정수로 출력한다.
6. 반드시 JSON만 출력한다(마크다운·설명문 금지)."""

USER_PROMPT_TEMPLATE = """\
아래 설계개요서 원문에서 필드를 추출해 JSON으로만 답하세요.

## 설계개요서 원문
{text}

## 요구 출력 (JSON)
다음 키를 가진 JSON 객체만 반환하세요. 각 값은
{{"value": 값 또는 null, "quote": "원문 인용 또는 null", "confidence": 0.0~1.0}} 형식이며,
원문에 근거 없는 필드는 null 입니다.

{{
  "zone_type": "용도지역(예: 제2종일반주거지역)",
  "land_area_sqm": "대지면적(㎡ 숫자)",
  "building_area_sqm": "건축면적(㎡ 숫자)",
  "total_floor_area_sqm": "연면적(㎡ 숫자)",
  "bcr_pct": "건폐율(% 숫자)",
  "far_pct": "용적률(% 숫자)",
  "building_height_m": "건축물 최고높이(m 숫자)",
  "floors_above": "지상 층수(정수)",
  "floors_below": "지하 층수(정수)",
  "units": "세대수(정수)",
  "parking": "주차대수(정수)",
  "building_use": "주용도(예: 공동주택)"
}}
"""


def _cast_value(key: str, value: Any) -> Any:
    """필드별 타입 캐스팅 — 실패·빈값은 None(임의값 대입 금지)."""
    if value is None or isinstance(value, bool):
        return None
    if key in _STR_FIELDS:
        s = str(value).strip()
        return None if not s or s.lower() in ("null", "none") else s
    s = str(value).strip().replace(",", "")
    if not s or s.lower() in ("null", "none"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        num = float(m.group(0))
    except ValueError:
        return None
    if key in _INT_FIELDS:
        return int(num)
    return num


def _normalize_field(key: str, raw: Any) -> dict[str, Any] | None:
    """LLM 응답의 필드 1건을 {value, quote, confidence}로 정규화.

    value가 원문 근거 없이 비어 있으면 필드 자체를 None으로 둔다(날조 금지).
    confidence는 LLM이 제시한 값만 사용하고 미제시면 None(임의 부여 금지).
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        value = _cast_value(key, raw.get("value"))
        if value is None:
            return None
        quote = raw.get("quote")
        quote = str(quote).strip()[:200] if quote not in (None, "", "null") else None
        confidence: float | None = None
        try:
            c = raw.get("confidence")
            if c is not None and not isinstance(c, bool):
                cf = float(c)
                if 0.0 <= cf <= 1.0:
                    confidence = round(cf, 2)
        except (TypeError, ValueError):
            confidence = None
        return {"value": value, "quote": quote, "confidence": confidence}
    # 스칼라로만 답한 경우 — 값은 수용하되 quote 없음은 없음 그대로(정직).
    value = _cast_value(key, raw)
    if value is None:
        return None
    return {"value": value, "quote": None, "confidence": None}


class DesignBriefInterpreter(BaseInterpreter):
    """설계개요서 텍스트 → 구조화 필드({value, quote, confidence}) 추출기."""

    name = "design_brief"
    expected_keys = list(BRIEF_FIELDS)
    fallback_key = ""  # JSON 미발견 시 빈 dict — 호출자가 정규식 폴백으로 처리
    max_tokens = 2048
    system_prompt = SYSTEM_PROMPT

    def __init__(self) -> None:
        # 추출 전용 짧은 작업 — 타임아웃 단축(design_intent 패턴).
        super().__init__(timeout_sec=30.0)

    # 기반 파서는 값을 str()로 평탄화한다 — 본 인터프리터는 필드가
    # {value, quote, confidence} 중첩 객체이므로 구조를 보존해 파싱한다.
    def _parse_response(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[1:end])
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start == -1 or brace_end == -1:
                logger.warning("설계개요 응답에서 JSON 미발견", interp=self.name, raw_length=len(raw))
                return {}
            try:
                parsed = json.loads(text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                logger.warning("설계개요 응답 JSON 파싱 실패", interp=self.name, raw_length=len(raw))
                return {}
        if not isinstance(parsed, dict):
            return {}
        return {key: parsed.get(key) for key in self.expected_keys if parsed.get(key) is not None}

    async def extract(self, text: str) -> dict[str, Any]:
        """설계개요 텍스트에서 필드를 추출한다. 실패 시 빈 dict(호출자 폴백)."""
        cleaned = (text or "").strip()
        if not cleaned:
            return {}
        prompt = USER_PROMPT_TEMPLATE.format(text=cleaned[:8000])
        raw = await self._invoke(prompt, cache_data={"design_brief": cleaned[:8000]})
        if not raw:
            return {}
        return {key: _normalize_field(key, raw.get(key)) for key in BRIEF_FIELDS}


# ─────────────────────────────────────────────────────────────────────────────
# 정규식 폴백 (한국어 라벨)
# ─────────────────────────────────────────────────────────────────────────────
# 정규식 일치는 원문 인용(quote)이 보장되지만 의미 해석(표 문맥 등) 불확실성이
# 남으므로 보수적 고정 confidence를 부여한다(LLM 점수와 구분).
_RULE_CONFIDENCE = 0.5

# 소수점은 뒤에 숫자가 있을 때만(목차 번호 "6. 세대수"의 "6."이 숫자로 오인되는 것 방지)
_NUM = r"(?P<num>[0-9][0-9,]*(?:\.[0-9]+)?)"
_AREA_UNIT = r"(?P<unit>㎡|m²|m2|평)"

_FIELD_PATTERNS: dict[str, str] = {
    "land_area_sqm": rf"대\s*지\s*면\s*적\s*[:：]?\s*약?\s*{_NUM}\s*{_AREA_UNIT}",
    "building_area_sqm": rf"건\s*축\s*면\s*적\s*[:：]?\s*약?\s*{_NUM}\s*{_AREA_UNIT}",
    "total_floor_area_sqm": rf"연\s*면\s*적\s*[:：]?\s*약?\s*{_NUM}\s*{_AREA_UNIT}",
    "bcr_pct": rf"건\s*폐\s*율\s*[:：]?\s*약?\s*{_NUM}\s*%",
    "far_pct": rf"용\s*적\s*률\s*[:：]?\s*약?\s*{_NUM}\s*%",
    "building_height_m": rf"(?:최고\s*)?높\s*이\s*[:：]?\s*약?\s*{_NUM}\s*m",
    "floors_above": rf"지\s*상\s*{_NUM}\s*층",
    "floors_below": rf"지\s*하\s*{_NUM}\s*층",
    "units": rf"{_NUM}\s*세\s*대",
    "parking": rf"주\s*차(?:\s*대\s*수)?\s*[:：]?\s*약?\s*{_NUM}\s*대",
}

# 용도지역 — legal_zone_limits.ZONE_LIMITS 표준 용도지역명만 매칭(임의 지역명 생성 금지).
_ZONE_PATTERN = (
    r"(?P<zone>제\s*[123]\s*종\s*(?:일반|전용)\s*주거지역|준주거지역|중심상업지역|일반상업지역|"
    r"근린상업지역|유통상업지역|전용공업지역|일반공업지역|준공업지역|보전녹지지역|생산녹지지역|"
    r"자연녹지지역|계획관리지역|생산관리지역|보전관리지역|농림지역|자연환경보전지역)"
)
# 주용도 — '용도지역'과의 오매칭 방지를 위해 라벨 직후 구분자(콜론)를 요구한다.
_USE_PATTERN = r"(?:주\s*용\s*도|건축물\s*용도|용\s*도)\s*[:：]\s*(?P<use>[^\n,;|]{2,30})"


def _line_of(text: str, pos: int) -> str:
    """매칭 위치가 포함된 원문 라인(quote용, 200자 컷)."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:200]


def _parse_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_brief_rule_based(text: str) -> dict[str, Any]:
    """한국어 라벨 정규식으로 설계개요 필드를 추출한다(LLM 폴백).

    각 필드는 {value, quote(매칭 원문 라인), confidence(보수 고정), method:"rule"}.
    매칭 실패 필드는 None — 원문에 없는 값은 만들지 않는다(날조 금지).
    """
    t = text or ""
    fields: dict[str, Any] = {key: None for key in BRIEF_FIELDS}

    for key, pattern in _FIELD_PATTERNS.items():
        m = re.search(pattern, t)
        if not m:
            continue
        value = _parse_number(m.group("num"))
        if value is None:
            continue
        unit = (m.groupdict() or {}).get("unit")
        if unit == "평":
            # 결정적 단위환산(1평=3.3058㎡) — 원문 표기는 quote에 보존.
            value = round(value * _PYEONG_TO_SQM, 2)
        if key in _INT_FIELDS:
            value = int(value)
        fields[key] = {
            "value": value,
            "quote": _line_of(t, m.start()),
            "confidence": _RULE_CONFIDENCE,
            "method": "rule",
        }

    mz = re.search(_ZONE_PATTERN, t)
    if mz:
        fields["zone_type"] = {
            "value": re.sub(r"\s+", "", mz.group("zone")),
            "quote": _line_of(t, mz.start()),
            "confidence": _RULE_CONFIDENCE,
            "method": "rule",
        }

    mu = re.search(_USE_PATTERN, t)
    if mu:
        use = mu.group("use").strip()
        if use:
            fields["building_use"] = {
                "value": use,
                "quote": _line_of(t, mu.start()),
                "confidence": _RULE_CONFIDENCE,
                "method": "rule",
            }

    return fields


# ─────────────────────────────────────────────────────────────────────────────
# 통합 진입점
# ─────────────────────────────────────────────────────────────────────────────
async def extract_brief(text: str, *, use_llm: bool = True) -> dict[str, Any]:
    """설계개요 텍스트 → 구조화 필드. LLM 우선, 실패 시 한국어 라벨 정규식 폴백.

    Returns:
        {"fields": {key: {value, quote, confidence}|None}, "source": "llm"|"rule"|"empty",
         "note": str|None}
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return {
            "fields": {key: None for key in BRIEF_FIELDS},
            "source": "empty",
            "note": "입력 텍스트 없음 — 필드 추출 생략(원문 없는 값 날조 금지)",
        }

    if use_llm:
        try:
            fields = await DesignBriefInterpreter().extract(cleaned)
            if fields and any(v is not None for v in fields.values()):
                return {"fields": fields, "source": "llm", "note": None}
            logger.warning("설계개요 LLM 추출 빈 결과 — 정규식 폴백", chars=len(cleaned))
        except Exception as e:  # noqa: BLE001 — LLM 실패는 폴백으로 흡수
            logger.warning("설계개요 LLM 추출 실패 — 정규식 폴백", error=str(e)[:120])

    return {
        "fields": parse_brief_rule_based(cleaned),
        "source": "rule",
        "note": "한국어 라벨 정규식 폴백 — 매칭 원문 인용 동반, 미매칭 필드는 null",
    }
