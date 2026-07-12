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
            feasibility, reason, conditions, blocked_reasons = self._grade(
                pkey, path, area, near_station, near_station_m,
                adjacency_contiguous, parcel_count, key, blockers,
            )
            scenarios.append({
                "path": path["label"],
                "path_key": pkey,
                "target_zone": target_zone,
                "expected_far_pct_low": round(low_far) if low_far is not None else None,
                "expected_far_pct_high": round(high_far) if high_far is not None else None,
                "expected_far_source": far_source,
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

        far_range = self._potential_range(scenarios)
        return {
            "current_zone": key or zone_type,
            "scenarios": scenarios,
            "potential_far_range": far_range,
            "summary": self._summary(key, scenarios, far_range, blockers),
            "disclaimer": self._disclaimer(),
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
    def _potential_range(scenarios: list[dict]) -> dict[str, Any] | None:
        highs = [s["expected_far_pct_high"] for s in scenarios
                 if s.get("expected_far_pct_high") and s["feasibility"] in ("상", "중")]
        if not highs:
            highs = [s["expected_far_pct_high"] for s in scenarios if s.get("expected_far_pct_high")]
        if not highs:
            return None
        return {
            "min_pct": min(highs),
            "max_pct": max(highs),
            "note": "가능성 상/중 시나리오의 예상 용적률 상한 범위(예상치·목표지역 기준).",
        }

    @staticmethod
    def _summary(zone: str, scenarios: list[dict], far_range: dict | None, blockers: list[str]) -> str:
        if not scenarios:
            return f"'{zone}'의 종상향 경로 예상치를 산출하지 못했습니다."
        top = scenarios[0]
        parts = [
            f"현행 '{zone}'에서 종상향/종변경 잠재 시나리오 {len(scenarios)}건을 예상치로 검토했습니다(실현 보장 아님)."
        ]
        if far_range:
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
