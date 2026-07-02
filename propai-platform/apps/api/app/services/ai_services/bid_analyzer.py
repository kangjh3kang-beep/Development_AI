"""나라장터(G2B) AI 입찰 분석 엔진.

적정 투찰가 예측, 사업성 자동 진단(Monte Carlo), 리스크 스코어링을 수행한다.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.g2b_bid import G2BAwardStat, G2BBid
from app.schemas.g2b_bid import G2BBidAnalyzeRequest, G2BBidAnalyzeResponse

logger = logging.getLogger(__name__)


# ── 추정가격 역산 상수 (입찰 데이터엔 연면적/층수/구조가 없으므로 estimated_price로 역산) ──

# 건물유형별 평당 도급공사비 기준값(원/평, 2026). StandardQuantityEstimator 키와 1:1 일치 필수.
CONSTRUCTION_COST_PER_PYEONG: dict[str, int] = {
    "아파트": 6_500_000,
    "공동주택": 6_200_000,
    "오피스텔": 6_800_000,
    "다세대주택": 5_500_000,
    "근린생활시설": 5_800_000,
}
_DEFAULT_COST_PER_PYEONG = 6_000_000

# 구조유형 보정계수 (StandardQuantityEstimator.STRUCTURE_FACTORS와 동일 개념)
_STRUCTURE_FACTORS: dict[str, float] = {
    "RC": 1.00, "SRC": 1.15, "SC": 1.10, "PC": 0.92, "목구조": 0.70,
}

# 지역 보정계수 (평당공사비)
_REGION_COST_FACTORS: list[tuple[str, float]] = [
    ("서울", 1.08), ("경기", 1.03), ("인천", 1.03),
    ("부산", 1.00), ("대구", 1.00), ("광주", 1.00),
    ("대전", 1.00), ("울산", 1.00), ("세종", 1.00),
]

# building_type → GRESB 영문 / permit_validator dev_type 매핑
_BUILDING_TYPE_EN: dict[str, str] = {
    "아파트": "apartment", "공동주택": "apartment", "오피스텔": "office",
    "다세대주택": "apartment", "근린생활시설": "commercial",
}
_BUILDING_TYPE_DEV: dict[str, str] = {
    "아파트": "M02", "공동주택": "M01", "오피스텔": "M08",
    "다세대주택": "M01", "근린생활시설": "M13",
}

# 주거 계열(QTO/수지 적용 대상). 용역/물품·비주거는 간이 분석.
_RESIDENTIAL_BUILDING_TYPES = {"아파트", "공동주택", "오피스텔", "다세대주택"}

PYEONG_PER_SQM = 3.3058


class BidAnalyzer:
    """입찰 건에 대한 AI 분석을 수행한다."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze(self, bid: G2BBid, req: G2BBidAnalyzeRequest) -> G2BBidAnalyzeResponse:
        """입찰 건을 종합 분석한다."""

        # 1. 지역/공종별 과거 낙찰가율 조회
        region_stats = await self._get_region_award_stats(bid.bid_type, bid.region_sido)
        similar_count = await self._count_similar_bids(bid.bid_type, bid.region_sido)

        # 2. 적정 투찰가율 예측
        bid_rate = self._predict_bid_rate(region_stats)

        # 3. 사업성 자동 진단 (Monte Carlo 간이 시뮬레이션)
        npv, roi, profit_prob = self._run_monte_carlo(
            estimated_price=int(bid.estimated_price or 0),
            avg_award_rate=region_stats.get("avg", 85.0),
            cost_volatility=req.cost_volatility_pct,
            iterations=req.simulation_iterations,
        )

        # 4. 리스크 스코어링
        risk_cost = self._score_cost_risk(req.cost_volatility_pct, region_stats)
        risk_trust = self._score_trust_risk(bid.org_type or "")
        risk_competition = self._score_competition_risk(similar_count, bid.bid_count)
        risk_total = (risk_cost * 0.4) + (risk_trust * 0.3) + (risk_competition * 0.3)

        # 5. AI 요약 텍스트 생성
        summary = self._generate_summary(
            bid=bid,
            bid_rate=bid_rate,
            npv=npv,
            roi=roi,
            risk_total=risk_total,
            region_avg=region_stats.get("avg"),
        )

        # DB에 AI 결과 캐시
        bid.ai_risk_score = round(risk_total, 2)
        bid.ai_recommended_bid_rate = round(bid_rate["mid"], 3)
        bid.ai_analysis_summary = summary
        bid.updated_at = datetime.utcnow()
        await self.db.commit()

        return G2BBidAnalyzeResponse(
            bid_notice_no=bid.bid_notice_no,
            bid_notice_nm=bid.bid_notice_nm,
            estimated_price=int(bid.estimated_price) if bid.estimated_price else None,
            recommended_bid_rate_low=round(bid_rate["low"], 3),
            recommended_bid_rate_mid=round(bid_rate["mid"], 3),
            recommended_bid_rate_high=round(bid_rate["high"], 3),
            expected_npv=npv,
            expected_roi=roi,
            profit_probability=profit_prob,
            risk_score_cost=round(risk_cost, 2),
            risk_score_trust=round(risk_trust, 2),
            risk_score_competition=round(risk_competition, 2),
            risk_score_total=round(risk_total, 2),
            region_avg_award_rate=region_stats.get("avg"),
            similar_bids_count=similar_count,
            ai_summary=summary,
            g2b_url=bid.g2b_url,
        )

    async def analyze_feasibility(
        self, bid: G2BBid, req: G2BBidAnalyzeRequest
    ) -> G2BBidAnalyzeResponse:
        """6엔진 연동 정밀 분석 — QTO→원가→수지MC→민감도→용도지역→법규→ESG→시장.

        경량 analyze()를 베이스로 호출한 뒤, 사업성/원가/법규/ESG 섹션을 채운다.
        각 엔진은 독립 try/except로 실패해도 해당 섹션만 None.
        """
        # 1) 경량 분석으로 base 응답 확보 (투찰가/리스크/요약/DB 캐시)
        base = await self.analyze(bid, req)
        warnings: list[str] = []

        integrator = BidFeasibilityIntegrator(self.db)
        await integrator.run(bid, req, base, warnings)

        base.analysis_warnings = warnings

        # 2) LLM(Claude) 자연어 해석 — 6엔진 수치를 입찰 전략으로 해석.
        #    실패해도 규칙기반 결과는 그대로 반환(graceful fallback).
        if getattr(req, "include_ai_interpretation", True):
            try:
                from app.schemas.g2b_bid import BidInterpretation
                from app.services.ai_services.bid_interpreter import BidInterpreter

                interp = await BidInterpreter().generate_interpretation(
                    base.model_dump(mode="json"),
                    model_tier=getattr(req, "model_tier", "standard"),
                )
                if interp:
                    base.ai_interpretation = BidInterpretation(**interp)
                else:
                    warnings.append("AI 해석 미생성(LLM 미설정/호출 실패) — 규칙기반 결과만 제공")
            except Exception as e:
                warnings.append(f"AI 해석 실패: {str(e)[:80]}")

        base.analysis_warnings = warnings
        # 정밀 분석 결과를 raw_data에 캐시 (신규 컬럼 회피)
        try:
            raw = dict(bid.raw_data or {})
            raw["ai_feasibility"] = base.model_dump(mode="json")
            bid.raw_data = raw
            await self.db.commit()
        except Exception as e:
            logger.warning("정밀분석 캐시 저장 실패: %s", str(e)[:120])
        return base

    # ──────────────────────────────────────────
    # 내부 분석 메서드
    # ──────────────────────────────────────────

    async def _get_region_award_stats(
        self, bid_type: str, region_sido: str | None
    ) -> dict:
        """지역/공종별 과거 낙찰가율 통계를 조회한다."""
        conditions = [G2BBid.award_rate.isnot(None)]
        if bid_type:
            conditions.append(G2BBid.bid_type == bid_type)
        if region_sido:
            conditions.append(G2BBid.region_sido == region_sido)

        result = await self.db.execute(
            select(
                func.avg(G2BBid.award_rate),
                func.min(G2BBid.award_rate),
                func.max(G2BBid.award_rate),
                func.stddev(G2BBid.award_rate),
            ).where(and_(*conditions))
        )
        row = result.one_or_none()
        if row and row[0] is not None:
            return {
                "avg": float(row[0]),
                "min": float(row[1]) if row[1] else 70.0,
                "max": float(row[2]) if row[2] else 100.0,
                "std": float(row[3]) if row[3] else 5.0,
            }
        # 데이터 없으면 업종별 기본값
        defaults = {"공사": 85.5, "용역": 82.0, "물품": 88.0}
        avg = defaults.get(bid_type, 85.0)
        return {"avg": avg, "min": avg - 10, "max": avg + 5, "std": 5.0}

    async def _count_similar_bids(self, bid_type: str, region_sido: str | None) -> int:
        """최근 90일간 유사 공종의 입찰 건수를 조회한다."""
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        conditions = [G2BBid.bid_type == bid_type, G2BBid.notice_dt >= ninety_days_ago]
        if region_sido:
            conditions.append(G2BBid.region_sido == region_sido)
        result = await self.db.execute(
            select(func.count()).where(and_(*conditions))
        )
        return result.scalar() or 0

    @staticmethod
    def _predict_bid_rate(stats: dict) -> dict:
        """과거 통계 기반으로 적정 투찰가율 구간을 예측한다."""
        avg = stats["avg"]
        std = stats.get("std", 5.0)
        return {
            "low": max(60.0, avg - std * 1.0),
            "mid": avg,
            "high": min(100.0, avg + std * 0.5),
        }

    @staticmethod
    def _run_monte_carlo(
        estimated_price: int,
        avg_award_rate: float,
        cost_volatility: float,
        iterations: int,
    ) -> tuple[int | None, float | None, float | None]:
        """간이 Monte Carlo 시뮬레이션으로 예상 NPV/ROI를 산출한다."""
        if estimated_price <= 0:
            return None, None, None

        random.seed(42)
        revenue = estimated_price * (avg_award_rate / 100.0)
        positive_count = 0
        npv_sum = 0.0

        for _ in range(iterations):
            cost_factor = 1 + random.gauss(0, cost_volatility / 100.0)
            cost = estimated_price * 0.85 * cost_factor  # 원가율 약 85%
            profit = revenue - cost
            npv_sum += profit
            if profit > 0:
                positive_count += 1

        mean_npv = int(npv_sum / iterations)
        roi = (mean_npv / (estimated_price * 0.85)) * 100 if estimated_price > 0 else 0.0
        profit_prob = (positive_count / iterations) * 100

        return mean_npv, round(roi, 2), round(profit_prob, 2)

    @staticmethod
    def _score_cost_risk(volatility_pct: float, stats: dict) -> float:
        """공사비 변동 리스크를 0~100으로 스코어링한다."""
        std = stats.get("std", 5.0)
        base = min(100.0, volatility_pct * 3)
        spread = min(100.0, std * 5)
        return (base * 0.6) + (spread * 0.4)

    @staticmethod
    def _score_trust_risk(org_type: str) -> float:
        """발주기관 유형별 신뢰도 리스크를 0~100으로 스코어링한다."""
        trust_map = {"중앙행정기관": 10, "공기업": 15, "지자체": 25, "기타공공기관": 40}
        return float(trust_map.get(org_type, 50))

    @staticmethod
    def _score_competition_risk(similar_count: int, bid_count: int | None) -> float:
        """경쟁 강도를 0~100으로 스코어링한다."""
        if bid_count and bid_count > 0:
            return min(100.0, bid_count * 5.0)
        return min(100.0, similar_count * 2.0)

    @staticmethod
    def _generate_summary(
        bid: G2BBid,
        bid_rate: dict,
        npv: int | None,
        roi: float | None,
        risk_total: float,
        region_avg: float | None,
    ) -> str:
        """AI 분석 요약 텍스트를 생성한다."""
        lines = [f"■ 공고: {bid.bid_notice_nm}"]

        if bid.estimated_price:
            lines.append(f"■ 추정가격: {int(bid.estimated_price):,}원")

        lines.append(
            f"■ 적정 투찰가율: {bid_rate['low']:.1f}% ~ {bid_rate['high']:.1f}% (중앙값 {bid_rate['mid']:.1f}%)"
        )

        if region_avg:
            lines.append(f"■ 해당 지역({bid.region_sido or '전국'}) 평균 낙찰가율: {region_avg:.1f}%")

        if npv is not None:
            lines.append(f"■ 예상 NPV: {npv:,}원 / ROI: {roi:.1f}%")

        risk_level = "낮음" if risk_total < 30 else ("보통" if risk_total < 60 else "높음")
        lines.append(f"■ 종합 리스크: {risk_total:.1f}점 ({risk_level})")

        if risk_total < 30:
            lines.append("▶ AI 추천: 적극적 참여를 권고합니다.")
        elif risk_total < 60:
            lines.append("▶ AI 추천: 조건부 참여를 권고합니다. 공사비 변동에 유의하세요.")
        else:
            lines.append("▶ AI 추천: 신중한 검토가 필요합니다. 리스크 요인을 면밀히 분석하세요.")

        return "\n".join(lines)


