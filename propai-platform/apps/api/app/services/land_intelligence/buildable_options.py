"""Stage 1 — 건축가능항목 선정·랭킹(인허가가능성 × 가용용적률).

목표 파이프라인(사용자 정의)의 2단계: 법규분석(현재속성 + 달성가능속성) 다음에
"이 부지에서 무엇을 지을 수 있는가"를 건축유형(사업유형)별로 나열하고, **인허가가능성**과
**가용 용적률**로 랭킹해 최우선 사업유형을 제시한다.

결정론·무날조·additive — 신규 의존성 0. 기존 빌딩블록만 조합한다:
- allowed_uses(design_geometry): 용도지역별 허용 건축물(국토계획법 별표 양허 목록)을
  '결정입력'으로 승격(기존엔 참조목록뿐이었음).
- classify_building_type(massing_strategy): 용도→건축유형(아파트/주상복합/오피스텔/빌라/상업).
- legal_limits_for(legal_zone_limits): 용도지역별 법정 용적률 상한(가용 far 폴백).
- UpzoningPotentialAnalyzer 결과(comprehensive sec8): 종상향 달성가능 용도지역·예상 far·
  가능성 등급(상/중/하)을 그대로 재사용(DRY — 중복 계산 금지).

랭킹식:  score = permit_feasibility_weight × achievable_far_pct
- permit_feasibility_weight: 현행(종상향 불필요)=1.0 · 종상향 상=0.85 · 중=0.6 · 하=0.35.
- 현행 용도지역 내 항목은 인허가가 가장 용이(가중치 1.0). 종상향 전제 항목은 가능성
  등급으로 감산해, '높은 용적률이지만 인허가가 어려운' 항목이 과대평가되지 않게 한다.

정직성(2계층 분리):
- 현행 옵션의 가용 far = 실효 용적률(조례 기준 사실값) — 현재 바로 지을 수 있는 값.
- 종상향 옵션의 가용 far = 목표 용도지역의 예상 far(예상치·실현 보장 아님) — upzoning에서 위임.
- allowed_uses가 None(별표 미매핑 용도지역: 녹지·관리 등)이면 현행 옵션을 만들지 않는다
  (불허 단정·날조 금지). 종상향 후 주거지역으로 바뀌면 그때 옵션이 생긴다.
"""

from __future__ import annotations

from typing import Any

from app.services.cad.massing_strategy import (
    TYPE_MIXED_USE,
    TYPE_OFFICETEL,
    classify_building_type,
)
from app.services.design_ingest.design_geometry import allowed_uses as _design_geometry_allowed_uses
from app.services.zoning.legal_zone_limits import legal_limits_for


def _allowed_uses(zone_type: str | None) -> list[str] | None:
    """용도지역 → 허용 건축물 용도 목록(별표 SSOT 수렴, P0-6/RC5).

    ★과거: design_geometry.ALLOWED_USES_BY_ZONE(설계기하 전용 표)을 1차 소스로 썼는데 그 표에
    녹지·관리·농림 키가 없어 자연녹지 등에서 현행 옵션이 0건으로 나왔다(개발방식 섹션은 별표
    기준 단독·전원 가능이라고 답하는데 랭킹은 0건 — 3소스 모순, 라이브 재현). 개발유형 별표
    SSOT(development_type_analyzer.ZONE_ALLOWED_BUILDINGS — 국토계획법 시행령 별표2~20, 자연
    녹지 등 녹지지역 3종 포함)를 1차 소스로 삼고, 그 표에 없는 용도지역만 design_geometry로
    폴백한다(design_geometry는 설계기하 전용 표로 그대로 유지 — 수정 없음).
    """
    from app.services.zoning.development_type_analyzer import ZONE_ALLOWED_BUILDINGS

    key = (zone_type or "").replace(" ", "").strip()
    raw = ZONE_ALLOWED_BUILDINGS.get(key)
    if not raw:
        for zk in ZONE_ALLOWED_BUILDINGS:
            if zk in key or key in zk:
                raw = ZONE_ALLOWED_BUILDINGS[zk]
                break
    if raw:
        # type_name 공백 제거(design_geometry 표기·_USE_TO_PRODUCT 매칭과 정합 — 예: "제1종 근린생활시설"
        # → "제1종근린생활시설"). _product_and_type의 부분일치(예: "공동주택" in u)는 영향 없음.
        return [str(item["type_name"]).replace(" ", "") for item in raw]
    return _design_geometry_allowed_uses(zone_type)


