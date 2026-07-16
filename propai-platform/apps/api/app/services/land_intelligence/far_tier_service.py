"""실효용적률 계층 산정 + 종상향 잠재 시나리오 — 단일출처(SSOT) 공용 모듈.

`ComprehensiveAnalysisService`(`/analysis/comprehensive`)와 `LandInfoService`
(`/zoning/comprehensive`·`/zoning/analyze` 화면경로)가 **동일 로직**을 공유하도록
모듈 레벨 함수로 추출한다(로직 복제 금지). 두 호출 모두 이 함수만 사용한다.

반환 필드는 프론트(site-analysis page.tsx, cf6dfda) 캡처 필드명과 정합:
- effective_far(객체, effective_far_pct·far_basis_detail 포함)
- upzoning(scenarios·potential_far_range 포함) / upzoning_scenarios / potential_far_range
"""

from __future__ import annotations

import contextlib
from typing import Any

import structlog

from app.services.zoning.far_incentive_calculator import calculate as calc_far_incentive

logger = structlog.get_logger()

_PYEONG = 3.305785  # 1평 = 3.305785㎡


def build_area_annotation(
    *,
    land_area: float,
    effective_far: float,
    effective_bcr: float,
    parcel_count: int = 1,
    zone_mix: list | None = None,
) -> str:
    """면적의존 문구(최대 연면적/건축면적) 생성 — 단일필지·다필지 공용 SSOT.

    왜 필요한가(쉬운 설명): 이 문구는 "대지면적 X㎡ 기준 최대 연면적 …"인데, 여러 필지를
    합친 부지(다필지)에서는 X가 통합 면적이어야 한다. 예전엔 이 문구를 대표필지(작은 면적)로
    한 번 만들고, 다필지 통합 때 숫자(용적률)만 바꾸고 문구는 안 고쳐서 "763㎡ 기준" 같은
    대표필지 값이 그대로 노출되는 버그가 있었다. 그래서 문구 생성을 이 함수 1곳으로 모아,
    단일 경로와 다필지 통합 경로가 같은 함수로 문구를 만들게 한다(어긋남 원천 차단).
    """
    max_gfa = land_area * effective_far / 100
    max_bldg = land_area * effective_bcr / 100
    # 다필지(2필지 이상)면 "통합 대지면적"임을 명시해 대표필지 오인을 막는다(정직 표기).
    if parcel_count and parcel_count >= 2:
        mix_note = ""
        if zone_mix and len(zone_mix) >= 2:
            mix_note = "(용도지역 혼재 — 면적가중 실효치 적용) "
        prefix = f"{parcel_count}개 필지 통합 대지면적 {land_area:,.1f}㎡ {mix_note}기준으로"
    else:
        prefix = f"대지면적 {land_area:,.1f}㎡ 기준으로"
    return (
        f"{prefix} 최대 연면적 {max_gfa:,.1f}㎡ (약 {max_gfa / _PYEONG:,.0f}평), "
        f"최대 건축면적 {max_bldg:,.1f}㎡ (약 {max_bldg / _PYEONG:,.0f}평)까지 "
        f"건축이 가능합니다."
    )


def _structural_cap_for(
    zone_type: str | None, effective_bcr: float,
) -> tuple[float | None, int | None, str | None]:
    """용도지역 법정 층수상한(legal_zone_limits SSOT) × 실효 건폐율 = 구조상한(%).

    ★확정버그(2026-07-12): 자연/생산녹지 등은 법정 용적률 '범위'(예: 자연녹지 50~100%)만
    보면 100%까지 허용되는 것처럼 보이지만, 국토계획법 시행령 별표15~17 두문(4층 이하)이
    실질 상한을 만든다(건폐 20%×4층=80% < 법정 100%). 이 물리적 상한을 반영하지 않으면
    실효 용적률을 과대표시하는 할루시네이션이 된다(90초진단 재현). 근거 미확인 zone
    (legal_zone_limits.max_floors=None)은 (None,None,None) — 절대 적용하지 않는다(무날조).
    단일필지(calc_effective_far)·다필지 통합(rebuild_area_dependent) 양쪽이 이 헬퍼 하나로
    구조상한을 산정한다(산식 복제 금지).
    """
    from app.services.zoning.legal_zone_limits import legal_limits_for

    limits = legal_limits_for(zone_type) or {}
    floor_cap = limits.get("max_floors")
    if not floor_cap:
        return None, None, None
    return round(effective_bcr * floor_cap, 2), floor_cap, limits.get("floor_cap_basis")


