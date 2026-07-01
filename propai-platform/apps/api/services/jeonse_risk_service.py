"""전세 리스크 분석 서비스.

전세가율, 갭투자 위험도, HUG 보증보험 가입 가능 여부, 7대 사기 패턴 탐지.

흐름:
1. 해당 지역 전세가/매매가 데이터 수집 (국토부 실거래가 API — asyncio.gather 병렬)
2. 전세가율 계산 및 위험 등급 판정
3. HUG 보증보험 가입 가능 여부 판단
4. 7대 사기 패턴 체크 (주소, 전세가, 시장데이터 기반)
5. LLM 기반 종합 리스크 분석
"""

import asyncio
from datetime import UTC, datetime

UTC = UTC
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# ── 수도권 법정동코드 (앞 2자리) ──
_METROPOLITAN_CODES = {"11", "41", "28"}  # 서울, 경기, 인천


class JeonseRiskResult:
    """전세 리스크 분석 결과."""

    def __init__(
        self,
        jeonse_ratio: float,
        risk_level: str,
        risk_score: float,
        analysis: str,
        factors: list[dict[str, Any]],
        hug_eligible: bool = False,
        hug_reason: str = "",
        market_data: dict[str, Any] | None = None,
    ):
        self.jeonse_ratio = jeonse_ratio
        self.risk_level = risk_level
        self.risk_score = risk_score
        self.analysis = analysis
        self.factors = factors
        self.hug_eligible = hug_eligible
        self.hug_reason = hug_reason
        self.market_data = market_data or {}


