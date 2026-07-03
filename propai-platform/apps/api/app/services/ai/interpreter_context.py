"""인터프리터 공용 컨텍스트 빌더(SSOT) — 6개 생성허브 산출물의 단일 조립기.

배경(REFACTOR CR-1/CR-3):
- 후보지 진단서(precheck)는 우량 전용 인터프리터 SiteAnalysisInterpreter를 두고도
  산출경로가 우회(dead-path)돼 80자 한 줄만 나온다. 재구현 0으로 기존 인터프리터를
  배선·확장하려면, 서비스가 이미 조립한 실데이터(용도지역·실효한도·공시지가·근거·법령
  링크·특이부지 등)를 **인터프리터가 기대하는 스키마**로 옮겨주는 어댑터가 필요하다.
- 이 모듈은 그 어댑터를 **순수함수·부작용 없음·외부호출 없음**으로 제공한다. 이후 5개
  산출물(설계·수지·인허가·시장·심의)이 동일 SSOT를 재사용해 각자 재구현하지 않게 한다.

핵심 원칙(무목업·정직·graceful):
- 없는 값은 넣지 않는다(무날조). 모든 조회는 .get으로 방어(누락 키 KeyError 금지).
- URL은 legal_reference_registry.build_law_url만이 생성한다(여기서 조립 금지).
  법령명이 검증(verified)된 경우에만 legal_link을 채우고, 아니면 None(pending 취지).
- 외부 I/O·async·과금 전무. 순수 매핑/직렬화만 담당한다.
"""
from __future__ import annotations

import contextlib
from typing import Any


