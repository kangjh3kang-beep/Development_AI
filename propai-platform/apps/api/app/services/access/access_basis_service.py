"""접도·도로 기반(access_basis) 조립자 — 명세 P4 'Statutory Road·Access'.

special_parcel 내 실존 판정 룰군(㉗)과 토지이음 접도요건 보강을 **재사용·합성**해,
도로 접근을 legal / physical / emergency 3상태로 분리한 AccessAssessment로 승격한다.
(★신규는 이 조립자·스키마·라우터 표면만 — 판정 로직은 special_parcel/tojieum 재사용.)

재사용(그린필드 금지):
- ㉗ special_parcel._rule_by_road(§44 맹지)·_rule_by_road_law(도로법 접도구역·연결허가)·
  _rule_by_fire_performance(소방 성능위주설계) + 신설 세분 룰 _rule_by_cul_de_sac(막다른 도로)·
  _rule_by_flag_lot(자루형 대지)·_rule_by_emergency_access(소방·공사차량) — 모두 special_parcel.
- gate_decision/tentative_marker/_RANK(게이트 정책) — special_parcel.
- assess_road_conditions(건축법 §44·시행령 §28 접도요건) — legal.tojieum_supplement.
- build_evidence_block(근거·법령링크 공용 계약) — data_validation.evidence_contract.

정직 원칙:
- 판정 불가(도로접면·도로폭·통로폭 미상 등)는 REQUIRES_AUTHORITY_CONFIRMATION로, 확정 PASS를
  만들지 않는다("법정도로 근거 없는 PASS 0"). 값이 없는 항목은 미제공/강등(날조·낙관 폴백 금지).
"""
from __future__ import annotations

from typing import Any

from app.schemas.access import AccessAssessment, AccessFinding, AccessStateResult
from app.services.data_validation.evidence_contract import build_evidence_block
from app.services.zoning import special_parcel as sp

# 상태 한글 라벨.
_STATE_LABEL: dict[str, str] = {
    "legal": "법정 접도(건축법 §44·시행령 §28)",
    "physical": "현황 물리적 접근(도로폭·통로)",
    "emergency": "소방·응급·공사차량 접근",
}

# 개발가능성 등급(special_parcel _RANK 값) → 정직 상태값(스키마 AccessStatus).
_STATUS_BY_DEV: dict[str, str] = {
    "POSSIBLE": "PASS",
    "CAUTION": "PASS",
    "CONDITIONAL": "CONDITIONAL",
    "PRECONDITION": "CONDITIONAL",
    "NEEDS_OFFICIAL_SURVEY": "REQUIRES_AUTHORITY_CONFIRMATION",
    "REQUIRES_AUTHORITY_CONFIRMATION": "REQUIRES_AUTHORITY_CONFIRMATION",
    "BLOCKED": "BLOCKED",
}

# 개발가능성 등급 → 해결가능성(YES/CONDITIONAL/NO).
_RESOLVABLE_BY_DEV: dict[str, str] = {
    "POSSIBLE": "YES",
    "CAUTION": "YES",
    "CONDITIONAL": "CONDITIONAL",
    "PRECONDITION": "CONDITIONAL",
    "NEEDS_OFFICIAL_SURVEY": "CONDITIONAL",
    "REQUIRES_AUTHORITY_CONFIRMATION": "CONDITIONAL",
    "BLOCKED": "NO",
}

# 종합 등급 한글 라벨.
_SEVERITY_LABEL: dict[str, str] = {
    "POSSIBLE": "접도 가능",
    "CAUTION": "사전확인 필요",
    "CONDITIONAL": "조건부 가능(도로 확보·협의 선행)",
    "PRECONDITION": "중대한 선행절차 필수",
    "NEEDS_OFFICIAL_SURVEY": "공식 확인 필요",
    "REQUIRES_AUTHORITY_CONFIRMATION": "법정 접도 근거 미확정(관할 확인 필요)",
    "BLOCKED": "접도 불가",
}

# 접도요건 판정(assess_road_conditions status) → 개발가능성 등급.
_ROAD_COND_DEV: dict[str, str] = {
    "충족": "POSSIBLE",
    "검토": "CONDITIONAL",
    "미상": "REQUIRES_AUTHORITY_CONFIRMATION",
    "불가": "CONDITIONAL",  # 맹지 — 진입로 확보 조건부(별도 _rule_by_road 요인과 동일 등급)
}

_RES_RANK = {"NO": 0, "CONDITIONAL": 1, "YES": 2}


def _rank(dev: str) -> int:
    return sp._RANK.get(dev, 0)


def _worst_dev(devs: list[str]) -> str:
    """여러 등급 중 가장 제약 큰 등급(_RANK 최댓값)."""
    return max(devs, key=_rank) if devs else "POSSIBLE"


