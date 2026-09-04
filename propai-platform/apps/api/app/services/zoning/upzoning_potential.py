"""종상향/종변경 잠재력 분석(upzoning potential).

현행 '실효 용적률'(조례 기준 사실값)과 **별도로**, 도시개발사업·지구단위계획·정비사업·
역세권 활성화/시프트·공공주택지구·가로주택/모아주택 등으로 현재 용도지역보다 용적률을
상향할 수 있는 **잠재 시나리오(예상치)**를 다층 분석한다.

핵심 설계(정직성 — 2계층 분리):
- 본 모듈의 산출은 모두 **예상치/시나리오**다. 실현 보장이 아니다.
- 각 시나리오는 경로(path)·예상 변경 용도지역(target_zone)·예상 용적률(목표지역 조례/법정
  기준 범위)·조건(conditions)·가능성 등급(feasibility 상/중/하 + 사유)·근거법령(legal_basis)·
  전제·불확실성(caveats)을 **반드시 동반**한다(단정 금지).
- 보유 데이터(면적·입지·인접·구역지정 여부)로 판정 가능한 범위만 등급화하고, 부족분은
  "조건부·확인필요"로 정직하게 표시한다.

규칙엔진: 용도지역별 '현실적 종상향 경로'를 매핑한다. 개발방식 시뮬레이터
(DevelopmentScenarioSimulator)의 정책 판정 로직과 정합하되, 여기서는 '종상향 후 예상 용적률
projection'에 초점을 둔다. 외부 호출은 하지 않으며(테스트 가능), 목표지역 조례 용적률은
주입 가능한 resolver(없으면 법정범위 상한)로 도출한다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from app.services.zoning.legal_zone_limits import (
    LEGAL_BASIS,
    legal_limits_for,
    normalize_zone_name,
)

logger = structlog.get_logger(__name__)

# 종상향 시나리오 페이로드임을 검증기·프론트가 식별하는 컨텍스트 마커.
# (legal_zone_limits 검증기는 이 마커가 있는 expected_far를 '현행 위법수치'로 오적발하지 않는다.)
SCENARIO_MARKER = "potential_upzoning_scenario"


# ── 종상향 경로 카탈로그 ──
# path: 경로명, target_progression: 용도지역 종상향 단계(현재→목표 후보),
# legal_basis: 근거법령(텍스트 표기), default_feasibility/conditions는 시나리오 생성 시 데이터로 보정.
#
# legal_ref_keys: legal_reference_registry 키 목록(verified URL 부착용). 시나리오 생성 시
#   get_legal_refs(keys)로 직렬화해 per-scenario `legal_refs`(클릭 가능한 law.go.kr 딥링크)를
#   부착한다. 지자체 운영기준(역세권 활성화·장기전세 등)은 law.go.kr 딥링크가 없으므로
#   레지스트리 키를 두지 않고 legal_basis 텍스트로만 정직 표기한다(죽은 링크·날조 링크 금지).
PATHS = {
    "도시개발사업": {
        "label": "도시개발사업(도시개발법)",
        "legal_basis": "도시개발법 제2·3·4조(도시개발구역 지정) · 국토계획법(용도지역 변경)",
        "legal_ref_keys": ["urban_dev_replot", "far_law"],
        "timeline_est": "5~10년(구역지정·개발계획·실시계획·환지/수용)",
        "min_area_sqm": 10000,  # 도시지역 1만㎡ 이상(비도시 3만㎡)
        "note": "환지/수용 방식 대규모 개발. 도시기본계획 부합 시 용도지역 상향 결정 가능.",
    },
    "지구단위계획수립": {
        "label": "지구단위계획 수립",
        "legal_basis": "국토계획법 제52조(지구단위계획) · 동법 시행령 제46조(완화)",
        "legal_ref_keys": ["district_unit_plan", "far_law"],
        "timeline_est": "2~5년(입안·결정·심의)",
        "min_area_sqm": 5000,
        "note": "획지·용도 유연화 + 상한용적률. 종세분 상향 또는 인센티브 용적 확보.",
    },
    "정비사업": {
        "label": "재개발·재건축(정비사업)",
        "legal_basis": "도시 및 주거환경정비법 · 국토계획법(정비구역 용도지역 변경)",
        "legal_ref_keys": ["redev_impl", "far_law"],
        "timeline_est": "8~15년(정비구역 지정·조합·관리처분)",
        "min_area_sqm": 10000,
        "note": "노후·불량 2/3 요건 충족 시 정비구역 지정과 함께 종상향 가능.",
    },
    "역세권활성화": {
        "label": "역세권 활성화사업(용도상향)",
        "legal_basis": "국토계획법(용도지역 변경) · 서울시 등 역세권 활성화사업 운영기준",
        # 국토계획법(용도지역 변경)만 verified 딥링크. 서울시 운영기준은 자치 운영지침(law.go.kr 딥링크 없음)→텍스트 유지.
        "legal_ref_keys": ["far_law"],
        "timeline_est": "3~6년(사업계획·심의)",
        "requires_station": True,
        "note": "역 승강장 인근 입지에서 일반→준주거/상업 상향, 증가용적 공공기여.",
    },
    "역세권시프트": {
        "label": "역세권 장기전세주택(시프트)",
        "legal_basis": "국토계획법 · 주택법 · 서울시 역세권 장기전세주택 운영기준",
        # 국토계획법·주택법은 verified. 서울시 장기전세 운영기준은 자치 운영지침→텍스트 유지(날조 링크 금지).
        "legal_ref_keys": ["far_law", "housing_approval"],
        "timeline_est": "3~6년",
        "requires_station": True,
        "requires_residential": True,
        "note": "주거 역세권에서 준주거 상향, 증가용적의 50% 장기전세 공급.",
    },
    "공공주택지구": {
        "label": "공공주택지구 지정",
        "legal_basis": "공공주택 특별법 제6조(지구지정) · 국토계획법(용도지역 변경)",
        "legal_ref_keys": ["public_housing", "far_law"],
        "timeline_est": "5~10년",
        "min_area_sqm": 10000,
        "public_led": True,
        "note": "LH·지방공사 등 공공시행. 지구지정과 함께 용도지역 일괄 상향.",
    },
    "가로주택·모아주택": {
        "label": "가로주택정비·모아주택(소규모정비)",
        "legal_basis": "빈집 및 소규모주택 정비에 관한 특례법 · 국토계획법",
        "legal_ref_keys": ["small_housing_road_project", "far_law"],
        "timeline_est": "3~6년",
        "max_area_sqm": 100000,
        "requires_residential": True,
        "note": "노후 저층주거지 소규모 통합정비. 용적률 법적상한까지 완화 가능(종상향에 준함).",
    },
}

# ── 용도지역별 현실적 종상향 목표 후보 ──
# 현재 용도지역 → 가능한 상향 목표 용도지역(현실적 1~2단계). 보수적으로 핵심경로만.
UPZONE_TARGETS: dict[str, list[str]] = {
    # 녹지: 도시개발/지구단위/공공주택지구로 일반주거 종변경(대규모 신규개발의 전형)
    "자연녹지지역": ["제1종일반주거지역", "제2종일반주거지역"],
    "생산녹지지역": ["제1종일반주거지역"],
    # 관리지역: 계획관리·지구단위로 일부 상향(보수적)
    "계획관리지역": ["제1종일반주거지역"],
    # 주거 종세분 상향(정비/지구단위/역세권)
    "제1종일반주거지역": ["제2종일반주거지역", "제3종일반주거지역"],
    "제2종일반주거지역": ["제3종일반주거지역", "준주거지역"],
    "제3종일반주거지역": ["준주거지역"],
    "제1종전용주거지역": ["제2종전용주거지역", "제1종일반주거지역"],
    "제2종전용주거지역": ["제1종일반주거지역"],
    # 준주거 → 상업(역세권/지구단위)
    "준주거지역": ["근린상업지역", "일반상업지역"],
    # 준공업 → 준주거/상업(정비·지구단위)
    "준공업지역": ["준주거지역", "근린상업지역"],
}

# 용도지역별 적용 가능한 종상향 경로(현실적 매핑).
ZONE_PATHS: dict[str, list[str]] = {
    "자연녹지지역": ["도시개발사업", "지구단위계획수립", "공공주택지구"],
    "생산녹지지역": ["도시개발사업", "공공주택지구"],
    "계획관리지역": ["도시개발사업", "지구단위계획수립"],
    "제1종일반주거지역": ["정비사업", "지구단위계획수립", "역세권활성화", "가로주택·모아주택"],
    "제2종일반주거지역": ["정비사업", "지구단위계획수립", "역세권활성화", "역세권시프트", "가로주택·모아주택"],
    "제3종일반주거지역": ["역세권활성화", "역세권시프트", "지구단위계획수립"],
    "제1종전용주거지역": ["지구단위계획수립", "정비사업"],
    "제2종전용주거지역": ["지구단위계획수립", "정비사업"],
    "준주거지역": ["역세권활성화", "지구단위계획수립"],
    "준공업지역": ["정비사업", "지구단위계획수립"],
}


def _scenario_legal_refs(path: dict[str, Any]) -> list[dict]:
    """경로의 legal_ref_keys를 레지스트리(get_legal_refs)로 직렬화해 verified 법령 링크를 반환.

    - get_legal_refs가 {key,law_name,article,title,url,url_status} 레코드를 만든다.
      url_status='verified'(law.go.kr 딥링크)만 클릭 링크, 'pending'/빈값은 프론트가 텍스트 폴백.
    - 레지스트리에 없거나 키 미정 경로는 빈 리스트(legal_basis 텍스트로만 표기 — 날조 링크 금지).
    - URL은 전적으로 레지스트리 출력만 사용한다(여기서 URL 조립 절대 금지).
    """
    keys = path.get("legal_ref_keys") or []
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys)
    except Exception:  # noqa: BLE001 — 레지스트리 실패는 텍스트 legal_basis로 graceful degrade.
        return []


def _target_far_pct(
    target_zone: str,
    sigungu: str | None,
    ordinance_far_resolver: Callable[[str, str], float | None] | None,
) -> tuple[float | None, float | None, str]:
    """목표 용도지역의 예상 용적률(조례 우선, 없으면 법정범위)을 도출.

    Returns: (low_far, high_far, source). low는 법정 하한·high는 적용 상한(조례 또는 법정 상한).
    """
    legal = legal_limits_for(target_zone)
    if not legal:
        return None, None, "미상"
    legal_max = legal.get("max_far_pct")
    legal_min = legal.get("min_far_pct")
    ord_far: float | None = None
    if ordinance_far_resolver and sigungu:
        try:
            ord_far = ordinance_far_resolver(sigungu, legal["zone_type"])
        except Exception:  # noqa: BLE001
            ord_far = None
    if ord_far is not None and legal_max is not None:
        applied = min(float(ord_far), float(legal_max))
        return float(legal_min or applied), applied, "지자체 도시계획조례(목표지역)"
    return (
        float(legal_min) if legal_min is not None else None,
        float(legal_max) if legal_max is not None else None,
        "국토계획법 시행령 법정 범위(목표지역 조례 확인 필요)",
    )


class UpzoningPotentialAnalyzer:
    """종상향/종변경 잠재력 규칙엔진. 외부 호출 없음(주입형 resolver만 선택 사용)."""

    def analyze(
        self,
        zone_type: str | None,
        land_area_sqm: float | None = None,
        sigungu: str | None = None,
        near_station: bool = False,
        near_station_m: float | None = None,
        adjacency_contiguous: bool | None = None,
        parcel_count: int = 1,
        special_districts: list[Any] | None = None,
        ordinance_far_resolver: Callable[[str, str], float | None] | None = None,
    ) -> dict[str, Any]:
        """종상향 시나리오 리스트 + 잠재 용적률 범위를 산출.

        Args:
            zone_type: 현재 용도지역명.
            land_area_sqm: 대지(통합) 면적(㎡). None이면 면적요건은 '확인필요'.
            sigungu: 시·군·구(목표지역 조례 용적률 도출용).
            near_station: 역세권(승강장 350~500m) 여부.
            adjacency_contiguous: 다필지 인접 여부(통합개발 가능성). None=미상.
            parcel_count: 필지 수.
            special_districts: 규제/특수구역(개발제한·상수원 등 → 종상향 제약).
            ordinance_far_resolver: (sigungu, zone)→조례 용적률(%) 주입형(없으면 법정범위).

        Returns:
            {"current_zone", "scenarios"[], "potential_far_range", "summary", "disclaimer"}.
        """
        key = normalize_zone_name(zone_type) or (zone_type or "")
        area = float(land_area_sqm or 0)
        blockers = self._blockers(special_districts)
        # ★레인C(P0) — special_districts가 None(미수집)이면 "확인 결과 규제구역 없음"([])과
        #   구분해 정직하게 표기한다. 개발제한구역·상수원보호구역 등은 이 데이터 없이는
        #   차단사유(blocked_reasons)에 전혀 반영되지 않으므로, blockers=[]가 "종상향 제약
        #   없음"으로 오독되지 않도록 data_gaps로 별도 명시한다(무날조 — 값을 만들지 않음).
        data_gaps: list[str] = []
        if special_districts is None:
            data_gaps.append(
                "규제구역(개발제한구역·상수원보호구역·문화재보호구역 등) 데이터 미수집 — "
                "종상향 차단사유(blocked_reasons)가 이 분석에 반영되지 않았을 수 있습니다(별도 확인 필요)."
            )

        targets = UPZONE_TARGETS.get(key, [])
        path_keys = ZONE_PATHS.get(key, [])

        scenarios: list[dict[str, Any]] = []
        if not targets or not path_keys:
            return {
                "current_zone": key or zone_type,
                "scenarios": [],
                "potential_far_range": None,
                "summary": (
                    f"'{zone_type or '미상'}'은(는) 정형화된 종상향 경로 매핑이 없습니다. "
                    "개별 도시·군관리계획·지구단위계획 변경 가능성은 지자체 확인이 필요합니다(예상치 미산출)."
                ),
                "disclaimer": self._disclaimer(),
                "data_gaps": data_gaps,
                "marker": SCENARIO_MARKER,
            }

        for pkey in path_keys:
            path = PATHS.get(pkey)
            if not path:
                continue
            # 목표 용도지역 선택: 경로 특성에 맞는 상향 후보(가장 보수적=첫 후보 기본)
            target_zone = self._pick_target(pkey, targets, key)
            if not target_zone:
                continue
            low_far, high_far, far_source = _target_far_pct(
                target_zone, sigungu, ordinance_far_resolver
            )
            # ★★범위 복원 — 종전엔 후보를 **하나만** 고르고 끝나, 상·하한이 같은 숫자가 됐다.
            #   화면엔 "예상 상한 150.0~150.0%" 로 찍혔고, 개발사는 그것을 **"그 위는 안 된다"**
            #   로 읽는다. 실제로는 `UPZONE_TARGETS["자연녹지지역"]` 에 제2종일반주거지역이
            #   index 1 로 **이미 들어 있었다**(2026-08-19 사용자 지적 — 도시개발법으로 2종
            #   상향이 가능한데 어떤 경로도 150% 를 넘지 못했다).
            #   모델의 **보수성이 사실로 표시되던 것**이 결함의 본체다. 후보 전체를 훑어
            #   범위로 낸다: 하한=보수 1단계, 상한=최대 후보.
            cands: list[dict] = []
            for tz in targets:
                c_low, c_high, c_src = _target_far_pct(tz, sigungu, ordinance_far_resolver)
                cands.append({
                    "target_zone": tz,
                    "expected_far_pct_low": round(c_low) if c_low is not None else None,
                    "expected_far_pct_high": round(c_high) if c_high is not None else None,
                    "expected_far_source": c_src,
                })
            _highs = [c["expected_far_pct_high"] for c in cands
                      if c["expected_far_pct_high"] is not None]
            # 상향 여지의 상한(최대 후보). ★하한은 최상위에서 쓰지 않는다 — 최상위 low/high 는
            #   `target_zone` 한 곳에 대해 내부 정합해야 하고, 후보 합집합의 하한을 섞으면
            #   다시 라벨과 값이 어긋난다(후보별 하한은 `target_zone_candidates` 에 있다).
            range_high = max(_highs) if _highs else None
            feasibility, reason, conditions, blocked_reasons = self._grade(
                pkey, path, area, near_station, near_station_m,
                adjacency_contiguous, parcel_count, key, blockers,
            )
            scenarios.append({
                "path": path["label"],
                "path_key": pkey,
                "target_zone": target_zone,
                # ★★2026-08-19 교정 — 라벨과 값은 **같은 용도지역**을 가리켜야 한다.
                #   직전 판은 상·하한을 **후보 전체의 합집합**(low=최소후보·high=최대후보)에서
                #   냈다. 그런데 `target_zone` 은 여전히 대표 후보 하나였다. 결과:
                #     target=제2종일반주거지역(법정 150~250)  ·  high=300  ← **법정상한 초과**
                #     source='지자체 도시계획조례(목표지역)'  ·  high=200  ← **조례값 150 초과**
                #   플랫폼 자신의 `check_against_legal` 이 '법정한도초과 high' 로 판정한다.
                #   이 저장소가 "자연녹지 200%" 사고 이후 막아 온 **날조 클래스**다 —
                #   출처를 붙인 채 그 출처를 넘는 값은 근거가 아니라 거짓 근거다.
                #   ★그러므로 최상위 3필드는 **대표 후보 하나에 대해 내부 정합**하게 낸다
                #     (`_target_far_pct` 가 이미 `min(조례, 법정)` 을 하고 있다 — 합집합
                #      덮어쓰기가 그 min 을 무력화하고 있었을 뿐이다).
                "expected_far_pct_low": round(low_far) if low_far is not None else None,
                "expected_far_pct_high": round(high_far) if high_far is not None else None,
                "expected_far_source": far_source,
                # 후보별 상세 — 각 항목은 **자기 용도지역의 범위**만 담는다(내부 정합).
                "target_zone_candidates": cands,
                "target_zone_max": (cands[-1]["target_zone"] if cands else None),
                # ★상향 여지는 **지우지 않는다** — 다만 그 값이 어느 용도지역의 것인지
                #   라벨과 함께 낸다. 종전엔 이 숫자가 `expected_far_pct_high` 로 올라가
                #   `target_zone` 라벨과 어긋났다(위 주석). 소비처(화면)는 이 쌍을 읽어
                #   "최대 제3종일반주거지역 상향 시 300%" 처럼 **용도지역을 밝혀** 표시한다.
                "upside_far_pct_high": range_high,
                "upside_far_zone": (
                    next((c["target_zone"] for c in reversed(cands)
                          if c["expected_far_pct_high"] == range_high), None)
                    if range_high is not None else None
                ),
                "upside_far_source": (
                    next((c["expected_far_source"] for c in reversed(cands)
                          if c["expected_far_pct_high"] == range_high), None)
                    if range_high is not None else None
                ),
                "conditions": conditions,
                "feasibility": feasibility,
                "feasibility_reason": reason,
                # ★P0 additive: 가능성을 강등시킨 구조적 사유(비연접 파편 필지·규제구역 등)를
                # 별도 배열로 명시 — feasibility_reason(자유서술)과 달리 프론트가 배지/경고로
                # 그대로 렌더할 수 있는 사유 목록이다(빈 배열=강등 사유 없음).
                "blocked_reasons": blocked_reasons,
                "legal_basis": path["legal_basis"],
                # verified law.go.kr 딥링크(레지스트리 단일출처). 프론트 LegalRefChip가
                # url_status='verified'는 클릭 링크, 'pending'/빈값은 텍스트 폴백(죽은 링크 금지).
                "legal_refs": _scenario_legal_refs(path),
                "timeline_est": path.get("timeline_est"),
                "caveats": self._caveats(pkey, blockers),
                "is_estimate": True,  # ★예상치(실현 보장 아님)
                "marker": SCENARIO_MARKER,
            })

        # 가능성 정렬(상>중>하), 동급은 예상 상한 용적률 내림차순.
        rank = {"상": 0, "중": 1, "하": 2}
        scenarios.sort(key=lambda s: (rank.get(s["feasibility"], 3),
                                      -(s.get("expected_far_pct_high") or 0)))

        far_range = self._potential_range(scenarios, key, targets)
        return {
            "current_zone": key or zone_type,
            "scenarios": scenarios,
            "potential_far_range": far_range,
            "summary": self._summary(key, scenarios, far_range, blockers),
            "disclaimer": self._disclaimer(),
            "data_gaps": data_gaps,
            "marker": SCENARIO_MARKER,
        }

    # ── 목표 용도지역 선택 ──
    @staticmethod
    def _pick_target(pkey: str, targets: list[str], current: str) -> str | None:
        if not targets:
            return None
        # 역세권 상향(활성화/시프트)은 가장 높은 후보(준주거/상업 지향),
        # 정비/도시개발/공공주택지구는 보수적 1단계(첫 후보).
        if pkey in ("역세권활성화", "역세권시프트"):
            return targets[-1]
        return targets[0]

    # ── 가능성 등급화(보유 데이터 근거) ──
    def _grade(
        self, pkey: str, path: dict, area: float, near_station: bool,
        near_station_m: float | None, adjacency: bool | None, parcel_count: int,
        zone: str, blockers: list[str],
    ) -> tuple[str, str, list[str], list[str]]:
        conditions: list[str] = []
        reasons: list[str] = []
        blocked_reasons: list[str] = []
        score = 0  # +가산/-감산 → 상/중/하

        # 1) 면적요건
        min_area = path.get("min_area_sqm")
        max_area = path.get("max_area_sqm")
        if min_area:
            conditions.append(f"대지면적 {min_area:,.0f}㎡ 이상(통합 시 합산)")
            if area and area >= min_area:
                score += 1
                reasons.append(f"면적 {area:,.0f}㎡ ≥ {min_area:,.0f}㎡ 충족")
            elif area:
                score -= 2
                reasons.append(f"면적 {area:,.0f}㎡ < {min_area:,.0f}㎡ 미달")
            else:
                reasons.append("면적 데이터 부족 — 확인필요")
        if max_area and area and area > max_area:
            score -= 2
            conditions.append(f"대지면적 {max_area:,.0f}㎡ 이하")
            reasons.append(f"면적 {area:,.0f}㎡ > {max_area:,.0f}㎡ 초과(경로 부적합)")

        # 2) 역세권 요건
        if path.get("requires_station"):
            conditions.append("역 승강장 인근 입지(통상 350~500m)")
            if near_station:
                score += 1
                dm = f"{near_station_m:.0f}m" if near_station_m else "역세권 범위"
                reasons.append(f"역세권 입지({dm}) 충족")
            else:
                score -= 2
                reasons.append("역세권 입지 아님(또는 미확인)")

        # 3) 주거지역 요건
        if path.get("requires_residential") and "주거" not in zone:
            score -= 2
            reasons.append("주거지역 아님(경로 부적합)")

        # 4) 다필지 통합개발 인접성
        if parcel_count >= 2:
            conditions.append("다필지 통합(합필/일단지) — 인접 필요")
            if adjacency is True:
                reasons.append("필지 인접(통합개발 가능)")
            elif adjacency is False:
                score -= 1
                reasons.append("필지 비인접(통합개발 제약)")
                blocked_reasons.append(
                    "비연접 파편 필지 — 지구단위계획 구역(일단의 토지) 성립 불확실"
                )
            else:
                reasons.append("인접성 미확인 — 현장/지적도 확인필요")

        # 5) 정책·계획 부합(공통 전제)
        if pkey in ("도시개발사업", "공공주택지구"):
            conditions.append("도시기본계획·도시관리계획 부합(상향 결정 필요)")
            # ★정직표기: 도시개발/공공주택 가능성 등급은 면적요건 기반 예비판정이다.
            #   구역지정 결정·기반시설·사업성(수지)은 이 등급에 반영되지 않았음을 명시한다
            #   (면적게이트만으로 '가능성 하/중'을 단정하지 않도록 — 감사 정직화).
            conditions.append(
                "면적요건 기반 예비판정 — 구역지정 결정·기반시설·사업성(수지)은 미반영(별도 확인 필요)"
            )
        if pkey == "정비사업":
            conditions.append("노후·불량건축물 2/3 이상 + 정비예정구역 부합")
        if pkey in ("역세권활성화", "역세권시프트"):
            conditions.append("증가 용적의 공공기여(임대·생활SOC) 부담")
        if pkey == "지구단위계획수립":
            conditions.append("지구단위계획 입안·결정·심의")
        if path.get("public_led"):
            conditions.append("공공(LH·지방공사 등) 시행 전제 — 민간 단독 추진 제한")
            score -= 1

        # 6) 규제 블로커(개발제한·상수원 등) — 종상향 자체를 어렵게 함
        if blockers:
            score -= 2
            reasons.append("규제구역(" + ", ".join(blockers) + ") — 종상향 제약")
            blocked_reasons.append(
                f"규제구역({', '.join(blockers)}) — 해제·완화 선행 없이는 종상향 불가"
            )

        if score >= 1:
            grade = "상"
        elif score >= -1:
            grade = "중"
        else:
            grade = "하"
        # ★확정 강등(P0): 비연접 파편 필지는 감점(-1)만으론 '중'까지만 내려가 종상향 가능성이
        # 여전히 남아있는 것처럼 보일 위험이 있다(라이브 재현: 파편 9필지+개발제한구역 혼합에서
        # "가능성 상·1순위" 산출). 인접성 불충족은 지구단위계획 등 '일단의 토지' 성립 요건
        # 자체가 흔들리는 구조적 결격이므로, 점수와 무관하게 등급을 '하'로 확정 강등한다.
        if parcel_count >= 2 and adjacency is False:
            grade = "하"
        reason = "; ".join(reasons) or "보유 데이터로 등급화(전제 충족 시)"
        return grade, reason, conditions, blocked_reasons

    @staticmethod
    def _blockers(special_districts: list[Any] | None) -> list[str]:
        """종상향을 제약하는 규제구역 토큰 추출(개발제한·상수원·자연공원 등)."""
        if not special_districts:
            return []
        tokens = ("개발제한", "그린벨트", "상수원", "자연공원", "도시자연공원",
                  "문화재", "비행안전", "군사시설", "보전")
        found: list[str] = []
        for d in special_districts:
            name = d if isinstance(d, str) else (
                (d.get("name") or d.get("district_name") or "") if isinstance(d, dict) else ""
            )
            for t in tokens:
                if t in name and t not in found:
                    found.append(t)
        return found

    @staticmethod
    def _caveats(pkey: str, blockers: list[str]) -> list[str]:
        base = [
            "예상치 — 실현 보장 아님(도시계획 결정·인허가 전제).",
            "용도지역 변경은 지자체 도시·군관리계획 결정사항(주민의견·심의 거침).",
        ]
        if pkey in ("역세권활성화", "역세권시프트"):
            base.append("운영지역(서울시 등) 한정 — 해당 지자체 운영기준 확인 필요.")
        if pkey == "공공주택지구":
            base.append("공공시행 전제 — 민간 토지는 수용·협의 대상이 될 수 있음.")
        if blockers:
            base.append(f"규제구역({', '.join(blockers)}) 해제·완화 선행 필요.")
        return base

    @staticmethod
    def _potential_range(
        scenarios: list[dict],
        zone: str = "",
        mapped_targets: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """시나리오들의 예상 용적률 상한을 모아 '범위'를 낸다.

        ★이 함수가 내는 값은 **범위가 아닐 수 있다.** 대표 목표 용도지역 선정(_pick_target)이
          보수적이라 여러 경로가 같은 목표를 가리키면 min_pct 와 max_pct 가 **같은 값**이 된다
          (실측: 자연녹지·계획관리·준공업 등은 항상 붕괴). 그때 화면이 `150~150%` 라고 적으면
          개발사는 "그 위는 안 된다"로 읽지만, 실제 의미는 "우리가 한 경로만 봤다"이다.
          그래서 붕괴 사실(is_collapsed)과 그 사유(honest_disclosure)를 **계약으로** 실어보낸다.
          소비처가 min==max 를 스스로 눈치채게 두면 그것은 계약이 아니라 우연이다.

        Args:
            scenarios: analyze()가 만든 시나리오 목록.
            zone: 현행 용도지역명(고지 문구에 사용).
            mapped_targets: 이 용도지역에 매핑된 상향 후보 전체(UPZONE_TARGETS).
                이번 산출에 **반영되지 않은** 후보를 정직하게 밝히는 데 쓴다(값은 만들지 않음).
        """
        graded = [s for s in scenarios
                  if s.get("expected_far_pct_high") and s["feasibility"] in ("상", "중")]
        if not graded:
            graded = [s for s in scenarios if s.get("expected_far_pct_high")]
        if not graded:
            return None

        highs = [s["expected_far_pct_high"] for s in graded]
        lo, hi = min(highs), max(highs)
        collapsed = lo == hi

        # 이번 산출에 실제로 반영된 목표 용도지역(입력 순서 유지·중복 제거).
        considered: list[str] = []
        for s in graded:
            tz = s.get("target_zone")
            if tz and tz not in considered:
                considered.append(tz)

        # ★R1 교정 — "평가해서 '하'로 판정했다"와 "아예 산출하지 않았다"는 **다른 말**이다.
        #   종전에는 미반영 후보를 `graded`(상/중만) 기준으로 뺐다. 그래서 시나리오가 실제로
        #   산출됐고 화면 목록에도 렌더되는 '하' 경로의 목표까지 "미산출 — 별도 확인 필요"로
        #   둔갑했다(실측 3케이스: 1종일반→3종일반300하 · 2종일반→준주거500하 · 준주거→일반상업1300하).
        #   확정된 부정 판정을 '열린 가능성'으로 격상시키는 낙관 과표시라, 이 PR 이 고치겠다고
        #   선언한 결함 클래스 그 자체다. 두 축을 갈라 각각의 사실을 말한다.
        produced: list[str] = []          # 산출된 값이 실제로 실린 목표(가능성 등급 무관)
        upside_zones: list[str] = []      # 대표 목표보다 높은 상향 후보(#700 upside 축)
        upside_far: dict[str, float] = {}  # 그 후보의 예상 용적률 — 문장에 값을 직접 싣는다
        for s in scenarios:
            tz = s.get("target_zone")
            if tz and tz not in produced:
                produced.append(tz)
            # ★#700(머지됨) 이후 — 대표 목표 외의 후보도 `target_zone_candidates` 에 **각자의
            #   용적률과 함께 실린다**. 그 값은 화면(UpzoningScenarioList)이 "최대 〈지역〉
            #   상향 시 N%" 로 렌더한다. 그러므로 그 목표를 "미산출"이라 말하면 **같은 카드에서
            #   목록과 고지가 싸운다**(실측 3케이스: 자연녹지→2종일반 250 · 제1종전용→1종일반
            #   200 · 준공업→근린상업 900).
            #   ★후보 전체를 무조건 넣지 않는다 — `expected_far_pct_high` 가 None 인 후보는
            #     `_target_far_pct` 가 법정한도를 못 찾은 것이라 **정말 아무 값도 산출되지
            #     않았다**(source='미상'). 그것까지 '산출됨'으로 치면 미산출 고지가 영영 죽는다.
            for c in (s.get("target_zone_candidates") or []):
                ctz = c.get("target_zone")
                if ctz and c.get("expected_far_pct_high") is not None and ctz not in produced:
                    produced.append(ctz)
            # 화면이 실제로 그 줄을 그리는 조건과 **같은 조건**으로 모은다(추정 금지 —
            # UpzoningScenarioList 는 upside_high > expected_high 일 때만 렌더한다).
            uz, uh = s.get("upside_far_zone"), s.get("upside_far_pct_high")
            if uz and uh is not None and uh > (s.get("expected_far_pct_high") or 0):
                prev = upside_far.get(uz)
                if prev is None or uh > prev:
                    upside_far[uz] = uh
                if uz not in upside_zones:
                    upside_zones.append(uz)
        # ① 미산출 — 매핑은 돼 있는데 시나리오 자체가 없다(진짜 "확인 필요").
        #    `mapped_targets`(UPZONE_TARGETS)에서 파생하므로 카탈로그가 늘면 자동 반영된다.
        unconsidered = [t for t in (mapped_targets or []) if t not in produced]
        # ② 평가 후 제외 — 산출은 됐으나 가능성 '하'라 범위에서 빠졌다(부정 판정이지 미산출이 아니다).
        excluded: list[dict[str, Any]] = []
        seen_excluded: set[str] = set()
        for s in scenarios:
            tz = s.get("target_zone")
            if not tz or tz in considered or tz in seen_excluded:
                continue
            # ★등급을 **확인하고** 담는다. 종전엔 "considered 에 없다"만 보고 담으면서 문구는
            #   가능성 '하'를 하드코딩했다. graded 에서 빠지는 길은 두 가지다 —
            #   ①가능성 '하'  ②expected_far_pct_high 가 falsy(0/None). ②로 빠진 상/중 경로가
            #   "'하'로 평가되어"라 표기되고 "(예상 0%)"까지 노출된다(주입으로 실증).
            #   ★현 프로덕션 배선에서는 ②가 **도달 불가**다: 조례 resolver
            #   (far_tier_service `if z and z.get("far")`)가 0 을 걸러 None 을 주고, 매핑된
            #   전 목표 용도지역이 법정 max_far_pct 를 보유한다. 그래서 이 가드의 변이는
            #   어떤 테스트도 죽이지 못한다(설명된 생존 — 잠재 결함에 대한 선제 가드).
            if s.get("feasibility") != "하":
                continue
            seen_excluded.add(tz)
            excluded.append({
                "target_zone": tz,
                "expected_far_pct_high": s.get("expected_far_pct_high"),
                "feasibility": s.get("feasibility"),
            })
        # ★세 축은 **배타**여야 한다 — 한 용도지역에 두 문장이 붙으면 고지가 자기 말을 겹쳐 쓴다.
        #   실측: 2종일반 비역세권의 준주거는 upside(최대 500% 렌더)이면서 동시에 '하' 제외
        #   대상이었다. 둘 다 참이지만, 더 구체적인 쪽('하'로 평가 + 값 + 목록 참조)만 남긴다.
        _excluded_zones = {e["target_zone"] for e in excluded}
        upside_zones = [z for z in upside_zones
                        if z not in considered and z not in _excluded_zones]

        out: dict[str, Any] = {
            "min_pct": lo,
            "max_pct": hi,
            "is_collapsed": collapsed,
            "scenario_count": len(graded),
            "considered_target_zones": considered,
            "unconsidered_target_zones": unconsidered,
            # 화면에 "최대 〈지역〉 상향 시 N%" 로 이미 보이는 목표(#700 축) — 미산출이 아니다.
            "upside_target_zones": upside_zones,
            # 평가 결과 '하'로 범위에서 빠진 목표 — "미산출"과 섞어 쓰지 않는다.
            "excluded_by_feasibility": excluded,
            "honest_disclosure": None,
            "note": "가능성 상/중 시나리오의 예상 용적률 상한 범위(예상치·목표지역 기준).",
        }
        if not collapsed:
            return out

        # ── 붕괴 — '범위'라고 부르지 않고, 왜 한 값인지 밝힌다 ──
        out["note"] = "가능성 상/중 시나리오의 예상 용적률 상한 — 단일 값(범위 미산출)."
        head = (
            f"검토한 경로 {len(graded)}건의 예상 용적률 상한이 모두 {hi:.0f}%로 같아 "
            f"범위가 산출되지 않았습니다. {hi:.0f}%는 상향 가능한 최댓값이 아니라 "
            f"본 분석이 검토한 경로의 예상치입니다."
        )
        # ★사유는 **절(clause) 조립**이다 — 한 가지에 몰아 쓰면 "미산출"과 "평가 결과 하"가
        #   다시 섞인다. 각 절은 자기가 아는 사실만 말한다.
        clauses: list[str] = []
        if len(considered) == 1:
            clauses.append(f" 검토한 경로가 모두 같은 목표 용도지역('{considered[0]}')을 가리켰습니다.")
        else:
            # ★현 카탈로그에서는 도달 불가다(2026-08-19 실측 — UPZONE_TARGETS 전수를 돌려도
            #   '목표는 다른데 예상 상한만 같은' 조합이 나오지 않는다). 목표지역 조례가 두
            #   용도지역에 같은 상한을 주면 발화하므로 방어로 남긴다 — 그래서 이 가지의
            #   문구 변이는 어떤 테스트도 죽이지 못한다(설명된 생존).
            clauses.append(
                f" 목표 용도지역은 서로 달랐으나({', '.join(considered)}) 예상 상한이 "
                f"모두 같았습니다 — 목표지역 조례 상한이 같은 값에서 걸린 결과입니다."
            )
        if upside_zones:
            # ★모순을 침묵으로 덮지 않고 **적극적으로 해소**한다 — #700 이 산출해 화면이 보여주는
            #   값을 고지가 직접 말한다("미산출"이 아니라 "함께 산출됐고 값은 이것").
            #   ★"별도 표시됩니다"처럼 **화면 동작을 단언하지 않는다**: 소비처마다 목록 렌더가
            #     다르다(site-analysis·설계감사는 UpzoningScenarioList 로 그 줄을 그리지만,
            #     종합분석 패널은 자체 목록이고 AutoRecommendPanel 은 목록 자체가 없다).
            #     백엔드가 보증할 수 없는 것을 단정하면 그 문장이 화면마다 참·거짓이 갈린다.
            listed_up = ", ".join(
                f"'{z}'(예상 {upside_far[z]:.0f}%)" if z in upside_far else f"'{z}'"
                for z in upside_zones
            )
            clauses.append(
                f" 더 높은 상향 후보 {listed_up}도 함께 산출됐습니다 — 범위 산출에는 대표 목표만"
                f" 반영했으며, 실제 도달 용적률은 상향 단계에 따라 달라집니다."
            )
        if excluded:
            # ★"미산출"이라 말하지 않는다. 이건 평가를 마친 **부정 판정**이고, 같은 카드의
            #   시나리오 목록에 등급·사유와 함께 이미 렌더된다(목록과 고지가 싸우면 안 된다).
            listed = ", ".join(
                f"'{e['target_zone']}'(예상 {e['expected_far_pct_high']:.0f}%)"
                if e.get("expected_far_pct_high") is not None else f"'{e['target_zone']}'"
                for e in excluded
            )
            clauses.append(
                f" {listed}은(는) 가능성 '하'로 평가되어 범위 산출에서 제외됐습니다"
                f"(미산출이 아니라 평가 결과입니다 — 사유는 아래 시나리오 목록 참조)."
            )
        if unconsidered:
            # ★#700 머지 후 이 절은 **현 카탈로그의 라이브 경로에서 도달 불가**다(실측 2026-08-20:
            #   전수 20케이스 unconsidered 0건 · 매핑된 전 목표가 법정 max_far_pct 를 보유해
            #   `target_zone_candidates` 에 값이 실린다). 남기는 이유는 둘이다 —
            #   ①법정한도를 못 찾는 목표가 카탈로그에 추가되면 즉시 발화한다(그때 "미산출"이 참).
            #   ②`_potential_range` 는 #700 이전 형상(candidates 없음)의 페이로드도 받는다.
            #   그래서 이 절의 변이는 라이브 픽스처로는 죽지 않는다(설명된 생존) — 대신 아래
            #   테스트가 `_potential_range` 를 직접 태워 두 형상을 가른다.
            clauses.append(
                f" 매핑된 상향 후보 중 {', '.join(unconsidered)}은(는) 이번 산출에 "
                f"반영되지 않았습니다 — 그 단계의 상향 여지는 미산출이며 별도 확인이 필요합니다."
            )
        # ★조건을 **실제 매핑 개수**에 결속한다. 종전엔 "excluded·unconsidered 가 비었으면"
        #   이라고만 봤는데, #700 이후 후보가 2개여도 둘 다 산출되면 그 조건이 참이 되어
        #   "후보가 하나뿐"이라는 **거짓**이 나온다(자연녹지는 후보 2개다).
        if (not excluded and not unconsidered and not upside_zones
                and len(considered) == 1 and len(mapped_targets or []) <= 1):
            clauses.append(
                f" 현행 '{zone or '해당 용도지역'}'에 매핑된 상향 후보가 "
                f"'{considered[0]}' 하나뿐이라 비교할 다른 목표가 없었습니다 — "
                f"그보다 높은 단계의 상향 여지는 미산출이며 별도 확인이 필요합니다."
            )
        out["honest_disclosure"] = head + "".join(clauses)
        return out

    @staticmethod
    def _summary(zone: str, scenarios: list[dict], far_range: dict | None, blockers: list[str]) -> str:
        if not scenarios:
            return f"'{zone}'의 종상향 경로 예상치를 산출하지 못했습니다."
        top = scenarios[0]
        parts = [
            f"현행 '{zone}'에서 종상향/종변경 잠재 시나리오 {len(scenarios)}건을 예상치로 검토했습니다(실현 보장 아님)."
        ]
        if far_range:
            # ★붕괴(min==max) 시 "약 150~150%"는 '그 위는 없다'로 읽힌다 — 범위인 척하지 않고,
            #   왜 한 값인지(honest_disclosure)를 서술문에도 그대로 싣는다. 화면만 고치고
            #   문장이 계속 "150~150%"라고 말하면 같은 오독이 남는다.
            if far_range.get("is_collapsed"):
                parts.append(
                    far_range.get("honest_disclosure")
                    # ★`or` 뒤는 **도달 불가 방어**다 — _potential_range 는 붕괴 시 항상
                    #   honest_disclosure 를 채운다. 그래서 이 문자열의 변이는 죽지 않는다
                    #   (설명된 생존). 남기는 이유: 외부에서 만든 far_range 가 들어와도
                    #   서술문이 값을 통째로 빠뜨리지 않게 하기 위함.
                    or (
                        f"가능성 상/중 경로 기준 예상 용적률 상한은 약 {far_range['max_pct']:.0f}% "
                        "한 값으로만 산출됐습니다(범위 미산출)."
                    )
                )
            else:
                parts.append(
                    f"가능성 상/중 경로 기준 예상 용적률 상한은 약 {far_range['min_pct']:.0f}~{far_range['max_pct']:.0f}%입니다."
                )
        parts.append(
            f"가장 유력한 경로는 '{top['path']}'(목표 {top['target_zone']}, 가능성 {top['feasibility']})입니다."
        )
        if blockers:
            parts.append(f"단, 규제구역({', '.join(blockers)})으로 종상향이 제약될 수 있어 해제·완화 검토가 선행되어야 합니다.")
        parts.append("모든 수치는 도시계획 결정·인허가를 전제로 한 예상치이며, 현행 실효 용적률과 구분됩니다.")
        return " ".join(parts)

    @staticmethod
    def _disclaimer() -> str:
        return (
            "본 분석은 종상향/종변경 '잠재 시나리오(예상치)'로, 현행 실효 용적률(조례 기준 사실값)과 "
            "분리됩니다. 각 시나리오의 예상 용적률은 목표 용도지역의 조례/법정 기준이며, 용도지역 변경은 "
            f"지자체 도시·군관리계획 결정·인허가를 전제로 합니다(단정 아님). 근거: {LEGAL_BASIS} 및 각 경로별 근거법령."
        )