# 인허가가능성(permit feasibility) → 가중치. 가용 용적률에 곱해 랭킹 점수를 만든다.
_FEASIBILITY_WEIGHT: dict[str, float] = {
    "현행": 1.0,  # 현행 용도지역 내 — 종상향 불필요(인허가 가장 용이)
    "상": 0.85,
    "중": 0.6,
    "하": 0.35,
}

# 인허가 난이도 사용자 라벨(프론트 표기·툴팁).
_DIFFICULTY_LABEL: dict[str, str] = {
    "현행": "용이 — 현행 용도지역 내(종상향 불필요)",
    "상": "보통 — 종상향 가능성 높음",
    "중": "보통~어려움 — 종상향 조건부",
    "하": "어려움 — 종상향 난이도 높음",
}

# 사업유형별 'FAR 활용 적합도'(0~9) — 점수 동점 시 보조 정렬키.
# ★주의: 사업성(수익) 수치를 날조하는 것이 아니라, 같은 용도지역(=같은 가용 far·같은 인허가
#   가능성)에서 모든 허용용도가 동점이 될 때, 그 용적률을 실제로 소진(활용)하는 고밀 사업유형을
#   대표로 앞세우기 위한 결정론 우선순위다(근생·단독이 고용적 종상향의 '최우선'으로 뜨는 왜곡 방지).
#   실제 사업성 비교는 Stage 3(유사건축물 시장조사·feasibility v2)에서 정량 산출한다.
_PRODUCT_FAR_UTILITY: dict[str, int] = {
    "주상복합": 9,
    "공동주택(아파트)": 8,
    "오피스텔": 7,
    "업무시설(오피스)": 6,
    "지식산업센터": 6,
    "판매시설(상업)": 5,
    "숙박시설": 5,
    "물류시설": 4,
    "공장": 3,
    "근린생활시설": 2,
    "단독·다가구주택": 1,
}

# 별표 허용 용도(use) → 사업유형(product) 라벨(결정론). 목록 외 use는 원문을 그대로 쓴다(무날조).
_USE_TO_PRODUCT: dict[str, str] = {
    "단독주택": "단독·다가구주택",
    "업무시설": "업무시설(오피스)",
    "판매시설": "판매시설(상업)",
    "숙박시설": "숙박시설",
    "제1종근린생활시설": "근린생활시설",
    "제2종근린생활시설": "근린생활시설",
    "공장": "공장",
    "물류시설": "물류시설",
    "지식산업센터": "지식산업센터",
    "오피스텔": "오피스텔",
}


def _norm(text: str | None) -> str:
    return (text or "").replace(" ", "").strip()