def rebuild_area_dependent(
    sec1: dict[str, Any],
    *,
    land_area: float,
    effective_far: float,
    effective_bcr: float,
    zone_type: str,
    national_far: float | None = None,
    parcel_count: int = 1,
    zone_mix: list | None = None,
) -> dict[str, Any]:
    """면적의존 산출물(annotations 문구 + far_optimization)만 통합 기준으로 재생성한다.

    ★다필지 통합 override 전용 공용 함수. calc_effective_far 전체를 다시 부르지 않는다 —
    대표필지 base의 조례값으로 단일존 실효율을 재산출하면 blended(면적가중) 수치와 어긋나기
    때문이다(혼재 용도지역 자기모순). 오직 '면적에만 의존하는' 산출물 2가지만 갈아끼운다.
    나머지 면적 무관 문구(법정/조례 서술)와 필드는 그대로 보존한다(무회귀).
    """
    out = dict(sec1)
    # ★None-값 가드(WP-U1f): sec1에 national_far_pct 키가 None '값'으로 존재하면 dict.get의
    #   기본값(effective_far)이 무시되어 _nat=None → 아래 float(_nat)에서 TypeError 크래시
    #   (다필지 override 경로: blended_far_legal_pct=None ∧ sec1.national_far_pct=None).
    #   None이면 기존 의도대로 effective_far로 폴백한다(값 의미 변화 없음 — 크래시 가드만).
    _nat_sec1 = out.get("national_far_pct")
    _nat = national_far if national_far is not None else (
        _nat_sec1 if _nat_sec1 is not None else effective_far
    )

    # 1) annotations 중 '면적의존 문구'만 교체(다른 문구는 순서·내용 보존).
    new_ann = build_area_annotation(
        land_area=land_area, effective_far=effective_far, effective_bcr=effective_bcr,
        parcel_count=parcel_count, zone_mix=zone_mix,
    )
    anns = list(out.get("annotations") or [])
    replaced = False
    for i, a in enumerate(anns):
        # 면적의존 문구는 "최대 연면적"과 "건축이 가능합니다"를 함께 가진다(식별 키).
        if isinstance(a, str) and "최대 연면적" in a and "건축이 가능합니다" in a:
            anns[i] = new_ann
            replaced = True
            break
    if not replaced and land_area > 0:
        anns.append(new_ann)  # 원래 면적문구가 없던 경우(면적 0 등) 추가
    out["annotations"] = anns

    # ── 구조상한(건폐율×층수) — 다필지 통합(대표/우세 zone 기준)도 단일필지와 동일 헬퍼로 산정 ──
    #   zone_mix 혼재 시에도 대표(우세) zone의 층수제한을 참고치로 노출한다(zone별 정밀 가중은
    #   이미 각 필지의 _far_eff가 calc_effective_far를 거치며 개별 반영 → blended에 전파됨).
    structural_cap_pct, floor_cap, floor_cap_basis = _structural_cap_for(zone_type, effective_bcr)
    out["structural_cap_pct"] = structural_cap_pct
    out["floor_cap"] = floor_cap
    out["floor_cap_basis"] = floor_cap_basis

    # 2) far_optimization(FAR 시나리오별 GFA 테이블)을 통합면적 기준으로 재생성.
    if land_area > 0:
        out["far_optimization"] = simulate_far_optimization(
            zone_type, effective_far, float(_nat), land_area,
            structural_cap_pct=structural_cap_pct,
        )
    return out


