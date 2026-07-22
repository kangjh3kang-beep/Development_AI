"""토지분석보고서(land_analysis_report_pdf.build_land_analysis_report) → 정본 ReportModel 어댑터.

★재구현 금지: 기존 PDF 생산자가 렌더하던 6섹션 구조(필지 요약 → 토지정보 집계 → 권리관계 안내 →
  규제·개발가능성 → 대지지분/세대 → 종합 의견)를 그대로 Block 으로 '옮겨 담기'만 한다(산식 복제 0).
  생산자가 표시용으로 이미 하던 단순 집계(총 면적·건수·용도지역 분포)·표시 서식(㎡/평, 원 단위)만
  동일하게 재현하고, 새로운 계산(법규 한도 재산정 등)은 절대 추가하지 않는다.

무목업: 값 없으면 fmt_value 로 '—' 표기, 데이터 미확보 섹션(권리관계 등)은 생산자가 하던 대로
  정직한 안내 문구를 NarrativeBlock 으로 남긴다(가짜값 생성 금지).
"""

from __future__ import annotations

from typing import Any

from app.services.provenance.lineage_ref import LineageRef

from .evidence_bridge import evidence_block_from_contract
from .model import (
    DataTableBlock,
    Evidence,
    EvidenceBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

_PY = 3.305785  # 1평 = 3.305785㎡ (생산자와 동일)

# 필지 유형 코드 → 사람이 읽는 라벨(생산자 land_analysis_report_pdf._CASE_LABEL 과 동일 — 파일간 사설
# import 를 피하기 위해 그대로 복제한 단순 라벨표, 계산이 아님).
_CASE_LABEL = {"land": "토지(나대지)", "building": "단일필지 건물", "aggregate": "집합건물(공동주택)"}


# ── 표시 서식 헬퍼(생산자의 _won/_sqm 을 그대로 이관, 빈값만 '-' → fmt_value 의 '—' 로 통일) ──
def _won(v: Any) -> str:
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return fmt_value(None)


def _sqm(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return fmt_value(None)
    return f"{f:,.1f}㎡ ({f / _PY:,.1f}평)" if f else fmt_value(None)


def _pct(v: Any) -> str:
    return f"{fmt_value(v)}%" if v is not None else fmt_value(None)


def _far_lineage_evidence_block(parcels: list[dict]) -> EvidenceBlock | None:
    """실효 용적률의 필드수준 계보(W2-2 대표 1경로) — 첫 필지의 far_basis_detail 을 채택.

    입력 계약(routers/auto_zoning.py `_enrich_effective_and_special` → `land_report` 핸들러가
    additive 로 실어 보내는 값 — 기존 소비자는 이 키가 없어도 무해):
        parcel["far_basis_detail"] = calc_effective_far()["far_basis_detail"]
        parcel["ordinance"]        = OrdinanceService.get_ordinance_limits() 원본(dict)

    ★"재구현 금지" 원칙: 여기서 용적률을 다시 계산하지 않는다 — calc_effective_far 가 이미
      계층별(법정범위→조례값→최종근거)로 나눠 준 dict 를 LineageRef 태그로 '옮겨 담기'만 한다.
    ★대표 1경로: far_basis_detail 을 가진 첫 필지 하나만 사용한다(v4.0 [필드수준 계보] 계약의
      끝-끝 연결을 실증하는 1차 배선 — 전 필지 배선은 후속 과제, 한계 참고).
    far_basis_detail 이 없는 입력(기존 호출부·zone_unmatched 등)은 None(정직 — 지어내지 않음).
    """
    target = next((p for p in parcels if isinstance(p.get("far_basis_detail"), dict)), None)
    if target is None:
        return None
    detail: dict[str, Any] = target["far_basis_detail"]
    ordinance = target.get("ordinance") if isinstance(target.get("ordinance"), dict) else {}
    items: list[Evidence] = []

    # ① 법정범위(RULE) — 국토계획법 시행령 별표에 코드화된 고정 상한. 스냅샷 대상이 아니라
    #    '규칙 인용'이므로 RULE 등급(항상 traced=True — 법령 자체는 미추적 사유가 없다).
    legal = detail.get("법정범위")
    if isinstance(legal, dict):
        ref = LineageRef(
            source_kind="RULE",
            basis="국토의 계획 및 이용에 관한 법률 시행령 제71~84조(용도지역별 건폐율·용적률 법정범위)",
        )
        items.append(Evidence(
            value=(
                f"법정 용적률 범위: {fmt_value(legal.get('min_far_pct'))}~"
                f"{fmt_value(legal.get('max_far_pct'))}%"
            ),
            basis=ref.basis, claim_type="FACT", lineage=ref.to_dict(),
        ))

    # ② 조례값(STATIC_CACHE/UNKNOWN) — ordinance.source 로 정직 등급을 가른다(스파이크 결론).
    ordinance_detail = detail.get("조례값")
    if isinstance(ordinance_detail, dict):
        src = str(ordinance.get("source") or "")
        prov = ordinance.get("provenance") if isinstance(ordinance.get("provenance"), dict) else {}
        ref: LineageRef | None
        if src == "지자체 조례(정적캐시)":
            # ★스파이크 결론: ORDINANCE_CACHE 는 정적캐시라 W2-1 SourceSnapshot 이 없다.
            #   SNAPSHOT 을 자칭하지 않고 STATIC_CACHE 로 정직 하강 — disclaimer(원문 재대조
            #   권장 문구)를 basis 로 그대로 인용해 "출처는 있으나 스냅샷 없음"을 명시한다.
            ref = LineageRef(
                source_kind="STATIC_CACHE",
                fact_status="STALE",  # 재검증 권장 — provenance.disclaimer 문구와 정합.
                basis=str(prov.get("disclaimer") or "정적캐시(조례 원문 재대조 권장)"),
            )
        elif src == "법제처API":
            # ★한계(W2-2 1차, 후속 W2-3): 법제처(MOLEG) 실시간 조회는 아직 SourceSnapshot
            #   opt-in 대상이 아니다(W2-1 은 VWorld·G2B 두 커넥터만). 스냅샷 없이 SNAPSHOT 을
            #   자칭하면 날조이므로 UNKNOWN(미추적)으로 정직 하강한다 — MOLEG 커넥터가
            #   SourceSnapshot 을 켜는 순간 이 분기를 SNAPSHOT+snapshot_fingerprint 로 승격한다.
            ref = LineageRef(
                source_kind="UNKNOWN", fact_status="UNKNOWN",
                basis="법제처 실시간 조회(SourceSnapshot 미연동 — 후속 과제)",
            )
        else:
            # source == "법정상한"(조례 미확보) 등 — far_basis_detail["조례값"]은 이미
            # ordinance_confirmed=True 일 때만 채워지므로(far_tier_service 계약) 이 분기는
            # 정상 경로에서 도달하지 않는다. 그래도 방어적으로 조용히 건너뛴다(정직 — 지어내지 않음).
            ref = None
        if ref is not None:
            items.append(Evidence(
                value=f"조례 용적률: {fmt_value(ordinance_detail.get('far_pct'))}%",
                basis=ref.basis, source=src or None, claim_type="FACT", lineage=ref.to_dict(),
            ))

    # ③ 최종근거(CALC) — calc_effective_far 의 결정론적 계층산정 결과(far_basis 문자열).
    final_basis = detail.get("최종근거")
    if final_basis:
        ref = LineageRef(source_kind="CALC", fact_status="DERIVED", basis=str(final_basis))
        items.append(Evidence(
            value=f"실효 용적률 산정근거: {final_basis}",
            basis=str(final_basis), claim_type="CALCULATION", lineage=ref.to_dict(),
        ))

    if not items:
        return None
    return EvidenceBlock(items=items, title="실효 용적률 계보(필드수준 — v4.0 계약 대표 1경로)")


def build_report_model_from_land(data: dict[str, Any]) -> ReportModel:
    """토지분석보고서 입력 dict(report_data) → 정본 ReportModel.

    data = {project_name, parcels:[{jibun,area_sqm,zone_type,bcr_pct,far_pct,jimok,
            official_price_per_sqm,parcel_case,building,status,reason}],
            units_by_parcel:{jibun:{plat_area_sqm,unit_count,units:[...],reliable}}}

    ★생산자(land_analysis_report_pdf.py)와 동일한 6섹션 구조를 유지한다. 모든 섹션 제목에 이미
      번호가 있으므로 section_no 는 비운다(이중번호 방지).
    """
    parcels: list[dict] = data.get("parcels") or []
    units_by: dict[str, Any] = data.get("units_by_parcel") or {}
    proj = data.get("project_name") or "토지분석보고서"

    # ── 생산자와 동일한 표시용 집계(신규 계산 아님, 여러 섹션에서 재사용) ──
    n = len(parcels)
    tot_area = sum(float(p.get("area_sqm") or 0) for p in parcels)
    tot_val = sum(float(p.get("official_price_per_sqm") or 0) * float(p.get("area_sqm") or 0) for p in parcels)
    by_case: dict[str, int] = {}
    zone_dist: dict[str, int] = {}
    for p in parcels:
        by_case[p.get("parcel_case") or "land"] = by_case.get(p.get("parcel_case") or "land", 0) + 1
        z = p.get("zone_type") or "미상"
        zone_dist[z] = zone_dist.get(z, 0) + 1

    sections: list[Section] = []

    # §1 필지 요약 · 유형 분류
    rows1 = []
    for i, p in enumerate(parcels, 1):
        rows1.append([
            str(i), fmt_value(p.get("jibun") or p.get("address")),
            _CASE_LABEL.get(p.get("parcel_case") or "land", fmt_value(None)),
            _sqm(p.get("area_sqm")), fmt_value(p.get("zone_type")),
            fmt_value(p.get("jimok")),
            "확정" if p.get("status") == "ok" else "보완필요",
        ])
    caption1 = (
        f"총 {n}필지 · 토지 {by_case.get('land', 0)} / 단일건물 {by_case.get('building', 0)} / "
        f"집합건물 {by_case.get('aggregate', 0)}."
    )
    sections.append(Section(title="1. 필지 요약 · 유형 분류", blocks=[
        DataTableBlock(
            headers=["#", "지번", "유형", "면적(㎡/평)", "용도지역", "지목", "상태"],
            rows=rows1, caption=caption1),
    ]))

    # §2 토지정보 집계
    zone_str = ", ".join(f"{z} {c}필지" for z, c in sorted(zone_dist.items(), key=lambda x: -x[1]))
    priced_n = sum(1 for p in parcels if (p.get("official_price_per_sqm") and p.get("area_sqm")))
    val_str = (f"{_won(tot_val)} (공시지가 확보 {priced_n}/{n}필지 기준)" if tot_val
               else f"{fmt_value(None)} (공시지가 미확보)")
    sections.append(Section(title="2. 토지정보 집계", blocks=[
        KVTableBlock(rows=[
            ("총 대지면적", _sqm(tot_area)),
            ("용도지역 분포", zone_str or fmt_value(None)),
            ("개별공시지가 기준 추정 토지가액", val_str),
        ]),
    ]))

    # §3 권리관계 안내 — 공공데이터로 확인 불가한 항목을 정직하게 고지(생산자 문구 그대로).
    sections.append(Section(title="3. 권리관계 안내", blocks=[
        NarrativeBlock(paragraphs=[
            "소유자·근저당·지상권 등 권리관계는 공공데이터로 확인할 수 없습니다. 정확한 권리분석은 "
            "토지조서 화면의 '등기부등본 열람/발급'으로 확보하시기 바랍니다. 본 보고서는 공부(토지대장·"
            "건축물대장·토지이용계획) 기반 정보만 포함합니다.",
        ]),
    ]))

    # §4 규제 · 개발가능성(법정 상한 기준) — 필지별 bcr_pct/far_pct 로 허용 건축면적/연면적 산출(생산자와
    # 동일한 표시용 산식을 그대로 이관, 신규 계산 아님).
    rows4 = []
    for p in parcels:
        jb_ = p.get("jibun") or p.get("address") or ""
        # 집합건물은 §5와 동일하게 표제부 대지면적(plat_area_sqm)을 기준으로 통일(기준 불일치 방지, 생산자 로직 유지).
        a = float(p.get("area_sqm") or 0)
        if p.get("parcel_case") == "aggregate":
            pa = (units_by.get(jb_) or {}).get("plat_area_sqm")
            if pa:
                a = float(pa)
        bcr = p.get("bcr_pct")
        far = p.get("far_pct")
        arch = f"{a * bcr / 100:,.0f}㎡" if (a and bcr is not None) else fmt_value(None)
        gfa = f"{a * far / 100:,.0f}㎡" if (a and far is not None) else fmt_value(None)
        rows4.append([
            fmt_value(p.get("jibun")), fmt_value(p.get("zone_type")),
            _pct(bcr), _pct(far),
            f"{a:,.0f}㎡" if a else fmt_value(None), arch, gfa,
        ])
    blocks4: list[Any] = [
        DataTableBlock(
            headers=["지번", "용도지역", "건폐율", "용적률", "대지면적", "허용 건축면적", "허용 연면적"],
            rows=rows4,
            caption="※ 필지별 법정 상한(국토계획법 시행령)이며, 용도지역이 섞인 다필지는 단순 합산이 "
                    "불가합니다(통합 한도는 면적가중 종합분석 참조). 지구단위계획·조례·인센티브로 가감될 수 있습니다."),
    ]
    # ★W2-2(v4.0 [필드수준 계보]): 실효 용적률의 계보(법정범위→조례값→최종근거)를 far_basis_detail
    #   이 실린 대표 1필지에서 뽑아 부착한다. 없으면(호출부가 아직 안 실어 보내면) 조용히 생략(무회귀).
    far_lineage = _far_lineage_evidence_block(parcels)
    if far_lineage is not None:
        blocks4.append(far_lineage)
    sections.append(Section(title="4. 규제 · 개발가능성(법정 상한 기준)", blocks=blocks4))

    # §5 대지지분/세대(집합건물) — 집합건물 필지가 있을 때만(생산자와 동일 조건부 렌더).
    agg_parcels = [p for p in parcels if (p.get("parcel_case") == "aggregate")]
    if agg_parcels:
        blocks5: list[Any] = []
        for p in agg_parcels:
            jb = p.get("jibun") or p.get("address") or fmt_value(None)
            u = units_by.get(jb) or {}
            units = u.get("units") or []
            bld = p.get("building") or {}
            blocks5.append(NarrativeBlock(paragraphs=[
                f"· {jb} — {bld.get('building_name') or '건물명 미상'} / "
                f"세대수 {fmt_value(bld.get('unit_count'))} / 대지면적 {_sqm(u.get('plat_area_sqm'))}",
            ]))
            if units:
                capped = units[:40]  # 보고서 가독성 상한(초과분은 토지조서 참조, 생산자와 동일)
                rows5 = [[
                    fmt_value(un.get("dong")), fmt_value(un.get("ho")),
                    f"{float(un.get('exclusive_area_sqm') or 0):,.2f}",
                    f"{float(un.get('land_share_sqm') or 0):,.2f}",
                    f"{float(un.get('land_share_pyeong') or 0):,.2f}",
                ] for un in capped]
                caption5 = f"※ 전체 {len(units)}세대 중 40세대 표기(전체는 토지조서 참조)." if len(units) > 40 else None
                blocks5.append(DataTableBlock(
                    headers=["동", "호", "전유면적(㎡)", "대지지분(㎡)", "대지지분(평)"],
                    rows=rows5, caption=caption5))
                val = u.get("validation") or {}
                if val.get("reliable"):
                    _reliable = "(세대 누락 없음·신뢰)"
                else:
                    _reliable = "(일부 세대 전유부 누락 가능 — 등기부 확인 권장)"
                blocks5.append(NarrativeBlock(paragraphs=[
                    "검증: Σ세대 대지지분 = 대지면적 비례배분" + _reliable,
                ]))
        sections.append(Section(title="5. 집합건물 세대 대지지분", blocks=blocks5))

    # 종합 의견 — §5(대지지분)가 없으면 5번, 있으면 6번으로 연속 번호 유지(생산자와 동일 규칙).
    sec_no = "6" if agg_parcels else "5"
    need_fix = sum(1 for p in parcels if p.get("status") != "ok")
    opinion = (
        f"본 보고서는 총 {n}필지, 대지면적 {_sqm(tot_area)} 규모의 토지를 공부 기반으로 분석한 결과입니다. "
        + (f"이 중 {by_case.get('aggregate', 0)}필지는 집합건물(공동주택)로 세대별 대지지분이 분할되어 있어 "
           "세대 단위 권리·매입 협의가 필요합니다. " if by_case.get("aggregate") else "")
        + (f"{need_fix}필지는 주소·PNU 보완이 필요하니 정확한 지번으로 재확인하시기 바랍니다. " if need_fix else "")
        + "구체적 개발규모는 지구단위계획·조례·인허가 검토로 확정되며, 권리관계는 등기부등본으로 확인하시기 바랍니다."
    )
    sections.append(Section(title=f"{sec_no}. 종합 의견", blocks=[NarrativeBlock(paragraphs=[opinion])]))

    # 산출 근거·법령 링크 — 입력 data 에 표준 근거 계약(evidence[]/legal_refs[])이 실제 담겨
    # 왔을 때만 부착한다(없으면 섹션 생략 — 정직). 현재 /land-report 생산자는 실효 한도값만
    # 넘기고 계약 블록은 아직 안 넘기므로, 생산자가 계약을 붙이는 즉시 여기서 자동 소비된다.
    # ★어댑터에서 법령키를 새로 발명하거나 URL 을 조립하지 않는다(레지스트리 verified 만 통과).
    ev_block = evidence_block_from_contract(
        {"evidence": data.get("evidence"), "legal_refs": data.get("legal_refs")}, title=None)
    if ev_block is not None:
        next_no = int(sec_no) + 1
        sections.append(Section(title=f"{next_no}. 산출 근거·법령 링크", blocks=[ev_block]))

    meta = ReportMeta(
        title="토지분석보고서",
        subtitle="PropAI 사통팔땅 · 공공데이터 기반 참고용(감정평가·법적효력 없음)",
        project_address=proj,
        confidential=False,  # 감정평가·법적효력 없는 참고자료 — 대외비 표기 없음(생산자와 동일).
    )

    return ReportModel(
        meta=meta,
        sections=sections,
        disclaimer="본 보고서는 공공데이터 기반 참고자료로 감정평가·법적 효력이 없습니다. © PropAI 사통팔땅",
    )