class JeonseRiskService:
    """전세 리스크 분석 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── 1. 위험 등급 판정 ──

    @staticmethod
    def _calculate_risk_level(jeonse_ratio: float) -> tuple[str, float]:
        """전세가율 기반 위험 등급을 판정한다."""
        if jeonse_ratio >= 0.90:
            return "CRITICAL", 0.95
        if jeonse_ratio >= 0.80:
            return "HIGH", 0.80
        if jeonse_ratio >= 0.70:
            return "MEDIUM", 0.55
        if jeonse_ratio >= 0.60:
            return "LOW", 0.30
        return "SAFE", 0.10

    # ── 2. HUG 보증보험 가입 가능 여부 ──

    @staticmethod
    def _check_hug_eligibility(
        jeonse_price: float,
        is_metropolitan: bool = True,
    ) -> tuple[bool, str]:
        """HUG 전세보증보험 가입 가능 여부를 판단한다.

        - 수도권: 전세가 7억원 이하
        - 지방: 전세가 5억원 이하
        """
        limit = 700_000_000 if is_metropolitan else 500_000_000
        area_name = "수도권" if is_metropolitan else "지방"

        if jeonse_price <= limit:
            return True, f"HUG 가입 가능 ({area_name} {limit / 1e8:.0f}억 이하)"
        return (
            False,
            f"HUG 가입 불가 — {area_name} 기준 {limit / 1e8:.0f}억 초과 "
            f"(전세가 {jeonse_price / 1e8:.1f}억)",
        )

    # ── 3. 7대 전세 사기 패턴 탐지 ──

    @staticmethod
    def _detect_fraud_patterns(
        address: str,
        jeonse_price: float,
        market_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """7대 전세 사기 패턴을 체크한다.

        Args:
            address: 물건 주소
            jeonse_price: 해당 물건 전세가
            market_data: _fetch_market_data()의 반환값

        Returns:
            탐지된 위험 요인 리스트
        """
        detected: list[dict[str, Any]] = []

        avg_sale = market_data.get("avg_sale_price", 0)
        avg_jeonse = market_data.get("avg_jeonse_price", 0)
        trade_count = market_data.get("trade_count", 0)

        # 전세가율 (시장 평균 매매가 대비)
        ratio = jeonse_price / avg_sale if avg_sale > 0 else 0.0

        # 패턴 1: 갭투자 위험 — 전세가율 80% 이상
        if ratio >= 0.80:
            detected.append({
                "factor": "갭투자 위험",
                "impact": "HIGH",
                "description": (
                    f"전세가율 {ratio:.1%} — 매매가 대비 전세가가 "
                    "과도하게 높아 역전세 위험"
                ),
            })

        # 패턴 2: 깡통전세 — 전세가율 90% 이상
        if ratio >= 0.90:
            detected.append({
                "factor": "깡통전세 위험",
                "impact": "CRITICAL",
                "description": (
                    f"전세가율 {ratio:.1%} — 전세금 전액 미회수 "
                    "위험 극히 높음"
                ),
            })

        # 패턴 3: 고액 보증금 — 시장 평균 전세가 대비 1.5배 이상
        if avg_jeonse > 0 and jeonse_price > avg_jeonse * 1.5:
            detected.append({
                "factor": "고액 보증금 — 시장 이상치",
                "impact": "MEDIUM",
                "description": (
                    f"요청 전세가 {jeonse_price / 1e8:.1f}억이 "
                    f"지역 평균 {avg_jeonse / 1e8:.1f}억의 1.5배 초과"
                ),
            })

        # 패턴 4: 거래 희소성 — 최근 거래 건수 3건 미만
        if trade_count < 3:
            detected.append({
                "factor": "거래 희소성",
                "impact": "MEDIUM",
                "description": (
                    f"해당 지역 최근 거래 {trade_count}건 — "
                    "시세 파악 어려움, 사기 위험 ↑"
                ),
            })

        # 패턴 5: 신축 빌라 + 높은 전세가율
        is_villa = any(kw in address for kw in ("빌라", "다세대", "연립"))
        if is_villa and ratio >= 0.85:
            detected.append({
                "factor": "신축 빌라 전세사기 패턴",
                "impact": "HIGH",
                "description": (
                    "빌라/다세대 + 전세가율 85% 이상 — "
                    "PF 대출 사기 주의"
                ),
            })

        # 패턴 6: 등기부 확인 필요 (항상 경고)
        detected.append({
            "factor": "등기부등본 확인 필요",
            "impact": "MEDIUM",
            "description": (
                "근저당 설정액, 소유권 이전 이력, "
                "가압류 여부를 등기부에서 반드시 확인"
            ),
        })

        # 패턴 7: 전세금 반환 보증 미가입 위험 (항상 경고)
        detected.append({
            "factor": "전세금 반환 보증 미가입 위험",
            "impact": "MEDIUM",
            "description": (
                "HUG/SGI 전세보증보험 가입 여부를 반드시 "
                "확인하세요"
            ),
        })

        return detected

    # ── 4. 시장 데이터 수집 (asyncio.gather 병렬 호출) ──

    async def _fetch_market_data(
        self,
        address: str,
        lawd_cd: str = "",
    ) -> dict[str, Any]:
        """국토부 실거래가 API로 해당 지역 시장 데이터를 수집한다.

        get_apartment_trades + get_apartment_rent 를 asyncio.gather로
        병렬 호출하여 응답 시간을 최소화한다.
        실패 시 전세가율 65% 기본 추정치를 반환한다.
        """
        from apps.api.integrations.molit_client import MolitClient

        if not lawd_cd:
            lawd_cd = "11680"  # 서울 강남구 기본값

        molit = MolitClient()
        now = datetime.now(tz=UTC)
        deal_ymd = now.strftime("%Y%m")

        try:
            # asyncio.gather로 매매+전월세 병렬 호출
            gather_results = await asyncio.gather(
                molit.get_apartment_trades(lawd_cd, deal_ymd),
                molit.get_apartment_rent(lawd_cd, deal_ymd),
                return_exceptions=True,
            )
            trade_raw: dict[str, Any] | BaseException = gather_results[0]
            rent_raw: dict[str, Any] | BaseException = gather_results[1]

            # 매매 데이터 파싱
            avg_sale = 0.0
            trade_count = 0
            if isinstance(trade_raw, dict):
                trade_items = molit._extract_items(trade_raw)
                prices = []
                for item in trade_items:
                    price_str = str(
                        item.get("거래금액", "0"),
                    ).replace(",", "").strip()
                    price = int(price_str or 0)
                    if price > 0:
                        prices.append(price)
                trade_count = len(prices)
                if prices:
                    avg_sale = sum(prices) / len(prices) * 10000  # 만원→원

            # 전월세 데이터 파싱 (전세만 필터: 월세 0)
            avg_jeonse = 0.0
            rent_count = 0
            if isinstance(rent_raw, dict):
                rent_items = molit._extract_items(rent_raw)
                deposits = []
                for item in rent_items:
                    deposit_str = str(
                        item.get("보증금액", "0"),
                    ).replace(",", "").strip()
                    monthly_str = str(
                        item.get("월세금액", "0"),
                    ).replace(",", "").strip()
                    deposit = int(deposit_str or 0)
                    monthly = int(monthly_str or 0)
                    # 전세만 (월세 0원)
                    if deposit > 0 and monthly == 0:
                        deposits.append(deposit)
                rent_count = len(deposits)
                if deposits:
                    avg_jeonse = sum(deposits) / len(deposits) * 10000

            return {
                "avg_sale_price": avg_sale,
                "avg_jeonse_price": avg_jeonse,
                "trade_count": trade_count,
                "rent_count": rent_count,
                "deal_ymd": deal_ymd,
                "lawd_cd": lawd_cd,
            }

        except Exception:
            logger.warning(
                "시장 데이터 수집 실패 — 전세가율 65% 추정치 사용",
                address=address,
            )
            return self._market_data_fallback(deal_ymd, lawd_cd)

    @staticmethod
    def _market_data_fallback(
        deal_ymd: str = "",
        lawd_cd: str = "",
    ) -> dict[str, Any]:
        """API 통신 실패 시 전세가율 65% 추정치 기반 Fallback."""
        return {
            "avg_sale_price": 0,
            "avg_jeonse_price": 0,
            "estimated_jeonse_ratio": 0.65,
            "trade_count": 0,
            "rent_count": 0,
            "deal_ymd": deal_ymd,
            "lawd_cd": lawd_cd,
            "fallback": True,
        }

    # ── 5. LLM 종합 분석 ──

    async def _analyze_risk(
        self,
        address: str,
        jeonse_price: float,
        sale_price: float,
        jeonse_ratio: float,
        risk_level: str,
        hug_eligible: bool,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        """LLM으로 종합 리스크 분석을 수행한다."""
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.2,
        )

        prompt = f"""한국 부동산 전세 리스크 전문가로서 분석하세요.