def wrap_evidence(
    value: Any,
    basis: str,
    source: str,
    provenance: str | None = None,
    legal_link: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    """근거 표준계약 1건 — {value, basis, source, provenance, legal_link, confidence}.

    Args:
        value:       근거가 뒷받침하는 값(수치·문자열 등).
        basis:       산정 근거·이유(사람이 읽는 설명).
        source:      원천 데이터 출처명(예: vworld_individual_land_price).
        provenance:  수집 경위·계층(선택). 없으면 None.
        legal_link:  ★verified 법령 URL만. 미검증이면 None(pending 취지).
        confidence:  신뢰도(high/medium/low/none 등, 선택).

    Returns:
        6키 표준계약 dict. legal_link은 검증된 링크가 있을 때만 채운다(할루시네이션 링크 금지).
    """
    return {
        "value": value,
        "basis": basis,
        "source": source,
        "provenance": provenance,
        "legal_link": legal_link,
        "confidence": confidence,
    }


def _verified_law_link(law_name: str | None, article: Any = None) -> str | None:
    """법령명이 있을 때만 레지스트리(build_law_url)로 verified 링크 생성. 없으면 None.

    URL 조립은 전적으로 build_law_url에 위임한다(여기서 문자열 조립 금지). 실패·미검증
    (법령명 공백)이면 None을 반환해 pending 취지를 유지한다(무날조 링크 방지).
    """
    name = (law_name or "").strip()
    if not name:
        return None
    try:
        from app.services.legal.legal_reference_registry import build_law_url

        url = build_law_url(name, article)
        return url or None
    except Exception:  # noqa: BLE001 — 레지스트리 실패 시 링크 없이(정직 pending)
        return None


def _map_analysis_data(collected: dict) -> dict[str, Any]:
    """collected(precheck 등 서비스 실데이터) → SiteAnalysisInterpreter가 기대하는 스키마.

    ★_extract_compact_data가 실제로 읽는 키에 정확 정합(무날조 — 없는 값은 생략).
    - 최상위: address / zone_type / land_area_sqm
    - effective_far: national_*(법정) / ordinance_*(조례) / effective_*(실효 적용값) / source
    - land_prices: official_price_per_sqm / official_price_per_pyeong / total_official_value_won
    - special_parcel: precheck detect_special_parcel 결과를 그대로 통과(is_special 게이트)
    """
    out: dict[str, Any] = {}

    # ── 최상위 식별자(무값이면 생략) ──
    addr = collected.get("address")
    if addr:
        out["address"] = addr
    zone = collected.get("zone_type")
    if zone:
        out["zone_type"] = zone
    area = collected.get("area_sqm")
    if area is None:
        area = collected.get("land_area_sqm")
    if area is not None:
        out["land_area_sqm"] = area

    # ── 실효 용적률/건폐율(effective_far) — precheck legal 매핑 ──
    #   법정(national)=bcr_pct/far_pct, 조례(ordinance)=ordinance_*_pct,
    #   실효 적용값(effective)=applied_*_pct. 값이 있는 항목만 채운다(무날조).
    legal = collected.get("legal") or {}
    if isinstance(legal, dict) and legal:
        far_block: dict[str, Any] = {}
        national_bcr = legal.get("bcr_pct")
        national_far = legal.get("far_pct")
        ordinance_bcr = legal.get("ordinance_bcr_pct")
        ordinance_far = legal.get("ordinance_far_pct")
        effective_bcr = legal.get("applied_bcr_pct")
        effective_far = legal.get("applied_far_pct")
        if national_bcr is not None:
            far_block["national_bcr_pct"] = national_bcr
        if national_far is not None:
            far_block["national_far_pct"] = national_far
        if ordinance_bcr is not None:
            far_block["ordinance_bcr_pct"] = ordinance_bcr
        if ordinance_far is not None:
            far_block["ordinance_far_pct"] = ordinance_far
        if effective_bcr is not None:
            far_block["effective_bcr_pct"] = effective_bcr
        if effective_far is not None:
            far_block["effective_far_pct"] = effective_far
        src = legal.get("far_source") or legal.get("source")
        if src:
            far_block["source"] = src
        height = legal.get("height_m")
        if height is not None:
            far_block["height_m"] = height
        if far_block:
            out["effective_far"] = far_block

    # ── 토지 시세(land_prices) — 공시지가만(시장가 데이터는 precheck 미수집→미생성) ──
    official = collected.get("official_price")
    if official is None:
        official = collected.get("official_price_per_sqm")
    if official is not None:
        lp: dict[str, Any] = {"official_price_per_sqm": official}
        try:
            per_pyeong = round(float(official) * 3.305785)
            lp["official_price_per_pyeong"] = per_pyeong
        except (TypeError, ValueError):
            pass
        if area is not None:
            with contextlib.suppress(TypeError, ValueError):
                lp["total_official_value_won"] = round(float(official) * float(area))
        out["land_prices"] = lp

    # ── 특이부지(special_parcel) — detect_special_parcel 결과를 그대로 통과 ──
    #   _extract_compact_data는 sp.get("is_special")로 게이트하므로 원형 유지가 안전.
    sp = collected.get("special_parcel")
    if isinstance(sp, dict) and sp.get("is_special"):
        out["special_parcel"] = sp

    return out


def _serialize_evidence_text(collected: dict) -> str | None:
    """evidence[]·legal_refs[]·소스 출처를 사람이 읽는 근거 문자열로 직렬화. 비면 None.

    각 evidence 항목은 target/formula/result/inputs를, legal_refs는 명칭·링크를 담는다.
    출처(sources)와 공시지가·조례 근거를 함께 실어 인터프리터가 값의 출처를 인지하게 한다.
    """
    lines: list[str] = []

    # (1) evidence 트레이스 — 한도·면적·수지 산출 근거.
    evidence = collected.get("evidence")
    if isinstance(evidence, list) and evidence:
        lines.append("[근거 트레이스]")
        for ev in evidence:
            if not isinstance(ev, dict):
                continue
            target = ev.get("target") or ev.get("id") or ""
            formula = ev.get("formula") or ""
            result = ev.get("result") or ""
            part = " · ".join(p for p in (target, formula) if p)
            if result:
                part = f"{part} → {result}" if part else str(result)
            if part:
                lines.append(f"- {part}")

    # (2) 법령 근거 — 명칭 + verified 링크(레지스트리 출력만).
    legal_refs = collected.get("legal_refs")
    if isinstance(legal_refs, list) and legal_refs:
        lines.append("[법령 근거]")
        for ref in legal_refs:
            if not isinstance(ref, dict):
                continue
            label = ref.get("label") or ref.get("name") or ref.get("key") or ""
            url = ref.get("url") or ""
            status = ref.get("url_status")
            if url and status != "pending":
                lines.append(f"- {label}: {url}")
            elif label:
                lines.append(f"- {label} (링크 확인 필요)")

    # (3) 공시지가 출처(개별공시지가) — 토지비 근거의 출처 명시.
    official = collected.get("official_price")
    if official is None:
        official = collected.get("official_price_per_sqm")
    if official is not None:
        lines.append(
            f"[공시지가] 개별공시지가 {official:,.0f}원/㎡ (출처: vworld_individual_land_price)"
            if isinstance(official, (int, float))
            else f"[공시지가] 개별공시지가 {official} (출처: vworld_individual_land_price)"
        )

    # (4) 데이터 출처 목록(provenance) — 어떤 원천을 참조했는지.
    sources = collected.get("sources")
    if isinstance(sources, list) and sources:
        uniq = [s for i, s in enumerate(sources) if s and s not in sources[:i]]
        if uniq:
            lines.append(f"[데이터 출처] {', '.join(str(s) for s in uniq)}")

    if not lines:
        return None
    return "\n".join(lines)


def _collect_signals(collected: dict) -> dict[str, Any]:
    """special_parcel·upzoning·buildable 신호를 요약 dict로. 없는 신호는 생략(무날조)."""
    signals: dict[str, Any] = {}

    sp = collected.get("special_parcel")
    if isinstance(sp, dict) and sp.get("is_special"):
        signals["special_parcel"] = {
            "developability": sp.get("developability"),
            "severity_label": sp.get("severity_label"),
            "resolvable": sp.get("resolvable"),
        }

    up = collected.get("upzoning")
    if isinstance(up, dict) and up.get("scenarios"):
        signals["upzoning_available"] = True

    bo = collected.get("buildable_options")
    if isinstance(bo, dict) and bo.get("options"):
        signals["buildable_options_available"] = True

    return signals


def build_interpreter_context(collected: dict) -> dict[str, Any]:
    """서비스 실데이터(collected) → 인터프리터 호출용 4요소 컨텍스트(SSOT).

    Args:
        collected: 서비스가 이미 조립한 실데이터 dict. precheck의 경우
            address·zone_type·area_sqm·legal(실효한도)·official_price·evidence[]·
            legal_refs[]·sources·special_parcel 등을 담는다(누락 허용 — .get 방어).

    Returns:
        {
          "analysis_data":   SiteAnalysisInterpreter._extract_compact_data가 기대하는 스키마,
          "evidence_text":   근거 직렬화 문자열 | None,
          "analysis_signals": special_parcel/upzoning/buildable 신호 dict,
          "prior_context":   원장 직전심사 문자열 | None(precheck엔 없을 수 있음),
        }

    순수함수: 부작용·외부호출 없음. collected가 비거나 키가 누락돼도 graceful
    (analysis_data는 빈 dict, evidence_text/prior_context는 None).
    """
    collected = collected or {}

    analysis_data = _map_analysis_data(collected)
    analysis_signals = _collect_signals(collected)

    # 신호를 analysis_data에도 병합(인터프리터가 special_parcel을 이미 읽으므로 중복 무해).
    # special_parcel은 _map_analysis_data가 원형으로 통과시키므로 여기선 별도 노출만.

    evidence_text = _serialize_evidence_text(collected)

    # prior_context: 원장 직전심사(있으면). precheck엔 원장이 없을 수 있으니 graceful None.
    prior = collected.get("prior_context")
    prior_context = str(prior) if prior else None

    return {
        "analysis_data": analysis_data,
        "evidence_text": evidence_text,
        "analysis_signals": analysis_signals,
        "prior_context": prior_context,
    }
