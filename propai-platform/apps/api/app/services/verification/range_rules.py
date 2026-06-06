"""모듈별 전용 범위 검증(Domain Range Rules) — 값 자체의 비현실 범위 적발.

Calc Ledger(산식 일치 검증)와 보완 관계: 산식이 맞아도 '값이 법정/현실 범위를 벗어난'
경우(취득세율 12% 초과, 건폐율 100% 초과, 평당공사비 비현실, 시세가 공시지가의 극단배수)를
결정론 규칙으로 잡는다. 원본·출력을 깊이탐색해 해당 키가 있을 때만 검사한다.
"""

from __future__ import annotations

from typing import Any

from app.services.verification.calc_ledger import _deep_find


def _find(source: Any, output: Any, keys: tuple[str, ...]) -> float | None:
    for h in (output, source):
        v = _deep_find(h, keys)
        if v is not None:
            return v
    return None


def _deep_find_str(obj: Any, keys: tuple[str, ...]) -> str | None:
    """중첩 dict/list에서 후보 키들 중 최초로 발견되는 비어있지 않은 문자열(깊이우선)."""
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            r = _deep_find_str(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find_str(v, keys)
            if r is not None:
                return r
    return None


def _find_str(source: Any, output: Any, keys: tuple[str, ...]) -> str | None:
    for h in (output, source):
        v = _deep_find_str(h, keys)
        if v is not None:
            return v
    return None


def run_range_checks(analysis_type: str, source: Any, output: Any) -> list[dict[str, str]]:
    """모듈별 범위 sanity 검증. 위반 이슈 목록 반환."""
    issues: list[dict[str, str]] = []
    at = (analysis_type or "").lower()

    def add(sev: str, claim: str, note: str) -> None:
        issues.append({"type": "수치범위", "claim": claim, "severity": sev, "note": note})

    # ── 공통: 건폐율·용적률·면적 ──
    bcr = _find(source, output, ("bcr", "building_coverage_ratio", "max_bcr", "effective_bcr"))
    if bcr is not None and bcr > 100:
        add("high", f"건폐율 {bcr}%", "건폐율은 100%를 초과할 수 없음")
    far = _find(source, output, ("far", "floor_area_ratio", "max_far", "effective_far"))
    if far is not None and (far < 0 or far > 2000):
        add("medium", f"용적률 {far}%", "용적률 범위(0~2000%) 이탈 — 확인 필요")
    area = _find(source, output, ("land_area_sqm", "land_area", "lot_area_sqm"))
    if area is not None and area < 0:
        add("high", f"면적 {area}㎡", "면적이 음수")

    # ── 법정 한도 대조(할루시네이션 핵심 차단) ──
    # 용도지역을 알면 일반 범위(0~2000%)가 아니라 '용도지역별 법정 상한'과 대조한다.
    # 자연녹지(법정 100%)에 200%가 제시되는 무출처 완화/추측을 high(fail)로 적발한다.
    zone_type = _find_str(
        source, output,
        ("zone_type", "zone", "use_zone", "용도지역", "zone_name", "zone_type_name"),
    )
    if zone_type:
        from app.services.zoning.legal_zone_limits import (
            _has_relaxation_basis,
            check_against_legal,
        )

        # 실효(effective)/적용(applied)/최대(max) 건폐율·용적률을 우선 대조.
        eff_bcr = _find(source, output, ("effective_bcr_pct", "effective_bcr", "applied_bcr_pct", "bcr"))
        eff_far = _find(source, output, ("effective_far_pct", "effective_far", "applied_far_pct", "far"))
        # 근거기반 판정: 페이로드(output·source) 전체에서 완화근거(기부채납/친환경/역세권/
        # 공공임대/지구단위계획 등) 신호를 탐색해 '근거 없는 법정초과'만 high로 적발한다.
        has_basis = _has_relaxation_basis(output) or _has_relaxation_basis(source)
        # 계층 적용 한도(조례 적용값·도시군관리계획/지구단위계획 상한)도 비교 기준에 반영한다.
        # source/output에 local_ordinance·zone_limits·상한용적률 등이 있으면 정당한 상향을
        # 할루시네이션으로 오적발하지 않는다(자연녹지 200%+계획상한 → info).
        for it in check_against_legal(
            zone_type, bcr_pct=eff_bcr, far_pct=eff_far, has_basis=has_basis,
            regulation_payload=[output, source],
            plan_payload=[output, source],
        ):
            issues.append(it)

    # ── 수익률(비현실 범위) ──
    roi = _find(source, output, ("profit_rate_pct", "roi", "roi_pct", "profit_rate"))
    if roi is not None and (roi > 500 or roi < -100):
        add("medium", f"수익률 {roi}%", "수익률이 비현실 범위(-100~500%) 이탈 — 가정 확인 필요")

    # ── 공사비: 평당 단가 현실범위(약 300~3,000만원/평) ──
    if at in ("cost", "feasibility", ""):
        pyeong = _find(source, output, ("per_pyeong_won", "cost_per_pyeong", "per_pyeong"))
        if pyeong is not None and (pyeong < 3_000_000 or pyeong > 30_000_000):
            add("medium", f"평당 공사비 {pyeong:,.0f}원",
                "평당 공사비가 현실범위(300~3,000만원/평)를 벗어남 — 단가·단위 확인")

    # ── 세금: 취득세율 법정 상한(12%) 초과 ──
    if at == "tax":
        rate = _find(source, output, ("base_rate", "acquisition_rate", "tax_rate"))
        # 분수형(0~1)일 때만 판정(퍼센트형과 혼동 방지)
        if rate is not None and 0 < rate <= 1 and rate > 0.12:
            add("high", f"취득세율 {rate * 100:.1f}%",
                "취득세 중과 상한(12%) 초과 — 세율표 확인(15% 등 미존재)")

    # ── 시장/AVM: 추정시세가 공시지가의 극단 배수 ──
    if at in ("market", "site", "avm", ""):
        est = _find(source, output, ("estimated_price_per_sqm", "estimated_value_per_sqm", "avm_price_per_sqm"))
        official = _find(source, output, ("official_price_per_sqm", "official_land_price", "공시지가"))
        if est is not None and official is not None and official > 0:
            ratio = est / official
            if ratio > 10 or ratio < 0.1:
                add("medium", f"추정시세/공시지가 배수 {ratio:.1f}x",
                    "추정시세가 공시지가 대비 극단 배수 — 비교표본·단위 확인")

    return issues