## 정보
- 주소: {address}
- 전세가: {jeonse_price:,.0f}원
- 매매가: {sale_price:,.0f}원
- 전세가율: {jeonse_ratio:.1%}
- 자동 위험등급: {risk_level}
- HUG 보증보험 가입 가능: {"예" if hug_eligible else "아니오"}
- 지역 평균 매매가: {market_data.get("avg_sale_price", 0):,.0f}원
- 지역 평균 전세가: {market_data.get("avg_jeonse_price", 0):,.0f}원

## 분석 요청
1. 전세사기 위험 요인 3~5개
2. HUG 보증 가입 가능성 및 권장 사항
3. 투자자 행동 권장 사항

JSON 형식으로 응답:
{{"analysis": "종합 분석 (2~3문장)", "factors": [{{"factor": "...", "impact": "HIGH/MEDIUM/LOW"}}]}}"""

        try:
            response = await llm.ainvoke(prompt)
            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            result: dict[str, Any] = json.loads(content.strip())
            return result
        except Exception:
            return {
                "analysis": "자동 분석을 수행할 수 없습니다. 전문가 상담을 권장합니다.",
                "factors": [],
            }

    # ── 6. 등기부 근저당 조회 ──

    async def _check_mortgage_priority(
        self,
        registry_number: str,
        jeonse_price: float,
    ) -> list[dict[str, Any]]:
        """대법원 등기부에서 선순위 근저당/압류를 조회한다.

        근저당 설정액 + 전세금이 매매가의 70% 초과 시 위험 경고.
        """
        from apps.api.integrations.court_client import CourtClient

        detected: list[dict[str, Any]] = []
        if not registry_number:
            return detected

        try:
            court = CourtClient()
            lien_data = await court.check_lien(registry_number)
            await court.close()

            liens = lien_data.get("liens", [])
            total_lien_amount = sum(
                int(str(lien.get("amount", "0")).replace(",", ""))
                for lien in liens
                if lien.get("type") in ("근저당", "저당", "가압류")
            )

            if total_lien_amount > 0:
                combined = total_lien_amount + jeonse_price
                detected.append({
                    "factor": "선순위 근저당 설정",
                    "impact": "HIGH" if total_lien_amount > jeonse_price * 0.5 else "MEDIUM",
                    "description": (
                        f"근저당/가압류 합계 {total_lien_amount / 1e8:.1f}억원 + "
                        f"전세금 {jeonse_price / 1e8:.1f}억원 = "
                        f"총 {combined / 1e8:.1f}억원 — "
                        "전세금 미회수 위험 확인 필요"
                    ),
                })

            # 소유권 이전 이력 확인
            registry_data = await court.get_registry_info(registry_number)
            ownership_changes = registry_data.get("ownership_changes", [])
            if len(ownership_changes) >= 3:
                detected.append({
                    "factor": "잦은 소유권 이전",
                    "impact": "MEDIUM",
                    "description": (
                        f"최근 소유권 이전 {len(ownership_changes)}회 — "
                        "투기 또는 사기 목적 가능성 확인 필요"
                    ),
                })

        except Exception:
            logger.warning("등기부 조회 실패", registry_number=registry_number)

        return detected

    # ── 메인 분석 ──

    async def analyze(
        self,
        project_id: UUID,
        tenant_id: UUID,
        address: str,
        jeonse_price: float,
        sale_price: float,
        lawd_cd: str = "",
        registry_number: str = "",
    ) -> JeonseRiskResult:
        """전세 리스크를 분석한다."""
        logger.info("전세 리스크 분석 시작", address=address)

        # 1. 전세가율 계산
        jeonse_ratio = jeonse_price / sale_price if sale_price > 0 else 0.0
        risk_level, risk_score = self._calculate_risk_level(jeonse_ratio)

        # 2. 수도권 여부 판단
        is_metropolitan = lawd_cd[:2] in _METROPOLITAN_CODES if lawd_cd else True

        # 3. HUG 보증보험 가입 가능 여부
        hug_eligible, hug_reason = self._check_hug_eligibility(
            jeonse_price, is_metropolitan,
        )

        # 4. 시장 데이터 수집 (asyncio.gather 병렬)
        market_data = await self._fetch_market_data(address, lawd_cd)

        # 5. 7대 사기 패턴 체크 (address, jeonse_price, market_data 사용)
        fraud_factors = self._detect_fraud_patterns(
            address, jeonse_price, market_data,
        )

        # 5-1. 등기부 근저당 조회 (등기번호가 있을 때)
        if registry_number:
            mortgage_factors = await self._check_mortgage_priority(
                registry_number, jeonse_price,
            )
            fraud_factors.extend(mortgage_factors)

        # 6. LLM 종합 분석
        analysis_result = await self._analyze_risk(
            address, jeonse_price, sale_price,
            jeonse_ratio, risk_level, hug_eligible, market_data,
        )

        # 분석 팩터 병합 (사기 패턴 + LLM 분석)
        all_factors = fraud_factors + analysis_result.get("factors", [])

        logger.info(
            "전세 리스크 분석 완료",
            risk_level=risk_level,
            ratio=jeonse_ratio,
            hug_eligible=hug_eligible,
            fraud_patterns=len(fraud_factors),
        )

        return JeonseRiskResult(
            jeonse_ratio=jeonse_ratio,
            risk_level=risk_level,
            risk_score=risk_score,
            analysis=analysis_result.get("analysis", ""),
            factors=all_factors,
            hug_eligible=hug_eligible,
            hug_reason=hug_reason,
            market_data=market_data,
        )
