"""법정요율 관리 서비스 — 현재 요율 조회, 이력, 자동 갱신."""

from __future__ import annotations

from typing import Any

from app.services.cost.origin_cost_calculator import RATES_2026

# 국민연금 단계 인상 일정 (2026~2033, 매년 +0.5%p → 사업주 부담분)
PENSION_SCHEDULE: dict[int, float] = {
    2026: 0.04750,
    2027: 0.05000,
    2028: 0.05250,
    2029: 0.05500,
    2030: 0.05750,
    2031: 0.06000,
    2032: 0.06250,
    2033: 0.06500,
}


class LegalRateService:
    """법정요율 관리 서비스."""

    def get_current_rates(self) -> dict[str, Any]:
        """2026년 현재 법정요율 12개를 반환한다."""
        rates = RATES_2026.copy()
        return {
            "year": 2026,
            "rates": rates,
            "pension_note": (
                "국민연금 요율은 2026년 4.75%(사업주), "
                "2033년까지 매년 0.5%p 인상 예정"
            ),
            "pension_schedule": PENSION_SCHEDULE,
        }

    def get_rate_history(self, rate_code: str | None = None) -> list[dict[str, Any]]:
        """요율 이력을 반환한다 (DB 미연결 시 2026 고정 데이터).

        rate_code가 None이면 전체, 아니면 해당 요율만 반환.
        """
        history: list[dict[str, Any]] = []
        for code, value in RATES_2026.items():
            if rate_code and code != rate_code:
                continue
            history.append({
                "rate_category": code,
                "rate_value": value,
                "effective_from": "2026-01-01",
                "effective_to": None,
                "gov_notice_no": f"고시 제2025-{hash(code) % 1000:03d}호",
                "source": "국토교통부/고용노동부/국민건강보험공단",
            })
        return history

    def refresh_rates(self) -> dict[str, Any]:
        """외부 API 요율 갱신 (스텁 — 실제 API 연동 대기).

        Returns:
            갱신 결과 dict
        """
        # TODO: CODIL API / 공공데이터포털 연동
        current = self.get_current_rates()
        return {
            "status": "no_changes",
            "checked_at": "2026-03-30T00:00:00",
            "current_rates": current["rates"],
            "changes_detected": [],
            "message": "현재 요율 변동 없음. 다음 정기 점검: 2026-07-01",
        }

    def get_pension_for_year(self, year: int) -> float:
        """특정 연도 국민연금 사업주 부담률을 반환한다."""
        if year in PENSION_SCHEDULE:
            return PENSION_SCHEDULE[year]
        if year < 2026:
            return 0.04500  # 2025 이전
        return 0.06500  # 2033 이후 최종