def rebuild_legal_basis_annotations(
    sec1: dict[str, Any],
    *,
    effective_far: float,
    effective_bcr: float,
    national_far: float | None = None,
    national_bcr: float | None = None,
    parcel_count: int = 1,
    zone_mix: list | None = None,
) -> dict[str, Any]:
    """다필지 통합(blended) override 시 '법정/조례 비교' 서술 문구만 통합 기준으로 재생성한다.

    ★P0-5(RC7) 봉합: rebuild_area_dependent는 면적의존 문구(최대 연면적 등)만 갈아끼우고
    "법정 용적률 상한은 250%입니다"·"실효 용적률은 법정상한(250%)과 조례(200%) 중 낮은 값인
    200%가 적용됩니다" 같은 법정/조례 비교 서술은 대표필지(단일존) 값 그대로 보존한다(그 함수의
    설계 계약 — 의도적). 하지만 다필지 통합에서는 표시 수치(effective_far_pct)가 면적가중
    blended 값(예: 139.6%)으로 override되므로, 저 문장을 그대로 두면 "실효 용적률 139.6% vs
    문장 속 200%가 적용됩니다" 같은 수치-서술 충돌이 남는다(라이브 재현 버그). 이 함수는 그
    법정/조례 비교 문장만 통합 기준 1문장으로 교체하고, 나머지 문구(면적문구·인센티브 안내 등)는
    건드리지 않는다(블라스트 최소).
    """
    out = dict(sec1)
    anns = list(out.get("annotations") or [])

    def _is_legal_basis_line(a: Any) -> bool:
        if not isinstance(a, str):
            return False
        return (
            ("법정" in a and ("건폐율 상한" in a or "용적률 상한" in a))
            or "실효 용적률은 법정상한" in a
            or "도시계획 조례에서 용적률을" in a
            or "조례에서 건폐율을" in a
        )

    insert_at = next((i for i, a in enumerate(anns) if _is_legal_basis_line(a)), 0)
    kept = [a for a in anns if not _is_legal_basis_line(a)]

    mix_note = ""
    if zone_mix and len(zone_mix) >= 2:
        mix_note = "(용도지역 혼재 — 필지별 법정상한이 다를 수 있어 개별 필지 기준과 차이가 있을 수 있음) "
    scope = f"{parcel_count}개 필지 통합 " if parcel_count and parcel_count >= 2 else ""
    summary = (
        f"{scope}면적가중 {mix_note}기준 실효 용적률은 {effective_far:g}%, "
        f"실효 건폐율은 {effective_bcr:g}%입니다"
    )
    if national_far is not None:
        summary += f"(통합 법정/조례 적용상한 기준 {national_far:g}%)"
    if national_bcr is not None:
        summary += f", 통합 건폐율 상한 기준 {national_bcr:g}%"
    summary += "."

    kept.insert(min(insert_at, len(kept)), summary)
    out["annotations"] = kept
    return out


