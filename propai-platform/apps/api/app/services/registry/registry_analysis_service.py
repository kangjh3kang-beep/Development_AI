"""부동산 등기정보 분석 — 법무사·변호사 에이전트 권리분석.

등기부등본(CODEF 조회 또는 직접 입력 텍스트)을 법무사/변호사 관점에서 분석해
소유정보·소유기간·매입금액·보유지분·가등기·압류/가압류·근저당·매도청구 가능여부 등
권리관계를 구조화해 제공한다. LLM 실패 시 graceful 폴백.
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_SYSTEM = """\
당신은 부동산 등기·권리분석 전문가 패널(법무사 20년 + 부동산 전문 변호사)입니다.
제시된 부동산등기부등본 내용만 근거로 권리관계를 정확히 분석합니다.
- 갑구(소유권): 소유자·지분·소유권 변동·거래가액·가등기·가처분·압류·가압류·경매개시
- 을구(소유권 이외): 근저당권(채권최고액·근저당권자)·전세권·지상권 등
원칙: 등기 내용에 있는 사실만 사용, 없으면 '기재 없음'. 추측·과장 금지. 법률자문이 아닌
참고용 분석임을 전제. 반드시 JSON만 출력."""

_TMPL = """\
아래 부동산등기부등본 내용을 법무사·변호사 관점에서 분석해 JSON으로만 답하세요.
{addr_line}
## 등기부 내용
{registry}

