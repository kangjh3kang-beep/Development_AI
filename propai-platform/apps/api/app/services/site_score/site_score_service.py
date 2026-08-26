"""PropAI SiteScore — 설명가능 학습형 입지 점수(0~100).

1차 자가학습(bootstrap): 가중치는 딥리서치(SOTA)로 도출한 연구기반 사전가중을 사용한다.
  - GIS-MCDA에 ML 가중(RF/XGBoost) + AHP/엔트로피 가중(MDPI Land 2024)
  - 15분 도시 보행 접근성(ScienceDirect 2023): 접근성 비중↑
  - 한국 맥락: 상권(SEMAS)·실거래 활성도·용도지역 반영
향후: 실거래/분양실적을 라벨로 XGBoost 학습 + SHAP로 가중·기여 대체(완전 자가학습).

런타임 자가보정: 상권·실거래·지가는 region_baseline(지역 평균)이 주어지면 상대 정규화,
없으면 연구기반 절대 밴드로 정규화한다. 누락 피처는 가중치를 재정규화해 불이익을 주지 않는다.
설명가능성: 각 피처의 정규화점수·가중·기여도(=정규화×가중)와 사유(note)를 함께 반환.
"""

from __future__ import annotations

from typing import Any

from app.services.external_api.poi_dedup import dedup_school_cluster
from app.services.verification.calc_ledger import _deep_find, _num

# 연구기반 사전가중(합=1.0). 접근성·상권 비중↑(15분도시·MCDA 근거).
# ★등급 발행 커버리지 하한 — 6개 지표 중 최소 몇 개를 확보해야 **등급을 말할 수 있는가**.
#
# 화면 감사 실측(2026-08-24): `covered=1 / total_features=6` 인데 `grade="D"` 가 단정돼
# 나갔다. 6개 중 1개만 확보한 상태는 "입지가 나쁘다"가 아니라 **"아직 모른다"** 인데,
# D 는 사용자에게 **최하 등급**으로 읽힌다 — 모름이 나쁨으로 둔갑한다.
#
# ★가중 재정규화가 이 결함을 키운다: 누락 지표를 빼고 남은 것에 가중을 몰아주므로
#   1개만 있어도 점수가 정상처럼 나오고 등급표가 그대로 적용된다.
#
# 3 = 과반(6개 중)에 못 미치더라도 **서로 다른 성격의 지표 셋**(예: 교통·상권·지가)이
# 모이면 상대 비교가 의미를 갖기 시작하는 지점. 이 값을 올리면 보류가 늘고, 내리면
# 근거 없는 단정이 늘어난다.
GRADE_COVERAGE_FLOOR: int = 3

WEIGHTS: dict[str, float] = {
    "transit": 0.24,    # 대중교통 접근성
    "commerce": 0.20,   # 상권 활력
    "market": 0.16,     # 실거래 시장 활성도
    "zoning": 0.16,     # 용도지역 개발가치
    "school": 0.12,     # 교육 접근성
    "landprice": 0.12,  # 지가(입지가치 프록시)
}

WEIGHT_BASIS = "연구기반 1차 가중(GIS-MCDA+15분도시). 데이터 누적 시 XGBoost/SHAP 자가학습으로 대체 예정."


def _band(value: float, points: list[tuple[float, float]]) -> float:
    """내림차순 (임계, 점수) 구간 선형보간 정규화(0~1). points는 우수→열위 순."""
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (t0, s0), (t1, s1) in zip(points, points[1:], strict=False):
        if t0 <= value <= t1:
            if t1 == t0:
                return s1
            r = (value - t0) / (t1 - t0)
            return s0 + (s1 - s0) * r
    return points[-1][1]


_ZONE_SCORE = [
    (("상업", "중심상업", "일반상업", "근린상업"), 1.0, "상업지역 — 개발 자유도·수익성 최상"),
    (("준주거", "준공업"), 0.85, "준주거/준공업 — 복합개발 유리"),
    (("제3종", "3종"), 0.7, "제3종일반주거 — 중밀 개발"),
    (("제2종", "2종"), 0.55, "제2종일반주거 — 중저밀"),
    (("제1종", "1종", "전용주거"), 0.4, "제1종/전용주거 — 저밀 제약"),
    (("녹지", "자연녹지", "보전", "관리", "농림"), 0.25, "녹지/관리 — 개발 제약 큼"),
]


