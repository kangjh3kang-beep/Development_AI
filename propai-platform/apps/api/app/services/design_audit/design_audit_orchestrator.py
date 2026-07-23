"""DA-3 — 설계심사 오케스트레이터(8엔진 병렬 + 결정론 종합판정).

흐름:
1. 조례 실효한도 선행 산정 — legal_zone_limits.applicable_limits_for
   (법정범위 → 조례 적용값 → 도시·군관리계획/지구단위계획 상한 계층).
2. asyncio.gather(return_exceptions=True)로 8개 엔진 병렬 실행:
   ① rules8        — 기하 8룰(BuildingComplianceService 검증기 재사용)
   ② design_review — 파라미터 법규검토(DesignReviewService)
   ③ solar_envelope— 정북일조 인벨로프(+ShadowSimulator 일영 SVG)
   ④ parking       — 법정주차(_compute_parking 재사용)
   ⑤ permit        — 인허가(check_permit_feasibility + PermitAnalysisService use_llm=False)
   ⑥ change_risk   — 설계변경 사전예측(DesignChangePredictor, 룰기반)
   ⑦ incentives    — [S4] 인센티브(upzoning_potential PATHS + far_tier_service + 기부채납 시뮬)
   ⑧ case_compare  — [S1~S3] 인근 인허가 사례 비교(PermitCaseService → summarize →
                      DesignReviewService.compare_with_nearby_cases)
3. 전 결과를 AuditFinding{check_id, engine, status, current, limit, legal_refs,
   improvement}로 정규화. 실패 엔진은 status='skipped'로 정직하게 표기.
4. overall은 결정론만: fail 존재 → 부적합, warning만 → 조건부적합(LLM 미개입).

정직성 원칙:
- legal_refs는 legal_reference_registry.get_legal_refs 출력만 사용(URL 조립·날조 금지).
- 데이터 부족 엔진은 skipped + 사유(임의 기본값으로 강행하지 않음).
- 리포트 S섹션 결합용 원자료(sections: s1_samples, s4_incentives,
  efficiency_metrics[S7 전용률·코어비율])를 함께 반환한다.

[UP3 — additive] 라우터 계약 어댑터 + 평면 문법 섹션:
- run(db, site=, params=, geometry=, ifc_file_url=, …): design_audit.py /run이
  호출하는 진입점. site에서 zone_type·sigungu·address·pnu만 추출하고 IFC 파라미터를
  병합(user>ifc)한 뒤 기존 audit()에 위임한다(audit·8엔진 시그니처 불변).
  반환에는 overall.verdict_en 영문 별칭(부적합→fail, 조건부적합→conditional,
  적합→pass)만 가산한다.
- audit(rooms=): 실 타일링(rooms) 제공 시 unit_plan_generator 경계 엔진
  (arch_grammar KB — classify_boundaries·place_openings·validate_connectivity)을
  실행해 LDK 오픈·1실 1문·채광창·연결성 결과를 engine='grammar' finding으로
  정규화하고 sections.grammar(boundaries·openings·grammar_warnings)에 적재한다.
  rooms 미제공 시 grammar는 skipped(정직) — 기존 8엔진·종합판정 결정론 불변
  (grammar warning은 기존 규칙대로 조건부적합에 반영).
"""

from __future__ import annotations

import asyncio
import math
from collections import Counter
from typing import Any

import structlog

from app.services.design_audit.geometry_adapter import design_payload_from_shapes

logger = structlog.get_logger()

# 엔진 이름(실행 순서 고정 — gather 결과 zip 매칭).
ENGINE_NAMES: tuple[str, ...] = (
    "rules8", "design_review", "solar_envelope", "parking",
    "permit", "change_risk", "incentives", "case_compare",
)

# AuditFinding.status 어휘.
STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_FAIL = "fail"
STATUS_INFO = "info"
STATUS_SKIPPED = "skipped"

# [UP3] overall.verdict 영문 별칭(라우터/프론트 계약) — 한국어 verdict는 불변(additive).
# '판정불가'는 설계 명세에 별칭이 없어 None(날조 금지 — 미정의는 미정의로).
VERDICT_EN_ALIASES: dict[str, str] = {
    "부적합": "fail",
    "조건부적합": "conditional",
    "적합": "pass",
}

# rules8 위반유형 → 법령 레지스트리 근거키(존재 검증된 키만 — 할루시네이션 링크 금지).
# height(가로구역 최고높이, 건축법 제60조)는 레지스트리 미보유 → 매핑 없음(텍스트만).
_RULES8_REF_KEYS: dict[str, tuple[str, ...]] = {
    "building_coverage": ("bldg_bcr", "bcr_limit"),
    "floor_area_ratio": ("bldg_far", "far_limit"),
    "height": (),
    "setback": ("site_open_space",),
    "sunlight": ("daylight_height", "daylight_height_dec"),
    "structure": ("structure_safety",),
}

# 건축물 용도 키워드 → 개발유형 코드(permit_validator 매트릭스 키).
_USE_TO_DEV_TYPE: tuple[tuple[str, str], ...] = (
    ("주상복합", "M07"),
    ("오피스텔", "M08"),
    ("지식산업센터", "M09"),
    ("도시형생활주택", "M13"),
    ("타운하우스", "M12"),
    ("전원", "M11"),
    ("단독", "M10"),
    ("공공임대", "M14"),
)
_DEFAULT_DEV_TYPE = "M06"  # 일반분양(공동주택) — 매핑 실패 시 기본(근거: 주용도 미상)