## 출력 JSON 스키마
{{
  "ownership": {{
    "current_owner": "현재 소유자(공동소유면 전원)",
    "share": "보유 지분(예: 단독, 1/2 등)",
    "acquisition_date": "소유권 취득일(등기원인일/접수일)",
    "acquisition_cause": "취득 원인(매매·상속·증여 등)",
    "acquisition_price": "거래가액(매매시, 기재 있으면)",
    "ownership_period": "현 소유자 보유기간(취득일~현재 추정)"
  }},
  "provisional_registration": {{"exists": true/false, "detail": "가등기 내용(있으면)"}},
  "seizure": [{{"type": "압류|가압류|경매개시|가처분", "holder": "권리자", "detail": "내용", "date": "일자"}}],
  "mortgage": [{{"max_claim": "채권최고액", "mortgagee": "근저당권자", "date": "설정일"}}],
  "other_rights": ["전세권·지상권 등 기타 권리(있으면)"],
  "right_to_demand_sale": {{"possible": "가능|조건부|불가|판단보류", "reason": "근거(소유구조·권리관계 관점)"}},
  "rights_analysis": "권리관계 종합 분석(3~5문장)",
  "risks": ["거래·개발상 권리 리스크 1~4개"],
  "safety_grade": "안전|주의|위험",
  "summary": "한줄 요약"
}}
"""


def _registry_text_from_codef(reg: dict[str, Any]) -> str:
    """CODEF 등기부 응답(구조화)에서 분석용 텍스트 구성."""
    parts: list[str] = []
    if reg.get("doc_title"):
        parts.append(f"문서: {reg['doc_title']}")
    if reg.get("owner"):
        parts.append(f"소유자(요약): {reg['owner']}")
    if reg.get("registry_office"):
        parts.append(f"관할등기소: {reg['registry_office']}")
    raw = reg.get("raw") or reg
    # 등기사항 요약/내용 직렬화(있는 만큼)
    for entry in (raw.get("resRegisterEntriesList") or []):
        for sm in (entry.get("resRegistrationSumList") or []):
            t = sm.get("resType", "")
            for cl in (sm.get("resContentsList") or []):
                for dl in (cl.get("resDetailList") or []):
                    if dl.get("resContents"):
                        parts.append(f"[{t}] {dl['resContents']}")
        for his in (entry.get("resRegistrationHisList") or []):
            t = f"{his.get('resType','')}/{his.get('resType1','')}"
            for cl in (his.get("resContentsList") or []):
                for dl in (cl.get("resDetailList") or []):
                    if dl.get("resContents"):
                        parts.append(f"[{t}] {dl['resContents']}")
    return "\n".join(parts)[:8000]


class RegistryAnalysisService:
    async def _land_info(self, address: str | None, pnu: str | None) -> dict[str, Any] | None:
        """토지 소유구분·지목·면적·공시지가·용도지역(VWorld/공공데이터). 등기부 미연동 시에도 제공."""
        if not address and not pnu:
            return None
        try:
            from app.services.external_api.vworld_service import VWorldService
            from app.services.zoning.auto_zoning_service import AutoZoningService

            vworld = VWorldService()
            owner_type = None
            land_area = land_category = official_price = zone_type = None
            effective_pnu = pnu
            if address:
                az = await AutoZoningService().analyze_by_address(address)
                effective_pnu = effective_pnu or az.get("pnu")
                zone_type = az.get("zone_type")
                land_area = az.get("land_area_sqm")
                land_category = az.get("land_category")
                official_price = az.get("official_price_per_sqm")
            if effective_pnu:
                li = await vworld.get_land_info(effective_pnu)
                if li:
                    props = li.get("properties") or {}
                    owner_type = props.get("owner_type")
                    land_area = land_area or props.get("area")
                    land_category = land_category or props.get("jimok")
                lc = await vworld.get_land_characteristics(effective_pnu)
                if lc:
                    land_area = land_area or lc.get("area_sqm")
                    land_category = land_category or lc.get("land_category")
                    official_price = official_price or lc.get("official_price_per_sqm")
                    zone_type = zone_type or lc.get("zone_type")
            return {
                "pnu": effective_pnu,
                "owner_type": owner_type,  # 소유구분(개인/국·공유 등) — 등기부 외 공부상
                "land_category": land_category,
                "land_area_sqm": land_area,
                "official_price_per_sqm": official_price,
                "zone_type": zone_type,
                "note": "공부상 소유구분·토지특성(소유자 성명·지분은 등기부 분석 결과 참조)",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("토지정보 조회 실패", err=str(e)[:80])
            return None

    async def analyze(
        self,
        address: str | None = None,
        pnu: str | None = None,
        registry_text: str | None = None,
    ) -> dict[str, Any]:
        origin = None
        source = None
        fetched_meta = None
        # 토지 소유구분·특성(항상 제공)
        land = await self._land_info(address, pnu)

        if registry_text and registry_text.strip():
            source = registry_text.strip()[:8000]
            origin = "manual"
        else:
            # CODEF 등 연동 조회 시도
            from app.services.registry.registry_service import RegistryService

            reg = await RegistryService().get_one(pnu=pnu, address=address)
            st = reg.get("status")
            if st == "ok":
                source = _registry_text_from_codef(reg)
                origin = reg.get("code") and "codef" or "codef"
                fetched_meta = {
                    "owner": reg.get("owner"), "registry_office": reg.get("registry_office"),
                    "doc_title": reg.get("doc_title"), "has_pdf": reg.get("has_pdf"),
                    "pdf_base64": reg.get("pdf_base64"),
                }
            else:
                # 등기부 데이터 미확보 — 토지정보는 제공 + 직접 입력 유도
                return {
                    "status": st or "not_available",
                    "origin": "none",
                    "land": land,
                    "message": (reg.get("message")
                                or "등기부 데이터를 가져오지 못했습니다. 등기부등본 내용을 직접 입력하거나 "
                                   "등기부 API(CODEF) 설정을 완료하세요."),
                    "ai": None,
                }

        if not source:
            return {"status": "empty", "origin": origin, "land": land,
                    "message": "분석할 등기부 내용이 없습니다.", "ai": None}

        ai = await self._llm(address, source)
        return {"status": "ok", "origin": origin, "land": land, "fetched": fetched_meta, "ai": ai}

    async def _llm(self, address: str | None, registry: str) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            addr_line = f"## 대상 부동산\n- 주소: {address}\n" if address else ""
            user = _TMPL.format(addr_line=addr_line, registry=registry)
            llm = get_llm(timeout=70, max_tokens=2500)
            resp = await llm.ainvoke(
                [SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
            data = json.loads(raw.strip())
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("등기 권리분석 LLM 실패, 폴백", err=str(e)[:100])
            return {
                "generated": False,
                "ownership": {}, "provisional_registration": {"exists": None},
                "seizure": [], "mortgage": [], "other_rights": [],
                "right_to_demand_sale": {"possible": "판단보류", "reason": "등기 내용 확인 필요"},
                "rights_analysis": "AI 권리분석은 일시적으로 제공되지 않습니다. 등기부 내용을 확인하세요.",
                "risks": [], "safety_grade": "주의", "summary": "분석 불가",
            }