def _zone_norm(zone: str) -> tuple[float, str]:
    z = zone or ""
    for keys, score, note in _ZONE_SCORE:
        if any(k in z for k in keys):
            return score, note
    return 0.5, "용도지역 미상 — 중립값 적용"


def compute_site_score(context: Any, region_baseline: dict[str, float] | None = None) -> dict[str, Any]:
    """부지 컨텍스트(또는 분석결과)에서 입지 점수·설명을 산출한다."""
    rb = region_baseline or {}

    infra = context.get("infrastructure") if isinstance(context, dict) and isinstance(context.get("infrastructure"), dict) else {}

    # 교통: nearest_subway.distance_m 우선, 폴백 subway_distance_m 깊이탐색
    nsub = infra.get("nearest_subway") if isinstance(infra.get("nearest_subway"), dict) else None
    subway_m = _num((nsub or {}).get("distance_m")) if nsub else _deep_find(context, ("subway_distance_m",))

    # 학교: 최근접 거리 + 개수 (★모학교 병합 G2 — 부속·분교 개별집계로 인한 학군 보너스 과대 차단)
    schools_raw = infra.get("schools") if isinstance(infra.get("schools"), list) else None
    schools = dedup_school_cluster(schools_raw) if schools_raw else None
    school_m = None
    school_n = 0
    if schools:
        school_n = len(schools)
        school_m = _num((schools[0] or {}).get("distance_m")) if isinstance(schools[0], dict) else None

    store_count = _deep_find(context, ("store_count", "commercial_count", "store_total"))
    tx_count = _deep_find(context, ("nearby_tx_count", "transaction_count", "tx_count", "nearby_count"))

    zone = ""
    if isinstance(context, dict):
        zone = context.get("zone_type") or context.get("zoneCode") or ""
        if not zone and isinstance(context.get("basic"), dict):
            zone = context["basic"].get("zone_type") or ""
    if not zone:
        zone = _deep_find_str(context, ("zone_type", "zoneCode", "zone_code")) or ""

    landprice = _deep_find(context, ("official_price_per_sqm", "pricePerSqm", "official_land_price"))

    factors: list[dict[str, Any]] = []

    def add(key: str, raw: Any, norm: float | None, note: str) -> None:
        if norm is None:
            return
        factors.append({"key": key, "name": _FNAME[key], "raw": raw,
                        "normalized": round(norm * 100, 1), "weight": WEIGHTS[key], "note": note})

    # 1) 교통
    if subway_m is not None:
        n = _band(subway_m, [(250, 1.0), (500, 0.85), (1000, 0.55), (1500, 0.3), (2500, 0.05)])
        add("transit", f"{int(subway_m)}m", n, f"최근접 지하철 {int(subway_m)}m")
    # 2) 상권
    if store_count is not None:
        base = rb.get("store_count")
        if base and base > 0:
            n = max(0.05, min(1.0, store_count / (base * 1.5)))
            note = f"상권 점포 {int(store_count)}개(지역평균 {int(base)} 대비)"
        else:
            n = _band(store_count, [(0.0, 0.1), (50.0, 0.3), (200.0, 0.55), (500.0, 0.8), (1000.0, 1.0)])
            note = f"상권 점포 {int(store_count)}개"
        add("commerce", int(store_count), n, note)
    # 3) 시장 활성도
    if tx_count is not None:
        n = _band(tx_count, [(0, 0.1), (30, 0.45), (100, 0.7), (300, 1.0)])
        add("market", int(tx_count), n, f"주변 실거래 {int(tx_count)}건(반경)")
    # 4) 용도지역
    if zone:
        zn, znote = _zone_norm(zone)
        add("zoning", zone, zn, znote)
    # 5) 교육
    if school_m is not None:
        n = _band(school_m, [(300, 1.0), (600, 0.8), (1000, 0.55), (1500, 0.3)])
        n = min(1.0, n + min(0.1, 0.03 * max(0, school_n - 1)))  # 학교 다수 보너스
        add("school", f"{int(school_m)}m/{school_n}개", n, f"최근접 학교 {int(school_m)}m, 반경 내 {school_n}개")
    # 6) 지가(입지가치 프록시)
    if landprice is not None:
        base = rb.get("official_price_per_sqm")
        if base and base > 0:
            n = max(0.1, min(1.0, landprice / (base * 2)))
            note = f"공시지가 {int(landprice):,}원/㎡(지역평균 {int(base):,} 대비)"
        else:
            n = _band(landprice, [(0, 0.1), (1_000_000, 0.4), (5_000_000, 0.7), (15_000_000, 1.0)])
            note = f"공시지가 {int(landprice):,}원/㎡"
        add("landprice", int(landprice), n, note)

    if not factors:
        # ★계약 일관성 — 등급이 없는 두 경로(0개 / 하한 미달)가 **같은 키 모양**을 내야
        #   소비처가 한 가지 방법으로 다룰 수 있다(키가 갈리면 한쪽만 처리하게 된다).
        return {"score": None, "grade": None, "factors": [],
                "grade_basis": (
                    f"판정 보류 — 입지 지표를 하나도 확보하지 못했습니다"
                    f"(등급 발행 최소 {GRADE_COVERAGE_FLOOR}/{len(WEIGHTS)}개)."
                ),
                "covered": 0, "total_features": len(WEIGHTS),
                "message": "입지 점수 산출에 필요한 데이터(교통·상권·실거래·용도지역 등)가 부족합니다.",
                "weight_basis": WEIGHT_BASIS}

    # 누락 피처 제외 후 가중 재정규화 → 기여도 계산
    wsum = sum(f["weight"] for f in factors)
    score = 0.0
    for f in factors:
        eff_w = f["weight"] / wsum
        f["effective_weight"] = round(eff_w, 3)
        f["contribution"] = round(f["normalized"] * eff_w, 1)
        score += f["contribution"]
    score = round(score, 1)

    # ★커버리지 하한 미달이면 **등급을 발행하지 않는다**(점수는 참고로 남긴다).
    #   정답이 '값'이 아니라 '보류'일 수 있다 — 같은 원칙을 탁상감정 신뢰도에도 적용했다.
    # ★2026-08-25 네이밍 정렬 — 종전 `grade_withheld_reason` 은 **이단아**였다.
    #   이 저장소의 확립된 관용은 **`X_basis`** 다(실측: `legal_basis` 293 · `far_basis` 135
    #   · `sample_basis` 18 · `gfa_basis` 16 · `price_basis` 12 · `area_basis` 11 …).
    #   뜻도 그쪽이 낫다 — **값이 어디서 왔는지**를 항상 말하므로 발행/보류 **양쪽**을 덮는다.
    #   (`_withheld_reason` 은 보류일 때만 채워져, 발행된 값의 근거는 아무도 말하지 않았다.)
    #   ★프론트 소비처 0건일 때 바꾼다 — 지금은 싸고 나중엔 비싸다.
    _covered = ", ".join(_FNAME.get(f["key"], f["key"]) for f in factors)
    if len(factors) < GRADE_COVERAGE_FLOOR:
        grade = None
        grade_basis = (
            f"판정 보류 — 입지 지표 {len(factors)}/{len(WEIGHTS)}개만 확보했습니다"
            f"(등급 발행 최소 {GRADE_COVERAGE_FLOOR}개). 확보한 지표: {_covered}"
            ". 점수는 확보분만으로 계산한 참고값입니다."
        )
    else:
        grade = ("A+" if score >= 90 else "A" if score >= 80 else "B+" if score >= 70
                 else "B" if score >= 60 else "C" if score >= 45 else "D")
        # ★발행했을 때도 **근거를 말한다** — 종전엔 이 자리가 비어 있었다(보류일 때만 채움).
        grade_basis = (
            f"입지 지표 {len(factors)}/{len(WEIGHTS)}개 확보(발행 최소 {GRADE_COVERAGE_FLOOR}개) "
            f"→ 점수 {score} 기준 등급 {grade}. 확보한 지표: {_covered}."
        )
    factors.sort(key=lambda x: x["contribution"], reverse=True)

    return {
        "score": score, "grade": grade,
        "grade_basis": grade_basis,
        "factors": factors,
        "covered": len(factors), "total_features": len(WEIGHTS),
        "weight_basis": WEIGHT_BASIS,
        "calibrated": bool(region_baseline),
    }


