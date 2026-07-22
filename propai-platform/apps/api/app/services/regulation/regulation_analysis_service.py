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
- 용적률 한도(법정/조례/실효): {far}{far_basis}
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
        self, address: str, pnu: str | None = None, use_llm: bool = True,
        with_senior: bool = True, parcels: list[dict] | None = None,
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

        # ── 다필지 통합면적/통합용도 전파(시장보고서와 동일 공용패턴) ──
        # 프론트가 2필지 이상 보내면(parcels) 대표 1필지가 아니라 '면적가중 통합면적·우세용도'로
        #   area·zone_type을 덮어쓴다(예: 12필지 12,079㎡인데 대표 1,161㎡만 분석하던 버그 해소).
        #   ★공용 단일경유: /zoning/integrated-analysis와 동일한 ComprehensiveAnalysisService.
        #   _integrated_context(면적가중 _aggregate_integrated_zoning 재사용) — 산식 복제 0.
        #   1필지 이하/실패면 통합 안 함(기존 단일 경로 그대로 = 무회귀). 통합 적용 시
        #   zone_limits(zl)도 통합용도 기준으로 재산정해야 limits/hierarchy/evidence가 일관된다.
        integrated: dict[str, Any] | None = None
        # 방어: 라우터는 parcels를 list[dict] 무스키마로 받으므로 dict 행만 통과시킨다.
        _rows = [p for p in parcels if isinstance(p, dict)] if parcels else []
        if len(_rows) >= 2:
            try:
                from app.services.land_intelligence.comprehensive_analysis_service import (
                    ComprehensiveAnalysisService,
                )

                integrated = await ComprehensiveAnalysisService()._integrated_context(_rows)
            except Exception as e:  # noqa: BLE001 — 통합집계 실패는 단일 경로로 폴백(분석 무중단)
                logger.warning("규제분석 다필지 통합집계 실패 — 단일필지 경로로 폴백(graceful)", err=str(e)[:120])
                integrated = None
        if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
            # 통합면적으로 area override → land_area_sqm·가능규모가 통합면적 기준.
            area = float(integrated["total_area_sqm"])
            # 대표 용도지역도 통합 우세값으로 보정(미상/혼재면 기존 zone_type 유지).
            _dom = integrated.get("dominant_zone")
            if _dom and _dom != "mixed_review_required":
                zone_type = _dom
                # 통합용도가 바뀌면 한도(zl)도 그 용도 기준으로 재조회해야 일관(legal_zone_limits 단일출처).
                try:
                    from app.services.zoning.legal_zone_limits import legal_limits_for

                    _zl2 = legal_limits_for(zone_type)
                    if isinstance(_zl2, dict) and _zl2:
                        zl = _zl2
                except Exception:  # noqa: BLE001 — 한도 재조회 실패면 기존 zl 유지(무손상)
                    pass

        # ── 정량 한도 ──
        limits = self._limits(zl)

        # ── WP-R1: 실효 용적률/건폐율 = far_tier_service SSOT 단일경유 소비(재계산 금지) ──
        # comp["effective_far"]는 collect_comprehensive가 이미 calc_effective_far로 산정한
        #   '구조상한 반영 실효치'(자연녹지 = 건폐 20% × 4층 = 80%). zone_limits(zl)엔
        #   effective_far_pct 키가 없어 _limits가 법정(100%)으로 폴백하므로, 여기서 SSOT값으로
        #   effective 슬롯을 덮어써 "실효 100%" 오표기(설계 스튜디오와 데이터원 발산)를 봉합한다.
        #   다필지 통합은 면적가중 blended 실효치(각 필지 calc_effective_far 경유·이미 클램프)가 우선.
        _eff = comp.get("effective_far")
        eff = _eff if isinstance(_eff, dict) else None
        eff_far_pct = eff.get("effective_far_pct") if eff else None
        eff_bcr_pct = eff.get("effective_bcr_pct") if eff else None
        if integrated:
            if integrated.get("blended_far_eff_pct") is not None:
                eff_far_pct = float(integrated["blended_far_eff_pct"])
            if integrated.get("blended_bcr_eff_pct") is not None:
                eff_bcr_pct = float(integrated["blended_bcr_eff_pct"])
        if eff_far_pct is not None and isinstance(limits.get("far"), dict):
            limits["far"]["effective"] = eff_far_pct
        if eff_bcr_pct is not None and isinstance(limits.get("bcr"), dict):
            limits["bcr"]["effective"] = eff_bcr_pct
        # ★적대리뷰 반영(HIGH): eff(구조상한 structural_cap_pct/floor_cap/floor_cap_basis/far_basis)는
        #   '대표(첫) 필지' 단일존 계산치다. 다필지 혼합(integrated 성공)은 effective(far/bcr)를 면적가중
        #   blended로 이미 덮어썼으므로, 대표필지의 구조상한을 그 옆에 그대로 노출하면 "실효 건폐율
        #   40%(blended) × 4층(대표) = 80%(대표)" 같은 가시적 산술 거짓이 재유입된다(far_tier_service.
        #   rebuild_legal_basis_annotations의 "139.6% vs 200%" 전례와 동일 클래스). integrated가 None일
        #   때만(진짜 단일필지 또는 통합실패 폴백 — 이 경우 eff_far_pct/eff_bcr_pct는 대표값 그대로라
        #   구조상한과 정합) 구조상한 상세를 노출한다(정직 — 다필지 혼합은 미표시가 안전).
        # ★근거체인 절단 수정(2026-07-19 라이브 신고 — AI 검증이 "far.effective=80 근거 미명시"
        #   경고): 위 가드는 혼합존의 산술 거짓(blended 40%×대표 4층=대표 80%)을 막으려는 것인데,
        #   **동질존**(zone_mix 1종 — 예: 12필지 전부 자연녹지)까지 근거를 숨겨 실효 80%가
        #   무근거 하드코딩처럼 보였다. 동질존에선 면적가중 blended = 단일존 실효치라 구조상한
        #   (건폐×층수상한)·far_basis가 전체 집합에 그대로 유효 — 산술 거짓이 성립하지 않는다.
        _zone_mix = integrated.get("zone_mix") if isinstance(integrated, dict) else None
        _uniform_zone = (
            bool(_zone_mix)
            and all(z.get("zone") for z in _zone_mix if isinstance(z, dict))
            and len({z.get("zone") for z in _zone_mix if isinstance(z, dict)}) == 1
        )
        # ★R1 하드닝(MAJOR): 동질존이어도 **시군구가 다르면** 필지별 조례 BCR이 달라
        #   blended(면적가중)가 대표필지 구조상한과 발산할 수 있다(예: blended 19%×4층 문구에
        #   대표 80%가 붙는 산술 거짓 — 이 가드가 원래 봉인하려던 결함 클래스). 동질존 표시는
        #   blended가 대표 구조상한 산식과 ε(0.5%p) 내로 정합할 때만 허용하고, 발산하면 기존
        #   안전 동작(미표시=정직)으로 폴백한다.
        _struct_consistent = True
        if integrated and _uniform_zone and eff:
            _cap = eff.get("structural_cap_pct")
            _fc = eff.get("floor_cap")
            if _cap is not None and _fc and eff_bcr_pct is not None:
                _struct_consistent = abs(float(eff_bcr_pct) * float(_fc) - float(_cap)) <= 0.5
            if _struct_consistent and _cap is not None and eff_far_pct is not None:
                _struct_consistent = abs(float(_cap) - float(eff_far_pct)) <= 0.5
        _show_structural = bool(eff) and (not integrated or (_uniform_zone and _struct_consistent))
        # 구조상한(건폐율×층수) 근거를 높이 카드 칩으로 노출(층수제한 zone만) — 레지스트리 단일출처.
        floor_cap = eff.get("floor_cap") if (eff and _show_structural) else None
        # 근거 텍스트를 응답 표면에 명시(additive) — AI 검증·프론트·전문가 패널이 동일 근거를 본다.
        #   far.effective_basis: "건폐 20%×4층=80% 구조상한(시행령 별표17)" 류의 산정 근거.
        #   height.basis: zl(height_basis) 우선, 없으면 구조상한 근거(floor_cap_basis)로 보충.
        if _show_structural and eff:
            _fb = eff.get("far_basis")
            if _fb and isinstance(limits.get("far"), dict):
                limits["far"]["effective_basis"] = _fb
            _fcb = eff.get("floor_cap_basis")
            if _fcb and isinstance(limits.get("height"), dict) and not limits["height"].get("basis"):
                limits["height"]["basis"] = _fcb
        if floor_cap and isinstance(limits.get("height"), dict):
            try:
                from app.services.legal.legal_reference_registry import get_legal_refs

                _hrefs = get_legal_refs(["green_zone_floor_cap"])
                if _hrefs:
                    limits["height"]["legal_ref"] = _hrefs[0]
            except Exception:  # noqa: BLE001 — 근거 칩 부착 실패는 높이 표기 무손상
                pass

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
        # WP-R2: 개별 규제 레벨은 legal_refs_for_districts(지역지구별 규제법령집) 단일경유로 부착하고,
        #   상위법령 레벨엔 §77/§78(bcr_law/far_law)·녹지 층수상한(green_zone_floor_cap)을 가산한다.
        self._attach_node_legal_refs(
            hierarchy, zone_type, sigungu, zl, districts=districts, has_floor_cap=bool(floor_cap),
        )
        # 구조상한 evidence 행도 동일 게이트(_show_structural) — 다필지 혼합엔 eff(대표필지) 미전달.
        evidence = self._build_evidence(zone_type, limits, sigungu, eff if _show_structural else None)

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

        # WP-R1: effective_far 통과키(구조상한 실체) — 프론트/근거패널이 소비(가산·옵셔널·무회귀).
        #   층수제한 없는 zone은 structural_cap_pct/floor_cap이 None(자연스레 미표기).
        #   다필지 혼합(_show_structural=False)은 대표필지 전용 구조상한/근거를 실지 않는다(정직 —
        #   blended effective_far_pct/effective_bcr_pct 헤드라인만 남기고 산술 불일치 필드는 생략).
        if eff:
            result["effective_far"] = {
                "effective_far_pct": eff_far_pct,
                "effective_bcr_pct": eff_bcr_pct,
                "structural_cap_pct": eff.get("structural_cap_pct") if _show_structural else None,
                "floor_cap": eff.get("floor_cap") if _show_structural else None,
                "floor_cap_basis": eff.get("floor_cap_basis") if _show_structural else None,
                "far_basis": eff.get("far_basis") if _show_structural else None,
            }

        # ── WP-R3 parity: 실제 사용된 필지 목록(주소+PNU) echo — 구획도/패널이 단일 권위목록 소비 ──
        #   다필지(2필지↑)면 전달된 행을, 아니면 해결된 단일 필지를 실어 클라 재파생 드리프트를 제거한다.
        _used: list[dict] = []
        if len(_rows) >= 2:
            for p in _rows:
                _a = (p.get("address") or "").strip()
                if _a:
                    _used.append({"address": _a, "pnu": p.get("pnu") or None})
        if not _used:
            _used = [{"address": address, "pnu": comp.get("pnu") or pnu}]
        result["parcels_used"] = _used

        # 다필지 통합 적용 사실(있으면) — 프론트가 "통합 N필지 기준" 표기에 사용.
        #   parcels 미전달/1필지면 키 자체를 생략(단일 경로 무회귀).
        if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
            result["integrated"] = {
                "parcel_count": integrated.get("parcel_count"),
                "total_area_sqm": integrated.get("total_area_sqm"),
                "dominant_zone": integrated.get("dominant_zone"),
            }

        # ── 시니어 자문 모세혈관 배선 — 심의(건폐/용적/높이 적합)·도시계획·법무사 ──
        # 규제 계층 분석에 시니어 판단프레임워크·근거·정량 verdict를 첨부한다. 실효 건폐/용적(actual)을
        # 법정상한(legal·없으면 실효)과 심의 CSP로 대조해 준수=PASS·초과=BLOCK 실판정을 산출한다
        # (build_compliance_inputs 공용 빌더·DRY). ★무회귀: 절대 raise 안 함(graceful).
        if with_senior:
            try:
                from app.services.senior_agents.consultation_hook import (
                    attach_senior_consultation_multi,
                    build_compliance_inputs,
                )

                _far = limits.get("far") if isinstance(limits, dict) else {}
                _bcr = limits.get("bcr") if isinstance(limits, dict) else {}
                _hgt = limits.get("height") if isinstance(limits, dict) else {}
                _far = _far if isinstance(_far, dict) else {}
                _bcr = _bcr if isinstance(_bcr, dict) else {}
                _hgt = _hgt if isinstance(_hgt, dict) else {}
                _sr_inputs = build_compliance_inputs(
                    far_actual=_far.get("effective"), far_limit=_far.get("legal") or _far.get("effective"),
                    bcr_actual=_bcr.get("effective"), bcr_limit=_bcr.get("legal") or _bcr.get("effective"),
                    height_actual=_hgt.get("value"), height_limit=_hgt.get("value"),
                )
                # 데이터 완결도 신호(정직 confidence): 건폐/용적/높이 3축 중 확보된 축 비율.
                _axes = (_bcr.get("effective") or _bcr.get("legal"),
                         _far.get("effective") or _far.get("legal"),
                         _hgt.get("value"))
                _completeness = sum(1 for a in _axes if a is not None) / len(_axes)
                # 풍성화(사용자 신고 '시니어 분석 빈약'): IRAC 체인(쟁점→규칙[법령 근거]→적용→결론)
                # 동봉 — 결정론·무LLM이라 지연/비용 0. 프론트 SeniorVerdictCard가 렌더.
                result["senior_consultation"] = attach_senior_consultation_multi(
                    ["deliberation", "urban", "legal"], _sr_inputs,
                    include_reasoning=True,
                    context_signals={"data_completeness": _completeness},
                )
            except Exception:  # noqa: BLE001 — 시니어 자문 첨부 실패는 규제 분석 무손상
                pass

        if use_llm:
            # WP-R1: 실효 용적률 근거(구조상한 등)를 프롬프트에 주입 → AI가 "실효 80%(4층 제한 바인딩)" 서술.
            #   다필지 혼합(_show_structural=False)은 대표필지 전용 근거문구를 주입하지 않는다(AI가
            #   blended 헤드라인 옆에 대표필지 근거를 잘못 서술하는 것을 방지 — 근거 없음이 정직).
            _far_basis = eff.get("far_basis") if (eff and _show_structural) else None
            result["ai"] = await self._llm(
                address, zone_type, zone_2, area, limits, districts, far_basis=_far_basis,
            )
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

        # 높이: 법정 미터 제한(max_height_m)이 우선이나, 녹지지역처럼 미터 제한이 없고
        # 층수 제한(4층 등)만 있는 경우 실효 높이(effective_height_m=층수×층고 근사)를 채택해
        # '제한 없음'으로 오표시되던 버그를 차단. max_floors/height_basis는 additive로 노출.
        height_value = zl.get("max_height_m")
        if height_value is None:
            height_value = zl.get("effective_height_m")
        return {
            "bcr": trio("max_bcr_pct", "ordinance_bcr_pct", "effective_bcr_pct"),
            "far": trio("max_far_pct", "ordinance_far_pct", "effective_far_pct"),
            "height": {
                "value": height_value,
                "unit": "m",
                "max_floors": zl.get("max_floors"),
                "basis": zl.get("height_basis"),
            },
            "parking": {"description": "주차장법 시행령 별표1 부설주차장 설치기준 적용(용도·면적별 산정)"},
        }

    @staticmethod
    def _sigungu(address: str) -> str:
        # ★조례 정본 레벨 단일 SSOT 경유(ordinance_service.resolve_ordinance_region):
        #   특별시/광역시→시 본청(서울특별시), 도 산하→시/군. 자치구(동작구 등)는 용적률/건폐율
        #   도시계획조례가 없어 조회 미스·연결실패를 유발하던 종전 버그(i>0로 시 본청 스킵)를 제거.
        from app.services.land_intelligence.ordinance_service import resolve_ordinance_region
        return resolve_ordinance_region(address) or ""

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
    def _level_ref_keys(
        level_name: str, zone_known: bool, has_du_plan: bool, has_floor_cap: bool = False,
    ) -> list[str]:
        """계층 레벨명 → 부착할 레지스트리 근거키 목록(중복 없는 순서 보존).

        zone_type 미확정(zone_known=False) 시 zone 종속 한도 근거는 부착하지 않는다
        (건폐/용적/용도 한도는 용도지역이 있어야 의미 있음 → 빈 배열로 정직 표기).
        """
        if level_name == "상위법령":
            # 용도지역 행위제한 + 건폐율/용적률(법률 §77/§78=bcr_law/far_law, 시행령 §84/§85=bcr_limit/
            #   far_limit) + 건축 한도 + 주차 기준. WP-R2: 법률 조문 링크(§77/§78)가 미배선이던 갭 봉합.
            base = ["zone_use", "bcr_law", "far_law", "bcr_limit", "far_limit", "bldg_far", "parking_min"]
            # 녹지 등 층수제한 zone은 구조상한(별표15~17 4층) 근거키를 함께 부착(높이 근거 정합).
            if has_floor_cap:
                base.append("green_zone_floor_cap")
            return base if zone_known else ["parking_min"]
        if level_name == "도시·군계획 / 지구단위계획":
            # 지구단위계획 근거는 해당 구역이 실제 있을 때만(가짜 링크 방지).
            return ["district_unit_plan"] if has_du_plan else []
        if level_name == "지자체 조례":
            # 조례 건폐/용적 강화 한도 — sigungu 치환 후 url 승격(미상이면 pending).
            return ["ordinance_bcr", "ordinance_far"] if zone_known else []
        return []

    def _attach_node_legal_refs(
        self, hierarchy: list[dict], zone_type: str, sigungu: str, zl: dict,
        districts: list[dict] | None = None, has_floor_cap: bool = False,
    ) -> None:
        """hierarchy 각 level dict에 legal_refs[]를 in-place 가산(기존 필드 무손상).

        - zone_type 미확정 → zone 종속 노드 legal_refs 빈 배열(할루시네이션 링크 금지).
        - 조례 노드는 sigungu를 전달해 조례명·url을 치환(미상이면 url_status='pending').
        - 개별 적용 규제·지구·구역 레벨은 legal_refs_for_districts(지역지구별 규제법령집)로 부착
          (WP-R2: 현재 [] 반환이던 갭 봉합 — 상대보호구역/비행안전/토지거래 등 개별법 조문 링크).
        - URL은 전적으로 get_legal_refs/legal_refs_for_districts 출력만 사용한다(여기서 URL 조립 금지).
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
            from app.services.legal.legal_reference_registry import (
                get_legal_refs,
                legal_refs_for_districts,
            )
        except Exception:  # noqa: BLE001
            return
        _dist_names = [
            d.get("name") for d in (districts or [])
            if isinstance(d, dict) and d.get("name")
        ]
        for lv in hierarchy:
            if not isinstance(lv, dict):
                continue
            level_name = lv.get("level", "")
            try:
                if level_name == "개별 적용 규제·지구·구역":
                    refs = (
                        legal_refs_for_districts(_dist_names, sigungu=sgg).get("refs", [])
                        if _dist_names else []
                    )
                    lv.setdefault("legal_refs", refs)
                else:
                    keys = self._level_ref_keys(level_name, zone_known, has_du_plan, has_floor_cap)
                    lv.setdefault("legal_refs", get_legal_refs(keys, sigungu=sgg) if keys else [])
            except Exception:  # noqa: BLE001
                lv.setdefault("legal_refs", [])

    @staticmethod
    def _build_evidence(
        zone_type: str, limits: dict, sigungu: str, eff: dict | None = None,
    ) -> list[dict]:
        """건폐/용적 한도 산출 트레이스(EvidencePanel 소비 구조).

        {label, value, basis, legal_ref_key}. 법정 상한 + (조례 실효값이 다르면) 조례 적용값을
        트레이스한다. zone_type 미확정 시 빈 배열. basis는 legal_zone_limits의 법정근거 문구를
        사용(레지스트리 단일출처 원문링크는 legal_ref_key로 프론트가 결합).

        WP-R1: eff(far_tier_service SSOT)에 구조상한(건폐율×층수)이 실려오면 "건폐 20%×4층=80%"의
        물리 상한 트레이스 1건을 가산해, 법정 100% 옆에 실효 80%의 실체를 근거패널에 노출한다.
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
        # WP-R1: 구조상한(건폐율×층수) 실효 트레이스 — 층수제한 zone(녹지 등)에서 실효 용적률의 실체.
        #   법정 100% 표기 옆에 "실효 건폐율×4층=80%"의 물리 상한을 근거패널에 노출한다(과대표시 차단).
        _eff = eff if isinstance(eff, dict) else {}
        structural_cap = _pct(_eff.get("structural_cap_pct"))
        floor_cap = _eff.get("floor_cap")
        if structural_cap and floor_cap:
            eff_bcr = _pct(bcr.get("effective")) or "-"
            floor_basis = _eff.get("floor_cap_basis") or "국토계획법 시행령 별표15~17 두문(4층 이하)"
            evidence.append({
                "label": "구조상한 실효 용적률", "value": structural_cap,
                "basis": (f"{zone_key} · 실효 건폐율 {eff_bcr} × {floor_cap}층 = {structural_cap} "
                          f"({floor_basis})"),
                "legal_ref_key": "green_zone_floor_cap",
            })
        return evidence

    async def _llm(
        self, address: str, zone: str, zone2: str, area: Any,
        limits: dict, districts: list[dict], far_basis: str | None = None,
    ) -> dict[str, Any]:
        # 초기화 단계를 호출 단계와 분리 — get_llm의 키 미설정 ValueError가 'parse'로
        # 오분류되던 결함 교정(사유 정직성: import/provider/timeout/parse 각자 자리).
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm
        except Exception as e:  # noqa: BLE001
            logger.warning("규제 LLM 모듈 로드 실패, 폴백", err=f"{type(e).__name__}: {str(e)[:100]}")
            return self._llm_fallback(zone, districts, "import")
        try:
            llm = get_llm(timeout=60, max_tokens=2500)
        except Exception as e:  # noqa: BLE001 — 키 미설정·모델 구성 오류 등
            logger.warning("규제 LLM 초기화 실패, 폴백", err=f"{type(e).__name__}: {str(e)[:100]}")
            return self._llm_fallback(zone, districts, "provider")
        try:
            bcr = limits["bcr"]; far = limits["far"]
            # WP-R1: 실효 용적률 근거 문구(구조상한 등)를 프롬프트에 병기 → AI가 실효치를 정확히 서술.
            far_basis_note = f" — 실효 근거: {far_basis}" if far_basis else ""
            user = _USER_TMPL.format(
                address=address,
                zone_type=zone or "미상",
                zone_2=f" + {zone2}" if zone2 else "",
                area=round(area) if area else "-",
                bcr=f"{bcr.get('legal') or '-'}/{bcr.get('ordinance') or '-'}/{bcr.get('effective') or '-'}",
                far=f"{far.get('legal') or '-'}/{far.get('ordinance') or '-'}/{far.get('effective') or '-'}",
                far_basis=far_basis_note,
                districts=", ".join(f"{d['name']}({d['impact']})" for d in districts[:20]) or "-",
            )
            resp = await llm.ainvoke(
                [SystemMessage(content=_SYSTEM + GROUNDING_RULE), HumanMessage(content=user)]
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="regulation")
            from app.services.ai.llm_json import parse_llm_json
            data = parse_llm_json(resp.content if hasattr(resp, "content") else str(resp))
            if not isinstance(data, dict):
                raise json.JSONDecodeError("JSON 객체가 아닌 응답", doc="", pos=0)
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("규제 LLM 해석 실패, 폴백", err=f"{type(e).__name__}: {str(e)[:100]}")
            # 폴백 사유 표면화(정직) — "일시 미제공"만으론 라이브 진단 불가. ★R1: 원 클래스명은
            # 프로바이더 fingerprint 소지 → coarse 분류만 노출(진단성 유지·내부정보 최소화).
            reason = (
                "timeout" if "Timeout" in type(e).__name__
                else "parse" if isinstance(e, (json.JSONDecodeError, KeyError))
                else "provider"
            )
            return self._llm_fallback(zone, districts, reason)

    @staticmethod
    def _llm_fallback(zone: str, districts: list[dict], reason: str) -> dict[str, Any]:
        """LLM 미가용 시의 정직 폴백(구조 요약) + coarse 사유."""
        return {
            "generated": False,
            "fallback_reason": reason,
            "summary": f"{zone or '미상'} 기준 적용 규제를 계층별로 정리했습니다. AI 통합 해석은 일시적으로 제공되지 않습니다.",
            "key_constraints": [d["name"] for d in districts if d["impact"] == "상"][:4],
            "dev_impact": "용도지역 허용용도와 조례 강화 한도, 중첩 규제를 우선 확인하세요.",
            "strategies": ["지구단위계획·조례 확인", "영향도 높은 규제 사전 협의"],
            "opportunities": [],
            "risks": [d["name"] for d in districts if d["impact"] in ("상", "중")][:3],
        }
