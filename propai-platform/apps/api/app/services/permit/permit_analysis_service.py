"""인.허가 AI 분석 서비스.

부지분석(용도지역·건폐율/용적률·면적) + 지자체 조례 + 상위법령을 종합하여,
개발방식별 인허가 가능성·근거법령·문제점·해결방안을 LLM(Claude)으로 분석한다.

- 상위법령: 국토의 계획 및 이용에 관한 법률, 건축법, 주택법, 도시개발법,
  도심 공공주택 복합사업(공공주택특별법), 도시 및 주거환경정비법
- 도시·군 관리계획 / 도시·군 계획 / 지구단위계획, 지자체 조례 우선순위 반영
- LLM 실패 시 규칙기반 폴백(graceful)
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 분석 대상 개발방식
DEV_METHODS = [
    "아파트(공동주택)",
    "주상복합",
    "오피스텔",
    "도시개발사업",
    "도심공공주택복합사업",
    "재개발·재건축(정비사업)",
    "단독·다세대주택",
]

_SYSTEM = """\
당신은 한국 건축·도시계획 인허가 전문가(행정사 18년 + 도시계획 15년)입니다.
상위법령(국토의계획및이용에관한법률, 건축법, 주택법, 도시개발법, 공공주택특별법(도심공공주택복합),
도시및주거환경정비법)과 도시·군관리계획·지구단위계획, 그리고 해당 지자체 조례의 우선순위를
정확히 적용해 분석합니다.

원칙:
1. 법조문은 가능한 한 정확히 인용(예: "건축법 제56조", "국토계획법 제76조", "주택법 제15조").
2. 용도지역 허용용도·건폐율·용적률 한도와 조례 강화 여부를 근거로 가능성을 판정.
3. 데이터에 있는 수치만 사용, 추정은 명시. 과장·허위 금지.
4. 상업지역(중심·일반·근린·유통상업지역)은 주거(공동주택·주상복합)·업무·판매시설이 모두 허용된다.
   상업지역에서 '공동주택 건축 불가'로 단정하지 말 것(주거용적률 제한·용도용적제는 규모 제약일 뿐 금지 아님).
5. 용적률은 '지자체 조례(실효 용적률)'를 법정상한보다 우선 적용한다. 부지정보의 '용적률 한도'와
   '지자체 조례'가 다르면 조례값을 기준으로 판정하고, 그 근거를 명시한다.
6. 부지정보의 '용적률 한도(실효)'는 이미 산정근거(법정·조례·구조상한 등)를 반영한 최종 실효치다.
   특히 산정근거가 '구조상한(건폐율×층수)'이면 녹지지역 4층 이하 등 층수제한으로 실효 용적률이
   법정 범위 상한보다 낮아진 것이므로, 그 값을 상향해 낙관적으로 재해석하지 말 것(과대낙관 금지).
7. 반드시 JSON만 출력(마크다운·설명문 금지)."""

_USER_TMPL = """\
아래 부지정보를 바탕으로 각 개발방식의 인허가 가능성을 분석해 JSON으로만 답하세요.

## 부지정보
- 주소: {address}
- 용도지역: {zone_type}
- 건폐율 한도: {max_bcr}%
- 용적률 한도(실효): {max_far}% (산정근거: {far_basis})
- 대지면적: {land_area_sqm}㎡
- 지자체 조례: {ordinance}
- 특별지구/지정: {special}
- 특이부지 감지: {special_parcel}

## 출력 JSON 스키마
{{
  "summary": "부지 종합 인허가 환경 요약(3~4문장, 용도지역·조례·상위계획 관점)",
  "methods": [
    {{
      "method": "개발방식명",
      "possibility": "상|중|하",
      "score": 0-100 정수,
      "key_laws": ["근거 법령/조문 2~4개"],
      "issues": ["인허가 문제점 1~3개"],
      "solutions": ["해결방안 1~3개"]
    }}
  ],
  "recommendation": "가장 유리한 개발방식과 그 이유 + 권고 절차(2~3문장)"
}}
분석할 개발방식: {methods}
"""

# 다필지(여러 필지) 통합 개발 — 최적/최고 용적률 산정 프롬프트
_MULTI_SYSTEM = """\
당신은 한국 도시계획·건축 인허가 및 용적률 산정 전문가입니다.
용도지역이 서로 다른 둘 이상의 필지를 하나의 대지로 통합(합필)해 개발할 때의
법정 용적률과 최적·최고 용적률을 정확히 산정합니다.

