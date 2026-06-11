"""프로젝트 현금흐름 자동 생성기.

토지매입→설계→시공→분양→정산 각 단계별 월간 현금흐름을 자동 생성한다.
PF대출 구조, 브릿지론, 자기자본 투입 스케줄을 포함한다.
"""

from __future__ import annotations

from typing import Any


class CashflowGenerator:
    """프로젝트 현금흐름 자동 생성기.

    토지매입→설계→시공→분양→정산 각 단계별 월간 현금흐름을 자동 생성한다.
    """

    def generate_monthly_cashflow(
        self,
        land_cost: float,
        construction_cost: float,
        construction_months: int,
        total_revenue: float,
        sale_start_month: int,          # 분양 시작 시점 (시공 개시 기준 월)
        sale_duration_months: int = 6,
        bridge_loan_rate: float = 0.08,   # 브릿지론 연이율
        pf_loan_rate: float = 0.065,      # PF 연이율
        equity_ratio: float = 0.3,        # 자기자본 비율
        design_months: int = 3,           # 설계 기간
        design_cost_ratio: float = 0.03,  # 설계비 비율 (공사비 대비)
    ) -> dict[str, Any]:
        """월별 현금흐름을 생성한다.

        Args:
            land_cost: 토지매입비 (원)
            construction_cost: 총 공사비 (원)
            construction_months: 시공 기간 (월)
            total_revenue: 총 분양수입 (원)
            sale_start_month: 분양 시작 월 (시공 대비, 0-based)
            sale_duration_months: 분양 기간 (월)
            bridge_loan_rate: 브릿지론 연이율
            pf_loan_rate: PF 연이율
            equity_ratio: 자기자본 비율
            design_months: 설계 기간 (월)
            design_cost_ratio: 설계비 비율

        Returns:
            월별 현금흐름 dict (rows, summary, phases)
        """
        rows: list[dict[str, Any]] = []

        # ── 전체 타임라인 설정 ──
        # Phase 0: 토지매입 (Month 0)
        # Phase 1: 설계 (Month 1 ~ design_months)
        # Phase 2: 시공 (Month design_months+1 ~ design_months+construction_months)
        # Phase 3: 분양/입주 (시공 중 sale_start_month부터)
        # Phase 4: 정산 (시공 완료 후 3개월)

        construction_start = design_months + 1
        construction_end = construction_start + construction_months - 1
        sale_abs_start = construction_start + sale_start_month
        sale_abs_end = sale_abs_start + sale_duration_months - 1
        settlement_months = 3
        total_months = construction_end + settlement_months + 1

        design_cost = construction_cost * design_cost_ratio
        total_project_cost = land_cost + design_cost + construction_cost

        # ── 자금 구조 ──
        equity_amount = total_project_cost * equity_ratio
        bridge_loan_amount = land_cost * (1 - equity_ratio)  # 토지비 중 타인자본
        pf_loan_amount = total_project_cost - equity_amount - bridge_loan_amount

        # 시공비 월별 분배 (S-커브 가중)
        monthly_construction = self._s_curve_distribution(
            construction_cost, construction_months
        )

        # 분양수입 월별 분배
        monthly_revenue = self._revenue_distribution(
            total_revenue, sale_duration_months
        )

        cumulative = 0.0
        cumulative_inflow = 0.0
        cumulative_outflow = 0.0
        outstanding_bridge = 0.0
        outstanding_pf = 0.0
        equity_in_total = 0.0    # 자기자본 투입 누계 (이익 계산 시 제외용)
        revenue_received = 0.0   # 분양수입 누계 (잔금 계산 전용 — 대출/자본 유입과 분리)
        interest_total = 0.0     # 이자 누계

        for month in range(total_months):
            inflow = 0.0
            outflow = 0.0
            items: list[str] = []

            # ── Phase 0: 토지매입 (Month 0) ──
            if month == 0:
                outflow += land_cost
                items.append("토지매입비")

                # 자기자본 투입 (토지비 중 equity_ratio)
                equity_for_land = land_cost * equity_ratio
                inflow += equity_for_land
                equity_in_total += equity_for_land
                items.append("자기자본(토지)")

                # 브릿지론 실행
                outstanding_bridge = bridge_loan_amount
                inflow += bridge_loan_amount
                items.append("브릿지론 실행")

            # ── Phase 1: 설계 (Month 1 ~ design_months) ──
            if 1 <= month <= design_months:
                monthly_design = design_cost / design_months
                outflow += monthly_design
                items.append("설계비")

            # ── 브릿지론 → PF 전환 (시공 시작 시) ──
            if month == construction_start:
                # 브릿지론 상환
                outflow += outstanding_bridge
                items.append("브릿지론 상환")

                # PF 실행
                outstanding_pf = pf_loan_amount + outstanding_bridge
                inflow += outstanding_pf
                items.append("PF대출 실행")

                # 자기자본 추가 투입
                equity_remaining = equity_amount - land_cost * equity_ratio
                if equity_remaining > 0:
                    inflow += equity_remaining
                    equity_in_total += equity_remaining
                    items.append("자기자본(시공)")

                outstanding_bridge = 0.0

            # ── Phase 2: 시공 ──
            if construction_start <= month <= construction_end:
                ci = month - construction_start
                if ci < len(monthly_construction):
                    outflow += monthly_construction[ci]
                    items.append("공사비")

            # ── 금융비용 (매월) ──
            interest = 0.0
            if outstanding_bridge > 0:
                interest += outstanding_bridge * (bridge_loan_rate / 12)
                items.append("브릿지론 이자")
            if outstanding_pf > 0:
                interest += outstanding_pf * (pf_loan_rate / 12)
                items.append("PF이자")
            outflow += interest
            interest_total += interest

            # ── Phase 3: 분양수입 (정산월 전까지만 — 잔금에서 일괄 정산) ──
            if sale_abs_start <= month <= min(sale_abs_end, construction_end):
                ri = month - sale_abs_start
                if ri < len(monthly_revenue):
                    rev = monthly_revenue[ri]
                    inflow += rev
                    revenue_received += rev
                    items.append("분양수입")

                    # 분양수입으로 PF 일부 상환
                    pf_repay = rev * 0.5  # 수입의 50% PF 상환
                    pf_repay = min(pf_repay, outstanding_pf)
                    if pf_repay > 0:
                        outflow += pf_repay
                        outstanding_pf -= pf_repay
                        items.append("PF 중도상환")

            # ── Phase 4: 정산 ──
            if month == construction_end + 1:
                # 잔여 분양대금 수령 — 분양수입 누계만 기준(대출·자본 유입과 분리)
                remaining_rev = total_revenue - revenue_received
                if remaining_rev > 0:
                    inflow += remaining_rev
                    revenue_received += remaining_rev
                    items.append("잔금 수령")

            if month == construction_end + 2:
                # PF 잔액 상환
                if outstanding_pf > 0:
                    outflow += outstanding_pf
                    items.append("PF 잔액 상환")
                    outstanding_pf = 0

            net = inflow - outflow
            cumulative += net
            cumulative_inflow += inflow
            cumulative_outflow += outflow

            rows.append({
                "month": month,
                "phase": self._get_phase_name(
                    month, construction_start, construction_end, sale_abs_start, sale_abs_end
                ),
                "items": ", ".join(items) if items else "-",
                "inflow": round(inflow),
                "outflow": round(outflow),
                "net": round(net),
                "cumulative": round(cumulative),
                "outstanding_bridge": round(outstanding_bridge),
                "outstanding_pf": round(outstanding_pf),
            })

        # ── 요약 ──
        # 자기자본 투입은 자금조달이지 수익이 아님 — 유입 누계에서 제외해야 실제 이익.
        # (대출은 실행=상환 상쇄, equity는 반환 행이 없으므로 빼지 않으면 이익이 equity만큼 과대)
        net_profit = cumulative_inflow - cumulative_outflow - equity_in_total
        # 이익률 분모: 실제 사업비(토지+설계+공사+이자) — 대출 상환액이 섞인 outflow 누계가 아님
        real_project_cost = land_cost + design_cost + construction_cost + interest_total

        # 언레버리지(금융 제외) 프로젝트 IRR — 토지·설계·공사 지출 vs 분양수입만으로 산정.
        # (rows의 net은 대출 드로/상환·자기자본 포함이라 IRR 폭증 → 의미있는 사업 IRR은 무차입 기준)
        unlevered = [0.0] * total_months
        unlevered[0] -= land_cost
        for m in range(1, design_months + 1):
            if m < total_months:
                unlevered[m] -= design_cost / max(1, design_months)
        for ci in range(len(monthly_construction)):
            m = construction_start + ci
            if m < total_months:
                unlevered[m] -= monthly_construction[ci]
        # 수입 분배는 rows와 동일하게: 정산월 전까지 월별, 잔여분은 정산월 일괄
        scheduled_rev = 0.0
        for ri in range(len(monthly_revenue)):
            m = sale_abs_start + ri
            if m < total_months and m <= construction_end:
                unlevered[m] += monthly_revenue[ri]
                scheduled_rev += monthly_revenue[ri]
        settle_m = construction_end + 1
        if settle_m < total_months and total_revenue > scheduled_rev:
            unlevered[settle_m] += total_revenue - scheduled_rev
        irr = self._irr_from_netflows(unlevered)

        summary = {
            "total_months": total_months,
            "total_inflow": round(cumulative_inflow),
            "total_outflow": round(cumulative_outflow),
            "equity_in_total": round(equity_in_total),
            "interest_total": round(interest_total),
            "net_profit": round(net_profit),
            "profit_rate_pct": round(net_profit / real_project_cost * 100, 2) if real_project_cost else 0,
            "peak_negative_cashflow": round(min(r["cumulative"] for r in rows)),
            "equity_amount": round(equity_amount),
            "bridge_loan_amount": round(bridge_loan_amount),
            "pf_loan_amount": round(pf_loan_amount),
            "irr_annual_pct": irr,
        }

        phases = {
            "land_acquisition": {"month": 0, "cost": round(land_cost)},
            "design": {"start": 1, "end": design_months, "cost": round(design_cost)},
            "construction": {
                "start": construction_start,
                "end": construction_end,
                "cost": round(construction_cost),
            },
            "sale": {
                "start": sale_abs_start,
                "end": sale_abs_end,
                "revenue": round(total_revenue),
            },
            "settlement": {
                "start": construction_end + 1,
                "end": construction_end + settlement_months,
            },
        }

        return {
            "rows": rows,
            "summary": summary,
            "phases": phases,
        }

    def _s_curve_distribution(self, total: float, months: int) -> list[float]:
        """S-커브 기반 공사비 월별 분배.

        초기(동원) → 중간(최대) → 후기(마무리) 패턴.
        """
        if months <= 0:
            return []

        weights: list[float] = []
        for i in range(months):
            # S-커브: sin 기반
            import math
            t = (i + 0.5) / months  # 0~1 범위 중앙
            w = math.sin(t * math.pi)  # 0→1→0 패턴
            w = max(w, 0.3)  # 최소 30% 가중
            weights.append(w)

        total_w = sum(weights)
        return [total * (w / total_w) for w in weights]

    def _revenue_distribution(self, total: float, months: int) -> list[float]:
        """분양수입 월별 분배 (초기 집중형)."""
        if months <= 0:
            return []

        # 초기 60%, 중기 25%, 후기 15% 분배
        weights = []
        for i in range(months):
            if i < months * 0.3:
                weights.append(2.0)
            elif i < months * 0.7:
                weights.append(1.0)
            else:
                weights.append(0.6)

        total_w = sum(weights)
        return [total * (w / total_w) for w in weights]

    def _get_phase_name(
        self,
        month: int,
        const_start: int,
        const_end: int,
        sale_start: int,
        sale_end: int,
    ) -> str:
        """월별 단계 이름을 반환한다."""
        if month == 0:
            return "토지매입"
        if month < const_start:
            return "설계"
        if month <= const_end:
            if sale_start <= month <= sale_end:
                return "시공+분양"
            return "시공"
        return "정산"

    def _irr_from_netflows(self, cashflows: list[float]) -> float | None:
        """월별 순현금흐름 리스트에서 연환산 IRR을 이분법으로 계산한다(순수 파이썬)."""
        try:
            # 부호 변화(유출→유입)가 없으면 IRR 정의 불가
            if not any(c < 0 for c in cashflows) or not any(c > 0 for c in cashflows):
                return None

            def npv_at(rate: float) -> float:
                return sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))

            # npv(0)=순현금합. 부호 기준으로 0에서 bracket을 키워 주근(主根)만 탐색
            # (극단 음수 rate에서 말기 현금흐름이 발산해 가짜 근을 잡는 문제 회피).
            base = npv_at(0.0)
            if abs(base) < 1.0:
                return 0.0
            if base > 0:  # IRR>0: 0에서 위로
                lo, hi = 0.0, 0.01
                ok = False
                for _ in range(80):
                    if npv_at(hi) < 0:
                        ok = True
                        break
                    hi = min(hi * 1.5, 10.0)
                if not ok:
                    return None  # 월 IRR>1000% 수준 — 비정상
            else:  # IRR<0: 0에서 아래로
                lo, hi = -0.01, 0.0
                ok = False
                for _ in range(80):
                    if npv_at(lo) > 0:
                        ok = True
                        break
                    lo = max(lo * 1.5, -0.99)
                if not ok:
                    return None
            # lo: npv>0, hi: npv<0 → 이분법
            for _ in range(200):
                mid = (lo + hi) / 2
                if npv_at(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            monthly_irr = (lo + hi) / 2
            annual_irr = (1 + monthly_irr) ** 12 - 1
            return round(annual_irr * 100, 2)
        except Exception:  # noqa: BLE001
            return None
