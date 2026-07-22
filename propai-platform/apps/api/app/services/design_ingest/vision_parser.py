"""비전 LLM 도면 파싱 — 이미지/PDF 설계도면을 멀티모달 LLM으로 DesignSpec 구조화.

엑셀(openpyxl)·DXF(ezdxf)는 텍스트/기하 파싱이 가능하지만, 스캔/렌더된 도면(이미지·PDF)은
멀티모달 이해가 필요하다. 여기서는 Claude 비전(get_llm 단일경유)으로 도면을 읽어
도면종류·면적·층수·세대수·주차·공간을 추출한다.

정직 원칙(★무목업):
- 키 미설정·LLM 실패·JSON 불량 → 숫자를 **지어내지 않고** 파일명 휴리스틱 메타만 채운 뒤
  meta.warnings + meta['vision']='unavailable'|'failed'로 정직 고지한다.
- LLM이 읽지 못한 값은 null → None(추정 금지). 비상식 값(음수·과대)은 거부한다(할루시네이션 가드).
- 모델 ID는 get_llm() 한 곳에서만 결정한다(llm_provider 단일출처).
- 토큰 계측(BaseInterpreter 단일경유)은 분석 인터프리터 대상이며, 인제스트-타임 비전 계측은 후속.
"""

from __future__ import annotations

import base64
import json
import logging
import math

from app.services.design_ingest.design_spec import (
    DRAWING_TYPES,
    DesignSpec,
    RoomSpec,
    detect_drawing_type,
)

logger = logging.getLogger(__name__)

# 형식 → 비전 입력 미디어 타입.
_IMAGE_MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# 할루시네이션 가드 — 비상식 값 거부용 상한(넉넉하게, 명백한 거짓만 차단).
_MAX_AREA_SQM = 5_000_000.0   # 5㎢ (초대형 단지도 포함)
_MAX_FLOORS = 200
_MAX_UNITS = 100_000
_MAX_PARKING = 100_000

# 비전 입력 크기 상한(선제 DoS/메모리 방어) — 초과 시 정직 강등(unavailable).
# 라우터 연결 시 UploadFile 크기 검증과 병행하되, 서비스 단에서도 1차 가드한다.
_MAX_INPUT_BYTES = 20 * 1024 * 1024  # 20MB

# LLM에 요청하는 추출 스키마(JSON only). null 허용 = 못 읽으면 지어내지 말 것.
_PROMPT = (
    "당신은 건축 도면을 판독하는 전문가입니다. 첨부된 설계도면을 분석해 아래 JSON "
    "스키마로만 응답하세요. 코드블록·설명 없이 순수 JSON만 출력합니다.\n"
    "읽을 수 없거나 도면에 없는 값은 반드시 null로 두세요(절대 추정·가정 금지).\n\n"
    "{\n"
    '  "drawing_type": "site_plan|floor_plan|section|elevation|parking|spec_sheet|bim|unknown",\n'
    '  "total_area_sqm": number|null,   // 연면적 또는 대지면적(㎡)\n'
    '  "floor_count": integer|null,     // 지상 층수\n'
    '  "unit_count": integer|null,      // 세대/가구 수\n'
    '  "parking_count": integer|null,   // 주차 대수\n'
    '  "rooms": ["공간명", ...],         // 도면에 표기된 실/공간 라벨(최대 30개)\n'
    '  "confidence": number,            // 0.0~1.0 판독 확신도\n'
    '  "summary": "도면 핵심 요약(한국어 1~3문장, 개인정보 제외)"\n'
    "}\n"
)


def media_type_for(filename: str) -> str | None:
    """이미지 파일명 → 미디어 타입. 미지원이면 None."""
    name = (filename or "").lower()
    for ext, mt in _IMAGE_MEDIA.items():
        if name.endswith(ext):
            return mt
    return None


def _message_text(resp: object) -> str:
    """LLM 응답에서 텍스트를 안전하게 추출(content가 str 또는 블록 리스트일 수 있음)."""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return str(content or "")