핵심 법리:
1. 국토계획법 시행령 제84조(둘 이상 용도지역 걸친 대지): 가장 작은 부분이 330㎡ 이하이면
   과반 또는 가중 큰 용도지역 기준 적용 가능. 그 외에는 각 용도지역 면적비율에 따른
   '가중평균 용적률'을 적용한다. (법정 통합 용적률 = Σ(필지면적×용적률한도)/Σ필지면적)
2. 최고 용적률 상향 수단: 지구단위계획(용적률 인센티브), 결합건축(건축법 제77조의4),
   특별건축구역(건축법 제69조), 공공기여(기부채납) 연동 상향, 용도지역 변경(종상향),
   역세권·도시정비형 재개발 등. 각 수단의 적용 가능성·전제조건을 명시.
3. 데이터에 있는 수치만 사용. 가정은 명시. 과장·허위 금지. JSON만 출력."""

_MULTI_TMPL = """\
아래 여러 필지를 하나의 대지로 통합 개발할 때 최적·최고 용적률을 산정하고 JSON으로만 답하세요.

## 통합 대상 필지 ({n}개 필지, 총면적 {total_area}㎡)
{parcel_lines}

## 참고: 면적가중평균 용적률(법정 통합 용적률) 사전계산값 = {blended_far}%
(데이터 누락 필지가 있으면 이 값은 부정확할 수 있으니 보정 의견을 제시하세요.)

