"""부동산 규제 종합 분석 서비스 (규제 계층 대시보드).

부지의 적용 규제를 상위법령 → 도시·군계획 → 지자체 조례 → 개별 적용규제의
계층 구조로 정리하고, 정량 한도(건폐/용적/높이/주차)와 LLM 통합 해석을 제공한다.

데이터 소스: LandInfoService.collect_comprehensive (VWORLD 토지이용계획 districts +
토지특성 + 조례 + zone_limits). 법령 인용은 큐레이션 정적 매핑(할루시네이션 방지),
서술 해석만 LLM.
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 적용규제 영향도 분류(district name 키워드)
_HIGH = ["토지거래", "개발제한", "군사시설", "비행안전", "문화재", "정화구역", "상수원", "수변구역"]
_MID = ["과밀억제", "지구단위", "재정비촉진", "정비구역", "고도지구", "방화지구", "경관지구",
        "최고높이", "리모델링", "역세권", "성장관리", "지구단위계획구역"]


def _impact(name: str) -> str:
    for k in _HIGH:
        if k in name:
            return "상"
    for k in _MID:
        if k in name:
            return "중"
    return "하"


_SYSTEM = """\
당신은 한국 부동산개발 인허가·도시계획 규제 전문가입니다.
제공된 부지의 용도지역·적용규제·조례 데이터만 근거로, 개발 관점의 규제 영향을
명료하게 해석합니다. 데이터에 없는 수치·법조문은 만들지 말고, JSON만 출력합니다."""

_USER_TMPL = """\
아래 부지 규제 데이터를 바탕으로 개발 관점의 통합 규제 해석을 JSON으로만 답하세요.

## 부지
- 주소: {address}
- 용도지역: {zone_type}{zone_2}
- 대지면적: {area}㎡
- 건폐율 한도(법정/조례/실효): {bcr}
- 용적률 한도(법정/조례/실효): {far}
- 적용 규제·지구·구역: {districts}

