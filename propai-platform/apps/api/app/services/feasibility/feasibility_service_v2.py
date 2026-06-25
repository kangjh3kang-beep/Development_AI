"""FeasibilityServiceV2 — 수지분석 고도화 통합 서비스.

전체 파이프라인 오케스트레이션:
입력 → 모듈 선택 → 계산 → 등급 판정 → 결과 반환.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.feasibility.modules.base_module import ModuleInput, ModuleOutput
from app.services.feasibility.modules.module_assembler import get_module, list_modules, ALL_MODULE_CODES
from app.services.feasibility.aggregation_engine import compare_scenarios

logger = logging.getLogger(__name__)


class FeasibilityServiceV2:
    """수지분석 고도화 v2 통합 서비스."""

    def calculate(self, inp: ModuleInput) -> ModuleOutput:
        """단일 개발유형 수지분석 실행.

        Args:
            inp: ModuleInput (development_type 필수)

        Returns:
            ModuleOutput
        """
        module = get_module(inp.development_type)

        errors = module.validate_input(inp)
        if errors:
            raise ValueError(f"입력 검증 실패: {', '.join(errors)}")

        return module.calculate(inp)

    def calculate_multi(self, inputs: list[ModuleInput]) -> dict[str, Any]:
        """복수 개발유형 비교 분석.

        Args:
            inputs: 여러 ModuleInput 리스트

        Returns:
            {'results': [...ModuleOutput...], 'comparison': {...}}
        """
        results = []
        for inp in inputs:
            output = self.calculate(inp)
            results.append(output)

        # 비교 분석용 dict 변환
        scenarios = []
        for r in results:
            scenarios.append({
                "name": f"{r.module_name} ({r.development_type})",
                "profit_rate_pct": r.profit_rate_pct,
                "roi_pct": r.roi_pct,
                "grade": r.grade,
                "net_profit_won": r.net_profit_won,
                "total_revenue_won": r.total_revenue_won,
                "total_cost_won": r.total_cost_won,
            })

        comparison = compare_scenarios(scenarios)

        return {
            "results": results,
            "comparison": comparison,
        }

    def list_available_modules(self) -> list[dict[str, str]]:
        """사용 가능한 개발유형 모듈 목록."""
        return list_modules()

    def get_module_info(self, development_type: str) -> dict[str, str]:
        """특정 모듈 정보."""
        module = get_module(development_type)
        return {
            "code": module.code,
            "name": module.name,
        }

    # ------------------------------------------------------------------
    # Auto-Recommend Top 3
    # ------------------------------------------------------------------

    async def auto_recommend_top3(
        self,
        address: str,
        land_area_sqm: float | None = None,
        region: str = "서울",
        equity_won: int = 10_000_000_000,  # 자기자본 100억 기본
        use_llm: bool = True,
        with_senior: bool = True,
    ) -> dict:
        """부지 주소로부터 최적 사업모델 Top 3 자동 추천."""

        # Step 1: 용도지역 자동 감지
        from ..zoning.auto_zoning_service import AutoZoningService
        zoning_service = AutoZoningService()
        zoning = await zoning_service.analyze_by_address(address)

        zone_type = zoning.get("zone_type", "")
        zone_limits = zoning.get("zone_limits") or {}
        site_area = land_area_sqm or zoning.get("land_area_sqm") or 1000
        special_districts = zoning.get("special_districts") or []
        land_category = zoning.get("land_category") or ""

        # Step 2: 특이부지 게이트 — 학교·도로·GB·농지·산지·맹지 등 비일상 토지는 Top3 산정 정책 분기.
        # ★게이트 정책 SSOT(special_parcel.gate_decision)로 일원화:
        #   BLOCK     → 후보 미생성·정직고지(가짜 ROI 금지).
        #   TENTATIVE → 도로(PRECONDITION·resolvable CONDITIONAL)·학교(PRECONDITION)·맹지 등은 후보를
        #               '산출하되' 선행절차 전제 '잠정치(확정 아님)'로 강등하고 확신 % 표시를 억제한다.
        #               (기존 결함: BLOCKED/NO만 차단해 도로 PRECONDITION이 통과→타운하우스88% 할루시네이션.)
        #   PASS      → 통상 산출.
        from ..zoning.special_parcel import detect_special_parcel, gate_decision, tentative_marker
        special = detect_special_parcel({
            "zone_type": zone_type,
            "land_category": land_category,
            "special_districts": special_districts,
            "road_contact": None,   # 추천 입력엔 접도 데이터 없음 → 맹지 오탐 방지(None=미판정)
            "road_width_m": None,
        })
        gate = gate_decision(
            special.get("developability") if special else None,
            special.get("resolvable") if special else None,
        )
        if special and gate == "BLOCK":
            # 후보생성 중단 — 개발규모/수지 미산정(정직). 가짜 ROI 금지.
            return {
                "address": address,
                "zone_type": zone_type,
                "zone_limits": zone_limits,
                "land_area_sqm": site_area,
                "recommendations": [],
                "all_results": [],
                "special_parcel": special,
                "honest_disclosure": special.get("honest_disclosure")
                or "통상 절차로 해결 불가능한 제약이 포함되어 개발규모를 산정하지 않습니다.",
                "land_price_reliable": False,
                "ai_interpretation": None,
            }

        # Step 2.1: 인허가 가능 유형 필터
        from .permit_validator import (
            get_permitted_types,
            check_permit_feasibility,
            DEVELOPMENT_TYPE_NAMES,
        )
        permitted_types = get_permitted_types(zone_type)

        if not permitted_types:
            return {
                "error": f"'{zone_type}' 용도지역에서 개발 가능한 사업모델이 없습니다.",
                "recommendations": [],
            }

        # Step 2.5: 실효 용적률 산정 — 법정범위→조례→계획상한→인센티브 계층(SSOT 공용 모듈).
        # ★결함A 근본수정: 기존 zone_limits.get("ordinance_far_pct")는 AutoZoningService가 절대
        #   채우지 않는 키라 항상 법정 폴백(max_far_pct)으로 떨어졌다. 정답 패턴(scenario_simulator/
        #   permits 검증)=OrdinanceService 조회 후 calc_effective_far에 주입해 실효치를 산출한다.
        #   ★local_ordinance:{} 빈값 금지 — 빈값이면 calc_effective_far가 법정값을 반환하므로
        #     반드시 get_ordinance_limits 결과(또는 조회 실패 시 법정 폴백)를 전달한다.
        from ..land_intelligence.ordinance_service import OrdinanceService
        from ..land_intelligence.far_tier_service import calc_effective_far
        try:
            ordinance = await OrdinanceService().get_ordinance_limits(address, zone_type)
        except Exception:  # noqa: BLE001 — 조회 실패 시 법정 폴백
            ordinance = None
        legal_max_far = zone_limits.get("max_far_pct", 250)  # 법정상한(라벨 보관)
        max_far = legal_max_far
        try:
            eff = calc_effective_far(
                {
                    "zone_limits": zone_limits,
                    "special_districts": special_districts,
                    "local_ordinance": ordinance or {},
                },
                zone_type,
                site_area,
            )
            eff_far = eff.get("effective_far_pct")
            if eff_far is not None and eff_far > 0:
                max_far = float(eff_far)  # 실효 용적률을 FAR→GFA→세대수·매출·ROI 전파에 사용
        except Exception:  # noqa: BLE001 — 산정 실패 시 법정 폴백 유지
            pass
        # 주: auto_recommend_top3는 FAR→GFA→세대수→매출→ROI만 사용한다(BCR은 footprint용이라 이 Top3
        #   산정 경로엔 미사용). 기존 max_bcr는 어떤 하류도 읽지 않던 사장 변수라 제거했다 — BCR 실효화는
        #   이 함수에선 불필요(리뷰 HIGH는 'BCR이 ROI에 영향' 가정이었으나 실제로는 미사용·무영향).

        # 토지비 신뢰성 — 공시지가 미확보 시 1.5M 묵시폴백이 들어가므로 절대 수익성(ROI·순이익)은
        #   '참고용'임을 정직 표기한다(랭킹은 profit_rate 상대비교라 유지). 가짜 확정값 노출 방지.
        official_price = zoning.get("official_price_per_sqm")
        land_price_reliable = bool(official_price and official_price > 0)

        results: list[dict[str, Any]] = []
        for dev_type in permitted_types:
            try:
                # 입력 생성은 공용 헬퍼(build_module_input)로 일원화 — 추천/통합추천이
                # 동일한 FAR→GFA→세대수→ModuleInput 변환을 쓰도록(로직 복제 방지).
                inp = self.build_module_input(
                    dev_type=dev_type,
                    site_area_sqm=site_area,
                    max_far_pct=max_far,
                    region=region,
                    address=address,
                    equity_won=equity_won,
                    official_price_per_sqm=zoning.get("official_price_per_sqm"),
                )

                output = self.calculate(inp)
                permit = check_permit_feasibility(dev_type, zone_type)

                # 종합 점수: 순이익(50%) + 수익률(30%) + 인허가용이성(20%)
                # 순이익 기준: 100억 이상이면 만점
                profit_amount_score = min(100, max(0, output.net_profit_won / 1e8))  # 100억→100점
                profit_rate_score = min(100, max(0, output.profit_rate_pct * 2))     # 50%→100점
                permit_score = (6 - permit["permit_complexity"]) * 20                # 1→100, 5→20
                composite = profit_amount_score * 0.5 + profit_rate_score * 0.3 + permit_score * 0.2

                results.append({
                    "development_type": dev_type,
                    "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                    "feasibility": {
                        "total_revenue_won": output.total_revenue_won,
                        "total_cost_won": output.total_cost_won,
                        "net_profit_won": output.net_profit_won,
                        "profit_rate_pct": output.profit_rate_pct,
                        "roi_pct": output.roi_pct,            # 사업수익률=순이익/총사업비(경로 간 비교 표준)
                        "roe_pct": output.roe_pct,            # 자기자본수익률(레버리지, 자기자본 제공 시만)
                        "npv_won": output.npv_won,
                        "grade": output.grade,
                    },
                    "permit": permit,
                    "unit_summary": {
                        "total_gfa_sqm": round(inp.total_gfa_sqm, 1),
                        "total_households": inp.total_households,
                        "avg_area_pyeong": round(inp.avg_area_pyeong, 1),
                    },
                    "composite_score": round(composite, 1),
                    "input_used": inp,  # For user refinement
                })
            except Exception as e:
                logger.warning(f"{dev_type} 계산 실패: {e}")

        # Step 3.5: 잠정 강등 — 특이부지가 TENTATIVE면 각 후보를 '선행절차 전제 잠정치(확정 아님)'로
        #   표시하고, 확신 % 노출을 억제한다(프론트가 확신 % 대신 '잠정' 배지로 렌더하도록 신호).
        #   ★할루시네이션 차단 핵심: 도로 단독 PRECONDITION에서 타운하우스88%가 '확정치'처럼 보이던 결함을
        #     데이터 레벨에서 잠정으로 강등(국소 UI 패치가 아니라 응답 계약으로).
        is_tentative = bool(special) and gate == "TENTATIVE"
        if is_tentative:
            t_reason = tentative_marker(
                special.get("developability"), special.get("resolvable"), special.get("severity_label"),
            )
            for r in results:
                r["tentative"] = True
                r["tentative_reason"] = t_reason

        # Step 4: 정렬 + Top 3
        results.sort(key=lambda r: r["composite_score"], reverse=True)
        top3 = results[:3]

        result = {
            "address": address,
            "zone_type": zone_type,
            "zone_limits": zone_limits,
            "land_area_sqm": site_area,
            "effective_far_pct": round(max_far, 1),   # FAR→GFA 산정에 실제 사용한 실효 용적률
            "legal_max_far_pct": legal_max_far,        # 법정상한(라벨용 — 실효와 다를 수 있음)
            "total_types_analyzed": len(results),
            "permitted_types": len(permitted_types),
            "recommendations": top3,
            "all_results": results,  # Full ranking for reference
            # 토지비 신뢰성 — False면 공시지가 미확보로 절대 수익성(ROI·순이익)은 참고용(랭킹은 상대비교 유효).
            "land_price_reliable": land_price_reliable,
            # 시나리오 상태 — "tentative"면 전 후보가 선행절차 전제 잠정치(확정 아님). 프론트 렌더 분기 신호.
            "scenario_status": "tentative" if is_tentative else "actual",
        }
        # 특이부지(CONDITIONAL/PRECONDITION/CAUTION)는 생성하되 경고 동반 — 정직 고지.
        if special:
            result["special_parcel"] = special
            result["honest_disclosure"] = special.get("honest_disclosure")

        # ── 시니어 금융전문가 자문 모세혈관 배선(P1·ROI게이트) ──
        # Top 후보의 자기자본비율(자기자본/총사업비)을 시니어 금융 평가기로 검증해
        # 비현실 수익구조(과거 ROI566% 사건류)에 정직 경고를 첨부한다.
        # ★계산값을 절대 덮어쓰지 않는다 — 자문·경고만 result에 부착(자문은 보조).
        # ★무회귀: with_senior=True 기본이되 attach_senior_consultation은 절대 raise 안 함.
        if with_senior and top3:
            try:
                from app.services.senior_agents.consultation_hook import (
                    attach_senior_consultation,
                )

                _top = top3[0]
                _feas = _top.get("feasibility") if isinstance(_top, dict) else None
                _sr_inputs: dict = {}
                if isinstance(_feas, dict):
                    _tc = _feas.get("total_cost_won")
                    if isinstance(_tc, (int, float)) and _tc > 0:
                        _sr_inputs["total_cost"] = float(_tc)
                        if equity_won and equity_won > 0:
                            _sr_inputs["equity"] = float(equity_won)
                if _sr_inputs:
                    result["senior_consultation"] = attach_senior_consultation(
                        "finance", _sr_inputs,
                    )
            except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 수지 분석 무손상
                pass

        # Step 5: AI 해석 생성 — 명시실행(use_llm=False면 규칙기반 결과만, LLM 생략)
        if use_llm:
            try:
                from app.services.ai.feasibility_interpreter import FeasibilityInterpreter
                interpreter = FeasibilityInterpreter()
                ai = await interpreter.generate_interpretation(result)
                result["ai_interpretation"] = ai
            except Exception:
                logger.warning("수지분석 AI 해석 생성 실패 — 폴백 처리")
                result["ai_interpretation"] = None
        else:
            result["ai_interpretation"] = None

        return result

    # ------------------------------------------------------------------
    # 공용 입력 빌더 (auto_recommend_top3 + 통합추천 공유)
    # ------------------------------------------------------------------

    def build_module_input(
        self,
        dev_type: str,
        site_area_sqm: float,
        max_far_pct: float,
        region: str,
        address: str = "",
        equity_won: int | None = None,
        official_price_per_sqm: float | None = None,
    ) -> ModuleInput:
        """용도지역 한도 기반으로 개발유형별 ModuleInput을 자동 생성한다.

        FAR→GFA→세대수→ModuleInput 변환을 한 곳에 모아, 추천(auto_recommend_top3)과
        다필지 통합추천이 동일 로직을 쓰도록 한다(로직 복제 방지·결과 정합).

        ★calculate/UnitMix 입력은 target_far가 아니라 total_gfa_sqm 임에 유의:
          total_gfa = 부지면적 × 실효용적률(%) ÷ 100. 세대수는 전용률 역산.

        Args:
            dev_type: 개발유형 코드(M01~M15).
            site_area_sqm: 부지(통합) 면적(㎡).
            max_far_pct: 적용 용적률 상한(%). 개발유형 일반치와 min으로 클램프.
            region: 지역(분양가 테이블 키).
            address: 주소(지역 분양가 보정용).
            equity_won: 자기자본(원). None이면 ModuleInput 기본(0).
            official_price_per_sqm: 공시지가(원/㎡). 미확보 시 1.5M 묵시폴백(절대수익성은 참고용).
        """
        # 적용 용적률 = 용도지역 상한과 개발유형 일반치 중 낮은 값(과대 산정 방지).
        effective_far = min(max_far_pct, self._get_type_typical_far(dev_type))
        total_gfa = site_area_sqm * effective_far / 100
        # 세대수 = 전용 가용면적(연면적×전용률) ÷ 전용면적
        # (전용률 미반영 시 공용면적 무시로 세대수 ~30% 과대 → 세대당 부담금·주차 왜곡)
        eff_ratio = self._get_type_efficiency_ratio(dev_type)
        avg_unit_area = self._get_type_avg_unit_area(dev_type)
        total_hh = max(1, int(total_gfa * eff_ratio / avg_unit_area))

        return ModuleInput(
            development_type=dev_type,
            total_land_area_sqm=site_area_sqm,
            total_gfa_sqm=total_gfa,
            total_households=total_hh,
            avg_sale_price_per_pyeong=self._get_regional_price(dev_type, region, address),
            # 분양가(원/평)는 공급면적 기준 시세 → 면적도 공급평수(전용/전용률)로 통일
            avg_area_pyeong=(avg_unit_area / eff_ratio) / 3.305785,
            sale_ratio=0.95 if dev_type not in ("M14", "M15") else 0.0,
            official_price_per_sqm=official_price_per_sqm or 1_500_000,
            price_multiplier=1.1,
            building_type=self._get_building_type(dev_type),
            sido_name=region,
            sigungu_name="",
            project_months=self._get_type_project_months(dev_type),
            discount_rate=0.08,
            equity_won=equity_won or 0,
        )

    # ------------------------------------------------------------------
    # Helper methods for auto-generation
    # ------------------------------------------------------------------

    def _get_type_typical_far(self, dev_type: str) -> float:
        """개발유형별 일반적 용적률."""
        typical = {
            "M01": 250, "M02": 300, "M03": 400, "M04": 250, "M05": 200,
            "M06": 250, "M07": 400, "M08": 500, "M09": 400, "M10": 100,
            "M11": 80, "M12": 150, "M13": 300, "M14": 250, "M15": 300,
        }
        return typical.get(dev_type, 250)

    def _get_type_avg_unit_area(self, dev_type: str) -> float:
        """개발유형별 평균 세대면적 (전용 m2)."""
        areas = {
            "M01": 84, "M02": 84, "M03": 59, "M04": 84, "M05": 49,
            "M06": 84, "M07": 102, "M08": 39, "M09": 50, "M10": 165,
            "M11": 200, "M12": 130, "M13": 30, "M14": 59, "M15": 84,
        }
        return areas.get(dev_type, 84)

    def _get_type_efficiency_ratio(self, dev_type: str) -> float:
        """개발유형별 전용률 (전용면적/공급면적).

        공동주택(아파트·오피스텔)은 코어·복도 등 공용면적으로 0.7~0.8,
        단독·전원·타운하우스는 공용면적이 작아 0.9 수준.
        """
        low_rise = {"M10", "M11", "M12"}  # 단독·전원·타운하우스
        if dev_type in low_rise:
            return 0.90
        if dev_type == "M08":  # 오피스텔 — 전용률 낮음
            return 0.55
        return 0.75

    def _get_regional_price(self, dev_type: str, region: str, address: str = "") -> int:
        """지역x개발유형별 평균 분양가 (원/평).

        시세 테이블은 regional_pricing 모듈(단일 출처)로 추출되어 파이프라인·추천이
        모두 동일한 분양가를 사용한다.
        """
        from app.services.feasibility.regional_pricing import (
            get_regional_sale_price_per_pyeong,
        )

        return get_regional_sale_price_per_pyeong(
            dev_type=dev_type, region=region, address=address
        )

    def _get_building_type(self, dev_type: str) -> str:
        """개발유형별 건축 유형."""
        types = {
            "M01": "apartment", "M02": "apartment", "M06": "apartment",
            "M07": "apartment", "M08": "officetel", "M09": "office",
            "M10": "house", "M11": "house", "M12": "townhouse",
            "M13": "apartment", "M14": "apartment", "M15": "apartment",
        }
        return types.get(dev_type, "apartment")

    def _get_type_project_months(self, dev_type: str) -> int:
        """개발유형별 예상 사업기간 (개월)."""
        months = {
            "M01": 60, "M02": 60, "M03": 48, "M04": 48, "M05": 36,
            "M06": 36, "M07": 42, "M08": 30, "M09": 36, "M10": 12,
            "M11": 12, "M12": 24, "M13": 24, "M14": 36, "M15": 48,
        }
        return months.get(dev_type, 36)
