"""인.허가 AI 분석 서비스.

부지분석(용도지역·건폐율/용적률·면적) + 지자체 조례 + 상위법령을 종합하여,
개발방식별 인허가 가능성·근거법령·문제점·해결방안을 LLM(Claude)으로 분석한다.

- 상위법령: 국토의 계획 및 이용에 관한 법률, 건축법, 주택법, 도시개발법,
  도심 공공주택 복합사업(공공주택특별법), 도시 및 주거환경정비법
- 도시·군 관리계획 / 도시·군 계획 / 지구단위계획, 지자체 조례 우선순위 반영
- LLM 실패 시 규칙기반 폴백(graceful)
"""

import json
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
4. 반드시 JSON만 출력(마크다운·설명문 금지)."""

_USER_TMPL = """\
아래 부지정보를 바탕으로 각 개발방식의 인허가 가능성을 분석해 JSON으로만 답하세요.

## 부지정보
- 주소: {address}
- 용도지역: {zone_type}
- 건폐율 한도: {max_bcr}%
- 용적률 한도: {max_far}%
- 대지면적: {land_area_sqm}㎡
- 지자체 조례: {ordinance}
- 특별지구/지정: {special}

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


class PermitAnalysisService:
    async def analyze(self, address: str, site: dict[str, Any] | None = None) -> dict[str, Any]:
        site = site or {}
        # 부지정보 보강(미제공 시 AutoZoningService)
        if not site.get("zone_type"):
            try:
                from app.services.zoning.auto_zoning_service import AutoZoningService

                az = await AutoZoningService().analyze_by_address(address)
                zl = az.get("zone_limits") or {}
                site = {
                    "zone_type": az.get("zone_type"),
                    "max_bcr": zl.get("max_bcr_pct") or zl.get("max_bcr"),
                    "max_far": zl.get("max_far_pct") or zl.get("max_far"),
                    "land_area_sqm": az.get("land_area_sqm"),
                    "special_districts": az.get("special_districts"),
                    **site,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("부지정보 수집 실패", err=str(e)[:80])

        # 조례(선택)
        ordinance_txt = "-"
        try:
            from app.services.land_intelligence.ordinance_service import OrdinanceService

            ordn = await OrdinanceService().get_ordinance_limits(address, site.get("zone_type") or "")
            if isinstance(ordn, dict) and ordn:
                ordinance_txt = (
                    f"건폐율 {ordn.get('effective_bcr') or ordn.get('ordinance_bcr') or '-'}%, "
                    f"용적률 {ordn.get('effective_far') or ordn.get('ordinance_far') or '-'}% "
                    f"(출처 {ordn.get('source', '-')})"
                )
        except Exception:  # noqa: BLE001
            pass

        result = await self._llm_analyze(address, site, ordinance_txt)
        result["site"] = {
            "address": address,
            "zone_type": site.get("zone_type"),
            "max_bcr": site.get("max_bcr"),
            "max_far": site.get("max_far"),
            "land_area_sqm": site.get("land_area_sqm"),
        }
        return result

    async def _llm_analyze(self, address: str, site: dict, ordinance: str) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(timeout=70, max_tokens=4000)
            user = _USER_TMPL.format(
                address=address,
                zone_type=site.get("zone_type") or "미상",
                max_bcr=site.get("max_bcr") or "-",
                max_far=site.get("max_far") or "-",
                land_area_sqm=site.get("land_area_sqm") or "-",
                ordinance=ordinance,
                special=", ".join(site.get("special_districts") or []) if isinstance(site.get("special_districts"), list) else (site.get("special_districts") or "-"),
                methods=", ".join(DEV_METHODS),
            )
            resp = await llm.ainvoke([SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)])
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
                raw = raw.strip()
            data = json.loads(raw)
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