_FNAME = {
    "transit": "교통 접근성", "commerce": "상권 활력", "market": "시장 활성도",
    "zoning": "용도지역 가치", "school": "교육 접근성", "landprice": "지가 수준",
}

# 입지점수 산출에 쓰인 원천 데이터 출처(provenance 신선도 집계 대상).
# 상권/교통은 Kakao Local POI, 용도지역/지가는 VWorld, 시장활성도는 MOLIT 실거래.
_SITE_SCORE_SOURCES = ["kakao_local", "vworld_zoning", "vworld_land_info", "molit_transactions"]


def build_site_score_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """입지점수 결과(factors) → 근거·법령·신선도 공용 블록(전역정책 Phase0, additive).

    compute_site_score가 만든 factors[]를 한 줄씩 근거 트레이스로 변환한다(각 피처의
    원시값·정규화·기여도·산식 note를 그대로 노출 — 가짜 근거 금지). 용도지역(zoning)
    피처가 있을 때만 법령 근거(zone_use=국토계획법 제76조 용도지역 건축제한)를 연결한다.
    근거 부재(factors 비었거나 점수 미산출)면 빈 블록(정직). graceful try/except.
    """
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        factors = result.get("factors") if isinstance(result.get("factors"), list) else []
        if not factors:
            return build_evidence_block()  # 빈 블록(정직 — 산출 데이터 부족)

        items: list[dict[str, Any]] = []
        ref_keys: list[str] = []
        for f in factors:
            if not isinstance(f, dict):
                continue
            key = f.get("key")
            name = f.get("name") or key or ""
            if not name:
                continue
            # value=원시값, basis=기여도·정규화·산식 사유(note). 가중 재정규화 결과까지 투명 노출.
            contrib = f.get("contribution")
            norm = f.get("normalized")
            eff_w = f.get("effective_weight")
            basis_parts = [str(f.get("note") or "").strip()]
            if norm is not None and eff_w is not None and contrib is not None:
                basis_parts.append(f"정규화 {norm}점 × 가중 {eff_w} = 기여 {contrib}점")
            basis = " · ".join(p for p in basis_parts if p) or None
            item: dict[str, Any] = {"label": name, "value": f.get("raw"), "basis": basis}
            # 용도지역 피처에만 법령 근거(국토계획법 제76조) 연결 — 레지스트리 verified 키.
            if key == "zoning":
                item["legal_ref_key"] = "zone_use"
                ref_keys.append("zone_use")
            items.append(item)

        # 종합점수 한 줄(연구기반 가중평균 산식 — weight_basis 노출).
        if result.get("score") is not None:
            items.append({
                "label": "입지 종합점수",
                "value": f"{result.get('score')}점 ({result.get('grade') or '-'})",
                "basis": str(result.get("weight_basis") or "연구기반 가중평균").strip(),
            })

        return build_evidence_block(
            items=items,
            legal_ref_keys=ref_keys,
            sources=_SITE_SCORE_SOURCES,
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 무손상(빈 블록 폴백)
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            return build_evidence_block()
        except Exception:  # noqa: BLE001
            return {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}


def _deep_find_str(obj: Any, keys: tuple[str, ...]) -> str | None:
    """문자열 값 깊이탐색(zone_type 등)."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            r = _deep_find_str(v, keys)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find_str(v, keys)
            if r:
                return r
    return None