# ──────────────────────────────────────────
# 추정가격 역산 헬퍼 (모듈 레벨)
# ──────────────────────────────────────────

def _classify_from_notice(notice_nm: str) -> dict:
    """공고명 정규식으로 building_type/structure_type/규모 힌트 추출 (NLP 미사용)."""
    import re

    text = notice_nm or ""
    # building_type (StandardQuantityEstimator 키와 1:1)
    # 1) 건물 신축/증축형: 면적·층수가 의미 있어 GFA 역산·QTO 적용 대상.
    # 2) 토목·설비·단종형(사면정비·배수로·농로·포장·승강기설치·전기/소방공사 등):
    #    "건물"이 아니므로 GFA 역산이 무의미 → "비건물"로 분류해 QTO 미적용.
    non_building = re.search(
        r"사면|비탈면|옹벽|배수로?|수로|농로|포장|도로|교량|상하수도|관로|"
        r"준설|하천|정비사업|사방|수리시설|저수지|제방|법면|굴착|토공|"
        r"승강기|엘리베이터|에스컬레이터|전기공사|소방공사|통신공사|"
        r"기계설비|냉난방|조경공사|식재|살수|방수공사|도장공사",
        text,
    )
    building = re.search(
        r"신축|증축|개축|대수선|건립|신설.*(청사|센터|관|동)|건축공사", text
    )
    if re.search(r"아파트|APT", text, re.I):
        btype = "아파트"
    elif re.search(r"오피스텔", text):
        btype = "오피스텔"
    elif re.search(r"다세대|연립|빌라", text):
        btype = "다세대주택"
    elif re.search(r"근린생활|근생|상가|판매시설|청사|관사|업무시설|사옥", text):
        btype = "근린생활시설"
    elif non_building and not building:
        btype = "비건물"  # 토목·설비·단종공사 → GFA역산/QTO 미적용
    elif building:
        btype = "공동주택"  # 건물 신축이 명시된 일반 건물
    else:
        btype = "비건물"  # 건물 키워드가 전혀 없으면 보수적으로 비건물 처리

    # structure_type
    if re.search(r"SRC|철골철근", text):
        stype = "SRC"
    elif re.search(r"철골|S조|\bSC\b", text):
        stype = "SC"
    elif re.search(r"\bPC\b|프리캐스트", text):
        stype = "PC"
    else:
        stype = "RC"

    # 규모 힌트 (공고명에 명시된 경우만)
    floors_above = None
    m = re.search(r"지상\s*(\d+)\s*층", text)
    if m:
        floors_above = int(m.group(1))
    floors_below = None
    m = re.search(r"지하\s*(\d+)\s*층", text)
    if m:
        floors_below = int(m.group(1))
    gfa = None
    m = re.search(r"연면적\s*([\d,]+(?:\.\d+)?)\s*(?:㎡|m2|m²)", text)
    if m:
        gfa = float(m.group(1).replace(",", ""))

    return {
        "building_type": btype,
        "structure_type": stype,
        "floor_count_above": floors_above,
        "floor_count_below": floors_below,
        "total_gfa_sqm": gfa,
    }