## 출력 JSON 스키마
{{
  "blended_far": 면적가중평균 용적률(%) 숫자,
  "optimal_far": "현실적으로 인허가 가능한 최적 용적률(%) — 법정+통상 인센티브 반영" 숫자,
  "max_far": "모든 상향수단 적용 시 이론적 최고 용적률(%)" 숫자,
  "far_rationale": "최적·최고 용적률 산정 근거(가중평균 계산 + 상향수단별 적용가능성, 4~6문장)",
  "far_key_laws": ["근거 법령/조문 3~5개(국토계획법 시행령 제84조, 건축법 제77조의4 결합건축 등)"],
  "integration_issues": ["다필지 통합개발 인허가 문제점 2~4개(합필요건·용도지역 경계·조례 등)"],
  "integration_solutions": ["해결방안 2~4개"]
}}
"""


class PermitAnalysisService:
    async def analyze(
        self,
        address: str,
        site: dict[str, Any] | None = None,
        parcels: list[str] | None = None,
        use_llm: bool = True,
        with_senior: bool = True,
    ) -> dict[str, Any]:
        site = await self._enrich_site(address, site or {})
        ordinance_txt = await self._ordinance_text(address, site)

        # 명시실행: use_llm=False면 LLM 내러티브를 건너뛰고 규칙기반 결과만 반환.
        result = (
            await self._llm_analyze(address, site, ordinance_txt)
            if use_llm
            else self._fallback(site)
        )
        result["site"] = {
            "address": address,
            "zone_type": site.get("zone_type"),
            "max_bcr": site.get("max_bcr"),
            "max_far": site.get("max_far"),  # 실효(구조상한 포함) 용적률 — SSOT 단일경유
            "land_area_sqm": site.get("land_area_sqm"),
            # 실효 용적률 근거·신뢰성 정직 전파(예 "구조상한(건폐율×층수)"). 소비처(프론트/시니어
            # 자문)가 자연녹지 80%가 조례가 아닌 층수제한(4층)에서 왔음을 정직 표기하도록 additive.
            "far_basis": site.get("far_basis"),
            "far_reliable": site.get("far_reliable"),
            "legal_max_far": site.get("legal_max_far"),
            "structural_cap_pct": site.get("structural_cap_pct"),
            "floor_cap": site.get("floor_cap"),
            "floor_cap_basis": site.get("floor_cap_basis"),
            # 특이부지 게이트(가산) — None이면 일상부지. 정직 고지/할루시네이션 방지.
            "special_parcel": site.get("special_parcel"),
        }

        # 다필지(2개 이상) 통합 개발 → 최적/최고 용적률 산정
        addrs = [a.strip() for a in (parcels or []) if a and a.strip()]
        # 주 주소를 1번 필지로 포함(중복 제거)
        merged: list[str] = []
        for a in [address, *addrs]:
            if a and a.strip() and a.strip() not in merged:
                merged.append(a.strip())
        if len(merged) >= 2:
            result["multi_parcel"] = await self._analyze_multi_parcel(
                merged, primary_site=site, use_llm=use_llm
            )

        # ── 시니어 자문 모세혈관 배선 — 심의(건폐/용적 적합)·도시계획·법무사 ──
        # 인허가 결과에 시니어 전문가 판단프레임워크·근거·정량 verdict를 첨부한다. 실효(조례 반영)
        # 용적률/건폐율(actual)을 법정상한(legal_max_far가 있으면 한도)과 심의 CSP로 대조해 준수=PASS·
        # 초과=BLOCK 실판정을 산출한다(build_compliance_inputs 공용 빌더·DRY).
        # ★무회귀: with_senior=True 기본이되 attach_senior_consultation_multi는 절대 raise 안 함.
        if with_senior:
            try:
                from app.services.senior_agents.consultation_hook import (
                    attach_senior_consultation_multi,
                    build_compliance_inputs,
                )

                _far_eff = site.get("max_far")
                _bcr_eff = site.get("max_bcr")
                # 법정상한(legal_max_far)이 있으면 한도로(조례<법정 초과 검출), 없으면 실효를 한도로.
                _far_lim = site.get("legal_max_far") or _far_eff
                _sr_inputs = build_compliance_inputs(
                    far_actual=_far_eff, far_limit=_far_lim,
                    bcr_actual=_bcr_eff, bcr_limit=_bcr_eff,
                )
                result["senior_consultation"] = attach_senior_consultation_multi(
                    ["deliberation", "urban", "legal"], _sr_inputs,
                )
            except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 인허가 분석 무손상
                pass

        return result

    async def _enrich_site(self, address: str, site: dict[str, Any]) -> dict[str, Any]:
        """부지정보 보강(미제공 시 AutoZoningService).

        ★실효 용적률 SSOT 단일화(WP-U1): 실효 용적률을 자체 재계산(min(법정,조례))하지 않고
        far_tier_service.calc_effective_far(법정범위→조례→계획상한→인센티브→구조상한 계층)를
        단일경유한다. 이 헬퍼는 **구조상한(건폐율×층수)**을 마지막 계층으로 씌워, 자연/생산녹지
        (건폐 20%×4층=80% < 법정 100%) 등에서 실효 용적률을 80%로 정직 산정한다 —
        수지(feasibility_v2)·종합(comprehensive)·규제(regulation) 표면과 동일(교차 일치).
        과거 이 경로는 구조상한을 누락해 자연녹지를 100%로 과대표시, 인허가 가능성을 과대낙관했다
        (site_hallucination_guard·green_zone_dev_coverage 정책 위반 — "2026-06-19 산/임야 과대표시"
        버그클래스). 층수제한이 없는 zone(제2종일반주거 250%·일반상업 1300% 등)은
        _structural_cap_for가 (None,None,None)을 반환해 완전 무영향(안 낮아짐).
        """
        # 이미 실효 용적률이 주입된 site(설계엔진 등 SSOT 소비처)는 재계산하지 않고 소비한다.
        if site.get("zone_type") and site.get("max_far"):
            return self._attach_special_parcel(site)
        try:
            from app.services.zoning.auto_zoning_service import AutoZoningService

            az = await AutoZoningService().analyze_by_address(address)
            zone_type = az.get("zone_type") or ""
            zl = az.get("zone_limits") or {}
            legal_far = zl.get("max_far_pct") or zl.get("max_far")
            # 폴백 기본값(SSOT 산정 실패 시): 조례 미반영 법정값. far_reliable=False로 정직 표기.
            eff_far = legal_far
            eff_bcr = zl.get("max_bcr_pct") or zl.get("max_bcr")
            far_basis: str | None = None
            far_reliable = False
            structural_cap_pct = floor_cap = floor_cap_basis = None

            # 조례(실효) 한도를 OrdinanceService로 조회해 local_ordinance로 주입한다(빈값이면 법정 폴백).
            # ★정답 기준선(feasibility_service_v2:302·comprehensive:427)과 동일 경로: OrdinanceService
            #   조회 결과를 그대로 calc_effective_far에 넘겨 계층 산정에 반영한다.
            ordinance: dict[str, Any] = {}
            try:
                from app.services.land_intelligence.ordinance_service import OrdinanceService
                _o = await OrdinanceService().get_ordinance_limits(address, zone_type)
                if isinstance(_o, dict):
                    ordinance = _o
            except Exception:  # noqa: BLE001 — 조회 실패 시 법정 폴백
                pass

            # ── 실효 용적률 SSOT 단일경유(구조상한 포함) — 재계산 금지, 소비만 ──
            try:
                from app.services.land_intelligence.far_tier_service import calc_effective_far
                eff = calc_effective_far(
                    {
                        "zone_limits": zl,
                        "special_districts": az.get("special_districts") or [],
                        "local_ordinance": ordinance,
                    },
                    zone_type,
                    float(az.get("land_area_sqm") or 0) or 0,
                )
                _eff_far = eff.get("effective_far_pct")
                if _eff_far is not None and _eff_far > 0:
                    eff_far = float(_eff_far)  # 실효(구조상한 포함) 용적률
                    far_reliable = True
                _eff_bcr = eff.get("effective_bcr_pct")
                if _eff_bcr is not None and _eff_bcr > 0:
                    eff_bcr = float(_eff_bcr)
                far_basis = eff.get("far_basis")
                structural_cap_pct = eff.get("structural_cap_pct")
                floor_cap = eff.get("floor_cap")
                floor_cap_basis = eff.get("floor_cap_basis")
            except Exception:  # noqa: BLE001 — 산정 실패 시 법정 폴백 유지(far_reliable=False)
                pass

            site = {
                "zone_type": az.get("zone_type"),
                "max_bcr": eff_bcr,
                "max_far": eff_far,  # 실효(구조상한 포함) 용적률 — SSOT calc_effective_far 단일경유
                "legal_max_far": legal_far,
                "far_basis": far_basis,  # 실효 산정 근거(예 "구조상한(건폐율×층수)") — 정직 전파
                "far_reliable": far_reliable,
                "structural_cap_pct": structural_cap_pct,
                "floor_cap": floor_cap,
                "floor_cap_basis": floor_cap_basis,
                "land_area_sqm": az.get("land_area_sqm"),
                "land_category": az.get("land_category"),  # 지목(특이부지 감지 입력)
                "special_districts": az.get("special_districts"),
                **{k: v for k, v in site.items() if v is not None},
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("부지정보 수집 실패", err=str(e)[:80], address=address[:40])
        return self._attach_special_parcel(site)

    @staticmethod
    def _special_parcel_grounding(sp: dict[str, Any] | None) -> str:
        """특이부지 감지 결과 → LLM 프롬프트 그라운딩 문자열(없으면 '특이사항 없음').

        개발가능성·해결가능성과 요인별 필요인허가(예: 산지전용허가)·선행절차를 명시해,
        특이부지를 일반 개발지처럼 단정하지 않도록 모델을 사실에 묶는다.
        """
        if not sp:
            return "특이사항 없음(일상적 개발부지)"
        lines: list[str] = [
            f"개발가능성={sp.get('severity_label') or sp.get('developability')}",
            f"해결가능성={sp.get('resolvable')}",
        ]
        for f in (sp.get("factors") or [])[:4]:
            prereq = ", ".join(f.get("permit_prerequisites") or [])
            lines.append(
                f"· {f.get('category')}: {(f.get('implications') or [''])[0]}"
                + (f" [필요절차: {prereq}]" if prereq else "")
            )
        if sp.get("honest_disclosure"):
            lines.append(f"⚠ {sp['honest_disclosure']}")
        return " / ".join(lines)

    @staticmethod
    def _attach_special_parcel(site: dict[str, Any]) -> dict[str, Any]:
        """지목·용도지역·구역으로 특이부지(산지·학교용지·GB·맹지 등)를 감지해 site에 가산.

        LLM 그라운딩에 개발가능성·해결가능성·필요인허가·특이요인을 명시 주입해, 비일상 토지를
        일반 개발지처럼 분석하는 할루시네이션(예: 산지에 산지전용허가 누락)을 방지한다.
        규칙기반(detect_special_parcel)·가산 필드라 기존 동작 무손상. 접도정보는 미수집이라
        road_contact/road_width_m 미전달(None)로 맹지 오탐을 막는다.
        """
        try:
            from app.services.zoning.special_parcel import detect_special_parcel

            sp = detect_special_parcel({
                "zone_type": site.get("zone_type"),
                "land_category": site.get("land_category"),
                "special_districts": site.get("special_districts") or [],
            })
            if sp:
                site["special_parcel"] = sp
        except Exception:  # noqa: BLE001 — 감지 실패해도 인허가 분석은 계속(graceful)
            pass
        return site

    @staticmethod
    async def _ordinance_text(address: str, site: dict[str, Any]) -> str:
        try:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            ordn = await OrdinanceService().get_ordinance_limits(address, site.get("zone_type") or "")
            if isinstance(ordn, dict) and ordn:
                return (
                    f"건폐율 {ordn.get('effective_bcr') or ordn.get('ordinance_bcr') or '-'}%, "
                    f"용적률 {ordn.get('effective_far') or ordn.get('ordinance_far') or '-'}% "
                    f"(출처 {ordn.get('source', '-')})"
                )
        except Exception:  # noqa: BLE001
            pass
        return "-"

    async def _analyze_multi_parcel(
        self, addresses: list[str], primary_site: dict[str, Any], use_llm: bool = True
    ) -> dict[str, Any]:
        """용도지역이 다른 여러 필지를 통합 개발할 때 최적·최고 용적률 산정."""
        import asyncio

        # 각 필지 부지정보 보강(주 필지는 재사용)
        enriched: list[dict[str, Any]] = []
        sites = await asyncio.gather(
            *[self._enrich_site(a, {}) for a in addresses[1:]], return_exceptions=True
        )
        site_list = [primary_site, *[(s if isinstance(s, dict) else {}) for s in sites]]
        for addr, s in zip(addresses, site_list, strict=False):
            area = s.get("land_area_sqm")
            far = s.get("max_far")
            enriched.append({
                "address": addr,
                "zone_type": s.get("zone_type"),
                "max_far": far,
                "max_bcr": s.get("max_bcr"),
                "land_area_sqm": area,
            })

        blended = self._blended_far(enriched)
        total_area = sum(p["land_area_sqm"] or 0 for p in enriched)
        # 명시실행: use_llm=False면 규칙기반(가중평균) 폴백만 반환.
        llm = (
            await self._llm_multi_parcel(enriched, blended, total_area)
            if use_llm
            else self._multi_parcel_fallback(blended)
        )
        return {"parcels": enriched, **llm}

    @staticmethod
    def _num(v: Any) -> float | None:
        """숫자/숫자형 문자열만 float로, 그 외('데이터 없음' 등)는 None."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            import re

            m = re.search(r"-?\d+(?:\.\d+)?", v.replace(",", ""))
            if m:
                return float(m.group())
        return None

    @staticmethod
    def _blended_far(parcels: list[dict[str, Any]]) -> float | None:
        """면적가중평균 용적률(국토계획법 시행령 제84조). 면적 누락 시 단순평균."""
        # TODO(계약표준화 후속): 정본 _aggregate_integrated_zoning(면적가중 blended_far_*_pct)
        #   위임 검토 — 값 산출 경로 변경이라 이번(계약 shape 정규화) 라운드 제외.
        #   scenario_simulator._blended_far 와 동일 산식이 3벌 존재(정본 일원화 대상).
        weighted = [(p["land_area_sqm"], p["max_far"]) for p in parcels if p.get("max_far")]
        if not weighted:
            return None
        if all(a for a, _ in weighted):
            tot = sum(a for a, _ in weighted)
            return round(sum(a * f for a, f in weighted) / tot, 1) if tot else None
        # 면적 일부/전부 누락 → 단순평균(근사)
        fars = [f for _, f in weighted]
        return round(sum(fars) / len(fars), 1)

    async def _llm_analyze(self, address: str, site: dict, ordinance: str) -> dict[str, Any]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm

            llm = get_llm(timeout=70, max_tokens=4000)
            user = _USER_TMPL.format(
                address=address,
                zone_type=site.get("zone_type") or "미상",
                max_bcr=site.get("max_bcr") or "-",
                max_far=site.get("max_far") or "-",
                far_basis=site.get("far_basis") or "법정/조례 상한",
                land_area_sqm=site.get("land_area_sqm") or "-",
                ordinance=ordinance,
                special=", ".join(site.get("special_districts") or []) if isinstance(site.get("special_districts"), list) else (site.get("special_districts") or "-"),
                special_parcel=self._special_parcel_grounding(site.get("special_parcel")),
                methods=", ".join(DEV_METHODS),
            )
            resp = await llm.ainvoke([SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)])
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="permit")
            from app.services.ai.llm_json import parse_llm_json
            data = parse_llm_json(resp.content if hasattr(resp, "content") else str(resp))
            if not isinstance(data.get("methods"), list):
                raise ValueError("methods 누락")
            data["ai"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("인허가 LLM 분석 실패, 폴백", err=str(e)[:100])
            return self._fallback(site)

    @staticmethod
    def _fallback(site: dict) -> dict[str, Any]:
        zone = site.get("zone_type") or "미상"
        methods = []
        for m in DEV_METHODS:
            methods.append({
                "method": m,
                "possibility": "중",
                "score": 50,
                "key_laws": ["국토계획법 제76조(용도지역 행위제한)", "건축법"],
                "issues": [f"{zone}의 허용용도·건폐율/용적률 한도 확인 필요"],
                "solutions": ["지구단위계획·조례 확인 후 세부 검토"],
            })
        return {
            "ai": False,
            "summary": f"{zone} 기준 개발방식별 인허가 환경 — 상세 분석은 AI 연결 후 제공됩니다.",
            "methods": methods,
            "recommendation": "용도지역 허용용도와 조례를 우선 확인하세요.",
        }

    async def _llm_multi_parcel(
        self, parcels: list[dict[str, Any]], blended: float | None, total_area: float
    ) -> dict[str, Any]:
        """다필지 통합 개발 최적·최고 용적률 LLM 산정. 실패 시 가중평균 기반 폴백."""
        parcel_lines = "\n".join(
            f"- {i + 1}) {p['address']} | 용도지역 {p.get('zone_type') or '미상'} | "
            f"용적률한도 {p.get('max_far') or '-'}% | 면적 {round(p['land_area_sqm']) if p.get('land_area_sqm') else '-'}㎡"
            for i, p in enumerate(parcels)
        )
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm

            # ★max_tokens 4000: 단일필지 _llm_analyze(4000)와 동일 캡 — 2500은 다필지 한국어
            #   JSON 절단→파싱 실패→폴백 강등 위험(규제분석 2500 캡 절단 실측과 동일 클래스).
            llm = get_llm(timeout=70, max_tokens=4000)
            user = _MULTI_TMPL.format(
                n=len(parcels),
                total_area=round(total_area) if total_area else "-",
                parcel_lines=parcel_lines,
                blended_far=blended if blended is not None else "-",
            )
            resp = await llm.ainvoke(
                [SystemMessage(content=_MULTI_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="permit")
            from app.services.ai.llm_json import parse_llm_json
            data = parse_llm_json(resp.content if hasattr(resp, "content") else str(resp))
            data["ai"] = True
            # 용적률 3종은 숫자 또는 None으로 정규화(LLM이 "데이터 없음" 등 문자열 반환 대비)
            for k in ("blended_far", "optimal_far", "max_far"):
                data[k] = self._num(data.get(k))
            # 산정 누락 시 가중평균으로 보정
            if data.get("blended_far") is None and blended is not None:
                data["blended_far"] = blended
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("다필지 용적률 LLM 산정 실패, 폴백", err=str(e)[:100])
            return self._multi_parcel_fallback(blended)

    @staticmethod
    def _multi_parcel_fallback(blended: float | None) -> dict[str, Any]:
        """다필지 통합 용적률 규칙기반(가중평균) 폴백. LLM 미사용/실패 공용."""
        return {
            "ai": False,
            "blended_far": blended,
            "optimal_far": blended,
            "max_far": None,
            "far_rationale": (
                "용도지역이 다른 필지를 통합 개발 시 국토계획법 시행령 제84조에 따라 면적가중평균 "
                "용적률이 기본 적용됩니다. 지구단위계획·결합건축·종상향 등 상향수단은 AI 연결 후 상세 제시됩니다."
            ),
            "far_key_laws": [
                "국토의 계획 및 이용에 관한 법률 시행령 제84조(둘 이상 용도지역 걸친 대지)",
                "건축법 제77조의4(결합건축)",
            ],
            "integration_issues": ["합필 요건·용도지역 경계 정합·조례 확인 필요"],
            "integration_solutions": ["지구단위계획 수립 검토 후 통합 용적률 상향 협의"],
        }
