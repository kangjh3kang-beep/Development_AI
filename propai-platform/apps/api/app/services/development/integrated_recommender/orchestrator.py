"""다필지 통합 → 개발방식별 용적률·수지 순위 추천 오케스트레이터(1차 증분).

흐름:
  1) enrich_context: 주소별로 부지정보 1회 수집(AutoZoningService) + 게이트 결손키 정규화.
  2) 게이트: special_parcel.detect_multi_parcel → 해결불가(NO)/원칙불가(BLOCKED)면 후보생성 중단
     (가짜 면적/수지 미산정 — 할루시네이션 차단).
  3) 통과 시: 통합면적·주용도지역·현행 실효용적률 산정 → 허용 개발유형별 수지 평가 → 순위.

★기존 자산 재사용(신규 최소):
  - AutoZoningService.analyze_by_address  : 외부호출(주소→PNU→용도/면적/지목/공시지가/특수구역)
  - special_parcel.detect_multi_parcel    : 다필지 특이부지 게이트
  - far_tier_service.calc_effective_far   : 현행 실효용적률(법정→조례→계획상한 SSOT)
  - permit_validator.get_permitted_types  : 용도지역 허용 개발유형
  - FeasibilityServiceV2.build_module_input/calculate : FAR→GFA→세대수→수지(추천과 동일 로직)
  - composite 공식                         : auto_recommend_top3와 동일(순이익0.5+수익률0.3+인허가0.2)

무목업: 공시지가 미확보 시 land_price_reliable=False로 절대 수익성(순이익·NPV)은 참고용 표기.
종상향/다층렌즈/J좌표/엔진연동은 후속(이번 제외) — 현행 실효용적률 1개 기준만 평가.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 게이트 차단 기준 — 통상 절차로 해결 불가(NO) 또는 원칙적 개발 불가(BLOCKED).
_BLOCK_DEVELOPABILITY = {"BLOCKED"}
_BLOCK_RESOLVABLE = {"NO"}


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

        # 2) 다필지 특이부지 게이트.
        from app.services.zoning.special_parcel import detect_multi_parcel

        gate = detect_multi_parcel(parcels)
        blocked = (
            gate.get("developability") in _BLOCK_DEVELOPABILITY
            or gate.get("resolvable") in _BLOCK_RESOLVABLE
        )
        if blocked:
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

        # 4) 허용 개발유형별 수지 평가 → 순위.
        from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
        from app.services.feasibility.permit_validator import (
            DEVELOPMENT_TYPE_NAMES,
            check_permit_feasibility,
            get_permitted_types,
        )

        service = FeasibilityServiceV2()
        permitted = get_permitted_types(primary_zone)
        region = self._region_from_address(addrs[0])
        primary_address = addrs[0]
        # 공시지가 폴백 표기를 위해 주필지 공시지가(있으면) 전달.
        primary_price = next((p.get("official_price_per_sqm") for p in valid if p.get("official_price_per_sqm")), None)

        ranked: list[dict[str, Any]] = []
        for dev_type in permitted:
            try:
                inp = service.build_module_input(
                    dev_type=dev_type,
                    site_area_sqm=integrated_area,
                    max_far_pct=baseline_far,
                    region=region,
                    address=primary_address,
                    official_price_per_sqm=primary_price,
                )
                output = service.calculate(inp)
                permit = check_permit_feasibility(dev_type, primary_zone)

                # composite — auto_recommend_top3와 동일 공식(순이익0.5+수익률0.3+인허가0.2).
                profit_amount_score = min(100, max(0, output.net_profit_won / 1e8))  # 100억→100점
                profit_rate_score = min(100, max(0, output.profit_rate_pct * 2))      # 50%→100점
                permit_score = (6 - permit["permit_complexity"]) * 20                 # 1→100, 5→20
                composite = profit_amount_score * 0.5 + profit_rate_score * 0.3 + permit_score * 0.2

                ranked.append({
                    "method": dev_type,
                    "type_name": DEVELOPMENT_TYPE_NAMES.get(dev_type, dev_type),
                    # 적용 용적률 = min(현행 실효용적률 baseline, 개발유형 일반치) — build_module_input 동일 산정.
                    #   ★최상위 baseline_far_pct(부지 현행 실효)와 다를 수 있음(유형 일반치로 클램프된 '적용치').
                    "applied_far_pct": round(inp.total_gfa_sqm / integrated_area * 100, 1) if integrated_area else None,
                    "total_gfa_sqm": round(inp.total_gfa_sqm, 1),
                    "net_profit": output.net_profit_won,
                    "profit_rate_pct": output.profit_rate_pct,
                    "npv": output.npv_won,
                    "composite": round(composite, 1),
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("통합추천 %s 수지 계산 실패: %s", dev_type, e)

        ranked.sort(key=lambda r: r["composite"], reverse=True)

        # 지목(land_category) 미확보 필지 — 지목 기반 특이부지 게이트(학교용지·농지·임야 등)가
        #   생략됐을 수 있으므로 '안전'이 아니라 '판정 못 함'으로 정직 고지(게이트 무력화 표면화).
        land_cat_missing = sum(1 for p in parcels if not (p.get("land_category") or "").strip())
        honest = (
            "랭킹은 동일 면적·현행 실효용적률 기준 상대비교입니다. "
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
            "land_price_reliable": land_price_reliable,
            "honest_disclosure": honest,
            "note": "1차 증분 — 현행 실효용적률 1개 기준 평가. 종상향/다층렌즈/엔진연동은 후속.",
        }

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

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