def _num(value: Any) -> float | None:
    """유한 실수만 통과(bool·NaN·inf·비수치 → None) — 가짜 수치 금지."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def make_finding(
    check_id: str,
    engine: str,
    status: str,
    *,
    current: Any = None,
    limit: Any = None,
    legal_ref_keys: list[str] | tuple[str, ...] | None = None,
    improvement: str | None = None,
    note: str | None = None,
    sigungu: str | None = None,
) -> dict[str, Any]:
    """AuditFinding 정규화 — 모든 엔진 결과의 단일 스키마.

    legal_refs는 legal_reference_registry.get_legal_refs 출력만 사용한다
    (레지스트리 미존재 키는 자동 제외 — 할루시네이션 링크 금지).
    """
    legal_refs: list[dict[str, Any]] = []
    if legal_ref_keys:
        try:
            from app.services.legal.legal_reference_registry import get_legal_refs

            legal_refs = get_legal_refs([k for k in legal_ref_keys if k], sigungu=sigungu)
        except Exception as e:  # noqa: BLE001 — 근거 부착 실패는 빈 배열(graceful)
            logger.warning("설계심사 법령근거 부착 스킵", check_id=check_id, error=str(e)[:120])
            legal_refs = []
    finding: dict[str, Any] = {
        "check_id": check_id,
        "engine": engine,
        "status": status,
        "current": current,
        "limit": limit,
        "legal_refs": legal_refs,
        "improvement": improvement,
    }
    if note:
        finding["note"] = note
    return finding


def _dev_type_from_use(building_use: str | None) -> tuple[str, str]:
    """주용도 문자열 → 개발유형 코드(+판정 근거). 매핑 실패 시 M06(주용도 미상 표기)."""
    use = (building_use or "").strip()
    for keyword, code in _USE_TO_DEV_TYPE:
        if keyword and keyword in use:
            return code, f"주용도 '{use}' → {code}"
    if use:
        return _DEFAULT_DEV_TYPE, f"주용도 '{use}' 매핑 없음 — 공동주택 일반분양({_DEFAULT_DEV_TYPE}) 가정"
    return _DEFAULT_DEV_TYPE, f"주용도 미입력 — 공동주택 일반분양({_DEFAULT_DEV_TYPE}) 가정"


def _efficiency_metrics(params: dict[str, Any]) -> dict[str, Any]:
    """[S7] 효율 지표(전용률·코어비율) — 결정론 산술, 데이터 없으면 None(정직).

    - 전용률(%) = 전용면적 합 ÷ 연면적 × 100. 전용면적 합은 exclusive_area_sqm
      우선, 없으면 세대수×평균전용면적으로 산출(산출근거 basis에 명시).
    - 코어비율(%) = core_area_sqm ÷ 연면적 × 100 (코어면적 미입력 시 None).
    - 공용비율(%) = 100 − 전용률 (코어+복도+설비 등 공용 전체 — 코어비율과 구분).
    """
    notes: list[str] = []
    gfa = _num(params.get("total_floor_area_sqm"))
    exclusive = _num(params.get("exclusive_area_sqm"))
    basis: str | None = "exclusive_area_sqm 입력값" if exclusive is not None else None
    if exclusive is None:
        units = _num(params.get("units"))
        avg_unit = _num(params.get("avg_unit_area_sqm"))
        if units and avg_unit:
            exclusive = units * avg_unit
            basis = "세대수 × 평균전용면적"

    efficiency_pct: float | None = None
    common_ratio_pct: float | None = None
    if exclusive is not None and gfa and gfa > 0:
        efficiency_pct = round(exclusive / gfa * 100, 1)
        common_ratio_pct = round(100 - efficiency_pct, 1)
        if efficiency_pct > 100:
            notes.append("전용면적 합이 연면적을 초과(물리적 모순) — 입력값 재확인 필요")
        elif not (70 <= efficiency_pct <= 85):
            notes.append("전용률이 통상 범위(70~85%) 밖 — 코어·공용면적 계상 재확인 권장")
    else:
        notes.append("전용률 미산출 — 연면적 또는 전용면적(세대수×평균전용) 데이터 없음")

    core = _num(params.get("core_area_sqm"))
    core_ratio_pct: float | None = None
    if core is not None and gfa and gfa > 0:
        core_ratio_pct = round(core / gfa * 100, 1)
    else:
        notes.append("코어비율 미산출 — 코어면적(core_area_sqm) 데이터 없음")

    return {
        "efficiency_pct": efficiency_pct,          # 전용률(%)
        "core_ratio_pct": core_ratio_pct,          # 코어비율(%) — 코어면적/연면적
        "common_area_ratio_pct": common_ratio_pct,  # 공용비율(%) = 100 − 전용률
        "basis": basis,
        "notes": notes,
    }


def _compare_with_prior(prior: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Phase 1: status 변화 표면화 + Phase 2: 결정론 모순 플래그(additive, 판정 미반영, 순수)."""
    from app.services.ledger.contradiction import detect_contradictions
    payload = (prior or {}).get("payload") or {}
    prev = {f.get("check_id"): f for f in (payload.get("findings_brief") or [])}
    cur = {f.get("check_id"): f for f in findings}
    changes = []
    for cid, c in cur.items():
        p = prev.get(cid)
        if p and p.get("status") != c.get("status"):
            changes.append({"check_id": cid, "prev_status": p.get("status"), "now_status": c.get("status")})
    # Phase 2: prior vs 현재 findings의 결정론 모순(status 플립·수치 델타) — 현재 findings만 비교
    # (현재 verdict는 이 시점 미전달 → 주입 오염 방지; verdict 모순은 findings status 플립으로 감지).
    contradictions = detect_contradictions(prior, {"findings_brief": findings})
    return {
        "prior_version": prior.get("version"),
        "prior_verdict": payload.get("verdict"),
        "status_changes": changes,
        "contradictions": contradictions,
        "note": "이전 대비 상태 변화·모순(참고용) — 종합판정은 현재 결정론 결과를 따른다",
    }