def calc_effective_far(base: dict, zone_type: str, land_area: float = 0) -> dict[str, Any]:
    """실효 용적률 계층(법정범위→조례→계획상한→인센티브) 산정.

    `base`는 LandInfoService.collect_comprehensive 결과(local_ordinance·zone_limits·
    special_districts 포함). far_basis_detail 메타를 동봉해 그라운딩/검증기가 활용한다.
    """
    ordinance = base.get("local_ordinance") or {}
    zone_limits = base.get("zone_limits") or {}

    # 법정상한 SSOT: zone_limits가 비어/누락이어도 용도지역명으로 법정값을 도출한다.
    # (과거 폴백 60/200은 자연녹지(법정 20/100)에 200%/60%를 지어내는 할루시네이션 원인이었음)
    from app.services.zoning.legal_zone_limits import (
        applicable_limits_for,
        legal_limits_for,
    )
    legal = legal_limits_for(zone_type) or {}
    legal_bcr = legal.get("max_bcr_pct")
    legal_far = legal.get("max_far_pct")
    legal_min_far = legal.get("min_far_pct")

    # ★P0-1(RC1) 무날조 정직 반환: 용도지역이 법정 SSOT(legal_limits_for)에서도, zone_limits
    #   페이로드에서도 확인되지 않으면(예: 개발제한구역·도로 등 '용도지역'이 아닌 용도구역/지목이
    #   zone_type으로 잘못 들어온 경우) 아래 60%/200% 하드코딩 폴백으로 넘어가지 않고 여기서
    #   eff/legal 모두 None으로 정직 반환한다. 과거엔 이 경로가 자연녹지(법정 20/100)에 200%/60%를
    #   지어내 다필지 면적가중 블렌드를 139.6%로 오염시켰다(라이브 재현: 자연녹지+개발제한구역
    #   혼재 9필지). 소비처(_aggregate_integrated_zoning)는 이미 eff=None 필지를 가중에서
    #   제외하고 warning을 남기는 구조라 여기서 None만 정직 반환하면 전파는 안전하다.
    zl_bcr_present = bool(zone_limits.get("max_bcr_pct") or zone_limits.get("bcr"))
    zl_far_present = bool(zone_limits.get("max_far_pct") or zone_limits.get("far"))
    if legal_bcr is None and legal_far is None and not zl_bcr_present and not zl_far_present:
        return {
            "national_bcr_pct": None,
            "national_far_pct": None,
            "ordinance_bcr_pct": None,
            "ordinance_far_pct": None,
            "effective_bcr_pct": None,
            "effective_far_pct": None,
            "far_basis": "zone_unmatched",
            "far_basis_detail": {
                "법정범위": None,
                "조례값": None,
                "계획상한": None,
                "인센티브": None,
                "최종근거": "용도지역 미확인(법정 상한 매칭 실패) — 임의값 미생성(정직)",
                "데이터출처": [],
                "조례확인필요": True,
            },
            "ordinance_confirmed": False,
            "legal_min_far_pct": None,
            "legal_max_far_pct": None,
            "relaxation_present": False,
            "far_incentive": {},
            "source": "미확인",
            "annotations": [
                f"'{zone_type or '(용도지역 미상)'}'은(는) 법정 건폐율/용적률 상한 매칭에 실패한 "
                "용도지역(개발제한구역 등 비도시계획 용도구역이거나 지목이 잘못 전달된 경우 포함)"
                "입니다. 임의 수치를 지어내지 않고 실효/법정 용적률을 정직하게 미확인으로 처리합니다."
            ],
            # 구조상한(건폐율×층수) — zone 미확인이라 산정 불가(스키마 정합용 additive None).
            "structural_cap_pct": None,
            "floor_cap": None,
            "floor_cap_basis": None,
            "far_optimization": {},
        }

    # ── 계층 적용 한도 산정: 법정범위 → 조례 적용값 → 도시·군관리계획/지구단위계획 상한.
    # base(local_ordinance/zone_limits)와 special_districts(계획 상한용적률)를 페이로드로 전달.
    applied = applicable_limits_for(
        zone_type,
        sigungu=(ordinance.get("sigungu") if isinstance(base.get("local_ordinance"), dict) else None),
        regulation_payload=base,
        plan_payload=base.get("special_districts"),
    ) or {}

    # ★법정(국토계획법) 상한은 '용도지역 라벨 기준 SSOT(legal_*)'를 최우선으로 채택한다.
    # (이전: 업스트림 zone_limits.max_*_pct를 먼저 신뢰 → 라벨과 불일치한 값(예: 일반상업지역에
    #  제1종주거값 60/200)이 그대로 표시되고 실효=min(200,800)=200으로 오염되는 버그.
    #  법정값은 용도지역명으로 결정되는 고정 상한이므로, 라벨에서 도출한 legal_*가 진실의 단일원천.)
    national_bcr = float(
        legal_bcr
        or zone_limits.get("max_bcr_pct")
        or zone_limits.get("bcr")
        or 60
    )
    national_far = float(
        legal_far
        or zone_limits.get("max_far_pct")
        or zone_limits.get("far")
        or 200
    )
    ordinance_bcr = float(ordinance.get("effective_bcr") or ordinance.get("ordinance_bcr") or national_bcr)
    ordinance_far = float(ordinance.get("effective_far") or ordinance.get("ordinance_far") or national_far)
    effective_bcr = min(national_bcr, ordinance_bcr)
    effective_far = min(national_far, ordinance_far)

    # ── 완화근거(basis) 인지: effective는 '법정값을 기본'으로 하되, 페이로드에 명시적
    #    완화근거/완화율이 있을 때만 상향을 반영한다(근거 없으면 법정값 유지).
    #    interpreter·검증기가 활용하도록 basis 메타를 동봉한다.
    from app.services.zoning.legal_zone_limits import (
        SANITY_MULTIPLIER,
        _has_relaxation_basis,
    )
    relaxation_ratio = (
        ordinance.get("relaxation_ratio_pct")
        or ordinance.get("완화율")
        or base.get("relaxation_ratio_pct")
    )
    basis_present = (
        relaxation_ratio is not None
        or _has_relaxation_basis(ordinance)
        or _has_relaxation_basis(base.get("special_districts"))
    )
    far_basis = "법정/조례"  # 기본: 법정값(조례 가감 반영)

    # ── 산정 계층: 1)법정범위 → 2)조례 적용값 → 3)도시·군관리계획/지구단위계획 상한 → 4)인센티브.
    ordinance_confirmed = bool(applied.get("ordinance_confirmed"))
    plan_far_ceiling = applied.get("plan_far_pct")
    # 기준 용적률(상한): 조례 적용값(있으면) > 법정범위 max(없으면, 확인필요 플래그).
    if ordinance_confirmed:
        far_basis = f"조례 적용값({applied.get('far_source') or '지자체 도시계획조례'})"
    # 도시·군관리계획/지구단위계획 상한용적률이 있으면 최우선(조례·법정 초과 정당).
    if plan_far_ceiling is not None:
        effective_far = max(effective_far, float(plan_far_ceiling))
        far_basis = "도시·군관리계획/지구단위계획 상한용적률(최우선 적용)"

    # 4) 인센티브 완화율(근거 있을 때만) — 상한용적률 cap.
    if basis_present and relaxation_ratio is not None:
        try:
            ratio = float(relaxation_ratio)
            # 완화율(%)을 기준 용적률에 반영하되 합리성 절대 상한(법정×배수) 내로 제한.
            relaxed = national_far * (1.0 + ratio / 100.0)
            cap = national_far * SANITY_MULTIPLIER
            effective_far = min(max(effective_far, relaxed), cap)
            far_basis = f"완화근거(완화율 {ratio:g}%) 반영"
        except (TypeError, ValueError):
            pass
    elif basis_present and plan_far_ceiling is None and not ordinance_confirmed:
        # 근거 키워드는 있으나 정량 완화율·조례·계획 미제시 → 법정값 유지(가능성만 안내).
        far_basis = "완화근거 명시(정량 완화율 미제시 — 별도 검토 필요)"

    # ★provenance 정직성: 조례 미확정(법정상한 폴백)이고 계획상한·완화근거도 없으면
    #   far_basis를 '법정상한 적용(조례 미확인)'으로 정직 표기한다(false-confirmed 방지).
    #   ordinance_service 3차 폴백(source='법정상한', recheck_recommended=True)을 신호로 인식.
    #   ★recheck_recommended는 ordinance_service._attach_provenance가 최상위가 아닌
    #   ordinance["provenance"]["recheck_recommended"]에 싣는다(top-level 읽기는 항상 falsy
    #   dead-branch였음) — provenance 하위를 우선 읽고, 구버전 호출부 호환을 위해 top-level도
    #   폴백으로 허용한다.
    _ord_src = str(ordinance.get("source") or "")
    _ord_provenance = ordinance.get("provenance") if isinstance(ordinance.get("provenance"), dict) else {}
    _ord_recheck = bool(_ord_provenance.get("recheck_recommended")) or bool(
        ordinance.get("recheck_recommended")
    )
    if (
        not ordinance_confirmed
        and plan_far_ceiling is None
        and not basis_present
        and ("법정상한" in _ord_src or _ord_recheck)
    ):
        far_basis = "법정상한 적용(조례 미확인)"

    # ── 구조상한(건폐율×층수) 계층 — 층수 제한 존재 zone(자연/생산녹지 등)만 최종 적용 ──
    #   법정/조례/계획/인센티브를 모두 반영한 '기존 실효'가 최종 확정된 시점에 마지막으로
    #   물리적 상한(건폐율×층수)을 씌운다 — min(기존 실효, 구조상한). 층수상한이 없는 zone은
    #   _structural_cap_for가 (None,None,None)을 반환해 완전히 무영향(기존값 그대로).
    structural_cap_pct, floor_cap, floor_cap_basis = _structural_cap_for(zone_type, effective_bcr)
    _effective_far_before_structural_cap = effective_far
    _structural_cap_bound = structural_cap_pct is not None and structural_cap_pct < effective_far
    if _structural_cap_bound:
        effective_far = structural_cap_pct
        far_basis = "구조상한(건폐율×층수)"

    # ── far_basis 상세 메타: 산정 계층·데이터출처를 그라운딩/검증기가 활용하도록 동봉.
    far_basis_detail: dict[str, Any] = {
        "법정범위": {
            "min_far_pct": legal_min_far if legal_min_far is not None else national_far,
            "max_far_pct": legal_far if legal_far is not None else national_far,
            "max_bcr_pct": legal_bcr,
        },
        "조례값": (
            {
                "far_pct": applied.get("ordinance_far_pct"),
                "bcr_pct": applied.get("ordinance_bcr_pct"),
                "confirmed": ordinance_confirmed,
            }
            if ordinance_confirmed
            else None
        ),
        "계획상한": (
            {"far_pct": plan_far_ceiling, "bcr_pct": applied.get("plan_bcr_pct")}
            if plan_far_ceiling is not None
            else None
        ),
        "인센티브": (
            {"relaxation_ratio_pct": float(relaxation_ratio)}
            if (relaxation_ratio is not None)
            else None
        ),
        "최종근거": far_basis,
        "데이터출처": applied.get("sources") or ["법정범위"],
        "조례확인필요": not ordinance_confirmed and plan_far_ceiling is None,
    }

    incentive: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        incentive = calc_far_incentive(
            zone_type=zone_type,
            ordinance_far=effective_far,
            donation_ratio_pct=0.0,
            national_far=national_far,
        )

    # 분석 주석 생성 — 전문적 부동산 용어, 자연스러운 한국어
    source = ordinance.get("source", "법정상한")
    sido = ordinance.get("sido", "")
    sigungu = ordinance.get("sigungu", "")
    region_name = f"{sido} {sigungu}".strip() or "해당 지자체"

    annotations: list[str] = []
    annotations.append(
        f"국토계획법 시행령에 따른 {zone_type}의 법정 건폐율 상한은 {national_bcr}%, "
        f"법정 용적률 상한은 {national_far}%입니다."
    )

    if ordinance_far < national_far:
        diff_pct = national_far - ordinance_far
        annotations.append(
            f"{region_name} 도시계획 조례에서 용적률을 {ordinance_far}%로 규정하여, "
            f"법정상한 대비 {diff_pct:.0f}%p 낮게 적용됩니다. "
            f"이는 해당 지역의 도시계획 방향(기반시설 용량, 주거환경 보전 등)을 반영한 것입니다."
        )
    elif ordinance_far == national_far:
        annotations.append(
            f"{region_name}의 조례 용적률이 법정상한({national_far}%)과 동일하게 규정되어 있어, "
            f"별도의 조례 제한 없이 법정상한이 그대로 적용됩니다."
        )

    if ordinance_bcr < national_bcr:
        annotations.append(
            f"{region_name} 조례에서 건폐율을 {ordinance_bcr}%로 강화 적용하고 있습니다. "
            f"(법정상한 {national_bcr}% 대비 {national_bcr - ordinance_bcr:.0f}%p 축소)"
        )

    annotations.append(
        f"실효 용적률은 법정상한({national_far}%)과 조례({ordinance_far}%) 중 "
        f"낮은 값인 {_effective_far_before_structural_cap}%가 적용되며, "
        f"실효 건폐율은 {effective_bcr}%입니다."
    )

    if _structural_cap_bound:
        # ★구조상한(건폐율×층수)이 법정/조례 한도보다 낮은 실질 상한으로 바인딩된 경우 —
        # 위 문장의 '법정상한/조례 중 낮은 값'만으로는 최종 적용치를 설명하지 못하므로
        # (수치-서술 불일치 방지) 이 사실을 별도 문장으로 명시한다.
        annotations.append(
            f"다만 {zone_type}은 층수 제한({floor_cap}층 이하 — {floor_cap_basis})이 있어, "
            f"실효 건폐율({effective_bcr}%) × {floor_cap}층 = 구조상한 {structural_cap_pct:g}%가 "
            f"법정/조례 한도보다 낮은 실질 상한이 되어 실효 용적률은 {effective_far:g}%로 적용됩니다."
        )

    if land_area > 0:
        # 면적의존 문구(최대 연면적/건축면적)는 공용 생성기 1곳에서 만든다(SSOT — 다필지 override가
        #   같은 함수로 재생성하므로 대표필지·통합 문구가 어긋나지 않는다).
        annotations.append(
            build_area_annotation(
                land_area=land_area, effective_far=effective_far, effective_bcr=effective_bcr,
            )
        )

    if incentive.get("simulation_table"):
        base_far = incentive.get("base_far", effective_far)
        max_incentive_far = incentive.get("max_far", national_far)
        annotations.append(
            f"기부체납 활용 시 기본용적률 {base_far}%에서 최대 {max_incentive_far}%까지 "
            f"완화가 가능합니다 (국토계획법 시행령 제46조). "
            f"기부체납 비율에 따른 상세 시뮬레이션은 별도 섹션을 참조하세요."
        )

    return {
        "national_bcr_pct": national_bcr,
        "national_far_pct": national_far,
        "ordinance_bcr_pct": ordinance_bcr,
        "ordinance_far_pct": ordinance_far,
        "effective_bcr_pct": effective_bcr,
        "effective_far_pct": effective_far,
        "far_basis": far_basis,
        "far_basis_detail": far_basis_detail,
        "ordinance_confirmed": ordinance_confirmed,
        "legal_min_far_pct": legal_min_far if legal_min_far is not None else national_far,
        "legal_max_far_pct": legal_far if legal_far is not None else national_far,
        "relaxation_present": basis_present,
        "far_incentive": incentive,
        "source": source,
        "annotations": annotations,
        # 구조상한(건폐율×층수) — 층수제한 없는 zone은 전부 None(무회귀). additive.
        "structural_cap_pct": structural_cap_pct,
        "floor_cap": floor_cap,
        "floor_cap_basis": floor_cap_basis,
        "far_optimization": simulate_far_optimization(
            zone_type, effective_far, national_far, land_area,
            structural_cap_pct=structural_cap_pct,
        ),
    }