## 출력 JSON 스키마
{{
  "summary": "이 토지 규제 환경 종합(3~4문장, 개발 난이도·핵심 관점)",
  "key_constraints": ["개발에 결정적인 핵심 제약 2~4개(가장 영향 큰 것 우선)"],
  "dev_impact": "용적률·용도·인허가 측면에서 개발사업에 미치는 영향(2~3문장)",
  "strategies": ["규제 대응·완화·활용 전략 2~4개"],
  "opportunities": ["규제상 기회요인 1~3개"],
  "risks": ["규제상 리스크 1~3개"]
}}
"""


class RegulationAnalysisService:
    async def analyze(
        self, address: str, pnu: str | None = None, use_llm: bool = True
    ) -> dict[str, Any]:
        from app.services.land_intelligence.land_info_service import LandInfoService

        comp = await LandInfoService().collect_comprehensive(address, pnu=pnu)

        zone_type = comp.get("zone_type") or ""
        zone_2 = comp.get("zone_type_secondary") or ""
        zl = comp.get("zone_limits") or {}
        lr = comp.get("land_register") or {}
        lc = comp.get("land_characteristics") or {}
        lup = comp.get("land_use_plan") or {}
        districts_raw = lup.get("districts") or comp.get("special_districts") or []
        area = comp.get("land_area_sqm") or lr.get("area_sqm") or lc.get("area_sqm")

        # ── 정량 한도 ──
        limits = self._limits(zl)

        # ── 적용 규제 전수(영향도) ──
        districts = []
        seen = set()
        for d in districts_raw:
            name = (d.get("district_name") if isinstance(d, dict) else str(d)) or ""
            if not name or name in seen:
                continue
            seen.add(name)
            districts.append({
                "name": name,
                "code": d.get("district_code", "") if isinstance(d, dict) else "",
                "impact": _impact(name),
                "status": d.get("conflict_status", "") if isinstance(d, dict) else "",
                "register_date": d.get("register_date", "") if isinstance(d, dict) else "",
            })
        # 영향도 정렬(상>중>하)
        order = {"상": 0, "중": 1, "하": 2}
        districts.sort(key=lambda x: order.get(x["impact"], 3))

        # ── 규제 계층 ──
        sigungu = self._sigungu(address)
        hierarchy = self._hierarchy(zone_type, zone_2, districts, sigungu, zl)

        result: dict[str, Any] = {
            "address": address,
            "pnu": comp.get("pnu") or pnu,
            "zone_type": zone_type or None,
            "zone_type_secondary": zone_2 or None,
            "land_area_sqm": area,
            "land_category": lr.get("land_category") or lc.get("land_category"),
            "land_use_situation": lr.get("land_use_situation") or lc.get("land_use_situation"),
            "limits": limits,
            "hierarchy": hierarchy,
            "districts": districts,
            "coordinates": comp.get("coordinates"),
        }

        if use_llm:
            result["ai"] = await self._llm(address, zone_type, zone_2, area, limits, districts)
        else:
            result["ai"] = None
        return result

    @staticmethod
    def _limits(zl: dict) -> dict[str, Any]:
        def trio(legal_k: str, ord_k: str, eff_k: str) -> dict[str, Any]:
            return {
                "legal": zl.get(legal_k),
                "ordinance": zl.get(ord_k),
                "effective": zl.get(eff_k) or zl.get(ord_k) or zl.get(legal_k),
                "unit": "%",
            }

        return {
            "bcr": trio("max_bcr_pct", "ordinance_bcr_pct", "effective_bcr_pct"),
            "far": trio("max_far_pct", "ordinance_far_pct", "effective_far_pct"),
            "height": {"value": zl.get("max_height_m"), "unit": "m"},
            "parking": {"description": "주차장법 시행령 별표1 부설주차장 설치기준 적용(용도·면적별 산정)"},
        }

    @staticmethod
    def _sigungu(address: str) -> str:
        parts = (address or "").split()
        for i, p in enumerate(parts):
            if p.endswith(("시", "군", "구")) and i > 0:
                return p
        return parts[1] if len(parts) > 1 else (parts[0] if parts else "")

    def _hierarchy(
        self, zone: str, zone2: str, districts: list[dict], sigungu: str, zl: dict
    ) -> list[dict]:
        z = f"{zone} {zone2}"
        # 1) 상위법령
        laws = [
            {"name": "국토의 계획 및 이용에 관한 법률", "ref": "제76·77·78조",
             "desc": "용도지역 행위제한·건폐율·용적률 상한"},
            {"name": "건축법", "ref": "제55·56·60·61조",
             "desc": "건폐율·용적률·높이·일조 등 대지 안의 건축 제한"},
            {"name": "주차장법", "ref": "시행령 별표1",
             "desc": "용도·면적별 부설주차장 설치 기준"},
        ]
        if any(k in z for k in ["주거", "준주거"]):
            laws.append({"name": "주택법", "ref": "제15조",
                         "desc": "30세대 이상 공동주택 사업계획승인 대상"})
        if any("정비" in d["name"] or "재정비촉진" in d["name"] or "재개발" in d["name"]
               for d in districts):
            laws.append({"name": "도시 및 주거환경정비법", "ref": "-",
                         "desc": "정비구역 내 정비사업 절차·기준"})
        if any("도시개발" in d["name"] or "택지" in d["name"] for d in districts):
            laws.append({"name": "도시개발법", "ref": "-", "desc": "도시개발구역 사업 절차"})

        # 2) 도시·군계획
        plans = [
            {"name": "도시·군기본계획 / 도시·군관리계획", "ref": "-",
             "desc": "용도지역·기반시설·도시계획시설 등 상위 공간계획"},
        ]
        for d in districts:
            if any(k in d["name"] for k in ["지구단위", "재정비촉진", "정비구역", "도시개발", "성장관리"]):
                plans.append({"name": d["name"], "ref": d.get("code", ""),
                              "desc": "지구단위계획 등 세부 도시관리계획(별도 지침 적용)"})

        # 3) 지자체 조례
        ords = [
            {"name": f"{sigungu} 도시계획 조례", "ref": "-",
             "desc": (f"건폐율 {zl.get('ordinance_bcr_pct') or '-'}% · "
                      f"용적률 {zl.get('ordinance_far_pct') or '-'}% 등 조례 강화 한도")},
            {"name": f"{sigungu} 건축 조례", "ref": "-", "desc": "대지·높이·주차 등 지역 건축 기준"},
        ]

        return [
            {"level": "상위법령", "items": laws},
            {"level": "도시·군계획 / 지구단위계획", "items": plans},
            {"level": "지자체 조례", "items": ords},
            {"level": "개별 적용 규제·지구·구역",
             "items": [{"name": d["name"], "ref": d.get("code", ""),
                        "desc": f"영향도 {d['impact']}" + (f" · {d['status']}" if d.get("status") else "")}
                       for d in districts]},
        ]

    async def _llm(
        self, address: str, zone: str, zone2: str, area: Any,
        limits: dict, districts: list[dict],
    ) -> dict[str, Any]:
        try:
            from app.services.ai.llm_provider import get_llm
            from app.services.ai.base_interpreter import GROUNDING_RULE
            from langchain_core.messages import HumanMessage, SystemMessage

            bcr = limits["bcr"]; far = limits["far"]
            user = _USER_TMPL.format(
                address=address,
                zone_type=zone or "미상",
                zone_2=f" + {zone2}" if zone2 else "",
                area=round(area) if area else "-",
                bcr=f"{bcr.get('legal') or '-'}/{bcr.get('ordinance') or '-'}/{bcr.get('effective') or '-'}",
                far=f"{far.get('legal') or '-'}/{far.get('ordinance') or '-'}/{far.get('effective') or '-'}",
                districts=", ".join(f"{d['name']}({d['impact']})" for d in districts[:20]) or "-",
            )
            llm = get_llm(timeout=60, max_tokens=2500)
            resp = await llm.ainvoke(
                [SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            raw = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                raw = raw[4:] if raw.lower().startswith("json") else raw
                raw = raw.strip()
            data = json.loads(raw)
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("규제 LLM 해석 실패, 폴백", err=str(e)[:100])
            return {
                "generated": False,
                "summary": f"{zone or '미상'} 기준 적용 규제를 계층별로 정리했습니다. AI 통합 해석은 일시적으로 제공되지 않습니다.",
                "key_constraints": [d["name"] for d in districts if d["impact"] == "상"][:4],
                "dev_impact": "용도지역 허용용도와 조례 강화 한도, 중첩 규제를 우선 확인하세요.",
                "strategies": ["지구단위계획·조례 확인", "영향도 높은 규제 사전 협의"],
                "opportunities": [],
                "risks": [d["name"] for d in districts if d["impact"] in ("상", "중")][:3],
            }
