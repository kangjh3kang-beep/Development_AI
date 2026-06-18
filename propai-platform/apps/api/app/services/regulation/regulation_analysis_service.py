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

        # 신뢰 레이어(additive): 계층 각 노드에 법령링크(legal_refs) 가산 + 한도 근거 트레이스(evidence).
        # zone_type 미확정 시 해당 노드 legal_refs는 빈 배열(가짜 링크 금지). url은 레지스트리 출력만.
        self._attach_node_legal_refs(hierarchy, zone_type, sigungu, zl)
        evidence = self._build_evidence(zone_type, limits, sigungu)

        land_category = lr.get("land_category") or lc.get("land_category")

        # 특이부지 감지(additive) — 지목 기반 비일상 토지(임야·농지·학교용지 등) 게이트를
        # 규제 계층 응답에도 부착한다. 정량 한도(FAR 등) 표기는 변경하지 않고, is_special일
        # 때만 별도 노드/경고로 가산해 "법정 한도가 그대로 실현되지 않을 수 있음"을 정직 고지한다.
        # 접도(road)는 규제분석 단계에서 미수집이라 None 전달(맹지 판정은 건너뜀).
        special_parcel = self._detect_special(land_category, zone_type, districts_raw)

        result: dict[str, Any] = {
            "address": address,
            "pnu": comp.get("pnu") or pnu,
            "zone_type": zone_type or None,
            "zone_type_secondary": zone_2 or None,
            "land_area_sqm": area,
            "land_category": land_category,
            "land_use_situation": lr.get("land_use_situation") or lc.get("land_use_situation"),
            "limits": limits,
            "hierarchy": hierarchy,
            "districts": districts,
            "coordinates": comp.get("coordinates"),
            # 한도(건폐/용적) 산출 근거 트레이스 — EvidencePanel 소비 구조. zone_type 미확정 시 빈 배열.
            "evidence": evidence,
        }
        # is_special일 때만 부착(무목업) — 일상 부지면 키 자체를 넣지 않아 하위호환·무회귀.
        if special_parcel:
            result["special_parcel"] = special_parcel

        if use_llm:
            result["ai"] = await self._llm(address, zone_type, zone_2, area, limits, districts)
        else:
            result["ai"] = None
        return result

    @staticmethod
    def _detect_special(
        land_category: str | None, zone_type: str, districts_raw: list
    ) -> dict[str, Any] | None:
        """지목·용도지역·구역으로 특이부지 감지(zoning.special_parcel 재사용).

        규제분석 단계에서 미수집인 접도(road_contact/road_width_m)는 None으로 넘겨
        맹지 판정을 건너뛴다(가짜 판정 방지). special_districts는 land_use_plan의
        districts 원본 이름 목록으로 구성한다. 예외 시 None(graceful·무회귀).
        """
        try:
            from app.services.zoning.special_parcel import detect_special_parcel

            sd = []
            for d in districts_raw or []:
                name = (d.get("district_name") if isinstance(d, dict) else str(d)) or ""
                if name:
                    sd.append(name)
            return detect_special_parcel({
                "land_category": land_category,
                "zone_type": zone_type,
                "special_districts": sd,
                "road_contact": None,
                "road_width_m": None,
            })
        except Exception:  # noqa: BLE001
            return None

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

    # ─────────────────────────────────────────────────────────────────────────
    # 신뢰 레이어(additive): 계층 노드별 법령링크(legal_refs) + 한도 산출 근거(evidence).
    # 기존 hierarchy/items 필드는 1개도 변경하지 않고 각 level에 legal_refs[]만 가산한다.
    # law.go.kr URL은 전적으로 legal_reference_registry.get_legal_refs 출력만 사용하며
    # (여기서 URL 직접 조립 금지), zone_type 미확정 시 zone 종속 노드 legal_refs는 빈 배열.
    # 규제 항목 ↔ 레지스트리 키 매핑:
    #   건폐율→bcr_limit, 용적률→far_limit, 용도제한→zone_use, 주차→parking_min,
    #   지구단위→district_unit_plan, 조례→ordinance_bcr/ordinance_far.
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _level_ref_keys(level_name: str, zone_known: bool, has_du_plan: bool) -> list[str]:
        """계층 레벨명 → 부착할 레지스트리 근거키 목록(중복 없는 순서 보존).

        zone_type 미확정(zone_known=False) 시 zone 종속 한도 근거는 부착하지 않는다
        (건폐/용적/용도 한도는 용도지역이 있어야 의미 있음 → 빈 배열로 정직 표기).
        """
        if level_name == "상위법령":
            # 용도지역 행위제한·건폐율·용적률(국토계획법/시행령) + 건축 한도 + 주차 기준.
            base = ["zone_use", "bcr_limit", "far_limit", "bldg_far", "parking_min"]
            return base if zone_known else ["parking_min"]
        if level_name == "도시·군계획 / 지구단위계획":
            # 지구단위계획 근거는 해당 구역이 실제 있을 때만(가짜 링크 방지).
            return ["district_unit_plan"] if has_du_plan else []
        if level_name == "지자체 조례":
            # 조례 건폐/용적 강화 한도 — sigungu 치환 후 url 승격(미상이면 pending).
            return ["ordinance_bcr", "ordinance_far"] if zone_known else []
        return []

    def _attach_node_legal_refs(
        self, hierarchy: list[dict], zone_type: str, sigungu: str, zl: dict
    ) -> None:
        """hierarchy 각 level dict에 legal_refs[]를 in-place 가산(기존 필드 무손상).

        - zone_type 미확정 → zone 종속 노드 legal_refs 빈 배열(할루시네이션 링크 금지).
        - 조례 노드는 sigungu를 전달해 조례명·url을 치환(미상이면 url_status='pending').
        - URL은 전적으로 get_legal_refs 출력만 사용한다(여기서 URL 조립 금지).
        - 부착 중 예외가 나도 원본 계층은 그대로 둔다(graceful).
        """
        zone_known = bool(zone_type and str(zone_type).strip())
        has_du_plan = any(
            isinstance(it, dict) and any(
                k in str(it.get("name", ""))
                for k in ("지구단위", "재정비촉진", "정비구역", "도시개발", "성장관리")
            )
            for lv in hierarchy
            if lv.get("level") == "도시·군계획 / 지구단위계획"
            for it in (lv.get("items") or [])
        )
        sgg = sigungu if (sigungu and str(sigungu).strip() and str(sigungu).strip() != "미확인") else None
        try:
            from app.services.legal.legal_reference_registry import get_legal_refs
        except Exception:  # noqa: BLE001
            return
        for lv in hierarchy:
            if not isinstance(lv, dict):
                continue
            keys = self._level_ref_keys(lv.get("level", ""), zone_known, has_du_plan)
            try:
                lv.setdefault("legal_refs", get_legal_refs(keys, sigungu=sgg) if keys else [])
            except Exception:  # noqa: BLE001
                lv.setdefault("legal_refs", [])

    @staticmethod
    def _build_evidence(zone_type: str, limits: dict, sigungu: str) -> list[dict]:
        """건폐/용적 한도 산출 트레이스(EvidencePanel 소비 구조).

        {label, value, basis, legal_ref_key}. 법정 상한 + (조례 실효값이 다르면) 조례 적용값을
        트레이스한다. zone_type 미확정 시 빈 배열. basis는 legal_zone_limits의 법정근거 문구를
        사용(레지스트리 단일출처 원문링크는 legal_ref_key로 프론트가 결합).
        """
        if not (zone_type and str(zone_type).strip()):
            return []
        try:
            from app.services.zoning.legal_zone_limits import legal_limits_for

            legal = legal_limits_for(zone_type)
        except Exception:  # noqa: BLE001
            legal = None
        if not legal:
            return []
        zone_key = legal.get("zone_type") or zone_type
        ref_keys = legal.get("legal_ref_keys") or {}
        far_key = ref_keys.get("far")
        bcr_key = ref_keys.get("bcr")
        sgg = sigungu if (sigungu and str(sigungu).strip() and str(sigungu).strip() != "미확인") else "지자체"

        def _pct(v) -> str | None:
            if v is None:
                return None
            try:
                n = float(v)
            except (TypeError, ValueError):
                return None
            return f"{int(n)}%" if n == int(n) else f"{n:g}%"

        bcr = limits.get("bcr") or {}
        far = limits.get("far") or {}
        evidence: list[dict] = []
        # 법정 상한(건폐/용적) — legal_zone_limits SSOT.
        bcr_legal = _pct(legal.get("max_bcr_pct"))
        if bcr_legal and bcr_key:
            evidence.append({
                "label": "법정 건폐율 상한", "value": bcr_legal,
                "basis": f"{zone_key} · 국토계획법 시행령 제84조", "legal_ref_key": bcr_key,
            })
        far_legal = _pct(legal.get("max_far_pct"))
        if far_legal and far_key:
            evidence.append({
                "label": "법정 용적률 상한", "value": far_legal,
                "basis": f"{zone_key} · 국토계획법 시행령 제85조", "legal_ref_key": far_key,
            })
        # 조례 실효값이 법정과 다르면 별도 트레이스(조례 근거키로).
        ord_bcr = _pct(bcr.get("ordinance"))
        if ord_bcr and ord_bcr != bcr_legal:
            evidence.append({
                "label": "조례 적용 건폐율", "value": ord_bcr,
                "basis": f"{zone_key} · {sgg} 도시계획 조례(실효값)", "legal_ref_key": "ordinance_bcr",
            })
        ord_far = _pct(far.get("ordinance"))
        if ord_far and ord_far != far_legal:
            evidence.append({
                "label": "조례 적용 용적률", "value": ord_far,
                "basis": f"{zone_key} · {sgg} 도시계획 조례(실효값)", "legal_ref_key": "ordinance_far",
            })
        return evidence

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
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="regulation")
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
