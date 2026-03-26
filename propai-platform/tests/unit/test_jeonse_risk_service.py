"""전세 리스크 분석 서비스 품질 게이트 테스트.

Step 1.2 검증:
1. _fetch_market_data가 API 통신 실패 시 Fallback(전세가율 65% 추정치) 반환
2. _detect_fraud_patterns에 7대 사기 패턴이 최소 3개 이상 분기문으로 체크됨
3. HUG 보증보험 수도권/지방 기준 검증
"""

from apps.api.services.jeonse_risk_service import JeonseRiskService


class TestMarketDataFallback:
    """_fetch_market_data API 실패 시 Fallback 검증."""

    def test_fallback_returns_65_pct_estimate(self) -> None:
        """Fallback은 전세가율 65% 추정치를 포함한다."""
        result = JeonseRiskService._market_data_fallback("202603", "11680")
        assert result["estimated_jeonse_ratio"] == 0.65
        assert result["fallback"] is True
        assert result["avg_sale_price"] == 0
        assert result["avg_jeonse_price"] == 0
        assert result["lawd_cd"] == "11680"

    def test_fallback_without_params(self) -> None:
        """파라미터 없이 호출해도 안전하다."""
        result = JeonseRiskService._market_data_fallback()
        assert result["estimated_jeonse_ratio"] == 0.65
        assert result["fallback"] is True


class TestFraudPatternDetection:
    """7대 전세 사기 패턴 탐지 검증.

    분기 조건이 최소 3개 이상 존재하며,
    각각 다른 시나리오에서 정확히 탐지되는지 확인한다.
    """

    def _high_risk_market_data(self) -> dict:
        return {
            "avg_sale_price": 500_000_000,
            "avg_jeonse_price": 250_000_000,
            "trade_count": 10,
            "rent_count": 5,
        }

    def test_gap_investment_pattern(self) -> None:
        """패턴 1: 갭투자 위험 (전세가율 80% 이상)."""
        market = self._high_risk_market_data()
        # 전세 4억 / 매매 5억 = 80%
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 강남구 테스트아파트", 400_000_000, market,
        )
        gap_factors = [f for f in result if "갭투자" in f["factor"]]
        assert len(gap_factors) >= 1
        assert gap_factors[0]["impact"] == "HIGH"

    def test_deep_gap_pattern(self) -> None:
        """패턴 2: 깡통전세 위험 (전세가율 90% 이상)."""
        market = self._high_risk_market_data()
        # 전세 4.6억 / 매매 5억 = 92%
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 강남구 테스트", 460_000_000, market,
        )
        deep_factors = [f for f in result if "깡통" in f["factor"]]
        assert len(deep_factors) >= 1
        assert deep_factors[0]["impact"] == "CRITICAL"

    def test_high_deposit_outlier_pattern(self) -> None:
        """패턴 3: 고액 보증금 — 시장 평균 1.5배 초과."""
        market = self._high_risk_market_data()
        # 전세가 4억 > 평균 전세 2.5억 × 1.5 = 3.75억
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 강남구", 400_000_000, market,
        )
        outlier = [f for f in result if "고액" in f["factor"]]
        assert len(outlier) >= 1

    def test_low_trade_count_pattern(self) -> None:
        """패턴 4: 거래 희소성 — 거래 3건 미만."""
        market = {
            "avg_sale_price": 300_000_000,
            "avg_jeonse_price": 150_000_000,
            "trade_count": 1,
            "rent_count": 0,
        }
        result = JeonseRiskService._detect_fraud_patterns(
            "경기 파주", 150_000_000, market,
        )
        scarcity = [f for f in result if "희소" in f["factor"]]
        assert len(scarcity) >= 1

    def test_new_villa_pattern(self) -> None:
        """패턴 5: 신축 빌라 + 높은 전세가율."""
        market = self._high_risk_market_data()
        # 주소에 '빌라' 포함 + 전세가율 85%+
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 관악구 신축빌라 101호", 430_000_000, market,
        )
        villa = [f for f in result if "빌라" in f["factor"]]
        assert len(villa) >= 1

    def test_always_warns_registry_and_guarantee(self) -> None:
        """패턴 6,7: 등기부 확인 + 보증 미가입은 항상 경고."""
        market = self._high_risk_market_data()
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 강남구", 200_000_000, market,
        )
        # 등기부 + 보증 경고는 항상 포함
        factor_names = [f["factor"] for f in result]
        assert any("등기부" in name for name in factor_names)
        assert any("보증" in name for name in factor_names)

    def test_safe_address_still_has_warnings(self) -> None:
        """안전한 전세가율이라도 등기부/보증 경고는 포함된다."""
        market = {
            "avg_sale_price": 1_000_000_000,
            "avg_jeonse_price": 400_000_000,
            "trade_count": 50,
            "rent_count": 30,
        }
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 강남구 안전아파트", 300_000_000, market,
        )
        # 최소 2개 (등기부 + 보증 항상 경고)
        assert len(result) >= 2

    def test_at_least_3_branch_conditions_checked(self) -> None:
        """7대 패턴 중 최소 3개 이상 분기 조건이 코드에 존재함을 증명."""
        # 높은 위험 시나리오에서 3개 이상 탐지되어야 함
        market = {
            "avg_sale_price": 300_000_000,
            "avg_jeonse_price": 100_000_000,
            "trade_count": 1,
        }
        # 전세가 2.7억 / 매매 3억 = 90%
        result = JeonseRiskService._detect_fraud_patterns(
            "서울 관악구 신축빌라", 270_000_000, market,
        )
        # 갭투자 + 깡통 + 고액 + 희소 + 빌라 + 등기부 + 보증 = 7개
        assert len(result) >= 3


class TestHUGEligibility:
    """HUG 전세보증보험 가입 가능 여부 검증."""

    def test_metropolitan_under_7_billion(self) -> None:
        """수도권 7억 이하 → 가입 가능."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            500_000_000, is_metropolitan=True,
        )
        assert eligible is True
        assert "가능" in reason

    def test_metropolitan_over_7_billion(self) -> None:
        """수도권 7억 초과 → 가입 불가."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            800_000_000, is_metropolitan=True,
        )
        assert eligible is False
        assert "불가" in reason

    def test_local_under_5_billion(self) -> None:
        """지방 5억 이하 → 가입 가능."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            400_000_000, is_metropolitan=False,
        )
        assert eligible is True

    def test_local_over_5_billion(self) -> None:
        """지방 5억 초과 → 가입 불가."""
        eligible, reason = JeonseRiskService._check_hug_eligibility(
            600_000_000, is_metropolitan=False,
        )
        assert eligible is False
        assert "불가" in reason


class TestRiskLevel:
    """전세가율 기반 위험 등급 검증."""

    def test_safe(self) -> None:
        level, score = JeonseRiskService._calculate_risk_level(0.50)
        assert level == "SAFE"
        assert score < 0.20

    def test_low(self) -> None:
        level, _ = JeonseRiskService._calculate_risk_level(0.65)
        assert level == "LOW"

    def test_medium(self) -> None:
        level, _ = JeonseRiskService._calculate_risk_level(0.75)
        assert level == "MEDIUM"

    def test_high(self) -> None:
        level, _ = JeonseRiskService._calculate_risk_level(0.85)
        assert level == "HIGH"

    def test_critical(self) -> None:
        level, score = JeonseRiskService._calculate_risk_level(0.95)
        assert level == "CRITICAL"
        assert score >= 0.90
