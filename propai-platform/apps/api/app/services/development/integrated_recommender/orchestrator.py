"""다필지 통합 → 개발방식별 용적률·수지 순위 추천 오케스트레이터(1차 증분).

흐름:
  1) enrich_context: 주소별로 부지정보 1회 수집(AutoZoningService) + 게이트 결손키 정규화.
  2) 게이트: special_parcel.detect_multi_parcel → 해결불가(NO)/원칙불가(BLOCKED)면 후보생성 중단
     (가짜 면적/수지 미산정 — 할루시네이션 차단).
  3) 통과 시: 통합면적·주용도지역·현행 실효용적률 산정 → 허용 개발유형별 수지 평가 → 순위.
  4) 종상향 축(2차 증분): 현행 외에, 가능성 '상/중' 종상향 시나리오별(목표 용도지역의 상향
     용적률 × 목표지역 허용 개발유형) 후보도 같은 로직으로 평가해 단일 순위에 통합한다.
     잠재 후보는 정직 마커(조건부·단정 아님)를 반드시 동반한다.

★기존 자산 재사용(신규 최소):
  - AutoZoningService.analyze_by_address  : 외부호출(주소→PNU→용도/면적/지목/공시지가/특수구역)
  - special_parcel.detect_multi_parcel    : 다필지 특이부지 게이트
  - far_tier_service.calc_effective_far   : 현행 실효용적률(법정→조례→계획상한 SSOT)
  - far_tier_service.calc_upzoning        : 종상향 잠재 시나리오(규칙엔진·추가 외부콜 0)
  - permit_validator.get_permitted_types  : 용도지역 허용 개발유형
  - FeasibilityServiceV2.build_module_input/calculate : FAR→GFA→세대수→수지(추천과 동일 로직)
  - composite 공식                         : auto_recommend_top3와 동일(순이익0.5+수익률0.3+인허가0.2)

무목업: 공시지가 미확보 시 land_price_reliable=False로 절대 수익성(순이익·NPV)은 참고용 표기.
★이중계상 방지: 현행 후보는 calc_effective_far(baseline_far)로, 잠재 후보는 시나리오의
  expected_far_pct_high로 — 용적률 출처를 단일화한다. 잠재 후보에 인센티브/완화를 재가산하지
  않는다(상향 용적률을 그대로 사용). 다층렌즈/J좌표/엔진연동은 후속.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 게이트 정책은 special_parcel.gate_decision(SSOT)로 일원화한다 — auto_recommend_top3와 동일 기준.
#   (BLOCK=후보 미생성·정직고지, TENTATIVE=선행절차 전제 잠정치로 강등, PASS=통상 산출.)
#   ★국소 임계 분기 금지: 도로 PRECONDITION 같은 선행절차형이 한쪽 게이트만 통과하는 회귀를 막는다.


class IntegratedRecommender:
    """다필지 통합 개발방식 추천 엔진."""

    async def recommend(
        self,
        addresses: list[str],
        parcel_subset_policy: str = "전체",
    ) -> dict[str, Any]:
        """다필지 주소 리스트로부터 개발방식별 수지 순위를 산정한다.

        Args:
            addresses: 분석 대상 필지 주소 리스트(1개 이상).
            parcel_subset_policy: 필지 부분집합 정책(현재 '전체'만 — 후속 확장 자리).

        Returns:
            게이트 통과 시 순위 포함 dict, 차단 시 {gate, honest_disclosure}만.
        """
        addrs = [a.strip() for a in (addresses or []) if a and a.strip()]
        if not addrs:
            return {
                "error": "주소가 1개 이상 필요합니다.",
                "ranked": [],
            }

        # 1) 컨텍스트 수집 + 게이트 결손키 정규화 (외부호출 1회/필지).
        parcels = await self._enrich_context(addrs)

        # 2) 다필지 특이부지 게이트 — 통합(전체) 종합 판정. SSOT gate_decision으로 정책 분기.
        from app.services.zoning.special_parcel import (
            detect_multi_parcel,
            gate_decision,
            tentative_marker,
        )

        gate = detect_multi_parcel(parcels)
        decision = gate_decision(gate.get("developability"), gate.get("resolvable"))
        if decision == "BLOCK":
            # 후보생성 중단 — 개발규모/수지 미산정(정직). 게이트·정직고지만 반환.
            return {
                "site": {"addresses": addrs, "parcel_count": len(parcels)},
                "gate": gate,
                "integrated_area_sqm": None,
                "baseline_far_pct": None,
                "ranked": [],
                "land_price_reliable": False,
                "honest_disclosure": gate.get("honest_disclosure")
                or "통상 절차로 해결 불가능한 제약이 포함되어 개발규모를 산정하지 않습니다.",
            }

        # 3) 게이트 통과 — 통합면적·주용도지역·현행 실효용적률 산정.
        valid = [p for p in parcels if (p.get("land_area_sqm") or 0) > 0]
        integrated_area = float(sum((p.get("land_area_sqm") or 0) for p in valid))
        primary_zone = self._primary_zone(valid or parcels)

        # 공시지가 신뢰성 — 전 유효필지가 공시지가를 확보해야 절대 수익성 신뢰(아니면 참고용).
        prices = [p.get("official_price_per_sqm") for p in valid]
        land_price_reliable = bool(valid) and all(bool(x and x > 0) for x in prices)

        if integrated_area <= 0 or not primary_zone:
            return {
                "site": {"addresses": addrs, "parcel_count": len(parcels)},
                "gate": gate,
                "integrated_area_sqm": integrated_area or None,
                "baseline_far_pct": None,
                "ranked": [],
                "land_price_reliable": False,
                "honest_disclosure": "유효 필지 면적/용도지역을 확보하지 못해 개발규모를 산정하지 않습니다.",
            }

        # 현행 실효용적률(법정→조례→계획상한 SSOT). base는 주필지 컨텍스트로 구성.
        baseline_far = self._baseline_far(valid or parcels, primary_zone, integrated_area)
        if baseline_far is None or baseline_far <= 0:
            # 실효용적률 미산정 — 개발규모/수지 미산정(정직, 가짜 용적률 미생성).
            return {
                "site": {"addresses": addrs, "parcel_count": len(parcels), "primary_zone": primary_zone},
                "gate": gate,
                "integrated_area_sqm": round(integrated_area, 1),
                "baseline_far_pct": None,
                "ranked": [],
                "upzoning_scenarios": None,
                "land_price_reliable": False,
                "honest_disclosure": "현행 실효용적률을 산정하지 못해 개발규모를 산정하지 않습니다.",
            }

        # 4) 허용 개발유형별 수지 평가 → 순위.
        from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
        from app.services.feasibility.permit_validator import get_permitted_types

        service = FeasibilityServiceV2()
        permitted = get_permitted_types(primary_zone)
        region = self._region_from_address(addrs[0])
        primary_address = addrs[0]
        # 공시지가 폴백 표기를 위해 주필지 공시지가(있으면) 전달.
        primary_price = next((p.get("official_price_per_sqm") for p in valid if p.get("official_price_per_sqm")), None)

        ranked: list[dict[str, Any]] = []
        # 4-1) 현행 후보 — baseline_far(calc_effective_far) 기준. far_basis="현행".
        for dev_type in permitted:
            cand = self._score_candidate(
                service, dev_type, primary_zone, integrated_area,
                baseline_far, region, primary_address, primary_price,
            )
            if cand is not None:
                cand["far_basis"] = "현행"
                ranked.append(cand)

        # 4-2) 종상향(up-zoning) 축 — 잠재 시나리오별 후보. scenario FAR 기준. far_basis="종상향".
        #   ★이중계상 방지: 현행은 baseline_far, 잠재는 scenario.expected_far_pct_high(단일 출처).
        #     인센티브/far_optimization 재적용 없음(상향 용적률을 그대로 사용).
        upzoning, upz_candidates = self._build_upzoning(
            service, valid or parcels, primary_zone, integrated_area,
            region, primary_address, primary_price,
        )
        ranked.extend(upz_candidates)

        # 4-3) 잠정 강등 — 통합 게이트가 TENTATIVE면(예: 도로 PRECONDITION·맹지·학교 등 선행절차형
        #   필지가 통합에 포함) 전 현행 후보를 '선행절차 전제 잠정치(확정 아님)'로 강등한다.
        #   ★도로는 통합 시 기반시설 편입 전제 — 단독으로 일반 분양개발 % 를 확정 제시하지 않는다.
        #   종상향(far_basis='종상향') 후보는 이미 자체 honest 마커가 있으므로 현행 후보에만 부착한다.
        is_tentative = decision == "TENTATIVE"
        if is_tentative:
            t_reason = tentative_marker(
                gate.get("developability"), gate.get("resolvable"),
                gate.get("severity_label"),
            )
            for r in ranked:
                if r.get("far_basis") == "현행":
                    r["tentative"] = True
                    r["tentative_reason"] = t_reason

        # 현행/잠재 통합 순위(composite 내림차순).
        ranked.sort(key=lambda r: r["composite"], reverse=True)

        # 지목(land_category) 미확보 필지 — 지목 기반 특이부지 게이트(학교용지·농지·임야 등)가
        #   생략됐을 수 있으므로 '안전'이 아니라 '판정 못 함'으로 정직 고지(게이트 무력화 표면화).
        land_cat_missing = sum(1 for p in parcels if not (p.get("land_category") or "").strip())
        has_upzoning = any(r.get("far_basis") == "종상향" for r in ranked)
        honest = (
            "랭킹은 동일 면적·현행 실효용적률 기준 상대비교입니다. "
            + ("⚠ 이 통합 사업구역에는 선행절차형 특이부지(도로·학교·맹지 등)가 포함되어, 현행 후보는 모두 "
               "선행절차(폐도·용도폐지·도시계획변경 등) 통과를 전제로 한 잠정치이며 확정이 아닙니다. "
               if is_tentative else "")
            + ("랭킹에는 현행(far_basis='현행')과 종상향 잠재(far_basis='종상향') 후보가 함께 포함됩니다. "
               "종상향 후보는 고시·심의 통과를 전제로 한 조건부 시나리오이며 단정이 아닙니다. "
               if has_upzoning else "")
            + ("" if land_price_reliable
               else "공시지가 미확보 필지가 있어 순이익·NPV 절대값은 참고용입니다(랭킹은 유효). ")
            + (f"지목 미확보 {land_cat_missing}필지 — 지목 기반 특이부지 판정이 생략됐을 수 있어 별도 확인이 필요합니다. "
               if land_cat_missing else "")
            + (gate.get("honest_disclosure") or "")
        ).strip()

        return {
            "site": {
                "addresses": addrs,
                "parcel_count": len(parcels),
                "primary_zone": primary_zone,
                "parcel_subset_policy": parcel_subset_policy,
            },
            "gate": gate,
            "integrated_area_sqm": round(integrated_area, 1),
            "baseline_far_pct": baseline_far,
            "ranked": ranked,
            # 시나리오 상태 — "tentative"면 현행 후보가 선행절차 전제 잠정치(확정 아님). 프론트 렌더 분기 신호.
            "scenario_status": "tentative" if is_tentative else "actual",
            # 종상향 잠재 시나리오 요약(조회 실패/없음이면 None) — 잠재 후보의 출처·정직 근거.
            "upzoning_scenarios": upzoning,
            "land_price_reliable": land_price_reliable,
            "honest_disclosure": honest,
            "note": "2차 증분 — 현행 실효용적률 + 종상향 잠재(2계층) 평가. 다층렌즈/엔진연동은 후속.",
        }

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _score_candidate(
        service: Any,
        dev_type: str,
        zone_for_permit: str,
        integrated_area: float,
        far_pct: float,
        region: str,
        address: str,
        official_price: float | None,
    ) -> dict[str, Any] | None:
        """단일 (개발유형 × 용적률) 후보의 수지·composite를 산정한다(현행·잠재 공용).

        ★현행/잠재가 '동일 로직'을 쓰도록 한 곳에 모은다(로직 복제 방지·결과 정합).
          - 용적률(far_pct)만 호출자가 다르게 넣는다: 현행=baseline_far, 잠재=시나리오 상향치.
          - 인허가 복잡도(permit_complexity)는 zone_for_permit(잠재면 목표 용도지역) 기준.
        composite 공식은 auto_recommend_top3와 동일(순이익0.5+수익률0.3+인허가0.2).
        실패(예외) 시 None을 반환해 후보에서 제외한다(가짜 수치 미생성).
        """
        from app.services.feasibility.permit_validator import (
            DEVELOPMENT_TYPE_NAMES,
            check_permit_feasibility,
        )

        try:
            inp = service.build_module_input(
                dev_type=dev_type,
                site_area_sqm=integrated_area,
                max_far_pct=far_pct,
                region=region,
                address=address,
                official_price_per_sqm=official_price,
            )
            output = service.calculate(inp)
            permit = check_permit_feasibility(dev_type, zone_for_permit)

            # composite — auto_recommend_top3와 동일 공식(순이익0.5+수익률0.3+인허가0.2).
            profit_amount_score = min(100, max(0, output.net_profit_won / 1e8))  # 100억→100점
            profit_rate_score = min(100, max(0, output.profit_rate_pct * 2))      # 50%→100점
            permit_score = (6 - permit["permit_complexity"]) * 20                 # 1→100, 5→20
            composite = profit_amount_score * 0.5 + profit_rate_score * 0.3 + permit_score * 0.2

            return {
                "method": dev_type,
                "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                # 적용 용적률 = min(입력 용적률, 개발유형 일반치) — build_module_input 동일 산정.
                #   ★최상위 baseline_far_pct(현행) 또는 시나리오 상향치(잠재)에서 유형 일반치로 클램프된 '적용치'.
                "applied_far_pct": round(inp.total_gfa_sqm / integrated_area * 100, 1) if integrated_area else None,
                "total_gfa_sqm": round(inp.total_gfa_sqm, 1),
                "net_profit": output.net_profit_won,
                "profit_rate_pct": output.profit_rate_pct,
                "npv": output.npv_won,
                "composite": round(composite, 1),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("통합추천 %s 수지 계산 실패: %s", dev_type, e)
            return None

    def _build_upzoning(
        self,
        service: Any,
        parcels: list[dict[str, Any]],
        primary_zone: str,
        integrated_area: float,
        region: str,
        address: str,
        official_price: float | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """종상향 잠재 시나리오를 조회해 (요약, 잠재 후보 리스트)를 만든다.

        흐름: calc_upzoning(현행 컨텍스트 재사용·추가 외부콜 0) → 가능성 '상/중' 시나리오만 채택
        → 시나리오별 (목표 용도지역 허용 개발유형 × 시나리오 상향 용적률)로 _score_candidate.

        ★이중계상 방지: 현행은 baseline_far, 잠재는 scenario.expected_far_pct_high(단일 출처).
          인센티브/far_optimization 재가산 없음(상향 용적률을 그대로 build_module_input에 전달).
        ★정직: 잠재 후보는 honest 마커·경로·가능성·근거를 동반(조건부·단정 아님). '하'는 제외.
        조회 실패/시나리오 없음 → (None, []) → 현행만(회귀0).
        """
        from app.services.feasibility.permit_validator import get_permitted_types
        from app.services.land_intelligence.far_tier_service import calc_upzoning

        # 종상향 분석은 보유 데이터(면적·역세권·규제구역·시군구) 기반 규칙엔진 — 추가 외부콜 없음.
        # base는 주용도지역 필지 컨텍스트 재사용(special_districts·local_ordinance·infrastructure).
        zone_parcels = [p for p in parcels if p.get("zone_type") == primary_zone] or parcels
        if not zone_parcels:
            return None, []
        primary = max(zone_parcels, key=lambda p: (p.get("land_area_sqm") or 0))
        base = {
            "zone_limits": primary.get("zone_limits") or {},
            "special_districts": primary.get("special_districts") or [],
            "local_ordinance": primary.get("local_ordinance") or {},
            "infrastructure": primary.get("infrastructure") or {},
        }

        try:
            upzoning = calc_upzoning(base, primary_zone, integrated_area)
        except Exception as e:  # noqa: BLE001
            logger.warning("통합추천 종상향 잠재 분석 실패: %s", e)
            return None, []

        # 가능성 '하'·근거없는 경로 제외 후, 가능성 높은 순(상>중)으로 정렬 — 동일 목표지역·유형
        #   중복 시 최상 가능성 경로만 남기기 위함(여러 경로가 같은 목표지역을 가리켜 후보 폭증·중복 방지).
        _FEAS_RANK = {"상": 0, "중": 1}
        _FEAS_DISCOUNT = {"상": 0.85, "중": 0.65}  # 조건부 할인(고시·심의 전제) — 확정 현행 부당 압도 방지.
        scenarios = sorted(
            [s for s in ((upzoning or {}).get("scenarios") or []) if s.get("feasibility") in ("상", "중")],
            key=lambda s: _FEAS_RANK.get(s.get("feasibility"), 9),
        )
        candidates: list[dict[str, Any]] = []
        seen: set[tuple] = set()  # (목표지역, 개발유형, 반올림 용적률) 중복 후보 제거
        for sc in scenarios:
            target_zone = sc.get("target_zone")
            up_far = sc.get("expected_far_pct_high")  # ★잠재 용적률 단일 출처(인센티브 재가산 금지).
            if not target_zone or not up_far or up_far <= 0:
                continue
            path = sc.get("path") or sc.get("path_key") or "종상향"
            feas = sc.get("feasibility")
            disc = _FEAS_DISCOUNT.get(feas, 0.6)
            # 종상향 후 허용 개발유형은 목표 용도지역 기준으로 재산정(허용유형 변동 반영).
            permitted_up = get_permitted_types(target_zone)
            for dev_type in permitted_up:
                key = (target_zone, dev_type, round(float(up_far)))
                if key in seen:
                    continue  # 동일 목표지역·유형은 최상 가능성 경로만 유지(중복 제거)
                seen.add(key)
                cand = self._score_candidate(
                    service, dev_type, target_zone, integrated_area,
                    float(up_far), region, address, official_price,
                )
                if cand is None:
                    continue
                cand["far_basis"] = "종상향"
                cand["upzoning_path"] = path
                cand["upzoning_target_zone"] = target_zone
                cand["upzoning_feasibility"] = feas
                cand["legal_basis"] = sc.get("legal_basis")
                # ★조건부 할인 — 순위에서 확정 현행을 부당하게 압도하지 않도록 가능성별 감점.
                #   원점수는 composite_raw로 보존(투명성).
                cand["composite_raw"] = cand["composite"]
                cand["composite"] = round(cand["composite"] * disc, 1)
                # ★정직 마커 — 조건부·단정 아님(고시·심의 통과 전제) + 순위 할인 반영 명시.
                cand["honest"] = (
                    f"종상향({path} 경로) 실현 시 가능 — 조건부·단정 아님"
                    f"(고시·심의 통과 전제, 가능성 '{feas}'). 순위는 조건부 할인(×{disc}) 반영."
                )
                candidates.append(cand)

        return upzoning, candidates

    async def _enrich_context(self, addrs: list[str]) -> list[dict[str, Any]]:
        """주소별 부지정보 수집 + 게이트 결손키 정규화(외부호출 1회/필지).

        AutoZoningService.analyze_by_address가 pnu·zone_type·land_area_sqm·land_category·
        official_price_per_sqm·special_districts를 반환한다. detect_multi_parcel이 요구하는
        키(land_category·zone_type·special_districts·road_contact/road_width_m)로 정규화한다.

        ★road_contact/road_width_m: analyze_by_address는 접도 데이터를 제공하지 않는다.
          0/False로 단정하면 special_parcel이 모든 필지를 맹지로 오탐하므로, 미확보 시 None으로
          두어 맹지 오탐을 방지한다(접도 판정은 후속 부지분석 결과 연동 시 보강).
        """
        import asyncio

        from app.services.zoning.auto_zoning_service import AutoZoningService

        az = AutoZoningService()

        async def one(addr: str) -> dict[str, Any]:
            try:
                r = await az.analyze_by_address(addr)
            except Exception as e:  # noqa: BLE001
                logger.warning("통합추천 컨텍스트 수집 실패(%s): %s", addr, e)
                r = {"address": addr}
            return {
                "address": addr,
                "pnu": r.get("pnu"),
                "zone_type": r.get("zone_type") or "",
                "zone_limits": r.get("zone_limits") or {},
                "land_area_sqm": r.get("land_area_sqm"),
                # 게이트 결손키 정규화 — detect_multi_parcel/detect_special_parcel 입력 정합.
                "land_category": r.get("land_category") or "",
                "special_districts": r.get("special_districts") or [],
                "official_price_per_sqm": r.get("official_price_per_sqm"),
                # 접도 미확보 → None(맹지 오탐 방지). 0/False로 단정하지 않음.
                "road_contact": None,
                "road_width_m": None,
                "coordinates": r.get("coordinates") or {},
                "warnings": r.get("warnings") or [],
            }

        return list(await asyncio.gather(*[one(a) for a in addrs]))

    @staticmethod
    def _primary_zone(parcels: list[dict[str, Any]]) -> str:
        """주용도지역 — 면적 최대 필지의 용도지역(없으면 첫 유효 용도지역)."""
        with_zone = [p for p in parcels if p.get("zone_type")]
        if not with_zone:
            return ""
        return max(with_zone, key=lambda p: (p.get("land_area_sqm") or 0)).get("zone_type") or ""

    @staticmethod
    def _baseline_far(parcels: list[dict[str, Any]], zone_type: str, land_area: float) -> float | None:
        """현행 실효용적률(%) — far_tier_service.calc_effective_far(SSOT) 산정.

        base는 주용도지역 필지의 zone_limits/special_districts로 구성(조례/계획상한 반영).
        """
        from app.services.land_intelligence.far_tier_service import calc_effective_far

        # 주용도지역 필지(면적 최대) 컨텍스트를 base로 사용.
        zone_parcels = [p for p in parcels if p.get("zone_type") == zone_type] or parcels
        primary = max(zone_parcels, key=lambda p: (p.get("land_area_sqm") or 0))
        base = {
            "zone_limits": primary.get("zone_limits") or {},
            "special_districts": primary.get("special_districts") or [],
            # local_ordinance는 1차 미수집 — calc_effective_far가 용도지역 라벨 기준 법정값으로 폴백.
            "local_ordinance": {},
        }
        try:
            eff = calc_effective_far(base, zone_type, land_area)
            far = eff.get("effective_far_pct")
            return float(far) if far is not None else None
        except Exception as e:  # noqa: BLE001
            logger.warning("통합추천 실효용적률 산정 실패: %s", e)
            return None

    @staticmethod
    def _region_from_address(address: str) -> str:
        """주소 첫 토큰을 지역(시·도)으로 추정 — 분양가 테이블 키(미상이면 '서울')."""
        token = (address or "").strip().split()
        return token[0] if token else "서울"