def simulate_far_optimization(
    zone_type: str, effective_far: float, national_far: float, land_area: float,
    structural_cap_pct: float | None = None,
) -> dict[str, Any]:
    try:
        from app.services.zoning.far_optimization_simulator import simulate_far_scenarios
        return simulate_far_scenarios(
            zone_type=zone_type,
            ordinance_far=effective_far,
            national_far=national_far,
            land_area_sqm=land_area,
            structural_cap_pct=structural_cap_pct,
        )
    except Exception:
        return {}


def calc_upzoning(
    base: dict,
    zone_type: str,
    land_area: float,
    location: Any = None,
    dev_plans: Any = None,
    *,
    parcel_count: int = 1,
    adjacency_contiguous: bool | None = None,
) -> dict[str, Any]:
    """현행 실효 용적률과 **분리된** 종상향/종변경 잠재 시나리오(예상치)를 산출.

    규칙엔진(UpzoningPotentialAnalyzer)에 수집 데이터(면적·역세권·특수구역·시군구)를
    전달한다. 목표 용도지역의 조례 용적률은 OrdinanceService 캐시를 동기 resolver로 주입한다.

    다필지 통합분석에서는 통합 면적(land_area)과 함께 통합 필지수(parcel_count)·인접성
    (adjacency_contiguous)을 주입한다. 단일필지 경로는 기본값(1·None)으로 종전과 동일하게 동작한다
    (하위호환·무회귀). 통합 면적이 커져 종상향 경로의 최소면적을 충족하면 가능성이 상향된다.
    """
    try:
        from app.services.zoning.upzoning_potential import UpzoningPotentialAnalyzer

        ordinance = base.get("local_ordinance") or {}
        sigungu = ordinance.get("sigungu") if isinstance(ordinance, dict) else None

        # 역세권 여부(location 섹션의 nearest_subway). location 미전달 시 base.infrastructure 폴백.
        near_station = False
        near_station_m: float | None = None
        loc = location if isinstance(location, dict) else (base.get("infrastructure") or {})
        if isinstance(loc, dict):
            subway = (loc.get("transportation") or {}).get("nearest_subway") or loc.get("nearest_subway")
            if isinstance(subway, dict):
                near_station_m = subway.get("distance_m")
                if near_station_m is not None and near_station_m <= 500:
                    near_station = True

        special_districts = base.get("special_districts") or (
            dev_plans.get("special_districts") if isinstance(dev_plans, dict) else []
        )

        analyzer = UpzoningPotentialAnalyzer()
        return analyzer.analyze(
            zone_type=zone_type,
            land_area_sqm=land_area,
            sigungu=sigungu,
            near_station=near_station,
            near_station_m=near_station_m,
            adjacency_contiguous=adjacency_contiguous,
            parcel_count=parcel_count,
            special_districts=special_districts,
            ordinance_far_resolver=ordinance_far_cache_resolver,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("종상향 잠재력 분석 스킵", error=str(e))
        return {
            "current_zone": zone_type,
            "scenarios": [],
            "potential_far_range": None,
            "summary": "종상향 잠재력 분석을 일시적으로 산출하지 못했습니다.",
            "disclaimer": "예상치 미산출",
        }


def ordinance_far_cache_resolver(sigungu: str, zone_type: str) -> float | None:
    """목표 용도지역의 조례 용적률(%)을 OrdinanceService 정적 캐시에서 동기 조회.

    외부 API 없이 캐시(ORDINANCE_CACHE)만 사용한다(없으면 None → 법정범위 폴백).
    """
    try:
        from app.services.land_intelligence.ordinance_service import ORDINANCE_CACHE

        sig = sigungu or ""
        # 1) 시·군·구 키워드가 매칭되는 시·도 블록 우선.
        for sido, sido_block in ORDINANCE_CACHE.items():
            if sig and (sig in sido or sido in sig):
                z = sido_block.get(zone_type)
                if z and z.get("far"):
                    return float(z["far"])
        # 2) 폴백: 캐시에 해당 용도지역 조례가 있는 첫 블록.
        for sido_block in ORDINANCE_CACHE.values():
            z = sido_block.get(zone_type)
            if z and z.get("far"):
                return float(z["far"])
        return None
    except Exception:  # noqa: BLE001
        return None