def _status_of(dev: str) -> str:
    return _STATUS_BY_DEV.get(dev, "REQUIRES_AUTHORITY_CONFIRMATION")


def _factor_to_finding(factor: dict[str, Any]) -> AccessFinding:
    """special_parcel 룰이 반환한 factor 1건 → AccessFinding."""
    dev = str(factor.get("developability") or "POSSIBLE")
    return AccessFinding(
        category=str(factor.get("category") or ""),
        developability=dev,
        status=_status_of(dev),  # type: ignore[arg-type]
        implications=[str(x) for x in (factor.get("implications") or [])],
        permit_prerequisites=[str(x) for x in (factor.get("permit_prerequisites") or [])],
        legal_basis=[str(x) for x in (factor.get("legal_basis") or [])],
        legal_ref_keys=[str(x) for x in (factor.get("legal_ref_keys") or [])],
    )


def _build_state(
    state: str, factors: list[dict[str, Any]], *, sigungu: str | None,
) -> AccessStateResult:
    """상태별 factor 목록을 종합해 AccessStateResult(근거계약 포함) 생성."""
    findings = [_factor_to_finding(f) for f in factors]
    dev = _worst_dev([str(f.get("developability") or "POSSIBLE") for f in factors])
    resolvable = _RESOLVABLE_BY_DEV.get(dev, "CONDITIONAL")
    status = _status_of(dev)

    # 근거계약(evidence) — 각 factor를 근거 트레이스로 직렬화(URL은 레지스트리 출력만).
    items: list[dict[str, Any]] = []
    keys: list[str] = []
    for f in factors:
        impl = f.get("implications") or []
        lrk = f.get("legal_ref_keys") or []
        items.append({
            "label": str(f.get("category") or ""),
            "value": str(f.get("developability") or ""),
            "basis": (str(impl[0]) if impl else None),
            "legal_ref_key": (str(lrk[0]) if lrk else None),
        })
        keys.extend(str(k) for k in lrk)
    block = build_evidence_block(items, keys, sigungu=sigungu, sources=["vworld_land_info"])

    summary = _state_summary(state, dev, findings)
    return AccessStateResult(
        state=state,  # type: ignore[arg-type]
        state_label=_STATE_LABEL[state],
        status=status,  # type: ignore[arg-type]
        developability=dev,
        resolvable=resolvable,
        summary=summary,
        findings=findings,
        evidence=block.get("evidence", []),
        legal_refs=block.get("legal_refs", []),
        provenance=block.get("provenance", []),
        trust=block.get("trust"),
    )


def _state_summary(state: str, dev: str, findings: list[AccessFinding]) -> str:
    """상태 정직 요약 — 등급별 문장 + 대표 요인."""
    label = _SEVERITY_LABEL.get(dev, dev)
    head = f"{_STATE_LABEL[state]}: {label}."
    if dev in ("REQUIRES_AUTHORITY_CONFIRMATION", "NEEDS_OFFICIAL_SURVEY"):
        head += " 근거 데이터 미확보로 확정할 수 없어 관할 확인이 필요합니다(확정 아님)."
    elif dev == "BLOCKED":
        head += " 현 상태로는 접근 확보가 불가합니다."
    elif dev in ("CONDITIONAL", "PRECONDITION"):
        head += " 도로 확보·협의 등 선행/병행이 조건입니다."
    reps = [f.category for f in findings if _rank(f.developability) >= _rank("CONDITIONAL")]
    if reps:
        head += " 요인: " + ", ".join(dict.fromkeys(reps)) + "."
    return head


# ──────────────────────────────────────────────────────────────────────────
# 상태별 조립 — 각 상태의 factor 목록을 special_parcel 룰 + tojieum 재사용으로 수집.
# ──────────────────────────────────────────────────────────────────────────

def _is_maengji(result: dict[str, Any]) -> bool:
    """맹지(도로 미접) 여부 — road_contact False·road_side 맹지·도로폭 0."""
    if result.get("road_contact") is False:
        return True
    side = str(result.get("road_side") or "")
    if "맹지" in side:
        return True
    width = sp._access_road_width(result)
    return isinstance(width, (int, float)) and width == 0