def _parse_json(text: str) -> dict | None:
    """LLM 텍스트에서 JSON 객체를 관대하게 추출(코드펜스·잡텍스트 허용). 실패 시 None.

    첫 '{'~마지막 '}' 구간만 취하므로 ```json 코드펜스는 자연히 배제된다(문자열 값 내부
    백틱을 손상시키지 않음). parse_constant로 NaN/Infinity 토큰을 None으로 무력화한다
    (json은 기본적으로 이를 허용 → content_hash 오염·int(nan) 예외 방지).
    """
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1], parse_constant=lambda _c: None)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _pos_number(v: object, upper: float) -> float | None:
    """양수이고 상한 이내인 수만 통과(음수·0·과대·비유한·비수치 거부=할루시네이션 가드).

    NaN/Infinity는 비교식(<=,>)을 모두 빠져나가므로 math.isfinite로 명시 차단한다
    (미차단 시 int(nan) 예외·content_hash 오염 유발).
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    fv = float(v)
    if not math.isfinite(fv) or fv <= 0 or fv > upper:
        return None
    return fv


def _pos_int(v: object, upper: int) -> int | None:
    f = _pos_number(v, float(upper))
    return int(f) if f is not None else None


def _apply_extraction(spec: DesignSpec, data: dict, filename: str) -> None:
    """LLM JSON을 DesignSpec에 검증·반영(비상식 값은 버림, 못 읽은 값은 None 유지)."""
    # 도면종류 — 허용 enum만 신뢰, 아니면 파일명 휴리스틱.
    dt = str(data.get("drawing_type") or "").strip()
    if dt in DRAWING_TYPES and dt != "unknown":
        spec.drawing_type = dt
    else:
        spec.drawing_type = detect_drawing_type(filename)

    spec.total_area_sqm = _pos_number(data.get("total_area_sqm"), _MAX_AREA_SQM)
    spec.floor_count = _pos_int(data.get("floor_count"), _MAX_FLOORS)
    spec.unit_count = _pos_int(data.get("unit_count"), _MAX_UNITS)
    spec.parking_count = _pos_int(data.get("parking_count"), _MAX_PARKING)

    rooms = data.get("rooms")
    if isinstance(rooms, list):
        spec.rooms = [
            RoomSpec(name=str(r).strip()[:60])
            for r in rooms[:30]
            if isinstance(r, (str, int, float)) and str(r).strip()
        ]

    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        spec.raw_summary = summary.strip()[:4000]

    conf = _pos_number(data.get("confidence"), 1.0)
    spec.meta["vision"] = "ok"
    if conf is not None:
        spec.meta["vision_confidence"] = round(conf, 3)


def _build_content(content: bytes, fmt: str, media_type: str | None) -> list[dict] | None:
    """멀티모달 입력 블록(텍스트 프롬프트 + 이미지/문서). 미지원이면 None."""
    b64 = base64.b64encode(content).decode("ascii")
    if fmt == "image" and media_type:
        # data URI image_url — langchain 멀티모달 표준 형식(프로바이더 호환 폭 넓음).
        return [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
        ]
    if fmt == "pdf":
        # Anthropic 네이티브 document 블록(langchain_anthropic 패스스루). 버전에 따라
        # 미지원일 수 있어 best-effort — 실패 시 상위에서 정직 스텁으로 처리된다.
        return [
            {"type": "text", "text": _PROMPT},
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            },
        ]
    return None


async def parse_drawing_with_vision(content: bytes, filename: str, fmt: str) -> DesignSpec:
    """이미지/PDF 도면을 비전 LLM으로 DesignSpec 구조화(best-effort·정직).

    fmt: 'image' | 'pdf'. 실패 시 숫자 없는 정직 스텁(meta.warnings) 반환 — 예외를 던지지 않음.
    """
    spec = DesignSpec(source_format=fmt)
    spec.title = (filename or "").rsplit("/", 1)[-1] or None
    spec.drawing_type = detect_drawing_type(filename)  # 기본값(LLM 성공 시 갱신)

    media_type = media_type_for(filename) if fmt == "image" else None
    if fmt == "image" and not media_type:
        spec.meta["warnings"] = [f"지원하지 않는 이미지 형식: {filename}"]
        spec.meta["vision"] = "unavailable"
        return spec

    if not content or len(content) > _MAX_INPUT_BYTES:
        size_mb = round(len(content) / (1024 * 1024), 1)
        spec.meta["warnings"] = [f"비전 입력 크기 초과/빈 파일({size_mb}MB, 상한 20MB)"]
        spec.meta["vision"] = "unavailable"
        return spec

    blocks = _build_content(content, fmt, media_type)
    if blocks is None:
        spec.meta["warnings"] = [f"비전 입력 구성 불가: {fmt}"]
        spec.meta["vision"] = "unavailable"
        return spec

    # LLM 호출 — 키 미설정/모델오류/네트워크 등 모든 실패는 정직 스텁으로 강등.
    try:
        from langchain_core.messages import HumanMessage

        from app.services.ai.llm_provider import get_llm

        llm = get_llm(provider="anthropic", max_tokens=1500, timeout=40.0)
        resp = await llm.ainvoke([HumanMessage(content=blocks)])
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort) —
        # 유일한 무계측 직접호출이라 캡 절단 감사(output==캡 대조)의 사각이었다.
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="design_ingest")
        data = _parse_json(_message_text(resp))
    except Exception as e:  # noqa: BLE001 — best-effort 비전, 실패는 정직 고지
        logger.warning("design_ingest 비전 파싱 실패(%s): %s", fmt, str(e)[:160])
        spec.meta["warnings"] = [f"비전 LLM 파싱 실패 — 메타만 추출({str(e)[:80]})"]
        spec.meta["vision"] = "failed"
        return spec

    if not data:
        spec.meta["warnings"] = ["비전 LLM 응답을 JSON으로 해석하지 못함 — 메타만 추출"]
        spec.meta["vision"] = "failed"
        return spec

    # 추출 반영 단계도 정직 강등으로 보호(예상 못한 값 형태에도 never-raises 보장).
    try:
        _apply_extraction(spec, data, filename)
    except Exception as e:  # noqa: BLE001
        logger.warning("design_ingest 비전 추출 반영 실패: %s", str(e)[:160])
        spec.meta["warnings"] = [f"비전 추출 반영 실패 — 메타만({str(e)[:80]})"]
        spec.meta["vision"] = "failed"
    return spec