def _region_cost_factor(region: str) -> float:
    for key, factor in _REGION_COST_FACTORS:
        if key in (region or ""):
            return factor
    return 0.95  # 그 외 지역


def _estimate_floors(gfa_sqm: float) -> int:
    if gfa_sqm < 3000:
        return 5
    if gfa_sqm < 10000:
        return 12
    if gfa_sqm < 30000:
        return 20
    return 30


def reverse_estimate_spec(bid: G2BBid, req: G2BBidAnalyzeRequest) -> dict:
    """추정가격 역산 + 수동보정으로 건축 개요(BidSpecEstimate dict)를 산출."""
    notice = _classify_from_notice(bid.bid_notice_nm or "")
    region = bid.region_sido or ""

    # building_type: 수동 override > 공고명 분류
    building_type = req.building_type_override or notice["building_type"]
    structure_type = req.structure_type or notice["structure_type"]

    est_price = int(bid.estimated_price or 0)
    source = "notice"
    confidence = 0.5

    # 연면적: 수동 > 공고명 명시 > 평당공사비 역산
    if req.total_gfa_sqm:
        gfa = float(req.total_gfa_sqm)
        source = "manual"
        confidence = 0.95
    elif building_type == "비건물":
        # 토목·설비·단종공사는 연면적 개념이 없어 GFA 역산/QTO를 적용하지 않는다.
        gfa = 0.0
        source = "non_building"
        confidence = 0.3
    elif notice["total_gfa_sqm"]:
        gfa = float(notice["total_gfa_sqm"])
        source = "notice"
        confidence = 0.8
    elif est_price > 0:
        cpp = CONSTRUCTION_COST_PER_PYEONG.get(building_type, _DEFAULT_COST_PER_PYEONG)
        cpp *= _STRUCTURE_FACTORS.get(structure_type, 1.0)
        cpp *= _region_cost_factor(region)
        gfa = est_price / cpp * PYEONG_PER_SQM
        source = "auto"
        confidence = 0.4
    else:
        gfa = 0.0
        source = "auto"
        confidence = 0.1

    floors_above = (
        req.floor_count_above
        or notice["floor_count_above"]
        or (_estimate_floors(gfa) if gfa > 0 else 5)
    )
    floors_below = (
        req.floor_count_below
        if req.floor_count_below is not None
        else (notice["floor_count_below"] if notice["floor_count_below"] is not None else 1)
    )

    return {
        "building_type": building_type,
        "total_gfa_sqm": round(gfa, 1),
        "floor_count_above": int(floors_above),
        "floor_count_below": int(floors_below),
        "structure_type": structure_type,
        "source": source,
        "confidence": confidence,
    }