def _legal_factors(result: dict[str, Any]) -> list[dict[str, Any]]:
    """법정 접도(legal) factor — 접도요건(§44·§28)+맹지+막다른 도로+도로법."""
    factors: list[dict[str, Any]] = []

    # 접도요건(건축법 §44·시행령 §28) — tojieum 재사용. road_side/폭 미상은 '미상'(RAC)로 정직 강등.
    from app.services.legal.tojieum_supplement import assess_road_conditions

    gfa = (sp._num(result.get("planned_gfa_sqm")) or sp._num(result.get("total_floor_area_sqm"))
           or sp._num(result.get("gfa_sqm")))
    road_cond = assess_road_conditions(result.get("road_side"), gfa)
    cond_dev = _ROAD_COND_DEV.get(str(road_cond.get("status") or ""), "REQUIRES_AUTHORITY_CONFIRMATION")
    factors.append({
        "category": "접도요건(건축법 §44·시행령 §28)",
        "developability": cond_dev,
        "implications": [
            str(road_cond.get("note") or ""),
            (f"{road_cond.get('gfa_tier')} — 요구 도로너비 {road_cond.get('required_road_width_m')}m 이상, "
             f"접도길이 {road_cond.get('required_contact_m')}m 이상."),
        ],
        "legal_basis": [str(road_cond.get("basis") or "건축법 제44조(대지와 도로의 관계)")],
        "legal_ref_keys": list(road_cond.get("legal_ref_keys") or ["road_relation"]),
        "permit_prerequisites": ["도로접면·도로폭 실측(현황측량·지적도) 확인",
                                 "요구 도로너비 미달 시 건축선 후퇴·도로 확보 검토"],
    })

    # 맹지(§44) — special_parcel 재사용. road_side='맹지'는 _rule_by_road가 직접 읽지 않으므로
    #   맹지 신호(_is_maengji)일 때 road_contact=False로 정규화해 동일 규칙 결과를 재생성한다(재구현 아님).
    fr = sp._rule_by_road(result)
    if fr is None and _is_maengji(result):
        fr = sp._rule_by_road({**result, "road_contact": False})
    if fr:
        factors.append(fr)
    # 막다른 도로(시행령 §3-3) — 신설 세분 룰.
    fc = sp._rule_by_cul_de_sac(result)
    if fc:
        factors.append(fc)
    # 도로법 접도구역·연결허가 — special_parcel 재사용.
    frl = sp._rule_by_road_law(result)
    if frl:
        factors.append(frl)
    return factors


def _physical_factors(result: dict[str, Any]) -> list[dict[str, Any]]:
    """현황 물리적 접근(physical) factor — 도로폭 실재 + 자루형 통로 + 현황도로."""
    factors: list[dict[str, Any]] = []
    width = sp._access_road_width(result)
    if _is_maengji(result):
        base_dev = "CONDITIONAL"
        note = "도로에 물리적으로 접하지 않아(맹지) 진입로 확보 없이는 현황 접근이 불가합니다."
    elif width is not None and width > 0:
        base_dev = "POSSIBLE"
        note = f"현황 도로폭 약 {width:g}m로 물리적 접근이 확인됩니다(정밀 폭은 현황측량 확인 권장)."
    else:
        base_dev = "REQUIRES_AUTHORITY_CONFIRMATION"
        note = ("현황 도로폭·접근 동선을 확정할 데이터가 미상입니다 — 현황측량·지적도로 물리적 접근을 "
                "확인해야 합니다(확정 아님).")
    factors.append({
        "category": "현황 물리적 접근(도로폭)",
        "developability": base_dev,
        "implications": [note],
        "legal_basis": ["건축법 제44조(대지와 도로의 관계)"],
        "legal_ref_keys": ["road_relation"],
        "permit_prerequisites": ["현황 도로폭·진입 동선 실측(현황측량)"],
    })
    # 자루형(旗竿) 대지 통로 — 신설 세분 룰.
    ff = sp._rule_by_flag_lot(result)
    if ff:
        factors.append(ff)
    # 현황도로(사실상 도로) — 인정 여부 관할 확인.
    blob = (str(result.get("road_type") or "") + " " + str(result.get("abutting_road_name") or ""))
    if result.get("is_current_road") is True or "현황도로" in blob.replace(" ", ""):
        factors.append({
            "category": "현황도로(사실상 도로) 인정",
            "developability": "CONDITIONAL",
            "implications": [
                "접한 도로가 지적상 도로가 아닌 현황도로(사실상 통행로)일 수 있어, 건축법상 도로 인정"
                "(이해관계인 동의·관할 지자체 도로지정) 여부 확인이 필요합니다.",
            ],
            "legal_basis": ["건축법 제45조(도로의 지정·폐지 또는 변경)", "건축법 제44조(대지와 도로의 관계)"],
            "legal_ref_keys": ["road_relation"],
            "permit_prerequisites": ["현황도로의 건축법상 도로 인정(지정) 여부 확인", "이해관계인 동의 여부 확인"],
        })
    return factors


