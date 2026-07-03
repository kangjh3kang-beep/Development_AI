"""개발기획 자동화 엔진 (7가지 개발방법 평가).

부지 프로파일(면적, 용도지역, 소유형태 등)을 기반으로
7가지 부동산 개발방법을 AHP 가중 평가하고 최적 방법을 추천한다.

7가지 개발방법:
1. 단독개발 — 토지 소유자 직접 개발
2. 합동개발 — 공동 사업 (토지주 + 시행사)
3. 환지방식 — 도시계획 사업 환지
4. 도시개발 — 도시개발사업
5. 도시정비 — 재개발/재건축
6. 민관합작(PPP) — Public-Private Partnership
7. 리모델링 — 기존 건물 리모델링
"""

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.development_method import DevelopmentMethodResult

logger = structlog.get_logger(__name__)

# ── 7가지 개발방법 ──

DEVELOPMENT_METHODS = [
    "단독개발",
    "합동개발",
    "환지방식",
    "도시개발",
    "도시정비",
    "민관합작(PPP)",
    "리모델링",
]

# ── AHP 가중치: [수익성, 사업기간, 위험도, 인허가용이] ──

AHP_WEIGHTS = [0.35, 0.25, 0.25, 0.15]

# ── 기본 점수 매트릭스 (7x4) ──
# 각 방법별 기본 점수 (1~10)
# [수익성, 사업기간(짧을수록 높음), 위험도(낮을수록 높음), 인허가용이]

BASE_SCORE_MATRIX: dict[str, list[float]] = {
    "단독개발":     [8, 8, 7, 9],
    "합동개발":     [7, 6, 6, 7],
    "환지방식":     [6, 4, 5, 4],
    "도시개발":     [9, 3, 4, 3],
    "도시정비":     [8, 3, 3, 3],
    "민관합작(PPP)": [7, 4, 5, 5],
    "리모델링":     [5, 7, 8, 8],
}


@dataclass
class SiteProfile:
    """부지 프로파일 데이터 클래스.

    개발방법 평가에 필요한 부지 특성 정보를 담는다.
    """

    site_area_sqm: float          # 부지 면적 (m2)
    zoning_type: str              # 용도지역 (제1종일반주거, 일반상업, 준공업 등)
    current_use: str              # 현재 용도 (나대지, 주거, 상업, 공업, 농지)
    ownership_type: str           # 소유 형태 (단독, 공유, 국유, 법인)
    road_frontage_m: float        # 접도 길이 (m)
    transit_score: float          # 교통접근성 (0~10)
    current_value_krw: float      # 현재 토지 가치 (원)
    building_age_years: int | None = None  # 기존 건물 연수 (리모델링용)
    num_owners: int = 1           # 소유자 수 (도시정비 난이도)