# ──────────────────────────────────────────
# 6엔진 연동 통합기
# ──────────────────────────────────────────

class BidFeasibilityIntegrator:
    """입찰 1건을 QTO/원가/수지/용도지역/법규/ESG/시장 엔진에 연결한다."""

    def __init__(self, db):
        self.db = db

    async def run(self, bid, req, base, warnings: list) -> None:
        """base 응답(G2BBidAnalyzeResponse)에 정밀 섹션을 채운다(in-place)."""
        from app.schemas.g2b_bid import (
            BidCostBreakdown,
            BidEsg,
            BidMarketFeed,
            BidPermitCheck,
            BidQtoItem,
            BidSensitivity,
            BidSpecEstimate,
            BidZoning,
            G2BAwardStatResponse,
        )

        est_price = int(bid.estimated_price or 0)

        # [0] 역산 스펙
        spec = reverse_estimate_spec(bid, req)
        base.spec = BidSpecEstimate(**spec)
        btype = spec["building_type"]
        is_residential = (bid.bid_type == "공사") and (btype in _RESIDENTIAL_BUILDING_TYPES)

        cost_total = 0
        # [1~3] QTO → 원가 → 원가MC
        if is_residential and spec["total_gfa_sqm"] > 0:
            try:
                from app.services.cost.cost_monte_carlo import CostMonteCarlo
                from app.services.cost.origin_cost_calculator import OriginCostCalculator
                from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator

                items = StandardQuantityEstimator().estimate(
                    building_type=btype,
                    total_gfa_sqm=spec["total_gfa_sqm"],
                    floor_count_above=spec["floor_count_above"],
                    floor_count_below=spec["floor_count_below"],
                    structure_type=spec["structure_type"],
                )
                cost = OriginCostCalculator().calculate(items=items)
                cost_total = int(cost.get("total_project_cost", 0) or 0)
                cost_mc = CostMonteCarlo(
                    cost, iters=min(req.simulation_iterations, 10000), seed=42
                ).run()
                base.cost_breakdown = BidCostBreakdown(
                    direct_cost=int(cost.get("direct_cost", 0) or 0),
                    total_project_cost=cost_total,
                    category_totals=cost.get("category_totals", {}) or {},
                    cost_p10=cost_mc.get("p10"),
                    cost_p50=cost_mc.get("p50"),
                    cost_p80=cost_mc.get("p80"),
                    cost_p90=cost_mc.get("p90"),
                    cv=cost_mc.get("cv"),
                    risk_contributions=cost_mc.get("risk_contributions", {}) or {},
                )
                base.qto = [
                    BidQtoItem(
                        work_code=str(it.get("work_code", "")),
                        item_name=str(it.get("item_name", "")),
                        unit=str(it.get("unit", "")),
                        quantity=float(it.get("quantity", 0) or 0),
                    )
                    for it in items[:30]
                ]
            except Exception as e:
                warnings.append(f"QTO/원가 분석 실패: {str(e)[:80]}")
        elif btype == "비건물":
            warnings.append("토목·설비·단종공사: 연면적 개념 없음 → QTO/원가 미적용, 도급 수지만 산출")
        else:
            warnings.append("비주거/용역·물품: QTO 미적용(추정가격 기반 간이 분석)")

        # [5] 입찰 수지 MC (도급공사 현실모델) + [2-4] 적정투찰가 BEP
        #
        # 도급공사 수지의 핵심:
        #   매출 = 낙찰금액 = 추정가(예정가격) × 낙찰가율
        #   원가 = 시공사 실원가 ≈ 추정가 × 실원가율(절대비율)
        # 예정가격은 이미 발주처 산정 원가+제경비+이윤을 포함하므로, 시공사 실원가는
        # 통상 예정가의 0.85~0.90 수준이다. 따라서 이윤 = 추정가 × (낙찰가율 - 실원가율).
        # 손익분기 낙찰가율 = 실원가율 × 100 으로 명확히 정의되며(이 가율 미만이면 적자),
        # 시장 낙찰가율이 손익분기를 상회하는 정도가 곧 마진이 된다.
        # (이전 모델은 원가를 '낙찰액 대비 비율'로 잡아 낙찰가율과 무관하게 항상 흑자가
        #  나오는 오류가 있었음 → 추정가 대비 절대 원가율로 교정.)
        region_stats = await self._region_stats(bid)
        try:
            from app.services.feasibility.monte_carlo_engine import MCVariable, run_monte_carlo

            avg_rate = region_stats["avg"]
            std_rate = region_stats["std"]
            # 실원가율: 추정가 대비 시공사 실원가 비율(평균 0.87, 표준편차는 입력 변동성 연동).
            cost_ratio_mean = 0.87
            cost_ratio_std = max(0.005, req.cost_volatility_pct / 100.0 * 0.3)

            def bid_npv_fn(v: dict) -> float:
                award_amount = est_price * (v["award_rate"] / 100.0)
                actual_cost = est_price * v["cost_ratio"]
                return award_amount - actual_cost  # 도급 이윤(원)

            mc = run_monte_carlo(
                calculate_fn=bid_npv_fn,
                variables=[
                    MCVariable(name="award_rate", mean=avg_rate, std=max(1.0, std_rate)),
                    MCVariable(name="cost_ratio", mean=cost_ratio_mean, std=cost_ratio_std),
                ],
                n_simulations=min(req.simulation_iterations, 10000),
                seed=42,
            )
            base_cost = est_price * cost_ratio_mean  # ROI 분모(기대 실원가)
            base.expected_npv = int(mc.get("mean", 0))
            base.profit_probability = round(mc.get("probability_positive", 0) * 100, 2)
            base.expected_roi = round(
                (mc.get("mean", 0) / base_cost * 100) if base_cost > 0 else 0.0, 2
            )

            # 손익분기 낙찰가율 = 실원가율 × 100 (이 가율 미만으로 받으면 적자).
            if est_price > 0:
                bep = cost_ratio_mean * 100.0
                base.break_even_bid_rate = round(bep, 2)
                margin = req.target_margin_pct
                # 적정 투찰가율: 손익분기 위에서 목표마진을 더하되, 시장 낙찰가율 통계
                # 범위 안에서 클램프하고 손익분기 미만으로는 절대 내려가지 않는다.
                low = max(bep, avg_rate - std_rate)
                mid = min(max(bep + margin, avg_rate), avg_rate + std_rate)
                mid = max(mid, low)
                high = max(mid, min(100.0, avg_rate + std_rate * 0.5))
                base.recommended_bid_rate_low = round(min(max(low, bep), 100.0), 3)
                base.recommended_bid_rate_mid = round(min(mid, 100.0), 3)
                base.recommended_bid_rate_high = round(min(high, 100.0), 3)
                base.recommended_bid_price = int(est_price * base.recommended_bid_rate_mid / 100.0)
                # 시장 낙찰가율이 손익분기 미만이면 적자 경고.
                if avg_rate < bep:
                    warnings.append(
                        f"시장 평균 낙찰가율({avg_rate:.1f}%)이 손익분기({bep:.1f}%) 미만 "
                        f"— 시장가 투찰 시 적자 위험, 원가절감 없이는 수주 비권장"
                    )
        except Exception as e:
            warnings.append(f"수지 시뮬레이션 실패: {str(e)[:80]}")

        # [6] 민감도
        try:
            from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis

            # 민감도도 [5]와 동일한 도급 수지모델(추정가 대비 절대 원가율)을 사용한다.
            def sens_fn(vals: dict) -> dict:
                award_amount = est_price * (vals["award_rate"] / 100.0)
                actual_cost = est_price * vals["cost_ratio"]
                profit = award_amount - actual_cost
                rate = (profit / actual_cost * 100) if actual_cost > 0 else 0
                return {"profit_rate_pct": round(rate, 2), "npv_won": round(profit)}

            sens = run_sensitivity_analysis(
                base_values={"award_rate": region_stats["avg"], "cost_ratio": 0.87},
                calculate_fn=sens_fn,
            )
            base.sensitivity = BidSensitivity(
                tornado=sens.get("tornado", []), scenarios=sens.get("scenarios", []),
            )
        except Exception as e:
            warnings.append(f"민감도 분석 실패: {str(e)[:80]}")

        # [7] 용도지역 (근사)
        addr = ""
        try:
            raw = bid.raw_data or {}
            addr = raw.get("cnstrtsiteRgnNm") or bid.region_sido or ""
            if addr:
                from app.services.zoning.auto_zoning_service import AutoZoningService

                zoning = await AutoZoningService().analyze_by_address(addr)
                limits = zoning.get("zone_limits") or {}
                base.zoning = BidZoning(
                    zone_type=zoning.get("zone_type"),
                    max_bcr_pct=limits.get("max_bcr_pct"),
                    max_far_pct=limits.get("max_far_pct"),
                    max_height_m=limits.get("max_height_m"),
                    pnu=zoning.get("pnu"),
                    warnings=["입찰 현장지역명 기반 근사(정확 주소 미상)"],
                )
        except Exception as e:
            warnings.append(f"용도지역 분석 실패: {str(e)[:80]}")

        # [8~9] 법규 PQ + 인허가 가능성
        try:
            from app.services.feasibility.permit_validator import check_permit_feasibility

            zone_type = base.zoning.zone_type if base.zoning else ""
            dev_type = _BUILDING_TYPE_DEV.get(btype, "M01")
            permit = check_permit_feasibility(dev_type, zone_type or "")
            base.permit_check = BidPermitCheck(
                is_permitted=permit.get("is_permitted"),
                permit_complexity=permit.get("permit_complexity"),
                reason=permit.get("reason"),
                rule_results=[],
            )
        except Exception as e:
            warnings.append(f"인허가 분석 실패: {str(e)[:80]}")

        # [10] ESG/GRESB
        if is_residential and spec["total_gfa_sqm"] > 0:
            try:
                from app.services.esg.gresb_scoring_service import GresbScoringService

                gresb = GresbScoringService().calculate_score(
                    building_type=_BUILDING_TYPE_EN.get(btype, "apartment"),
                    floor_area_sqm=spec["total_gfa_sqm"],
                )
                # GresbScoringService는 recommendations를 dict 리스트
                # (area/action/priority/potential_gain/cost_grade)로 반환하므로
                # BidEsg.recommendations(list[str]) 규격에 맞춰 문자열로 변환한다.
                raw_recs = gresb.get("recommendations", []) or []
                rec_texts = [
                    r
                    if isinstance(r, str)
                    else f"[{r.get('area', '')}] {r.get('action', '')}".strip()
                    for r in raw_recs
                ]
                base.esg = BidEsg(
                    total_score=gresb.get("total_score"),
                    grade=gresb.get("grade"),
                    components=gresb.get("components", {}) or {},
                    recommendations=rec_texts,
                )
            except Exception as e:
                warnings.append(f"ESG 분석 실패: {str(e)[:80]}")

        # [11] 시장동향 피드 (G2BAwardStat)
        try:
            stats = await self._award_stats_feed(bid)
            base.market_feed = BidMarketFeed(
                items=[G2BAwardStatResponse.model_validate(s) for s in stats],
                region_avg=region_stats["avg"],
                region_std=region_stats["std"],
            )
        except Exception as e:
            warnings.append(f"시장동향 피드 실패: {str(e)[:80]}")

    async def _region_stats(self, bid) -> dict:
        """지역/공종 낙찰가율 평균·표준편차 (BidAnalyzer 통계 재사용)."""
        analyzer = BidAnalyzer(self.db)
        return await analyzer._get_region_award_stats(bid.bid_type, bid.region_sido)

    async def _award_stats_feed(self, bid) -> list:
        """G2BAwardStat 시장 피드 (최근 집계)."""
        from sqlalchemy import select

        q = select(G2BAwardStat).where(G2BAwardStat.bid_type == bid.bid_type)
        if bid.region_sido:
            q = q.where(G2BAwardStat.region_sido == bid.region_sido)
        q = q.order_by(G2BAwardStat.stat_period.desc()).limit(12)
        result = await self.db.execute(q)
        return list(result.scalars().all())
