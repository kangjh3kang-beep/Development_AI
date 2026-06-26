"""구조화 렌더 브리프 합성 — 부지·인벨로프·프로그램을 결정론적 텍스트 산출물로 변환.

이 모듈은 '이미지'를 만들지 않는다. 이미지 생성 직전에 모델에게 줄 **구조화된 지시서**
(브리프)를 결정론적으로 합성한다. Karpathy 4대 거버넌스(Think-Before·Simplicity·Surgical·
Goal-Driven)를 accuracy_guards/negative/success_criteria로 번역해 주입한다.

핵심 원칙:
- 인벨로프 제약(건폐율/용적률/높이/공지)에는 각각 basis/source/confidence(근거계약)를 붙인다.
- 결정론: 같은 입력이면 같은 브리프(LLM 없이). use_llm=True는 자연어 '보강'일 뿐이며
  실패/키없음이면 결정론 브리프를 그대로 반환한다(graceful).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Karpathy 룰셋 원문 경로(정본은 마크다운, 코드는 이를 결정론 가드로 번역).
_RULESET_PATH = Path(__file__).parent / "rules" / "karpathy_render_ruleset.md"

# 인벨로프 제약 근거의 공통 출처/신뢰도. 법정 한도는 국토계획법 시행령, 인벨로프는 결정론 산식.
_LEGAL_SOURCE = "국토의 계획 및 이용에 관한 법률 시행령 §84/§85(zoning 권위 테이블)"
_ENVELOPE_SOURCE = "compute_buildable_envelope(정북일조 스트립적분·결정론 산식)"


def _constraint(value: Any, *, basis: str, source: str, confidence: str) -> dict[str, Any]:
    """근거계약 형태의 제약 1건 — {value, basis, source, confidence}.

    value 가 None 이면 '미확보'를 정직 표기(가짜 수치 금지). evidence_contract 스타일을 따른다.
    """
    return {
        "value": value,
        "basis": basis,
        "source": source if value is not None else "데이터 미확보(추정 금지)",
        "confidence": confidence if value is not None else "none",
    }


def _footprint_sqm(parcel: dict[str, Any], envelope: dict[str, Any]) -> float | None:
    """1층 바닥면적(건폐 footprint) — envelope 직접값 우선, 없으면 대지면적×건폐율로 산출.

    비-정북일조 용도지역(준주거/상업/녹지 등)은 envelope 에 bcr_footprint_sqm 가 없을 수 있어
    대지면적×건폐율(%) 로 폴백한다. 둘 다 미상이면 None(가짜 수치 금지·정직).
    """
    fp = envelope.get("bcr_footprint_sqm")
    if fp is not None:
        return fp
    land = envelope.get("land_area_sqm") or parcel.get("land_area_sqm")
    bcr = envelope.get("bcr_pct", (parcel.get("zone_limits") or {}).get("max_bcr_pct"))
    if land and bcr:
        return round(float(land) * (float(bcr) / 100.0), 1)
    return None


def _envelope_constraints(parcel: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """건폐율/용적률/높이/공지(이격) 제약을 근거계약으로 묶는다(각 값에 basis/source)."""
    limits = parcel.get("zone_limits") or {}
    bcr = envelope.get("bcr_pct", limits.get("max_bcr_pct"))
    far = envelope.get("far_pct", limits.get("max_far_pct"))
    realistic_far = envelope.get("realistic_far_pct", far)
    max_height = envelope.get("max_height_m")
    max_floors = envelope.get("max_floors")
    # 공지(공동주택 동간 채광거리 0.8H) — 정북일조 적용 시에만 산출됨.
    spacing = envelope.get("min_building_spacing_m")
    zone = parcel.get("zone_type") or envelope.get("zone") or ""

    out: dict[str, Any] = {
        "building_coverage_ratio_pct": _constraint(
            bcr,
            basis=f"{zone} 건폐율 상한",
            source=_LEGAL_SOURCE,
            confidence="high",
        ),
        "floor_area_ratio_pct": _constraint(
            realistic_far,
            basis=(
                f"{zone} 현실 용적률(층수제한 반영)"
                if envelope.get("binding") == "층수제한"
                else f"{zone} 용적률 상한"
            ),
            source=_ENVELOPE_SOURCE if envelope.get("binding") else _LEGAL_SOURCE,
            confidence="high" if realistic_far is not None else "none",
        ),
        "max_height_m": _constraint(
            max_height,
            basis=(
                f"인벨로프 현실 층수 {max_floors}층 × 층고"
                if max_floors
                else "가로구역별 최고높이 별도 확인"
            ),
            source=_ENVELOPE_SOURCE,
            confidence="medium",  # 직사각 근사·층고 가정 — 정밀 높이는 별도
        ),
        "max_floors": _constraint(
            max_floors,
            basis="인벨로프 유효 연면적 ÷ 건폐율 바닥(정북일조 사선 반영)",
            source=_ENVELOPE_SOURCE,
            confidence="medium",
        ),
    }
    # 공지(이격) — 정북일조 적용 용도지역에서만 값이 있음(없으면 정직 표기).
    out["open_space_setback_m"] = _constraint(
        spacing,
        basis="공동주택 동간 채광 인동간격 0.8H(건축법 시행령 §86②)",
        source=_ENVELOPE_SOURCE,
        confidence="medium" if spacing is not None else "none",
    )
    return out


def _site_context(parcel: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """향·스케일·주변 맥락(결정론으로 아는 것만 — 모르는 주변은 지어내지 않는다)."""
    shadow = envelope.get("shadow_analysis") or {}
    noon_alt = shadow.get("noon_altitude_deg")
    coords = parcel.get("coordinates") or {}
    return {
        "address": parcel.get("address"),
        "orientation_note": (
            "정북 방향 일조 사선이 매스 단면을 규정(북측 계단식 후퇴)."
            if envelope.get("applies_north_light")
            else "정북일조 미적용 용도지역(준주거·상업 등) — 사선 단면 제약 없음."
        ),
        "winter_noon_solar_altitude_deg": noon_alt,  # 동지 정오 태양고도(있으면)
        "land_area_sqm": parcel.get("land_area_sqm"),
        "lot_width_m": envelope.get("lot_width_m"),
        "lot_depth_m": envelope.get("lot_depth_m"),
        # 주변 맥락은 '확인된 것만' — 미확인 주변(공원/강/산)은 negative로 생성 금지 처리.
        "surroundings": "주변 맥락은 확인된 데이터가 없으면 지어내지 않음(negative 참조).",
        "coordinates": {"lat": coords.get("lat"), "lon": coords.get("lon")} if coords else None,
    }


def _accuracy_guards(envelope: dict[str, Any]) -> list[str]:
    """Karpathy 정확성 가드 — 결정론으로 항상 동일하게 생성(렌더가 지켜야 할 사실)."""
    guards = [
        "대지경계·도로·인접 필지·스카이라인을 보존한다(왜곡·삭제 금지) [Surgical]",
        "지정한 대지 영역(footprint/envelope)에만 개입한다 [Surgical]",
        "건폐율/용적률/높이 한도를 시각적으로 초과하는 매스를 그리지 않는다 [Goal-Driven]",
    ]
    if envelope.get("applies_north_light"):
        guards.append(
            "정북측 계단식 후퇴(일조 사선) 단면을 반영한다 — "
            f"북측 약 {envelope.get('floors_at_north_edge', '?')}층 → "
            f"남측 최대 {envelope.get('floors_at_deep', '?')}층 [Surgical]"
        )
    return guards


def _negative(parcel: dict[str, Any]) -> list[str]:
    """Karpathy 네거티브(생성 금지) — Simplicity/Surgical 위반 항목."""
    neg = [
        "요청하지 않은 조경·정원·가로수·화단 장식 추가 금지 [Simplicity]",
        "인물·차량·간판·동물 등 무관한 요소 추가 금지 [Simplicity]",
        "대지경계/도로/스카이라인 왜곡·삭제 금지 [Surgical]",
        "건폐율·용적률·높이 한도 초과 매스 금지 [Goal-Driven]",
    ]
    if not (parcel.get("coordinates")):
        neg.append("좌표 미확보 — 실제 주변 지형/랜드마크를 지어내지 말 것 [Simplicity]")
    return neg


def _success_criteria(parcel: dict[str, Any], envelope: dict[str, Any]) -> list[str]:
    """Goal-Driven 검증 가능 성공 기준 — 사람/검증기가 체크 가능한 형태."""
    crit: list[str] = []
    zl = parcel.get("zone_limits") or {}
    if envelope.get("bcr_pct") is not None or zl.get("max_bcr_pct") is not None:
        crit.append("건폐율 표기가 한도 이내로 일치한다")
    if envelope.get("realistic_far_pct") is not None or envelope.get("far_pct") is not None:
        crit.append("용적률(현실) 표기가 인벨로프 산출값과 일치한다")
    if envelope.get("max_floors"):
        crit.append(f"건물 층수가 인벨로프 권장 상한({envelope.get('max_floors')}층) 이내다")
    if envelope.get("applies_north_light"):
        crit.append("정북측 계단식 후퇴(일조 사선) 단면이 표현된다")
    crit.append("대지경계·도로·스카이라인이 보존된다")
    return crit


def _assumptions(parcel: dict[str, Any], envelope: dict[str, Any]) -> list[str]:
    """결정론 가정(정직 표기) — 인벨로프 근사 + 부지 해석 출처."""
    out = list(envelope.get("assumptions") or [])
    zone_source = parcel.get("zone_source")
    if zone_source:
        out.append(f"용도지역 출처: {zone_source}")
    if not parcel.get("land_area_sqm"):
        out.append("대지면적 미확보 — 인벨로프 일부가 폴백 추정일 수 있음")
    return out


def synthesize_brief(
    *,
    parcel: dict[str, Any],
    envelope: dict[str, Any],
    program: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """부지·인벨로프·프로그램 → 구조화 렌더 브리프(결정론).

    Args:
        parcel:   AutoZoningService 결과 등 {address, zone_type, zone_limits, land_area_sqm, ...}.
        envelope: compute_buildable_envelope 결과(인벨로프 제약·층수·일조).
        program:  용도/규모 옵션 {building_use, scale, style?, materials?, view?} (선택).

    Returns:
        role/site_context/envelope_constraints/program/design_language/materials/
        environment/camera/assumptions/accuracy_guards/negative/success_criteria/output 를
        갖는 dict. (LLM 보강은 enrich_brief_with_llm로 별도 — 이 함수는 순수 결정론.)
    """
    program = program or {}
    use = program.get("building_use") or "공동주택"
    scale = program.get("scale") or "중층"

    brief: dict[str, Any] = {
        "role": (
            "한국 건축 인허가 맥락의 부지 맞춤 건축 외관 렌더 — 용도지역 법정 한도와 "
            "정북일조 인벨로프를 준수하는 사실적 매스를 묘사한다."
        ),
        "site_context": _site_context(parcel, envelope),
        "envelope_constraints": _envelope_constraints(parcel, envelope),
        "program": {
            "building_use": use,                       # 용도(공동주택/근생/주상복합 등)
            "scale": scale,                            # 규모(저층/중층/고층)
            # 사용자 요청 층수 우선 → 없으면 인벨로프 권장 상한 폴백.
            #  ★요청값을 envelope 와 분리해 둬야 Think-Before 의 '매스>인벨로프' 모순 검사가
            #    자동경로에서도 실제로 발화한다(요청이 상한 초과면 차단).
            "target_floors": program.get("target_floors") or envelope.get("max_floors"),
            "footprint_sqm": _footprint_sqm(parcel, envelope),
            "gfa_sqm": envelope.get("effective_gfa_sqm") or envelope.get("envelope_gfa_sqm"),
        },
        "design_language": program.get("style")
        or "절제된 현대 한국 도시 건축 — 명료한 매스, 균형 잡힌 입면 비례.",
        "materials": program.get("materials")
        or ["노출 콘크리트/석재 기단", "유리 커튼월·창호", "금속 패널 코니스"],
        "environment": {
            "time_of_day": (program.get("environment") or {}).get("time_of_day", "주간(맑음)"),
            "weather": (program.get("environment") or {}).get("weather", "맑음"),
            "lighting": "동지 정오 태양고도 기준 자연광(일조 사선 가시화)",
        },
        "camera": {
            "view": (program.get("camera") or {}).get("view", "보행자 시점 3/4 외관"),
            "lens": (program.get("camera") or {}).get("lens", "표준 35mm 상당"),
        },
        "assumptions": _assumptions(parcel, envelope),
        "accuracy_guards": _accuracy_guards(envelope),
        "negative": _negative(parcel),
        "success_criteria": _success_criteria(parcel, envelope),
        "output": {
            "resolution": (program.get("output") or {}).get("resolution", "1024x1024"),
            "aspect_ratio": (program.get("output") or {}).get("aspect_ratio", "1:1"),
        },
        "ruleset": "karpathy_render_ruleset.md",
        "llm_enriched": False,
    }
    return brief


async def enrich_brief_with_llm(brief: dict[str, Any]) -> dict[str, Any]:
    """기존 설계 인터프리터(DesignInterpreter)로 브리프를 자연어 보강(graceful).

    BaseInterpreter 단일경유(_invoke) 패턴을 따르는 DesignInterpreter를 재사용한다.
    실패/키없음/예외면 결정론 브리프를 **그대로** 반환(llm_enriched=False 유지) — 무날조.
    성공 시 design_language/improvement 등 자연어 보강을 brief['llm_enrichment']에 가산.
    """
    try:
        from app.services.ai.design_interpreter import DesignInterpreter

        # 인벨로프/제약을 매스 데이터로 압축해 인터프리터에 전달(인터프리터가 키만 추출).
        ec = brief.get("envelope_constraints", {})
        design_data = {
            "building_use": brief.get("program", {}).get("building_use"),
            "num_floors": brief.get("program", {}).get("target_floors"),
            "total_floor_area_sqm": brief.get("program", {}).get("gfa_sqm"),
            "building_footprint_sqm": brief.get("program", {}).get("footprint_sqm"),
            "bcr_pct": (ec.get("building_coverage_ratio_pct") or {}).get("value"),
            "far_pct": (ec.get("floor_area_ratio_pct") or {}).get("value"),
            "max_height_m": (ec.get("max_height_m") or {}).get("value"),
        }
        interp = DesignInterpreter()
        result = await interp.generate_interpretation(design_data)
        if result:  # 빈 dict면 LLM 실패 → 결정론 브리프 유지
            brief = {**brief, "llm_enrichment": result, "llm_enriched": True}
    except Exception:  # noqa: BLE001 — 보강 실패는 결정론 브리프를 막지 않는다.
        pass
    return brief