class DevelopmentMethodService:
    """7가지 개발방법 AHP 가중 평가 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _adjust_scores(profile: SiteProfile) -> dict[str, list[float]]:
        """SiteProfile 기반으로 기본 점수를 조정한다.

        면적, 용도지역, 기존 건물 연수, 소유자 수 등에 따라
        각 개발방법의 기본 점수를 가감한다.

        Args:
            profile: 부지 프로파일

        Returns:
            조정된 점수 매트릭스 (방법명 -> [수익성, 사업기간, 위험도, 인허가용이])
        """
        adjusted: dict[str, list[float]] = {}

        for method, base_scores in BASE_SCORE_MATRIX.items():
            scores = list(base_scores)  # 원본 보호용 복사

            # ── 면적 기반 조정 ──
            if profile.site_area_sqm < 1000:
                # 소규모: 단독/리모델링 유리, 도시개발/정비 불리
                if method in ("단독개발", "리모델링"):
                    scores[0] += 1  # 수익성 +
                elif method in ("도시개발", "도시정비", "환지방식"):
                    scores[0] -= 2  # 수익성 -
                    scores[3] -= 2  # 인허가 -
            elif profile.site_area_sqm > 10000:
                # 대규모: 도시개발/정비 유리
                if method in ("도시개발", "도시정비"):
                    scores[0] += 2
                elif method == "단독개발":
                    scores[2] -= 2  # 위험도 증가

            # ── 용도지역 조정 ──
            if profile.zoning_type in ("일반상업지역", "근린상업지역"):
                if method in ("도시개발", "합동개발"):
                    scores[0] += 1
            elif profile.zoning_type in ("준공업지역",) and method == "도시정비":
                scores[0] += 2

            # ── 기존 건물이 있으면 리모델링 보너스 ──
            if profile.building_age_years and profile.building_age_years > 20 and method == "리모델링":
                scores[0] += 2
                scores[1] += 1

            # ── 소유자 많으면 도시정비 인허가 어려움 ──
            if profile.num_owners > 100 and method == "도시정비":
                scores[3] -= 3

            # ── 클램프 (1~10) ──
            adjusted[method] = [max(1, min(10, s)) for s in scores]

        return adjusted

    @staticmethod
    def _calculate_weighted_scores(
        adjusted_scores: dict[str, list[float]],
    ) -> dict[str, float]:
        """AHP 가중치를 적용하여 종합 점수를 계산한다.

        Args:
            adjusted_scores: 조정된 점수 매트릭스

        Returns:
            방법별 가중 종합 점수 딕셔너리
        """
        result: dict[str, float] = {}
        for method, scores in adjusted_scores.items():
            weighted = sum(s * w for s, w in zip(scores, AHP_WEIGHTS, strict=False))
            result[method] = round(weighted, 4)
        return result

    @staticmethod
    def _calculate_bcr(
        profile: SiteProfile, recommended_method: str, weighted_score: float
    ) -> float:
        """간이 BCR(비용효익비)를 산출한다.

        예상 개발이익 = 현재가치 x 수익 승수 (점수 기반)
        예상 비용 = 현재가치 x 비용 비율 (방법별)

        Args:
            profile: 부지 프로파일
            recommended_method: 추천 개발방법
            weighted_score: 해당 방법의 가중 점수

        Returns:
            BCR 값 (0 이상)
        """
        # 예상 개발이익 = 현재가치 x 수익 승수 (점수 높을수록 이익 큼)
        revenue_multiplier = 1.0 + (weighted_score / 10.0) * 0.5
        expected_benefit = profile.current_value_krw * revenue_multiplier

        # 예상 비용 = 현재가치 x 비용 비율 (방법별)
        cost_ratios: dict[str, float] = {
            "단독개발": 0.7,
            "합동개발": 0.65,
            "환지방식": 0.75,
            "도시개발": 0.8,
            "도시정비": 0.85,
            "민관합작(PPP)": 0.7,
            "리모델링": 0.5,
        }
        estimated_cost = profile.current_value_krw * cost_ratios.get(
            recommended_method, 0.7
        )

        if estimated_cost <= 0:
            return 0.0
        return round(expected_benefit / estimated_cost, 4)

    @staticmethod
    def _rank_methods(
        weighted_scores: dict[str, float],
    ) -> list[tuple[str, float]]:
        """가중 점수 기준 내림차순 정렬.

        Args:
            weighted_scores: 방법별 가중 점수

        Returns:
            (방법명, 점수) 튜플 리스트 (내림차순)
        """
        return sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)

    async def evaluate(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        site_profile: SiteProfile,
    ) -> DevelopmentMethodResult:
        """7가지 개발방법을 평가하고 최적 방법을 추천한다.

        Args:
            tenant_id: 테넌트 ID
            project_id: 프로젝트 ID
            site_profile: 부지 프로파일

        Returns:
            저장된 DevelopmentMethodResult 모델 인스턴스
        """
        logger.info(
            "개발방법 평가 시작",
            project_id=str(project_id),
            site_area_sqm=site_profile.site_area_sqm,
            zoning_type=site_profile.zoning_type,
        )

        adjusted = self._adjust_scores(site_profile)
        weighted = self._calculate_weighted_scores(adjusted)
        ranked = self._rank_methods(weighted)

        best_method, best_score = ranked[0]
        bcr = self._calculate_bcr(site_profile, best_method, best_score)

        # 방법별 점수 및 순위 JSON
        method_scores_json: dict[str, Any] = {
            m: {"score": s, "rank": i + 1}
            for i, (m, s) in enumerate(ranked)
        }

        # AHP 가중치 JSON
        ahp_weights_json: dict[str, float] = {
            "수익성": 0.35,
            "사업기간": 0.25,
            "위험도": 0.25,
            "인허가용이": 0.15,
        }

        # SiteProfile → dict
        site_profile_json: dict[str, Any] = asdict(site_profile)

        analysis_summary = (
            f"최적 개발방법: {best_method} (가중점수: {best_score}, BCR: {bcr})"
        )

        result = DevelopmentMethodResult(
            tenant_id=tenant_id,
            project_id=project_id,
            site_area_sqm=site_profile.site_area_sqm,
            zoning_type=site_profile.zoning_type,
            recommended_method=best_method,
            recommended_method_score=best_score,
            bcr=bcr,
            method_scores_json=method_scores_json,
            ahp_weights_json=ahp_weights_json,
            site_profile_json=site_profile_json,
            analysis_summary=analysis_summary,
        )
        self.db.add(result)
        await self.db.commit()
        await self.db.refresh(result)

        logger.info(
            "개발방법 평가 완료",
            project_id=str(project_id),
            recommended_method=best_method,
            score=best_score,
            bcr=bcr,
        )

        return result