class DesignAuditOrchestrator:
    """설계심사 오케스트레이터 — 조례 실효한도 선행 + 8엔진 병렬 + 결정론 판정."""

    def __init__(self, case_service: Any = None) -> None:
        # 인허가 사례 서비스 주입 가능(테스트 모킹·외부키 격리). 미주입 시 lazy 생성.
        self._case_service = case_service

    async def audit(
        self,
        params: dict[str, Any] | None,
        *,
        zone_type: str | None = None,
        sigungu: str | None = None,
        address: str | None = None,
        pnu: str | None = None,
        shapes: dict[str, Any] | None = None,
        regulation_payload: Any = None,
        plan_payload: Any = None,
        case_service: Any = None,
        rooms: list[dict[str, Any]] | None = None,
        prior_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """설계 파라미터·기하·맥락으로 8엔진 설계심사를 수행한다.

        Args:
            params: 병합된 설계 파라미터(geometry_adapter.merge_params 출력의 params).
            zone_type: 용도지역명(예: "제2종일반주거지역").
            sigungu: 시군구(조례 딥링크·인센티브 resolver용).
            address: 주소 — 제공 시에만 PermitAnalysisService(use_llm=False) 실행.
            pnu: 필지고유번호 — 제공 시에만 인근 인허가 사례 비교 실행.
            shapes: CAD 도형 페이로드(rules8 기하검증용, 없으면 해당 엔진 skipped).
            regulation_payload/plan_payload: 조례·도시군관리계획 페이로드(실효한도 계층).
            case_service: PermitCaseService 호환 객체(테스트 주입 — 생성자 주입보다 우선).
            rooms: [UP3] 실 타일링 [{name,x,y,w,h}](m, unit_plan_generator 좌표계) —
                제공 시에만 arch_grammar 평면 문법 검증(engine='grammar') 실행.
                미제공 시 sections.grammar는 skipped(정직) — 기존 동작 불변.
        """
        params = dict(params or {})

        # ── 1) 조례 실효한도 선행 산정(법정범위 → 조례 → 계획상한) ──
        from app.services.zoning.legal_zone_limits import applicable_limits_for, legal_limits_for

        limits = applicable_limits_for(
            zone_type, sigungu=sigungu,
            regulation_payload=regulation_payload, plan_payload=plan_payload,
        )
        legal = legal_limits_for(zone_type)
        applied_far = _num(limits.get("applied_far_pct")) if limits else None
        applied_bcr = _num(limits.get("applied_bcr_pct")) if limits else None
        max_height = _num(legal.get("max_height_m")) if legal else None
        if limits is not None:
            try:
                from app.services.legal.legal_reference_registry import get_legal_refs

                limits["legal_refs"] = get_legal_refs(
                    ["far_limit", "bcr_limit", "ordinance_far", "ordinance_bcr"],
                    sigungu=sigungu,
                )
            except Exception:  # noqa: BLE001
                limits["legal_refs"] = []

        # ── 2) 8엔진 병렬 실행(개별 실패 격리 — return_exceptions) ──
        results = await asyncio.gather(
            self._run_rules8(params, shapes, applied_bcr, applied_far, max_height, sigungu),
            self._run_design_review(params, applied_far, applied_bcr, sigungu),
            self._run_solar(params, zone_type, applied_bcr, applied_far, sigungu),
            self._run_parking(params, sigungu),
            self._run_permit(params, zone_type, address, applied_bcr, applied_far, sigungu),
            self._run_change_risk(params, zone_type),
            self._run_incentives(params, zone_type, sigungu, regulation_payload, limits),
            self._run_case_compare(params, pnu, sigungu, case_service or self._case_service),
            return_exceptions=True,
        )

        # ── 3) AuditFinding 정규화 + 실패 엔진 skipped(정직) ──
        findings: list[dict[str, Any]] = []
        engines_status: dict[str, str] = {}
        sections: dict[str, Any] = {}
        for name, result in zip(ENGINE_NAMES, results, strict=False):
            if isinstance(result, BaseException):
                engines_status[name] = "failed"
                logger.warning("설계심사 엔진 실패 — skipped 처리", engine=name, error=str(result)[:160])
                findings.append(make_finding(
                    name, name, STATUS_SKIPPED,
                    note=f"엔진 실행 실패 — 결과 미산출(정직한 생략): {str(result)[:160]}",
                ))
                continue
            engines_status[name] = "ok"
            findings.extend(result.get("findings") or [])
            section = result.get("section")
            if section:
                key, payload = section
                sections[key] = payload

        # ── [UP3] grammar: 평면 문법(LDK 오픈·1실 1문·채광창·연결성) ──
        # rooms 제공 시에만 실행(additive — 8엔진 gather·ENGINE_NAMES 불변).
        # warning은 기존 결정론 규칙 그대로 조건부적합에 반영, skipped는 판정 미반영.
        if rooms:
            grammar = self._run_grammar(rooms)
            engines_status["grammar"] = grammar["status"]
            findings.extend(grammar["findings"])
            sections["grammar"] = grammar["section"]
        else:
            sections["grammar"] = {
                "skipped": True,
                "note": "rooms(실 타일링) 미제공 — 평면 문법(경계·개구·연결성) 검증 생략",
            }

        # ── ⑨ bl_rules: 피난·방화(BL-007) — 정본 building_code_rules 위임(신작 금지) ──
        # UI가 '피난·방화 체크'를 광고했으나 8엔진에 피난 검사가 없어 광고-실검사 불일치였다.
        # 정본 BuildingCodeRuleEngine(BL-007 §34 직통계단/§46 방화구획/§35 특별피난계단)에 위임만 한다.
        # 주차(BL-005)는 엔진 ④ parking(_compute_parking, 동일 주차장법 시행령 §6 산식)에서 이미
        # 산정하므로 중복 계상 방지로 여기서 재검하지 않는다(정본 위임=BL-005·런타임=_compute_parking).
        bl = self._run_bl_rules(params, zone_type)
        engines_status["bl_rules"] = bl["status"]
        findings.extend(bl["findings"])
        if bl.get("section"):
            sections["bl_rules"] = bl["section"]

        # [S7] 효율 지표(결정론 산술 — 엔진 외 공통 섹션).
        sections["efficiency_metrics"] = _efficiency_metrics(params)

        # ── 4) 결정론 종합판정(LLM 미개입) ──
        counts = Counter(f.get("status") for f in findings)
        if counts.get(STATUS_FAIL):
            verdict = "부적합"
        elif counts.get(STATUS_WARNING):
            verdict = "조건부적합"
        elif counts.get(STATUS_PASS):
            verdict = "적합"
        else:
            verdict = "판정불가"  # 전 엔진 skipped/info — 데이터 부족을 정직하게 표기

        # Phase 1 성장루프: prior 비교 표면화(verdict/counts 결정론 결과는 절대 미변경, sections만 가산)
        if prior_context:
            sections["prior_comparison"] = _compare_with_prior(prior_context, findings)

        return {
            "schema_version": "design_audit/v1",
            "zone_type": zone_type,
            "sigungu": sigungu,
            "limits": limits,
            "findings": findings,
            "overall": {
                "verdict": verdict,
                "counts": dict(counts),
                "basis": (
                    "결정론 판정 — fail 존재 시 '부적합', warning만 존재 시 '조건부적합', "
                    "pass만 존재 시 '적합', 판정 가능한 결과 없음 시 '판정불가'(LLM 미개입)"
                ),
            },
            "engines": engines_status,
            "sections": sections,
            "params_used": params,
            "disclaimer": (
                "본 설계심사는 보유 데이터 기반 사전 자동심사(보조)이며 "
                "건축사·구조기술사 검토 및 인허가권자 판단을 대체하지 않습니다. "
                "법령 근거 링크는 검증된 레지스트리 출력만 사용합니다."
            ),
        }

    # ── [UP3] run: 라우터(design_audit.py /run) 계약 어댑터 — audit() 위임 ───
    async def run(
        self,
        db: Any,
        *,
        site: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
        ifc_file_url: str | None = None,
        use_llm: bool = True,
        use_verification_retry: bool = True,
        rooms: list[dict[str, Any]] | None = None,
        prior_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """라우터 계약(run) → 기존 audit() 위임 어댑터(additive — audit 시그니처 불변).

        - site에서 zone_type·sigungu·address·pnu만 추출한다(없는 키는 None — 날조 금지).
        - geometry는 audit(shapes=)로 그대로 전달한다(rules8 기하검증).
        - ifc_file_url 제공 시 geometry_adapter.params_from_ifc(db) 분석 후
          merge_params(user>ifc)로 병합하고, 출처·5%+ 괴리(conflicts)를
          param_merge 키로 정직 표면화한다(IFC 분석 실패는 빈 병합 — 무중단).
        - use_llm·use_verification_retry는 라우터 계약 호환용으로 수용만 한다 —
          본 오케스트레이터는 결정론 전용이며 AI 보조(blindspot)는 라우터(DA-4) 소관.
        - 반환은 audit() 결과에 overall.verdict_en 영문 별칭(부적합→fail,
          조건부적합→conditional, 적합→pass, 판정불가→None)만 가산한다.
        """
        del use_llm, use_verification_retry  # 계약 수용만(결정론 — LLM은 라우터 소관)
        site = site if isinstance(site, dict) else {}

        merged_params = dict(params or {})
        param_merge: dict[str, Any] | None = None
        if ifc_file_url:
            from app.services.design_audit.geometry_adapter import merge_params, params_from_ifc

            ifc = await params_from_ifc(
                db, site.get("project_id"), site.get("tenant_id"), ifc_file_url
            )
            merge = merge_params(user=merged_params, ifc=ifc.get("params") or {})
            merged_params = merge["params"]
            param_merge = {
                "param_sources": merge["param_sources"],
                "conflicts": merge["conflicts"],
                "priority": merge["priority"],
                "ifc_available": bool(ifc.get("available")),
                "ifc_note": ifc.get("note"),
            }

        # ★공용 키 봉합(C2R WP-A 패턴): 프론트/부지분석 SSOT는 용도지역을 zone_code로 싣고,
        # audit 엔진은 zone_type을 읽는다 — 키 절단으로 용도지역이 엔진에 미도달해 permit·
        # incentives·solar 등 한도의존 엔진이 무조건 skip되던 문제를 관용 폴백으로 봉합한다
        # (zone_type 우선, 없으면 zone_code — 둘 다 없으면 None으로 정직 skip).
        zone_type = site.get("zone_type") or site.get("zone_code")
        # 대지면적은 site(부지분석 SSOT)에 실려 오지만 엔진은 params.land_area_sqm를 읽는다.
        # params(개요서 명시값)에 없을 때만 site 값으로 보강한다(명시값 우선·무날조·덮어쓰기 금지).
        # ★falsy 통일(R2 리뷰): `in (None, "")`는 0을 통과시켜 "0㎡ 대지면적"이라는 무의미한
        #   명시값을 site 통합값보다 우선시켰다(주석 의도와 불일치 — 0은 값 없음과 동치로 취급).
        if not merged_params.get("land_area_sqm") and site.get("land_area_sqm") not in (None, ""):
            merged_params["land_area_sqm"] = site.get("land_area_sqm")

        result = await self.audit(
            merged_params,
            zone_type=zone_type,
            sigungu=site.get("sigungu"),
            address=site.get("address"),
            pnu=site.get("pnu"),
            shapes=geometry,
            # 조례·계획 상한 페이로드 전달 배선(인센티브 조례계층 실효한도 산정용) —
            # 미전달 시 None(far_tier_service가 용도지역 기본값으로 폴백, 무중단).
            regulation_payload=site.get("regulation_payload"),
            rooms=rooms,
            prior_context=prior_context,
        )

        overall = result.get("overall")
        if isinstance(overall, dict):
            overall["verdict_en"] = VERDICT_EN_ALIASES.get(str(overall.get("verdict")))
        if param_merge is not None:
            result["param_merge"] = param_merge
        return result

    # ── [UP3] grammar: 평면 문법 검증(unit_plan_generator 경계 엔진 재사용) ──
    def _run_grammar(self, rooms: list[dict[str, Any]]) -> dict[str, Any]:
        """arch_grammar KB 기반 평면 문법 검증을 AuditFinding으로 정규화한다.

        파이프라인(결정론 — unit_plan_generator 경계 엔진, arch_grammar KB 소비):
          boundaries_from_bbox_rooms(업로드 bbox 실의 공유변 — 타일링 갭 허용,
          미인접·갭은 warnings로 정직 보고) → classify_boundaries(LDK 오픈·
          1실 1문) → place_openings(문·채광창 50mm 그리드) →
          validate_connectivity(현관 기점 BFS).
        업로드 도면의 역추출 rooms는 bbox 근사라 빈틈없는 타일링을 보장하지
        않으므로, 타일링 전제인 extract_boundaries 대신 갭 허용 어댑터를 쓴다.
        경고(미배치·미도달·승격·창면적 미달·갭 등)는 warning, 무경고는 pass 1건.
        rooms 형식 오류·실행 실패는 skipped(정직) — 종합판정 미반영.
        """
        try:
            from app.services.cad.shapes_to_rooms import boundaries_from_bbox_rooms
            from app.services.cad.unit_plan_generator import (
                classify_boundaries,
                place_openings,
                validate_connectivity,
            )

            if not rooms:
                raise ValueError("rooms 비어 있음")
            for r in rooms:
                # 형식 검증 — bbox 결손은 기하 갭이 아닌 형식 오류(skipped 대상).
                # 어댑터의 갭 관용은 '키는 있으나 타일링이 안 맞는' 경우만이다.
                (str(r["name"]), float(r["x"]), float(r["y"]),
                 float(r["w"]), float(r["h"]))

            adj = boundaries_from_bbox_rooms(rooms)
            boundaries = adj["boundaries"]
            adj_warnings = adj["warnings"]
            classified, cls_warnings = classify_boundaries(boundaries, rooms)
            openings, open_warnings = place_openings(classified, rooms)
            conn_violations = validate_connectivity(rooms, classified, openings)
        except Exception as e:  # noqa: BLE001 — 형식 오류·엔진 실패는 skipped(정직)
            logger.warning("평면 문법 검증 실패 — skipped 처리", error=str(e)[:160])
            return {
                "status": "failed",
                "findings": [make_finding(
                    "grammar", "grammar", STATUS_SKIPPED,
                    note=f"평면 문법 검증 실패 — 결과 미산출(정직한 생략): {str(e)[:160]}",
                )],
                "section": {"skipped": True, "note": f"문법 검증 실패: {str(e)[:160]}"},
            }

        findings: list[dict[str, Any]] = []
        groups: tuple[tuple[str, list[dict[str, Any]]], ...] = (
            ("adjacency", adj_warnings),        # bbox 공유변 미인접·타일링 갭
            ("boundary", cls_warnings),         # LDK 오픈·1실 1문(승격/미배치)
            ("opening", open_warnings),         # 문·채광창 배치(미배치·창면적 미달)
            ("connectivity", conn_violations),  # 현관 기점 도달성(미도달)
        )
        for kind, items in groups:
            for w in items:
                findings.append(make_finding(
                    f"grammar_{kind}", "grammar", STATUS_WARNING,
                    current=w.get("actual"),
                    limit=w.get("legal"),
                    improvement=w.get("message"),
                    note=f"{w.get('rule')} — 대상: {w.get('field')}",
                ))
        if not findings:
            findings.append(make_finding(
                "grammar", "grammar", STATUS_PASS,
                current=f"경계 {len(classified)}개 · 개구 {len(openings)}개",
                note="평면 문법(LDK 오픈·1실 1문·채광창·현관 기점 연결성) 경고 없음",
            ))

        grammar_warnings = (
            list(adj_warnings) + list(cls_warnings)
            + list(open_warnings) + list(conn_violations)
        )
        # 리포트 S5 핑거용 요약(실데이터에서만 파생 — 가짜값 0)
        open_pairs = sorted(
            f"{b.get('room_a')}-{b.get('room_b')}"
            for b in classified
            if b.get("kind") == "open" and b.get("room_b")
        )
        section = {
            "skipped": False,
            "boundaries": classified,
            "openings": openings,
            "grammar_warnings": grammar_warnings,
            "ldk_open": {"open_count": len(open_pairs), "pairs": open_pairs},
            "connectivity": {
                "ok": not conn_violations,
                "violations": len(conn_violations),
            },
            "daylight": {
                "window_count": sum(
                    1 for o in openings if str(o.get("id", "")).startswith("w")
                ),
            },
        }
        return {"status": "ok", "findings": findings, "section": section}

    # ── ⑨ bl_rules: 피난·방화(BL-007) — 정본 building_code_rules 위임 ──────────
    def _run_bl_rules(self, params: dict[str, Any], zone_type: str | None) -> dict[str, Any]:
        """9번째 엔진 — 정본 building_code_rules에 위임해 피난·방화(BL-007)를 surface한다.

        신작 금지: BuildingCodeRuleEngine._check_fire_escape(건축법 시행령 §34 직통계단·
        §46 방화구획·§35 특별피난계단) 결과를 AuditFinding으로 옮겨 담기만 한다.
        데이터(층수·연면적·층당면적) 전무 시 skipped(정직 — 임의값으로 강행 금지).
        주차(BL-005)는 엔진 ④에서 이미 산정하므로 중복 계상 방지로 여기서 재검하지 않는다.
        """
        floors = _num(params.get("floors_above"))
        gfa = _num(params.get("total_floor_area_sqm"))
        floor_area = _num(params.get("floor_area_per_floor_sqm"))
        if floors is None and gfa is None and floor_area is None:
            return {
                "status": "skipped",
                "findings": [make_finding(
                    "bl_fire_escape", "bl_rules", STATUS_SKIPPED,
                    note="층수·연면적·층당면적 없음 — 피난/방화(직통계단·방화구획) 검토 생략(임의값 금지)",
                )],
                "section": None,
            }
        try:
            from app.services.permit.building_code_rules import (
                BuildingCodeRuleEngine,
                ComplianceStatus,
            )

            design = {
                "floor_count_above": int(floors) if floors is not None else 1,
                "total_gfa_sqm": gfa or 0.0,
                "floor_area_per_floor_sqm": floor_area or 0.0,
                "building_height_m": _num(params.get("building_height_m")) or 0.0,
            }
            res = BuildingCodeRuleEngine()._check_fire_escape(design, {"zone_type": zone_type or ""})
        except Exception as e:  # noqa: BLE001 — 정본 위임 실패는 skipped(정직)
            logger.warning("피난/방화(BL-007) 위임 실패 — skipped 처리", error=str(e)[:160])
            return {
                "status": "failed",
                "findings": [make_finding(
                    "bl_fire_escape", "bl_rules", STATUS_SKIPPED,
                    note=f"피난/방화 검토 실패 — 결과 미산출(정직한 생략): {str(e)[:160]}",
                )],
                "section": None,
            }

        # ComplianceStatus → AuditFinding.status.
        # ★WARNING→info(판정 미반영, R2 리뷰 확정방침): _check_fire_escape는 "5층 이상 OR
        #   층당 200㎡ 초과"면 **무조건** WARNING을 낸다 — 이는 확정 위반이 아니라 "직통계단·
        #   방화구획 요건이 존재하니 설계도서에서 확인하라"는 정직한 불확실 신호다(파라미터만으로
        #   판정 불가). 이 요건은 사실상 모든 중규모 이상 건물에서 발화하므로, 예전처럼
        #   STATUS_WARNING으로 verdict를 지배시키면 현실의 거의 모든 건물이 "조건부적합"에
        #   묶여 "적합"에 도달할 수 없다(모든 건물에서 발화하는 경고는 신호가 없다 — 헤드라인
        #   회귀). FAIL(확정 위반 — 이 룰은 현재 산출하지 않지만 향후 확장 대비)은 종전대로
        #   verdict에 반영한다. 검사 자체는 info로도 findings/PDF에 정직하게 surface된다
        #   (message에 "설계도서에서 확인 필요: ..." 문구 유지 — 무근거 낙관이 아니라 판정
        #   불가 항목의 정직한 등급).
        status_map = {
            ComplianceStatus.PASS: STATUS_PASS,
            ComplianceStatus.FAIL: STATUS_FAIL,
            ComplianceStatus.WARNING: STATUS_INFO,
            ComplianceStatus.NOT_APPLICABLE: STATUS_INFO,
        }
        finding = make_finding(
            "bl_fire_escape", "bl_rules", status_map.get(res.status, STATUS_INFO),
            current=res.actual_value,
            limit=res.required_value,
            legal_ref_keys=["evacuation"],
            improvement=res.message,
            note=f"{res.rule_name}({res.legal_basis})",
        )
        section = {
            "rule_id": res.rule_id,
            "status": str(res.status),
            "required": res.required_value,
            "actual": res.actual_value,
            "message": res.message,
            "legal_basis": res.legal_basis,
        }
        return {"status": "ok", "findings": [finding], "section": section}

    # ── ① rules8: 기하 8룰(BuildingComplianceService 검증기 재사용) ──────────
    async def _run_rules8(
        self,
        params: dict[str, Any],
        shapes: dict[str, Any] | None,
        applied_bcr: float | None,
        applied_far: float | None,
        max_height: float | None,
        sigungu: str | None,
    ) -> dict[str, Any]:
        payload = design_payload_from_shapes(shapes)
        if not payload.get("valid"):
            return {"findings": [make_finding(
                "rules8", "rules8", STATUS_SKIPPED,
                note="기하(도형) 데이터 없음/무효 — 8룰 기하검증 생략: "
                     + "; ".join(payload.get("issues") or []),
            )]}
        site_area = _num(params.get("land_area_sqm"))
        if not site_area or site_area <= 0:
            return {"findings": [make_finding(
                "rules8", "rules8", STATUS_SKIPPED,
                note="대지면적 없음 — 건폐율/용적률 기하검증 불가(임의 면적 가정 금지)",
            )]}
        if applied_bcr is None or applied_far is None:
            return {"findings": [make_finding(
                "rules8", "rules8", STATUS_SKIPPED,
                note="용도지역 한도 미상 — 기하 법규검증 생략(허위 한도 생성 금지)",
            )]}

        from apps.api.services.building_compliance_service import (
            DesignData,
            DesignLine,
            DesignPoint,
            DesignSurface,
            LegalLimits,
            LegalRegulationVerifier,
            StructuralAnalysisVerifier,
        )

        design = payload["design"]
        data = DesignData(
            points=[DesignPoint(**p) for p in design["points"]],
            lines=[DesignLine(**ln) for ln in design["lines"]],
            surfaces=[DesignSurface(**s) for s in design["surfaces"]],
            floor_count=design["floor_count"],
            building_height_m=design["building_height_m"],
            scale=design["scale"],
            setback_distances=design.get("setback_distances"),
            north_setback_m=design.get("north_setback_m", 0.0),
        )
        # min_setback은 조례·가로구역별 상이 — 미상 시 0(미적용)으로 정직 처리,
        # max_height 미상(None=무제한 포함)은 inf(높이룰 비활성).
        limits = LegalLimits(
            building_coverage_ratio=applied_bcr / 100.0,
            floor_area_ratio=applied_far / 100.0,
            max_height_m=max_height if max_height else float("inf"),
            min_setback_m=0.0,
            sunlight_hours_min=0.0,
        )
        violations = (
            LegalRegulationVerifier().verify(data, site_area, limits)
            + StructuralAnalysisVerifier().verify(data)
        )

        findings: list[dict[str, Any]] = []
        for v in violations:
            findings.append(make_finding(
                f"rules8_{v.type}", "rules8",
                STATUS_FAIL if v.severity == "error" else STATUS_WARNING,
                current=round(v.current_value, 4),
                limit=round(v.limit_value, 4),
                legal_ref_keys=list(_RULES8_REF_KEYS.get(v.type, ())),
                improvement=v.message + " — 착공 전 도면 조정으로 흡수 가능(설계변경비 최소화)",
                sigungu=sigungu,
            ))
        if not findings:
            findings.append(make_finding(
                "rules8", "rules8", STATUS_PASS,
                note="기하 법규검증(건폐율·용적률·높이·세트백·일조이격·벽체경간) 위반 없음",
                sigungu=sigungu,
            ))
        section = {
            "violations": [
                {"type": v.type, "message": v.message, "severity": v.severity,
                 "current_value": v.current_value, "limit_value": v.limit_value}
                for v in violations
            ],
            "issues": payload.get("issues") or [],
        }
        return {"findings": findings, "section": ("rules8", section)}

    # ── ② design_review: 파라미터 법규검토(DesignReviewService) ─────────────
    async def _run_design_review(
        self,
        params: dict[str, Any],
        applied_far: float | None,
        applied_bcr: float | None,
        sigungu: str | None,
    ) -> dict[str, Any]:
        far_v = _num(params.get("far_pct"))
        bcr_v = _num(params.get("bcr_pct"))
        if far_v is None and bcr_v is None:
            return {"findings": [make_finding(
                "design_review", "design_review", STATUS_SKIPPED,
                note="설계 건폐율·용적률 미입력 — 파라미터 법규검토 생략(0 가정 금지)",
            )]}
        if applied_far is None or applied_bcr is None:
            return {"findings": [make_finding(
                "design_review", "design_review", STATUS_SKIPPED,
                note="용도지역 실효한도 미상 — 파라미터 법규검토 생략(허위 한도 생성 금지)",
            )]}

        from app.services.design_review.design_review_service import DesignReviewService

        missing = [label for label, v in (("용적률", far_v), ("건폐율", bcr_v)) if v is None]
        review = DesignReviewService().review_design_parameters(
            {"far_applied": far_v if far_v is not None else 0,
             "bcr_applied": bcr_v if bcr_v is not None else 0},
            {"max_far": applied_far, "max_bcr": applied_bcr},
        )

        findings: list[dict[str, Any]] = []
        errors = review.get("errors_detected") or []
        corrections = review.get("correction_items") or []
        for idx, err in enumerate(errors):
            ref_key = err.get("legal_ref_key")
            findings.append(make_finding(
                f"design_review_{err.get('item')}", "design_review", STATUS_FAIL,
                current=err.get("current"),
                limit=err.get("limit"),
                legal_ref_keys=[ref_key] if ref_key else None,
                improvement=corrections[idx] if idx < len(corrections) else None,
                sigungu=sigungu,
            ))
        if not errors:
            findings.append(make_finding(
                "design_review", "design_review", STATUS_PASS,
                current=f"용적률 {far_v if far_v is not None else '미입력'}% · "
                        f"건폐율 {bcr_v if bcr_v is not None else '미입력'}%",
                limit=f"실효한도 용적률 {applied_far}% · 건폐율 {applied_bcr}%",
                legal_ref_keys=["bldg_far", "bldg_bcr"],
                note=("미입력 항목은 검증 대상에서 제외: " + ", ".join(missing)) if missing else None,
                sigungu=sigungu,
            ))
        return {"findings": findings, "section": ("design_review", review)}

    # ── ③ solar_envelope: 정북일조 인벨로프 + 일영 SVG ───────────────────────
    async def _run_solar(
        self,
        params: dict[str, Any],
        zone_type: str | None,
        applied_bcr: float | None,
        applied_far: float | None,
        sigungu: str | None,
    ) -> dict[str, Any]:
        land_area = _num(params.get("land_area_sqm"))
        if not zone_type or not land_area or land_area <= 0:
            return {"findings": [make_finding(
                "solar_envelope", "solar_envelope", STATUS_SKIPPED,
                note="용도지역 또는 대지면적 없음 — 정북일조 인벨로프 산정 생략",
            )]}

        from app.services.site_score.solar_envelope_service import compute_buildable_envelope

        envelope = compute_buildable_envelope(
            land_area_sqm=land_area,
            zone=zone_type,
            land_width_m=_num(params.get("site_width_m")),
            land_depth_m=_num(params.get("site_depth_m")),
            floor_height_m=_num(params.get("floor_height_m")) or 3.0,
            bcr_limit_pct=applied_bcr,
            far_limit_pct=applied_far,
        )
        if envelope.get("error"):
            return {"findings": [make_finding(
                "solar_envelope", "solar_envelope", STATUS_SKIPPED,
                note=f"인벨로프 산정 불가 — {envelope['error']}",
            )]}

        height_v = _num(params.get("building_height_m"))
        ceiling = _num(envelope.get("daylight_ceiling_m"))
        applies = bool(envelope.get("applies_north_light"))

        if applies and height_v is not None and ceiling is not None and height_v > ceiling:
            status = STATUS_WARNING  # v1 근사모형 — 확정 위반이 아닌 정밀검토 필요 경고
            improvement = (
                f"계획 높이 {height_v:.1f}m가 정북일조 사선 최고선(근사) {ceiling:.1f}m를 초과 — "
                "최상층 후퇴(테라스형)·정북측 이격 확대를 검토하고 정밀 일영분석으로 확정하세요."
            )
        else:
            status = STATUS_PASS
            improvement = None

        finding = make_finding(
            "solar_envelope", "solar_envelope", status,
            current=f"{height_v:.1f}m" if height_v is not None else "높이 미입력",
            limit=(f"일조 사선 최고선(근사) {ceiling:.1f}m" if (applies and ceiling is not None)
                   else "정북일조 미적용 용도지역"),
            legal_ref_keys=["daylight_height", "daylight_height_dec"] if applies else None,
            improvement=improvement,
            note=None if applies else "정북일조 미적용 용도지역 — 용적률/건폐율이 한도(인벨로프 참고)",
            sigungu=sigungu,
        )

        # 일영(그림자) SVG — 건물 풋프린트(건축면적 정사각 근사)와 높이가 있을 때만 생성.
        shadow_svg: str | None = None
        building_area = _num(params.get("building_area_sqm"))
        if height_v and building_area and building_area > 0:
            try:
                from app.services.drawing.shadow_simulator import ShadowSimulator

                side = math.sqrt(building_area)
                shadow_svg = ShadowSimulator().generate({
                    "building_w": side, "building_d": side, "building_h": height_v,
                    "analysis_date": "winter_solstice",
                })
            except Exception as e:  # noqa: BLE001 — SVG 실패는 인벨로프 결과를 막지 않음
                logger.warning("일영 SVG 생성 스킵", error=str(e)[:120])

        section = {
            "envelope": envelope,
            "shadow_svg": shadow_svg,
            "shadow_note": None if shadow_svg else "일영 SVG 미생성 — 건축면적·높이 데이터 필요(정사각 풋프린트 근사)",
        }
        return {"findings": [finding], "section": ("solar_envelope", section)}

    # ── ④ parking: 법정주차(_compute_parking 재사용) ─────────────────────────
    async def _run_parking(self, params: dict[str, Any], sigungu: str | None) -> dict[str, Any]:
        units = _num(params.get("units"))
        gfa = _num(params.get("total_floor_area_sqm"))
        if units is None and gfa is None:
            return {"findings": [make_finding(
                "parking", "parking", STATUS_SKIPPED,
                note="세대수·연면적 모두 없음 — 법정주차 산정 생략(0대 날조 금지)",
            )]}

        # ★주차 정본 = 주차장법 시행령 §6(별표1). 룰 정본은 building_code_rules.BL-005
        #   (_check_parking)이며, 여기 auto_design_engine._compute_parking은 동일 법적근거(§6)의
        #   런타임 계산 경로다(공동주택 1.0대/세대로 BL-005와 대수 산식 일치). 중복 계상 방지를 위해
        #   9번째 bl_rules 엔진은 주차를 재검하지 않고 피난(BL-007)만 surface한다(단일 SSOT).
        from app.services.cad.auto_design_engine import PARKING_RULES, _compute_parking

        building_use = str(params.get("building_use") or "공동주택")
        rule = PARKING_RULES.get(building_use, PARKING_RULES["공동주택"])
        if rule.get("per_unit") and units is None:
            return {"findings": [make_finding(
                "parking", "parking", STATUS_SKIPPED,
                note=f"'{building_use}'는 세대당 기준 — 세대수 미입력으로 법정주차 산정 불가(0대 날조 금지)",
            )]}
        calc = _compute_parking(int(units or 0), float(gfa or 0), building_use)
        required = int(calc.get("required") or 0)
        provided = _num(params.get("parking"))

        limit_text = f"최소 {required}대(주차장법 단순화 — 지역·전용면적별 세부기준 미반영)"
        if provided is None:
            finding = make_finding(
                "parking", "parking", STATUS_WARNING,
                current="미입력",
                limit=limit_text,
                legal_ref_keys=["parking_min", "parking_min_dec"],
                improvement=f"주차계획을 확정하고 최소 {required}대를 확보하세요(착공 후 부족 발견 시 고비용).",
                sigungu=sigungu,
            )
        elif provided < required:
            finding = make_finding(
                "parking", "parking", STATUS_FAIL,
                current=f"{provided:.0f}대",
                limit=limit_text,
                legal_ref_keys=["parking_min", "parking_min_dec"],
                improvement=(
                    f"{required - provided:.0f}대 추가 확보(기계식·필로티·지하층) 또는 "
                    "세대수·연면적을 법정주차 충족 수준으로 조정하세요."
                ),
                sigungu=sigungu,
            )
        else:
            finding = make_finding(
                "parking", "parking", STATUS_PASS,
                current=f"{provided:.0f}대",
                limit=limit_text,
                legal_ref_keys=["parking_min", "parking_min_dec"],
                sigungu=sigungu,
            )
        section = {"required": required, "provided": provided, "basis": calc, "use": building_use}
        return {"findings": [finding], "section": ("parking", section)}

    # ── ⑤ permit: 인허가(check_permit_feasibility + PermitAnalysisService) ──
    async def _run_permit(
        self,
        params: dict[str, Any],
        zone_type: str | None,
        address: str | None,
        applied_bcr: float | None,
        applied_far: float | None,
        sigungu: str | None,
    ) -> dict[str, Any]:
        if not zone_type:
            return {"findings": [make_finding(
                "permit", "permit", STATUS_SKIPPED,
                note="용도지역 미상 — 인허가 가능성 판정 생략(허위 판정 금지)",
            )]}

        from app.services.feasibility.permit_validator import check_permit_feasibility

        dev_type, dev_basis = _dev_type_from_use(params.get("building_use"))
        feasibility = check_permit_feasibility(dev_type, zone_type)
        permitted = bool(feasibility.get("is_permitted"))

        improvement = None
        if not permitted:
            try:
                from app.services.feasibility.permit_validator import (
                    DEVELOPMENT_TYPE_NAMES,
                    get_permitted_types,
                )

                allowed = [DEVELOPMENT_TYPE_NAMES.get(c, c) for c in get_permitted_types(zone_type)]
                improvement = (
                    f"{zone_type}에서 허용되는 개발유형으로 변경 검토: "
                    + (", ".join(allowed) if allowed else "허용 유형 없음(개발 불가 지역)")
                )
            except Exception:  # noqa: BLE001
                improvement = "용도지역 허용용도에 맞는 개발유형 변경 또는 용도지역 변경(종상향) 검토"

        finding = make_finding(
            "permit_feasibility", "permit",
            STATUS_PASS if permitted else STATUS_FAIL,
            current=f"{feasibility.get('type_name')}({dev_type})",
            limit=f"{zone_type} 허용용도(국토계획법 제76조)",
            legal_ref_keys=["zone_use", "building_permit"],
            improvement=improvement,
            note=dev_basis,
            sigungu=sigungu,
        )

        # 주소 제공 시에만 규칙기반 인허가 환경 분석(use_llm=False 고정 — 결정론).
        analysis: dict[str, Any] | None = None
        if address:
            try:
                from app.services.permit.permit_analysis_service import PermitAnalysisService

                analysis = await PermitAnalysisService().analyze(
                    address,
                    site={
                        "zone_type": zone_type,
                        "max_bcr": applied_bcr,
                        "max_far": applied_far,
                        "land_area_sqm": _num(params.get("land_area_sqm")),
                    },
                    use_llm=False,
                )
            except Exception as e:  # noqa: BLE001 — 보조 분석 실패는 판정을 막지 않음
                logger.warning("인허가 환경 분석 스킵", error=str(e)[:120])

        section = {"feasibility": feasibility, "dev_type_basis": dev_basis, "analysis": analysis}
        return {"findings": [finding], "section": ("permit", section)}

    # ── ⑥ change_risk: 설계변경 사전예측(DesignChangePredictor 룰기반) ──────
    async def _run_change_risk(self, params: dict[str, Any], zone_type: str | None) -> dict[str, Any]:
        from app.services.design_risk.design_change_predictor import DesignChangePredictor

        design = {
            "bcr": _num(params.get("bcr_pct")),
            "far": _num(params.get("far_pct")),
            "height_m": _num(params.get("building_height_m")),
            # ★이중 안전 — floors/units만 _num() 없이 원문(brief 추출은 문자열)을 그대로 써서
            #   design_change_predictor의 `floors >= 5` 등 수치비교가 'str'≥'int' TypeError로
            #   죽고, 그 예외가 삼켜져 'skipped'로 위장 표시되던 결함(라이브 재현). 흡수 지점
            #   (routers/design_audit.py:_normalize_numeric_params)에서 이미 정규화하지만,
            #   이 dict의 다른 모든 필드처럼 여기서도 _num()으로 재확인한다(근원 봉합).
            "floors": _num(params.get("floors_above")),
            "floor_height_m": _num(params.get("floor_height_m")),
            "gfa": _num(params.get("total_floor_area_sqm")),
            "units": _num(params.get("units")),
            "parking": _num(params.get("parking")),
            "building_type": params.get("building_use"),
            "avg_unit_area_sqm": _num(params.get("avg_unit_area_sqm")),
            "land_area_sqm": _num(params.get("land_area_sqm")),
            "building_area_sqm": _num(params.get("building_area_sqm")),
        }
        prediction = DesignChangePredictor().predict(design, zone_type or "")
        summary = prediction.get("summary") or {}
        high = int(summary.get("high") or 0)
        warn = int(summary.get("warn") or 0)

        # 예측 엔진은 '사전 경고'(확정 아님) — 법규 fail 판정은 rules8/design_review 소관.
        if high or warn:
            status = STATUS_WARNING
            top_items = [r.get("item") for r in (prediction.get("risks") or [])
                         if r.get("severity") == "high"][:3]
            improvement = str(summary.get("total_predicted_impact_note") or "")
            if top_items:
                improvement += " 우선 보완: " + ", ".join(str(t) for t in top_items)
        else:
            status = STATUS_PASS
            improvement = None

        finding = make_finding(
            "design_change_risk", "change_risk", status,
            current=f"고위험 {high}건 · 주의 {warn}건 · 참고 {int(summary.get('info') or 0)}건",
            limit=None,
            improvement=improvement,
            note="사전 예측·경고(확정 아님) — 건축사·구조기술사 검토 필요",
        )
        return {"findings": [finding], "section": ("change_risk", prediction)}

    # ── ⑦ incentives: [S4] 인센티브(종상향 PATHS + 실효FAR + 기부채납 시뮬) ──
    async def _run_incentives(
        self,
        params: dict[str, Any],
        zone_type: str | None,
        sigungu: str | None,
        regulation_payload: Any,
        limits: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not zone_type or limits is None:
            return {"findings": [make_finding(
                "far_incentive_potential", "incentives", STATUS_SKIPPED,
                note="용도지역 미상 — 인센티브·종상향 잠재력 산정 생략",
            )]}

        from app.services.land_intelligence import far_tier_service

        base = regulation_payload if isinstance(regulation_payload, dict) else {}
        land_area = _num(params.get("land_area_sqm")) or 0.0

        # 실효용적률 계층 + 기부채납 인센티브 시뮬레이션(far_tier_service 단일출처).
        effective = far_tier_service.calc_effective_far(base, zone_type, land_area)
        # 종상향 잠재 시나리오(upzoning_potential PATHS 규칙엔진 — 예상치).
        upzoning = far_tier_service.calc_upzoning(base, zone_type, land_area)
        donation = effective.get("far_incentive") or {}

        potential_range = upzoning.get("potential_far_range") or {}
        potential_high = _num(potential_range.get("max_pct"))
        donation_max = _num(donation.get("max_far"))
        limit_parts: list[str] = []
        if donation_max is not None:
            limit_parts.append(f"기부채납 시 최대 {donation_max:g}%")
        if potential_high is not None:
            limit_parts.append(f"종상향 예상 상한 {potential_high:g}%(예상치)")

        finding = make_finding(
            "far_incentive_potential", "incentives", STATUS_INFO,
            current=f"실효 용적률 {effective.get('effective_far_pct')}%",
            limit=" · ".join(limit_parts) if limit_parts else None,
            legal_ref_keys=["far_limit", "district_unit_plan"],
            improvement=upzoning.get("summary"),
            note="예상치 — 실현 보장 아님(도시계획 결정·인허가 전제), 종합판정(overall)에 미반영",
            sigungu=sigungu,
        )
        section = {
            "effective_far": effective,
            "donation_simulation": donation,
            "upzoning": upzoning,
        }
        return {"findings": [finding], "section": ("s4_incentives", section)}

    # ── ⑧ case_compare: [S1~S3] 인근 인허가 사례 비교 ────────────────────────
    async def _run_case_compare(
        self,
        params: dict[str, Any],
        pnu: str | None,
        sigungu: str | None,
        case_service: Any,
    ) -> dict[str, Any]:
        if not pnu:
            section = {"available": False, "note": "PNU 미제공 — 인근 인허가 사례 비교 생략"}
            return {
                "findings": [make_finding(
                    "nearby_case_position", "case_compare", STATUS_SKIPPED,
                    note="PNU 미제공 — 인근 인허가 사례 비교 생략(가짜 사례 생성 금지)",
                )],
                "section": ("s1_samples", section),
            }

        service = case_service
        if service is None:
            from app.services.permit.permit_case_service import PermitCaseService

            service = PermitCaseService()

        response = await service.get_nearby_cases(pnu)
        summary = response.summary
        summary_dict = summary.model_dump() if summary is not None else {}
        sample_count = int(summary_dict.get("count") or 0)
        case_summary = {
            "available": sample_count > 0,
            "sample_count": sample_count,
            **summary_dict,
        }

        from app.services.design_review.design_review_service import DesignReviewService

        comparison = DesignReviewService().compare_with_nearby_cases(
            {"far_applied": _num(params.get("far_pct")), "bcr_applied": _num(params.get("bcr_pct"))},
            case_summary,
        )

        available = bool(comparison.get("available"))
        far_v = _num(params.get("far_pct"))
        bcr_v = _num(params.get("bcr_pct"))
        current_parts = []
        if far_v is not None:
            current_parts.append(f"FAR {far_v:g}%")
        if bcr_v is not None:
            current_parts.append(f"BCR {bcr_v:g}%")
        finding = make_finding(
            "nearby_case_position", "case_compare",
            STATUS_INFO if available else STATUS_SKIPPED,
            current=" · ".join(current_parts) if current_parts else None,
            limit=None,
            improvement=comparison.get("note"),
            note=None if available else (response.note or "인근 인허가 사례 없음 — 비교 생략(정직)"),
        )
        section = {
            "available": available,
            "total": response.total,
            "summary": summary_dict,
            "source": getattr(response, "source", None),
            "note": response.note,
            "comparison": comparison,
        }
        return {"findings": [finding], "section": ("s1_samples", section)}


# 모듈 싱글턴 + 편의 진입점(기존 서비스 스타일).
design_audit_orchestrator = DesignAuditOrchestrator()


async def run_design_audit(params: dict[str, Any] | None, **kwargs: Any) -> dict[str, Any]:
    """모듈 편의 진입점 — DesignAuditOrchestrator.audit 위임."""
    return await design_audit_orchestrator.audit(params, **kwargs)
