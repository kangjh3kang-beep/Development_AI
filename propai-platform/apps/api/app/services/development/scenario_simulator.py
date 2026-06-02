"""다각도 개발방식 시뮬레이션.

단일/다필지 부지에 대해 관련 개발정책의 적용요건을 판정하고, 정책별 예상 용적률·
적정 기부채납·실현성을 산정해 최적 사업방안을 제안한다. 어떤 정책도 적용되지 않으면
단순 건축(현 용도지역 한도 내) 추진방안으로 폴백한다.

대상 정책: 단순건축 / 지구단위계획 연계 / 도시개발사업(도시개발법) / 가로주택정비사업 /
모아주택(소규모주택정비) / 소규모재건축 / 역세권 활성화사업 / 역세권 장기전세주택 /
재개발·재건축(정비사업).

요건·수치는 일반 기준 기반 추정이며 정밀 산정은 지구단위계획·심의 단계 확인이 필요하다.
규칙기반 후보 생성 + LLM 종합·검증(하이브리드).
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785


def _is_residential(zone: str) -> bool:
    return "주거" in (zone or "")


def _is_commercial(zone: str) -> bool:
    return "상업" in (zone or "") or "준주거" in (zone or "")


class DevelopmentScenarioSimulator:
    async def simulate(
        self,
        address: str,
        parcels: list[str] | None = None,
        site: dict[str, Any] | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        site = site or {}
        addrs = self._merge(address, parcels)
        multi = len(addrs) >= 2

        # 부지 정보 수집(단일/다필지)
        enriched, subway_m = await self._collect(addrs, site)
        total_area = sum(p.get("area") or 0 for p in enriched)
        far_legal = self._blended_far(enriched)
        zones = [p.get("zone") for p in enriched if p.get("zone")]
        primary_zone = zones[0] if zones else (site.get("zone_type") or "")
        near_station = (subway_m is not None and subway_m <= 500) or any(
            "역세권" in (p.get("zone") or "") for p in enriched
        )

        ctx = {
            "address": address, "multi": multi, "parcel_count": len(addrs),
            "total_area_sqm": round(total_area, 1) if total_area else None,
            "primary_zone": primary_zone, "zones": zones,
            "far_legal_blended": far_legal,
            "near_station_m": subway_m, "near_station": near_station,
        }

        scenarios = self._scenarios(ctx)
        # 적합도 정렬(가능>조건부>불가, est_far 내림차순)
        rank = {"가능": 0, "조건부": 1, "불가": 2}
        scenarios.sort(key=lambda s: (rank.get(s["applicable"], 3), -(s.get("est_far") or 0)))
        applicable = [s for s in scenarios if s["applicable"] in ("가능", "조건부")]
        recommended = applicable[0] if applicable else next(
            s for s in scenarios if s["scheme"] == "단순 건축"
        )

        result = {
            "site": ctx,
            "scenarios": scenarios,
            "recommended": {"scheme": recommended["scheme"], "est_far": recommended.get("est_far"),
                            "reason": recommended.get("notes") or recommended.get("pros", [""])[0]},
            "fallback_simple_build": next(s for s in scenarios if s["scheme"] == "단순 건축"),
        }
        if use_llm:
            result["ai"] = await self._llm(ctx, scenarios)
        return result

    # ── 부지 수집 ──
    @staticmethod
    def _merge(address: str, parcels: list[str] | None) -> list[str]:
        out: list[str] = []
        for a in [address, *(parcels or [])]:
            a = (a or "").strip()
            if a and a not in out:
                out.append(a)
        return out

    async def _collect(self, addrs: list[str], site: dict) -> tuple[list[dict], float | None]:
        import asyncio

        from app.services.zoning.auto_zoning_service import AutoZoningService, ZONE_LIMITS

        az = AutoZoningService()

        async def one(a: str) -> dict:
            try:
                r = await az.analyze_by_address(a)
                zl = r.get("zone_limits") or {}
                far = zl.get("max_far_pct") or zl.get("max_far")
                if not far and r.get("zone_type"):
                    lim = ZONE_LIMITS.get((r["zone_type"] or "").replace(" ", ""))
                    far = lim.get("max_far") if lim else None
                return {"address": a, "zone": r.get("zone_type"),
                        "area": r.get("land_area_sqm"), "max_far": far}
            except Exception:  # noqa: BLE001
                return {"address": a, "zone": None, "area": None, "max_far": None}

        enriched = await asyncio.gather(*[one(a) for a in addrs])
        enriched = list(enriched)
        # 주 필지 인근 지하철 거리(comprehensive)
        subway_m = None
        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            comp = await LandInfoService().collect_comprehensive(addrs[0])
            infra = comp.get("infrastructure") or {}
            ns = infra.get("nearest_subway") if isinstance(infra, dict) else None
            if isinstance(ns, dict):
                subway_m = ns.get("distance_m")
            # 면적/용도 보강
            if not enriched[0].get("area") and comp.get("land_area_sqm"):
                enriched[0]["area"] = comp["land_area_sqm"]
            if not enriched[0].get("zone") and comp.get("zone_type"):
                enriched[0]["zone"] = comp["zone_type"]
        except Exception:  # noqa: BLE001
            pass
        return enriched, subway_m

    @staticmethod
    def _blended_far(parcels: list[dict]) -> float | None:
        w = [(p.get("area"), p.get("max_far")) for p in parcels if p.get("max_far")]
        if not w:
            return None
        if all(a for a, _ in w):
            tot = sum(a for a, _ in w)
            return round(sum(a * f for a, f in w) / tot, 1) if tot else None
        fars = [f for _, f in w]
        return round(sum(fars) / len(fars), 1)

    # ── 규칙기반 시나리오 ──
    def _scenarios(self, c: dict) -> list[dict]:
        area = c.get("total_area_sqm") or 0
        zone = c.get("primary_zone") or ""
        far = c.get("far_legal_blended") or 0
        multi = c.get("multi")
        station = c.get("near_station")
        res = _is_residential(zone)
        com = _is_commercial(zone)
        S: list[dict] = []

        def add(scheme, applicable, est_far, contrib, requirements, pros, cons, notes):
            S.append({"scheme": scheme, "applicable": applicable,
                      "est_far": round(est_far) if est_far else None,
                      "contribution_pct": contrib, "requirements": requirements,
                      "pros": pros, "cons": cons, "notes": notes})

        # 1) 단순 건축 (항상 가능 — 폴백 기준)
        add("단순 건축", "가능", far or None, 0,
            ["현 용도지역 허용용도·건폐율/용적률 한도 내 건축"],
            ["인허가 절차 단순·신속", "별도 정비/지정 절차 불필요"],
            ["용적률 인센티브 없음(현 한도)"],
            "특별 개발정책 미적용 시 기본 추진방안")

        # 2) 지구단위계획 연계
        if area >= 5000 or multi:
            add("지구단위계획 연계", "가능", (far or 0) * 1.2, 12,
                ["대지 5,000㎡ 이상 또는 다필지 통합", "지구단위계획 수립·심의"],
                ["용적률 인센티브(통상 +10~20%)", "용도·획지 유연화", "다필지 통합개발 적합"],
                ["계획 수립·심의 기간 소요", "공공기여 수반"],
                "다필지 통합개발의 핵심 수단. 기부채납 약 10~15%로 용적 상향")
        else:
            add("지구단위계획 연계", "조건부", (far or 0) * 1.15, 12,
                ["소규모는 인접 지구단위계획구역 편입 여부 확인"],
                ["편입 시 인센티브 가능"], ["단독 수립은 규모상 비효율"],
                "면적 5,000㎡ 미만 — 인접 구역 편입/특별계획구역 검토")

        # 3) 도시개발사업(도시개발법)
        if area >= 10000:
            add("도시개발사업(도시개발법)", "가능", (far or 0) * 1.3, 25,
                ["도시지역 1만㎡ 이상(비도시 3만㎡)", "도시개발구역 지정"],
                ["환지/수용 방식 대규모 개발", "기반시설 일체 정비", "용적 상향 여지 큼"],
                ["구역지정·실시계획 등 장기 절차", "공공기여 큼"],
                "대규모 통합개발에 적합. 구역지정 요건 충족")
        else:
            add("도시개발사업(도시개발법)", "불가", None, None,
                ["도시지역 1만㎡ 이상 필요"], [], ["면적 미달"],
                f"총면적 {round(area):,}㎡ < 1만㎡ — 도시개발구역 지정 요건 미달")

        # 4) 가로주택정비사업
        if res and 0 < area < 10000:
            add("가로주택정비사업", "조건부", (far or 0) * 1.2, 0,
                ["가로구역(폭6m이상 도로로 둘러싸임)", "노후·불량건축물 2/3 이상",
                 "기존 주택 단독10/공동20세대 이상", "면적 1만㎡ 미만"],
                ["소규모·신속(정비계획 생략)", "용적률 법적상한까지 완화 가능", "공공임대 시 추가 인센티브"],
                ["노후도·세대수 요건 충족 필요", "주민 동의 필요"],
                "노후 저층주거지 소규모 통합정비에 적합 — 요건 현장확인 필요")
        else:
            add("가로주택정비사업", "불가", None, None,
                ["주거지역·면적1만㎡ 미만·노후2/3·가로구역 필요"], [], ["요건 미해당"],
                "주거지역 아님 또는 면적 1만㎡ 이상")

        # 5) 모아주택(소규모주택정비) / 모아타운
        if res and 1500 <= area <= 100000:
            add("모아주택/모아타운", "조건부", (far or 0) * 1.2, 0,
                ["소규모주택정비 관리지역(모아타운) 지정", "노후·불량 2/3 이상", "면적 1,500㎡~"],
                ["블록단위 통합·지하주차 공유", "용적률·층수 완화", "기반시설 국비 지원"],
                ["관리지역 지정 필요(서울 등)", "주민 합의"],
                "다세대·연립 밀집지 블록 통합개발 — 모아타운 지정 여부 확인")
        else:
            add("모아주택/모아타운", "불가", None, None,
                ["주거지역·면적 1,500㎡ 이상·노후 필요"], [], ["요건 미해당"], "")

        # 6) 역세권 활성화사업 / 역세권 장기전세주택
        if station:
            add("역세권 활성화사업", "조건부", (far or 0) * 1.5 if not com else (far or 0) * 1.2, 50,
                ["역 승강장 350m 이내", "용도지역 상향(일반→준주거/상업)", "증가용적 50% 공공기여"],
                ["용도지역 종상향으로 용적 대폭 상향", "복합개발 허용"],
                ["증가용적의 50% 공공기여(임대·생활SOC)", "심의 절차"],
                "역세권 입지 — 용도상향+공공기여로 고밀복합 가능")
            if res:
                add("역세권 장기전세주택(시프트)", "조건부", 500, 50,
                    ["역세권 350m 이내", "준주거 상향", "증가용적 50% 장기전세 공급"],
                    ["준주거 상향(용적 500%)으로 사업성↑", "공공성 확보"],
                    ["임대주택 기부채납 부담", "서울시 등 운영지역 한정"],
                    "주거 역세권 — 준주거 상향 + 장기전세 연계")
        else:
            add("역세권 활성화사업", "불가", None, None,
                ["역 승강장 350m 이내 필요"], [], ["역세권 범위 밖"],
                f"인근 역 거리 {c.get('near_station_m') or '미상'} — 역세권(350m) 미해당")

        # 7) 재개발·재건축(정비사업)
        if area >= 10000:
            add("재개발·재건축(정비사업)", "조건부", (far or 0) * 1.2, 15,
                ["정비구역 지정", "노후·불량건축물 2/3 이상", "면적 1만㎡ 이상"],
                ["대규모 정비·기반시설 확보", "용적률 상향"],
                ["정비구역 지정·조합설립 등 장기", "분담금·분쟁 리스크"],
                "노후 시가지 대규모 정비 — 노후도 요건 확인")
        else:
            add("재개발·재건축(정비사업)", "불가", None, None,
                ["면적 1만㎡ 이상·노후 필요"], [], ["면적 미달"], "")

        return S

    async def _llm(self, ctx: dict, scenarios: list[dict]) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            sys = ("당신은 부동산개발 사업방식 전문가다. 제공된 부지정보와 규칙기반 후보 시나리오를 "
                   "근거로 가장 합리적인 최적 사업방안을 추천하고 그 이유, 차선책, 주의사항을 제시한다. "
                   "데이터·후보에 근거하고 과장 금지. JSON만 출력." + GROUNDING_RULE)
            usr = (f"## 부지\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
                   f"## 후보 시나리오\n{json.dumps(scenarios, ensure_ascii=False)[:3000]}\n\n"
                   "## 출력 JSON\n{\"summary\":\"종합 판단 3~4문장\",\"best_scheme\":\"추천 사업방식\","
                   "\"why\":\"추천 이유 2~3문장\",\"alternatives\":[\"차선책 1~2개\"],"
                   "\"cautions\":[\"주의사항 1~3개\"]}")
            llm = get_llm(timeout=60, max_tokens=1500)
            resp = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=usr)])
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
            data = json.loads(raw.strip())
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("개발 시나리오 LLM 실패, 폴백", err=str(e)[:100])
            return {"generated": False, "summary": "규칙기반 시나리오를 참고하세요. AI 종합은 일시적으로 미제공.",
                    "best_scheme": None, "why": "", "alternatives": [], "cautions": []}