def _emergency_factors(result: dict[str, Any]) -> list[dict[str, Any]]:
    """소방·응급·공사차량 접근(emergency) factor — 소방 접근폭 + 성능위주설계."""
    factors: list[dict[str, Any]] = []
    fe = sp._rule_by_emergency_access(result)
    if fe:
        factors.append(fe)
    fp = sp._rule_by_fire_performance(result)
    if fp:
        factors.append(fp)
    if not factors:
        # 소형·신호 없음 — 소방 접근 특이 없음(법정 도로 접근으로 소방자동차 접근이 통상 확보되나
        #   현장 동선은 관할 소방서 확인 권장). 과대경보 없이 정직 고지만.
        factors.append({
            "category": "소방·응급 접근(일반 규모)",
            "developability": "POSSIBLE",
            "implications": [
                "일반 규모로 별도 소방 접근 특이사항은 감지되지 않았습니다 — 법정 도로 접근이 확보되면 "
                "소방자동차 접근이 통상 가능하나, 현장 진입·회차 동선은 관할 소방서 확인을 권장합니다.",
            ],
            "legal_basis": ["소방기본법(소방활동)"],
            "legal_ref_keys": [],
            "permit_prerequisites": ["필요 시 소방자동차 접근 동선 확인"],
        })
    return factors


def assess_access(result: dict[str, Any] | None = None, **kwargs: Any) -> AccessAssessment:
    """접도·도로 기반(P4) 종합 판정 — legal/physical/emergency 3상태 + 종합 게이트.

    입력(result 또는 kwargs)은 부지분석 result와 동형(road_side·road_width_m·road_contact·
    dead_end_road·flag_lot·fire_truck_access_width_m 등). 모든 값은 optional·미상 허용.
    ★근거 없는 확정 PASS를 만들지 않는다(법정 접도 근거 미확보 시 REQUIRES_AUTHORITY_CONFIRMATION).
    """
    data: dict[str, Any] = dict(result or {})
    data.update(kwargs)
    sigungu = data.get("sigungu") or None

    legal = _build_state("legal", _legal_factors(data), sigungu=sigungu)
    physical = _build_state("physical", _physical_factors(data), sigungu=sigungu)
    emergency = _build_state("emergency", _emergency_factors(data), sigungu=sigungu)
    states = [legal, physical, emergency]

    access_dev = _worst_dev([s.developability for s in states])
    worst_res_rank = min(_RES_RANK.get(s.resolvable, 1) for s in states)
    resolvable_overall = {0: "NO", 1: "CONDITIONAL", 2: "YES"}[worst_res_rank]
    gate = sp.gate_decision(access_dev, resolvable_overall)
    status = _status_of(access_dev)
    severity = _SEVERITY_LABEL.get(access_dev, access_dev)

    # 경고 — CONDITIONAL 이상 요인만 정직 노출(과대경보 방지).
    warnings: list[str] = []
    for s in states:
        for f in s.findings:
            if _rank(f.developability) >= _rank("CONDITIONAL") and f.implications:
                warnings.append(f"[접도-{s.state_label}] {f.category}: {f.implications[0]}")

    # 종합 정직 고지 — 게이트별 문장(잠정은 tentative_marker 재사용).
    if resolvable_overall == "NO" or gate == "BLOCK":
        honest = ("⚠ 정직 고지: 접도·도로 접근에 통상 절차로 해결하기 어려운 제약이 있어, 현 상태로는 "
                  "접근 확보가 불가합니다. 무리한 개발규모 산정은 제시하지 않습니다.")
    elif gate == "TENTATIVE":
        honest = sp.tentative_marker(access_dev, resolvable_overall, severity)
    else:
        honest = "법정 접도·현황 접근·소방 접근이 확인되었습니다(각 상태의 사전확인 사항 참고)."

    # 종합 근거계약(3상태 evidence 집계).
    all_items: list[dict[str, Any]] = []
    all_keys: list[str] = []
    for s in states:
        all_items.extend(s.evidence or [])
        for ref in (s.legal_refs or []):
            k = ref.get("key") or ref.get("legal_ref_key")
            if k:
                all_keys.append(str(k))
    block = build_evidence_block(all_items, all_keys, sigungu=sigungu, sources=["vworld_land_info"])

    return AccessAssessment(
        is_assessed=True,
        access_developability=access_dev,
        gate=gate,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        severity_label=severity,
        resolvable=resolvable_overall,
        legal=legal,
        physical=physical,
        emergency=emergency,
        warnings=warnings,
        honest_disclosure=honest,
        evidence=block.get("evidence", []),
        legal_refs=block.get("legal_refs", []),
        provenance=block.get("provenance", []),
        trust=block.get("trust"),
        echo={k: data.get(k) for k in ("address", "pnu") if data.get(k)},
    )