def _to_far(value: Any) -> float | None:
    """유한 양수 용적률(%)만 추출. 그 외(0·음수·비수치)는 None(가용 far 미확인)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _product_and_type(zone: str, use: str) -> tuple[str, str]:
    """(용도지역, 허용용도) → (사업유형 라벨, 건축유형[massing]). 결정론.

    공동주택은 상업/준주거에서 '주상복합', 주거지역에서 '공동주택(아파트)'으로 구분한다
    (classify_building_type의 massing 분류를 사업유형 라벨로 변환). 그 외 용도는 별표 원문
    기반 라벨(_USE_TO_PRODUCT)을 쓴다.
    """
    u = _norm(use)
    bt = classify_building_type(zone_code=zone, building_use=use)
    if "공동주택" in u or "아파트" in u:
        if bt == TYPE_MIXED_USE:
            return "주상복합", bt
        return "공동주택(아파트)", bt
    if "오피스텔" in u:
        return "오피스텔", TYPE_OFFICETEL
    return _USE_TO_PRODUCT.get(u, use), bt


def _candidate(
    *,
    zone: str,
    use: str,
    far: float | None,
    feasibility: str,
    via: str,
    is_current: bool,
    path_key: str | None = None,
    legal_refs: list[dict] | None = None,
    far_source: str = "",
) -> dict[str, Any]:
    """건축가능항목 후보 1건(랭킹 점수 포함)."""
    product, building_type = _product_and_type(zone, use)
    weight = _FEASIBILITY_WEIGHT.get(feasibility, 0.5)
    # far를 한 번 정수 반올림해 표시값(achievable_far_pct)·점수(score)를 일관 계산한다
    # (표시와 점수 근거가 어긋나지 않게). far 미확인이면 score 0(하위 랭크·정직).
    far_int = round(far) if far is not None else None
    score = round(weight * far_int, 1) if far_int is not None else 0.0
    return {
        "product": product,            # 사업유형 라벨(아파트/주상복합/오피스텔/상업…)
        "use": use,                    # 별표 허용 용도(원문·그라운딩)
        "building_type": building_type,  # Stage 2/4 매싱 핸드오프용 건축유형
        "zone": zone,                  # 이 항목이 가능한 용도지역(현행 또는 종상향 목표)
        "achievable_far_pct": far_int,
        "far_source": far_source,
        "permit_feasibility": feasibility,                 # 현행/상/중/하
        "permit_difficulty": _DIFFICULTY_LABEL.get(feasibility, "확인필요"),
        "via": via,                    # 달성 경로(현행 용도지역 / 종상향 경로명)
        "path_key": path_key,
        "is_current": is_current,      # True=현행 용도지역 내(바로 가능)
        "is_upzoning": not is_current,  # True=종상향 전제(예상치)
        # tier: is_current에서 파생된 응답 계약 필드(프론트·정렬정책 공유용 표준명).
        "tier": "current" if is_current else "upzoning",
        "legal_refs": legal_refs or [],
        "score": score,
    }


def rank_buildable_options(
    *,
    zone_type: str | None,
    effective_far_pct: Any = None,
    upzoning: dict[str, Any] | None = None,
    max_options: int = 14,
) -> dict[str, Any]:
    """건축가능항목을 인허가가능성 × 가용용적률로 랭킹해 반환.

    Args:
        zone_type: 현행 용도지역(한글명/코드).
        effective_far_pct: 현행 실효 용적률(조례 기준 사실값·%). None이면 법정상한 폴백.
        upzoning: comprehensive sec8(upzoning) 결과 dict — scenarios[] 재사용(DRY).
                  None이면 종상향 옵션 없이 현행만 산출.
        max_options: 반환 옵션 상한(현행/종상향 버킷 합산).

    Returns:
        {
          "options": [ {product, building_type, zone, achievable_far_pct,
                        permit_feasibility, permit_difficulty, via, is_current,
                        score, legal_refs, alternatives[]}, ... ],  # score 내림차순
          "top_recommendation": options[0] | None,
          "current_zone": zone_type,
          "summary": str,
          "disclaimer": str,
        }
        zone_type 미상 또는 가능 항목 0건이면 options=[]·정직 summary.
    """
    if not zone_type:
        return {
            "options": [],
            "top_recommendation": None,
            "current_zone": zone_type,
            "summary": "용도지역 미상 — 건축가능항목을 산출할 수 없습니다(주소/PNU 확인 필요).",
            "disclaimer": _disclaimer(),
        }

    candidates: list[dict[str, Any]] = []

    # ── (A) 현행 용도지역 내 건축가능항목(인허가 가장 용이) ──
    cur_uses = _allowed_uses(zone_type) or []
    cur_far = _to_far(effective_far_pct)
    cur_far_source = "현행 실효 용적률(조례 기준)"
    if cur_far is None:
        legal = legal_limits_for(zone_type)
        cur_far = _to_far(legal.get("max_far_pct")) if legal else None
        cur_far_source = "법정 용적률 상한(국토계획법 시행령·조례 미확인)"
    for use in cur_uses:
        candidates.append(_candidate(
            zone=zone_type, use=use, far=cur_far, feasibility="현행",
            via="현행 용도지역", is_current=True, far_source=cur_far_source,
        ))

    # ── (B) 종상향 달성가능 용도지역의 건축가능항목(예상치) ──
    # ★견고성(SSOT 계약): malformed 입력(비-dict upzoning·비-list scenarios·비-dict 요소)도
    #   crash 없이 현행 옵션만 반환하도록 isinstance 가드(직접/미래 호출자 보호).
    _up = upzoning if isinstance(upzoning, dict) else {}
    scenarios = _up.get("scenarios")
    scenarios = scenarios if isinstance(scenarios, list) else []
    for sc in scenarios:
        if not isinstance(sc, dict):
            continue
        target_zone = sc.get("target_zone")
        if not target_zone:
            continue
        feasibility = sc.get("feasibility") or "중"
        far = _to_far(sc.get("expected_far_pct_high"))
        far_source = sc.get("expected_far_source") or "종상향 목표지역 예상 용적률(예상치)"
        if far is None:
            legal = legal_limits_for(target_zone)
            far = _to_far(legal.get("max_far_pct")) if legal else None
        for use in (_allowed_uses(target_zone) or []):
            candidates.append(_candidate(
                zone=target_zone, use=use, far=far, feasibility=feasibility,
                via=sc.get("path") or "종상향", is_current=False,
                path_key=sc.get("path_key"), legal_refs=sc.get("legal_refs") or [],
                far_source=far_source,
            ))

    if not candidates:
        return {
            "options": [],
            "top_recommendation": None,
            "current_zone": zone_type,
            "summary": (
                f"'{zone_type}'은(는) 별표 허용용도 매핑·종상향 경로가 확인되지 않아 "
                "건축가능항목을 산출하지 못했습니다(지구단위·조례 개별 확인 필요)."
            ),
            "disclaimer": _disclaimer(),
        }

    # ── 사업유형×버킷(현행/종상향)별 대표 1건(최고 score) + 동일 유형 대안 ──
    # 같은 사업유형이라도 '현행 바로 가능'과 '종상향 후 가능(고용적)'은 별개 의사결정이므로
    # 버킷을 분리해 각 버킷의 최고 점수 항목을 대표로 둔다(과도한 dedup으로 옵션 은폐 방지).
    groups: dict[tuple[str, bool], list[dict[str, Any]]] = {}
    for c in candidates:
        groups.setdefault((c["product"], c["is_current"]), []).append(c)

    options: list[dict[str, Any]] = []
    for (_product, _is_cur), members in groups.items():
        members.sort(key=lambda m: m["score"], reverse=True)
        rep = dict(members[0])
        # 대안(동일 사업유형의 다른 경로) — 경로·목표지역·점수 요약. 변별 필드(use) 포함하고,
        # 대표와 (via,zone,score)가 동일한 무가치 중복(예 제1·2종근생→근린생활시설)은 제외.
        _seen: set[tuple[Any, Any, float]] = {(rep["via"], rep["zone"], rep["score"])}
        rep["alternatives"] = []
        for m in members[1:]:
            sig = (m["via"], m["zone"], m["score"])
            if sig in _seen:
                continue
            _seen.add(sig)
            rep["alternatives"].append({
                "use": m["use"],
                "via": m["via"],
                "zone": m["zone"],
                "achievable_far_pct": m["achievable_far_pct"],
                "permit_feasibility": m["permit_feasibility"],
                "score": m["score"],
            })
        options.append(rep)

    # ★정렬 정책(P0 수정): 현행(tier=current) 옵션은 종상향(tier=upzoning)보다 항상 상위다.
    # 과거엔 순수 score 정렬이라 '예상치·미확정'인 종상향이 점수만 높으면 '현행·바로가능'보다
    # 앞서 최우선 사업유형으로 오인될 위험이 있었다(라이브: 종상향 종속 사업유형이 1순위로
    # 표시). is_current를 최우선 정렬키로 승격하고, 그다음은 기존과 동일하게 ①score 내림차순
    # → ②동점 시 FAR 활용 적합도(고밀 사업유형 우대)로 티어 내부 순서를 유지한다.
    options.sort(
        key=lambda o: (
            o["is_current"],
            o["score"],
            _PRODUCT_FAR_UTILITY.get(o["product"], 0),
        ),
        reverse=True,
    )
    options = options[:max_options]

    return {
        "options": options,
        "top_recommendation": options[0] if options else None,
        "current_zone": zone_type,
        "summary": _summary(zone_type, options),
        "disclaimer": _disclaimer(),
    }


def _summary(zone: str, options: list[dict[str, Any]]) -> str:
    if not options:
        return f"'{zone}'의 건축가능항목을 산출하지 못했습니다."
    current_options = [o for o in options if o["is_current"]]
    upzoning_options = [o for o in options if o["is_upzoning"]]
    cur_cnt, up_cnt = len(current_options), len(upzoning_options)
    parts = [
        f"현행 '{zone}' 기준 건축가능 사업유형 {len(options)}건을 인허가가능성×가용용적률로 "
        f"랭킹했습니다(현행 {cur_cnt}건·종상향 전제 {up_cnt}건)."
    ]
    # ★서술 분리(P0): '최우선 사업유형'은 항상 현행 티어 1위로 한정하고, 종상향 1위는
    # 별도로 '조건부 잠재'로 표현한다(정렬정책과 정합 — 종상향이 최우선으로 오인되지 않게).
    if current_options:
        top_cur = current_options[0]
        far_txt = (
            f" 가용 용적률 약 {top_cur['achievable_far_pct']}%"
            if top_cur.get("achievable_far_pct") is not None else ""
        )
        parts.append(
            f"최우선 사업유형은 '{top_cur['product']}'(현행 용도지역 내·"
            f"인허가 {top_cur['permit_feasibility']}{far_txt})입니다."
        )
    else:
        parts.append("현행 용도지역 내 바로 가능한 사업유형은 확인되지 않았습니다.")
    if upzoning_options:
        top_up = upzoning_options[0]
        far_txt = (
            f" 가용 용적률 약 {top_up['achievable_far_pct']}%"
            if top_up.get("achievable_far_pct") is not None else ""
        )
        parts.append(
            f"종상향 전제 조건부 잠재 1순위는 '{top_up['product']}'"
            f"(종상향({top_up['via']}) 전제·인허가 {top_up['permit_feasibility']}{far_txt})이며, "
            "용적률은 예상치(실현 보장 아님)로 현행 실효값과 구분됩니다."
        )
    return " ".join(parts)


def _disclaimer() -> str:
    return (
        "건축가능항목은 국토계획법 시행령 별표(용도지역별 허용 건축물 양허목록)와 종상향 "
        "잠재 시나리오를 결합한 분석입니다. 현행 항목의 용적률은 실효(조례) 사실값, 종상향 "
        "항목은 목표지역 예상치(도시계획 결정·인허가 전제)입니다. 지구단위계획·조례 강화·세부 "
        "단서는 개별 확인이 필요하며, 목록에 없다고 불허로 단정하지 않습니다(양허 방식)."
    )
