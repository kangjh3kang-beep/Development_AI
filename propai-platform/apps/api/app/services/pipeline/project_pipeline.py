"""프로젝트 전주기 자동 분석 파이프라인.

주소 입력만으로 부지분석→설계→공사비→수지분석→세금→ESG→보고서를 순차 실행한다.
각 단계의 결과는 다음 단계의 입력으로 자동 전달된다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# ── Payload 인터페이스: 모듈 간 데이터 전달 계약 ──


class PipelineStage(StrEnum):
    SITE_ANALYSIS = "site_analysis"
    DESIGN = "design"
    # 심의/설계도면 자동분석(별도 엔진 BFF). design→design_review→cost 의존.
    # ★엔진 미연결 시 SKIPPED로 처리해 파이프라인 전체를 깨지 않는다(graceful).
    DESIGN_REVIEW = "design_review"
    COST = "cost"
    FEASIBILITY = "feasibility"
    TAX = "tax"
    ESG = "esg"
    REPORT = "report"


class PipelineStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageResult(BaseModel):
    stage: PipelineStage
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SiteToDesignPayload(BaseModel):
    """부지분석 → 설계 전달 데이터."""

    pnu_codes: list[str] = Field(default_factory=list)
    zone_type: str = ""
    # ★무날조(WP-U1c): 0.0=미산정 센티널. 과거 기본값 60/200은 부지자료 없이 페이로드가
    #   생성되면(부지단계 skip 등) 임의 한도를 '실측'처럼 발명했다 — _run_design은 0/None을
    #   W3-8 계약(assumed_fields 정직 표기 + 보수 기본치 명시 라벨링)으로 소비한다.
    max_bcr: float = 0.0
    max_far: float = 0.0
    max_height: float = 0.0
    land_area_sqm: float = 0.0
    # ★A-2(배선 P1 — usable 면적 전파, additive) — 다필지 통합 경로에서만 채워짐(gross 기준).
    #   land_area_sqm(개발규모=GFA 산정 기준)은 usable 채택, 이 필드(토지비 산정 기준)는
    #   gross 유지 — comprehensive_analysis_service F2/P0-2(c)와 동일 이원화. None=단일/미통합
    #   (다운스트림은 land_area_sqm으로 폴백 — 기존 동작 무회귀).
    land_area_gross_sqm: float | None = None
    land_shape: dict | None = None  # GeoJSON
    official_land_price: float = 0.0
    address: str = ""
    coordinates: dict | None = None  # {lat, lon}


class DesignToCostPayload(BaseModel):
    """설계 → 공사비 전달 데이터."""

    total_gfa_sqm: float = 0.0
    floor_count_above: int = 0
    floor_count_below: int = 0
    structure_type: str = "RC"
    building_type: str = ""
    unit_count: int = 0
    avg_unit_area_pyeong: float = 0.0


class CostToFeasibilityPayload(BaseModel):
    """공사비 → 수지분석 전달 데이터."""

    total_construction_cost: float = 0.0
    cost_per_pyeong: float = 0.0
    construction_months: int = 24
    material_quantities: list[dict] = Field(default_factory=list)
    cost_breakdown: dict[str, Any] = Field(default_factory=dict)  # 공종별 비용 상세


# ── 유닛믹스 고도화 상수 ──
# 건물유형별 전용률(연면적 대비 분양/전용면적 비율) 정본은 unit_standards로 수렴됨
# (P2 전용률 정본 수렴, 2026-07-11 — 구 자체 이중정의 _SELLABLE_EFFICIENCY_BY_TYPE/
# _DEFAULT_SELLABLE_EFFICIENCY 제거). ★(G4) FE/BE 이중 하드코딩 계약 상세 주석·프론트 미러
# (node-body-builders.ts)·계약 테스트 위치는 unit_standards.get_sellable_efficiency
# docstring 옆 주석을 참조. 값을 바꿀 때는 그쪽 표와 두 계약 테스트를 함께 갱신할 것.

# 유닛믹스 최적화를 적용할 주거 계열 건물유형(상업/근생은 평형 배분 미적용).
_RESIDENTIAL_TYPES = {"아파트", "다세대주택", "공동주택", "오피스텔"}

# 건물유형별 허용 평형(None=전체). 다세대·오피스텔은 중소형 위주.
_ENABLED_UNIT_TYPES: dict[str, list[str] | None] = {
    "아파트": None,
    "공동주택": None,
    "다세대주택": ["S39", "S49", "S59", "S74", "S84"],
    "오피스텔": ["S39", "S49", "S59"],
}

# 평형별 분양가 프리미엄 — 84㎡(25평)=1.0 기준으로 정규화.
# 지역 기준시세(regional_pricing 단일 출처, 만원/평)에 곱해 평형별 분양가를 산출한다.
_UNIT_PRICE_PREMIUM: dict[str, float] = {
    "S39": 0.80, "S49": 0.86, "S59": 0.91, "S74": 0.97,
    "S84": 1.00, "S102": 1.09, "S135": 1.20,
}

# 부지분석 오버라이드 중 숫자형 강제 변환 대상 키.
# 잘못된 입력(비숫자 문자열 등)이 float() 캐스팅에서 단계를 실패시키지 않도록 선검증한다.
_NUMERIC_SITE_OVERRIDE_KEYS = {
    "land_area_sqm", "official_land_price", "max_bcr", "max_far", "max_height",
    "national_bcr", "national_far", "ordinance_bcr", "ordinance_far",
}


class PipelineState(BaseModel):
    """파이프라인 전체 상태."""

    pipeline_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    address: str = ""
    status: PipelineStatus = PipelineStatus.PENDING
    current_stage: PipelineStage | None = None
    stages: dict[str, StageResult] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    # 모듈 간 전달 데이터
    site_to_design: SiteToDesignPayload | None = None
    design_to_cost: DesignToCostPayload | None = None
    cost_to_feasibility: CostToFeasibilityPayload | None = None


class ProjectPipeline:
    """프로젝트 전주기 자동 분석 파이프라인."""

    def __init__(self):
        self._stages_order = list(PipelineStage)

    async def run(
        self,
        address: str,
        project_id: str | None = None,
        options: dict | None = None,
    ) -> PipelineState:
        """주소 입력으로 전체 파이프라인 실행."""
        state = PipelineState(
            project_id=project_id or str(uuid.uuid4()),
            address=address,
            status=PipelineStatus.RUNNING,
        )
        # 각 단계 초기화
        for stage in self._stages_order:
            state.stages[stage.value] = StageResult(stage=stage)

        opts = options or {}
        skip_stages: list[str] = opts.get("skip_stages", [])
        stop_after: str | None = opts.get("stop_after")

        # 재실행 경로: 이전 결과(previous_stage_data)로 skip 단계 data·단계간 payload를
        # 선복원한다. 옵션 미전달 시 no-op — 기존 호출 하위호환.
        self._restore_previous(state, opts)

        # 순차 실행
        for stage in self._stages_order:
            state.current_stage = stage
            stage_result = state.stages[stage.value]

            # skip_stages에 포함된 단계는 SKIPPED 처리
            if stage.value in skip_stages:
                stage_result.status = PipelineStatus.SKIPPED
                continue

            stage_result.status = PipelineStatus.RUNNING
            stage_result.started_at = datetime.now()

            try:
                if stage == PipelineStage.SITE_ANALYSIS:
                    await self._run_site_analysis(state, opts)
                elif stage == PipelineStage.DESIGN:
                    await self._run_design(state, opts)
                elif stage == PipelineStage.DESIGN_REVIEW:
                    await self._run_design_review(state, opts)
                elif stage == PipelineStage.COST:
                    await self._run_cost(state, opts)
                elif stage == PipelineStage.FEASIBILITY:
                    await self._run_feasibility(state, opts)
                elif stage == PipelineStage.TAX:
                    await self._run_tax(state, opts)
                elif stage == PipelineStage.ESG:
                    await self._run_esg(state, opts)
                elif stage == PipelineStage.REPORT:
                    await self._run_report(state, opts)

                # 단계함수가 이미 설정한 status를 존중한다. design_review처럼 엔진 미연결 시
                # SKIPPED(또는 FAILED)로 바꾼 경우 그 상태를 보존해야 한다 — 무조건 COMPLETED로
                # 덮으면 degraded SKIPPED가 COMPLETED로 위장된다(정직성 위반). 단계함수가 상태를
                # 건드리지 않은 평시(RUNNING 유지)에만 COMPLETED로 승격한다(기존 단계 동작 무회귀).
                if stage_result.status == PipelineStatus.RUNNING:
                    stage_result.status = PipelineStatus.COMPLETED
                await self._verify_stage(state, stage)   # P5: 단계 산출 검증(additive·COMPLETED 단계만)
            except Exception as e:
                stage_result.status = PipelineStatus.FAILED
                stage_result.error = str(e)[:500]
            finally:
                stage_result.completed_at = datetime.now()
                if stage_result.started_at:
                    stage_result.duration_ms = int(
                        (stage_result.completed_at - stage_result.started_at).total_seconds() * 1000
                    )

            # stop_after: 지정된 단계까지만 실행하고 나머지는 pending으로 유지
            if stop_after and stage.value == stop_after:
                break

        # 전 단계 AI 해석은 기본 OFF(동기 실행 타임아웃 방지) — 보고서가 온디맨드로 지연 로드.
        # opts.with_ai_interpretation=True일 때만 인라인 부착(배치/비동기 경로용).
        if opts.get("with_ai_interpretation"):
            await self._attach_all_ai(state)

        state.status = PipelineStatus.COMPLETED
        state.current_stage = None
        return state

    async def _attach_all_ai(self, state: PipelineState) -> None:
        """design·cost·feasibility·tax·esg 단계 데이터에 인터프리터 해석을 병렬 부착.

        site_analysis는 _attach_site_ai에서 이미 부착. 각 stage.data["ai_interpretation"]에
        섹션별 서술 텍스트를 담아 통합보고서가 'AI 상세 해석'으로 렌더한다. LLM 실패는 graceful.
        """
        import asyncio

        jobs: list[tuple[str, Any]] = []
        try:
            from app.services.ai.cost_interpreter import CostInterpreter
            from app.services.ai.design_interpreter import DesignInterpreter
            from app.services.ai.esg_interpreter import EsgInterpreter
            from app.services.ai.feasibility_interpreter import FeasibilityInterpreter
            from app.services.ai.tax_interpreter import TaxInterpreter

            specs = [
                ("design", DesignInterpreter),
                ("cost", CostInterpreter),
                ("feasibility", FeasibilityInterpreter),
                ("tax", TaxInterpreter),
                ("esg", EsgInterpreter),
            ]
            for key, cls in specs:
                sr = state.stages.get(key)
                if sr and isinstance(sr.data, dict) and sr.status == PipelineStatus.COMPLETED \
                        and "ai_interpretation" not in sr.data:
                    jobs.append((key, cls().generate_interpretation(dict(sr.data))))
            if not jobs:
                return
            results = await asyncio.gather(*[c for _, c in jobs], return_exceptions=True)
            for (key, _), res in zip(jobs, results, strict=False):
                if isinstance(res, dict) and res:
                    state.stages[key].data["ai_interpretation"] = res
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("단계 AI 해석 부착 스킵: %s", str(e)[:140])

    # ── P5: 단계별 검증 강제(VerifierService) ──

    async def _verify_stage(self, state: PipelineState, stage: PipelineStage) -> None:
        """P5: 단계 산출을 VerifierService로 검증해 stage.data['verification']에 additive 부착.

        LLM 부재 시 규칙기반(_prescan+calc_ledger+range_rules) verdict — graceful. 결정론 산출
        수치는 변경하지 않는다(read·표면화 전용). COMPLETED 단계만 검증(skip/실패 단계 제외 — 정직).
        """
        try:
            sr = state.stages.get(stage.value)
            if sr is None or sr.status != PipelineStatus.COMPLETED:
                return
            data = sr.data if isinstance(sr.data, dict) else {}
            if not data:
                return
            from app.services.verification.verifier_service import VerifierService
            source = self._verify_source_for(state, stage) or data
            result = await VerifierService().verify(stage.value, source, data)
            data["verification"] = result
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("단계 검증 스킵: %s", str(e)[:140])

    def _verify_source_for(self, state: PipelineState, stage: PipelineStage) -> dict | None:
        """검증 source(근거 입력) 선택 — 단계간 payload 우선(없으면 None → 자기일관성)."""
        m = {
            PipelineStage.DESIGN: state.site_to_design,
            PipelineStage.COST: state.design_to_cost,
            PipelineStage.FEASIBILITY: state.cost_to_feasibility,
        }
        payload = m.get(stage)
        return payload.model_dump() if payload is not None else None

    # ── P5 T3: 공공데이터 cross_validate 신뢰가드(site_analysis) ──

    @staticmethod
    def _nearby_price_median(nt: Any) -> float | None:
        """nearby_transactions에서 ㎡당 가격 중앙값 추출(불가 시 None — 가짜값 생성 금지)."""
        import statistics
        items = nt if isinstance(nt, list) else (nt.get("items") if isinstance(nt, dict) else None)
        vals: list[float] = []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    v = it.get("price_per_sqm") or it.get("price_per_sqm_won")
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                        vals.append(float(v))
        return statistics.median(vals) if vals else None

    def _build_price_signals(self, data: dict[str, Any]) -> list[Any]:
        """site stage data의 가격 신호(공시지가·인근실거래) 수집 — cross_validate 입력."""
        from app.services.data_validation.trust import Signal
        pricing = data.get("pricing") if isinstance(data.get("pricing"), dict) else {}
        signals: list[Any] = []
        op = pricing.get("official_price_per_sqm")
        if isinstance(op, (int, float)) and not isinstance(op, bool) and op > 0:
            signals.append(Signal(name="공시지가", value=float(op), sample_size=1, source="공시지가", weight=1.0))
        med = self._nearby_price_median(pricing.get("nearby_transactions"))
        if med is not None and med > 0:
            signals.append(Signal(name="인근실거래", value=float(med), sample_size=3, source="실거래", weight=1.2))
        return signals

    def _attach_trust_guard(self, state: PipelineState) -> None:
        """site_analysis 공공데이터(가격)에 cross_validate 신뢰가드를 additive 부착(값 불변).

        가정 기본값(assumed_defaults)·신호 부족이면 진짜 가드를 붙이지 않는다(정직 skip).
        freshness(FreshnessChecker)는 per-source 타임스탬프 필요 → stage data에 없어 미적용
        (출처 수집층 public_data_registry에서 적용됨). 결정론·LLM 비개입.
        """
        try:
            sr = state.stages.get("site_analysis")
            if sr is None or not isinstance(sr.data, dict):
                return
            data = sr.data
            if data.get("data_quality") == "assumed_defaults":
                data.setdefault("trust_guard", {"skipped": True, "reason": "assumed_defaults"})
                return
            signals = self._build_price_signals(data)
            if not signals:
                data.setdefault("trust_guard", {"skipped": True, "reason": "no_price_signal"})
                return
            from app.services.data_validation.trust import cross_validate
            result = cross_validate(signals, plausible_min=0.0)
            pricing = data.get("pricing") if isinstance(data.get("pricing"), dict) else {}
            data["trust_guard"] = {
                "price_cross_validation": result.to_dict(),
                "data_sources": {
                    "official_land_price": bool(pricing.get("official_price_per_sqm")),
                    "nearby_transactions": self._nearby_price_median(
                        pricing.get("nearby_transactions")) is not None,
                    "assumed_fields": list(data.get("assumed_fields") or []),
                },
                "freshness": {"applied": False,
                              "note": "per-source 타임스탬프 부재 — 출처 수집층(public_data_registry)에서 적용"},
            }
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("신뢰가드 부착 스킵: %s", str(e)[:140])

    # ── 재실행(rerun) 지원: stage_overrides 소비·previous_stage_data 복원 헬퍼 ──

    @staticmethod
    def _maybe_float(value: Any) -> float | None:
        """숫자 변환 가능 시 float, 아니면 None — 잘못된 오버라이드가 단계를 실패시키지 않도록."""
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _maybe_int(cls, value: Any) -> int | None:
        f = cls._maybe_float(value)
        return None if f is None else int(f)

    @classmethod
    def _as_float(cls, value: Any, default: float = 0.0) -> float:
        f = cls._maybe_float(value)
        return default if f is None else f

    @classmethod
    def _as_int(cls, value: Any, default: int = 0) -> int:
        i = cls._maybe_int(value)
        return default if i is None else i

    @staticmethod
    def _stage_overrides_for(opts: dict, stage: str) -> dict[str, Any]:
        """options["stage_overrides"][stage]를 dict로 정규화해 반환한다(없으면 빈 dict — 하위호환)."""
        stage_overrides = (opts or {}).get("stage_overrides") or {}
        if not isinstance(stage_overrides, dict):
            return {}
        overrides = stage_overrides.get(stage)
        return dict(overrides) if isinstance(overrides, dict) else {}

    @staticmethod
    def _patch_remaining_overrides(
        data: dict[str, Any],
        overrides: dict[str, Any],
        applied: dict[str, Any],
        handled: frozenset[str] = frozenset(),
    ) -> None:
        """단계별 재계산 훅이 소비하지 않은 나머지 오버라이드 키를 산출 데이터에 직접 반영한다.

        handled: 전용 훅이 담당하는 키 — 훅에서 검증 실패(비숫자 등)로 미적용된 경우에도
        잘못된 값이 generic patch로 재유입돼 계산 결과를 오염시키지 않도록 제외한다.
        """
        for key, value in overrides.items():
            if key in applied or key in handled or value is None:
                continue
            data[key] = value
            applied[key] = value

    @classmethod
    def _apply_site_overrides(
        cls, target: dict[str, Any], overrides: dict[str, Any],
    ) -> dict[str, Any]:
        """부지분석 오버라이드를 수집 데이터(실API 병합 완료본)에 주입한다.

        병합 이후 호출되어 사용자값이 최우선이 된다. 실제 적용된 키 맵을 반환한다
        (applied_overrides 기록용).
        """
        applied: dict[str, Any] = {}
        for key, value in overrides.items():
            if value is None:
                continue
            if key in _NUMERIC_SITE_OVERRIDE_KEYS:
                num = cls._maybe_float(value)
                if num is None:
                    continue  # 비숫자 입력은 미적용(기록도 생략 — 정직성)
                value = num
            target[key] = value
            applied[key] = value
        # BCR/FAR 오버라이드: effective=min(national, ordinance) 산식에 사용자값이
        # 그대로 반영되도록 양 출처 모두에 주입한다(사용자값=최종 한도).
        if "max_bcr" in applied:
            target["national_bcr"] = applied["max_bcr"]
            target["ordinance_bcr"] = applied["max_bcr"]
        if "max_far" in applied:
            target["national_far"] = applied["max_far"]
            target["ordinance_far"] = applied["max_far"]
        if "max_bcr" in applied or "max_far" in applied:
            target["ordinance_source"] = "user_override"
        # ★A-2: 사용자가 land_area_sqm을 직접 오버라이드하면(사용자 입력 존중) usable/gross
        #   이원화 자체가 무의미해지므로 gross도 동일값으로 동기화한다(stale 통합-gross 잔존 방지).
        if "land_area_sqm" in applied:
            target["land_area_gross_sqm"] = applied["land_area_sqm"]
        # E7: 가정값이 사용자값으로 대체되면 해당 필드의 가정 표기를 해제한다.
        assumed = target.get("assumed_fields")
        if isinstance(assumed, list) and applied:
            remaining = [f for f in assumed if f not in applied]
            if remaining:
                target["assumed_fields"] = remaining
            else:
                target.pop("assumed_fields", None)
                target.pop("data_quality", None)
        return applied

    def _restore_previous(self, state: PipelineState, opts: dict) -> None:
        """options["previous_stage_data"]로 skip 단계 data와 단계간 payload 3종을 복원한다.

        복원이 없으면 skip된 단계의 payload(None)를 _run_design/_run_cost/_run_feasibility가
        기본값(500㎡/60%/200%)으로 대체해 재계산이 왜곡된다. 옵션 미전달 시 no-op(하위호환).
        재실행되는 단계는 자기 payload를 다시 생성하므로 선복원해도 안전하다.
        """
        prev = (opts or {}).get("previous_stage_data")
        if not prev:
            return

        # list[{stage, data}] / {stage: {data: ...}} / {stage: data} 형태 모두 수용
        normalized: dict[str, dict[str, Any]] = {}
        if isinstance(prev, list):
            for item in prev:
                if isinstance(item, dict) and item.get("stage"):
                    data = item.get("data")
                    if isinstance(data, dict):
                        normalized[str(item["stage"])] = data
        elif isinstance(prev, dict):
            for name, item in prev.items():
                if not isinstance(item, dict):
                    continue
                inner = item.get("data")
                normalized[str(name)] = inner if isinstance(inner, dict) else item
        if not normalized:
            return

        # 1) skip 단계의 이전 data 복원 — 보고서·후속 단계가 stage.data를 직접 참조한다.
        #    재실행 단계는 복원하지 않는다(실패 시 옛 데이터가 새 결과로 오인되는 것 방지).
        skip_stages = set((opts or {}).get("skip_stages") or [])
        for name, data in normalized.items():
            if name in skip_stages and name in state.stages and data:
                state.stages[name].data = dict(data)

        # 2) 단계간 payload 3종 복원 (SiteToDesign / DesignToCost / CostToFeasibility)
        site = normalized.get("site_analysis") or {}
        if site:
            zoning = site.get("zoning") if isinstance(site.get("zoning"), dict) else {}
            pnu_codes = site.get("pnu_codes")
            state.site_to_design = SiteToDesignPayload(
                pnu_codes=[str(p) for p in pnu_codes] if isinstance(pnu_codes, list) else [],
                zone_type=str(site.get("zone_type") or ""),
                # ★무날조(WP-U1c): 이전 결과에 한도가 없으면 60/200을 지어내지 않고 0.0(미산정
                #   센티널) — _run_design이 assumed_fields 정직 표기와 함께 소비(수치 동일·표기 가산).
                max_bcr=self._as_float(site.get("max_bcr"), 0.0),
                max_far=self._as_float(site.get("max_far"), 0.0),
                max_height=self._as_float((zoning or {}).get("max_height_m"), 0.0),
                land_area_sqm=self._as_float(site.get("land_area_sqm"), 0.0),
                land_shape=None,
                official_land_price=self._as_float(site.get("official_land_price"), 0.0),
                address=state.address,
                coordinates=site.get("coordinates") if isinstance(site.get("coordinates"), dict) else None,
            )

        design = normalized.get("design") or {}
        if design:
            avg_unit_sqm = self._as_float(design.get("avg_unit_sqm"), 0.0)
            state.design_to_cost = DesignToCostPayload(
                total_gfa_sqm=self._as_float(design.get("total_gfa_sqm"), 0.0),
                floor_count_above=self._as_int(design.get("floor_count_above"), 0),
                floor_count_below=self._as_int(design.get("floor_count_below"), 0),
                structure_type="RC",
                building_type=str(design.get("building_type") or ""),
                unit_count=self._as_int(design.get("unit_count"), 0),
                avg_unit_area_pyeong=round(avg_unit_sqm / 3.3058, 1) if avg_unit_sqm > 0 else 0.0,
            )

        cost = normalized.get("cost") or {}
        if cost:
            cost_breakdown = cost.get("cost_breakdown")
            state.cost_to_feasibility = CostToFeasibilityPayload(
                total_construction_cost=self._as_float(cost.get("total_construction_cost"), 0.0),
                cost_per_pyeong=self._as_float(cost.get("cost_per_pyeong"), 0.0),
                construction_months=self._as_int(cost.get("construction_months"), 24) or 24,
                # stage data에는 개수(material_item_count)만 보존됨 — 가짜 목록 대신 빈 목록(정직)
                material_quantities=[],
                cost_breakdown=cost_breakdown if isinstance(cost_breakdown, dict) else {},
            )

    async def _run_site_analysis(self, state: PipelineState, opts: dict):
        """STEP 1: 부지분석 — 프론트에서 전달한 데이터 우선, 없으면 외부 API 호출."""
        # ── 고도화 서비스 임포트 ──
        from app.services.zoning import development_type_analyzer as dta
        from app.services.zoning import far_incentive_calculator as fic

        # 프론트에서 site_data가 전달되었는지 확인
        pre_collected = opts.get("site_data")

        # site_data의 핵심 값이 유효한지 판단
        # land_area_sqm은 comprehensive에서 항상 보충하므로 zone_type만 체크
        has_valid_site_data = (
            pre_collected is not None
            and pre_collected.get("zone_type")
            and len(str(pre_collected.get("zone_type", ""))) > 0
        )

        # 유효한 site_data가 없으면 → 외부 API 호출하여 실제 데이터 수집
        if not has_valid_site_data:
            pre_collected = await self._fetch_real_site_data(state.address, pre_collected)

        if pre_collected is not None:
            # pre_collected에 누락된 데이터를 LandInfoService로 보충
            comprehensive: dict[str, Any] = {}
            try:
                from app.services.land_intelligence.land_info_service import LandInfoService
                land_svc = LandInfoService()
                comprehensive = await land_svc.collect_comprehensive(state.address)
            except Exception as e:  # noqa: BLE001 — 보충 실패는 pre_collected로 진행(무중단)
                # W3-8 연계: 무로그 침묵이던 보충 실패를 관측 가능하게(원인 추적).
                logger.warning("site 보충수집(collect_comprehensive) 실패 — pre_collected로 진행",
                               err=str(e)[:160])
                comprehensive = {}

            # comprehensive 데이터로 pre_collected 덮어쓰기 (실제 API 데이터 우선)
            if comprehensive:
                _clr = comprehensive.get("land_register") or {}
                if isinstance(_clr, dict) and float(_clr.get("area_sqm", 0) or 0) > 0:
                    pre_collected["land_area_sqm"] = float(_clr["area_sqm"])
                # 지목(land_category)·소유구분(owner_type): land_register 우선,
                # 비면 토지특성(land_characteristics)으로 백필(land_info_service:428-429 패턴 일관).
                # 무목업: 실제 수집값만 사용, 없으면 빈값 유지(가짜 소유구분 생성 금지).
                _lchar = comprehensive.get("land_characteristics") or {}
                _land_category = ""
                if isinstance(_clr, dict):
                    _land_category = (_clr.get("land_category") or "").strip()
                if not _land_category and isinstance(_lchar, dict):
                    _land_category = (_lchar.get("land_category") or "").strip()
                if _land_category:
                    pre_collected["land_category"] = _land_category
                _owner_type = ""
                if isinstance(_clr, dict):
                    _owner_type = (_clr.get("owner_type") or "").strip()
                if _owner_type:
                    pre_collected["owner_type"] = _owner_type
                if comprehensive.get("infrastructure"):
                    pre_collected["infrastructure"] = comprehensive["infrastructure"]
                if comprehensive.get("coordinates"):
                    pre_collected["coordinates"] = comprehensive["coordinates"]
                _bldg = comprehensive.get("building_detail") or comprehensive.get("building_info")
                if _bldg:
                    pre_collected["building_info"] = _bldg
                if comprehensive.get("land_use_plan"):
                    pre_collected["land_use_plan"] = comprehensive["land_use_plan"]
                if comprehensive.get("special_districts"):
                    pre_collected["special_districts"] = comprehensive["special_districts"]
                if comprehensive.get("nearby_transactions"):
                    pre_collected["nearby_transactions"] = comprehensive["nearby_transactions"]
                _ops = comprehensive.get("official_prices", [])
                if _ops and isinstance(_ops, list) and len(_ops) > 0:
                    price = float(_ops[0].get("price_per_sqm", 0) or 0)
                    if price > 0:
                        pre_collected["official_land_price"] = price
                pnu = comprehensive.get("pnu")
                if pnu:
                    pre_collected["pnu_codes"] = [pnu]

            # ★다필지 통합(RC#2): parcels가 오면 대표필지 면적을 통합면적으로 대체한다.
            #   그동안 site stage가 대표필지 land_register 면적을 무조건 덮어써(위 :578) 설계·수지·
            #   토지비가 전부 대표면적(예 763㎡)으로 캐스케이드되던 통로부재를 공용 SSOT로 봉합.
            #   우선순위: ①통합면적(parcels≥2) > ②사용자 제공 site_data 면적 > ③대표필지. 정직표기(area_basis).
            area_basis = "representative_parcel"
            _parcels = (opts or {}).get("parcels")
            if _parcels and isinstance(_parcels, list) and len(_parcels) >= 2:
                try:
                    from app.services.land_intelligence.comprehensive_analysis_service import (
                        build_integrated_context,
                    )
                    integrated = await build_integrated_context(_parcels)
                    if integrated and float(integrated.get("total_area_sqm") or 0) > 0:
                        # ★A-2(usable 면적 전파): 개발규모(GFA, land_area_sqm)는 usable
                        #   (land_area_effective_sqm — 도로·구거·하천 지목+BLOCKED 게이트 제외)
                        #   채택, 토지비(land_area_gross_sqm)는 gross 유지(F2/P0-2(c)와 동일
                        #   이원화 원칙 — 제외 필지도 실제 매입 대상이므로 축소 금지).
                        _gross_area = float(integrated["total_area_sqm"])
                        pre_collected["land_area_gross_sqm"] = _gross_area
                        _eff_area = integrated.get("land_area_effective_sqm")
                        pre_collected["land_area_sqm"] = (
                            float(_eff_area) if (_eff_area is not None and float(_eff_area) > 0)
                            else _gross_area
                        )
                        _dz = integrated.get("dominant_zone")
                        if _dz and _dz != "mixed_review_required":
                            pre_collected["zone_type"] = _dz
                        if integrated.get("blended_far_eff_pct") is not None:
                            pre_collected["effective_far"] = float(integrated["blended_far_eff_pct"])
                        if integrated.get("blended_bcr_eff_pct") is not None:
                            pre_collected["effective_bcr"] = float(integrated["blended_bcr_eff_pct"])
                        # 통합 메타를 site stage data에 부착 — 다운스트림(설계·수지·보고서) 그라운딩용.
                        pre_collected["integrated_zoning"] = integrated
                        pre_collected["parcel_count"] = integrated.get("parcel_count")
                        area_basis = "integrated_parcels"
                except Exception as e:  # noqa: BLE001 — 통합 실패는 단일 경로로 폴백(무중단)
                    logger.warning("파이프라인 다필지 통합 실패 — 대표필지 폴백", err=str(e)[:160])
            pre_collected["area_basis"] = area_basis  # 면적 출처 정직 표기(무날조)

            # 사용자 오버라이드(stage_overrides.site_analysis)는 실API 병합 이후 주입 —
            # comprehensive가 사용자값을 덮어쓰지 못하도록 적용 순서를 보장한다.
            site_overrides = self._stage_overrides_for(opts, "site_analysis")
            applied_site_overrides: dict[str, Any] = {}
            if site_overrides:
                applied_site_overrides = self._apply_site_overrides(pre_collected, site_overrides)

            zone_type = pre_collected.get("zone_type", "")
            land_area_sqm = pre_collected.get("land_area_sqm", 0.0)
            pnu_codes = pre_collected.get("pnu_codes", [])
            official_land_price = pre_collected.get("official_land_price", 0.0)

            # 국토계획법 법정 상한 — ★무날조(WP-U1c): 무자료 시 `or 200/60` 임의 기본값을
            #   발명하지 않는다(None 유지). 법정값의 진실원천은 아래 far_tier SSOT가 용도지역
            #   라벨(legal_limits_for)로 재확인하며, 여기 값은 zone_limits 보조 페이로드일 뿐이다.
            national_bcr = pre_collected.get("national_bcr") or pre_collected.get("max_bcr")
            national_far = pre_collected.get("national_far") or pre_collected.get("max_far")
            max_height = pre_collected.get("max_height", 0.0)

            # 조례 조회 (pre_collected에 없으면 OrdinanceService로 실시간 조회)
            ordinance_bcr = pre_collected.get("ordinance_bcr")
            ordinance_far = pre_collected.get("ordinance_far")
            ordinance_source = pre_collected.get("ordinance_source", "")
            # 조례 url 시군구 치환용(신뢰블록): 조회된 sigungu 보존(없으면 None → 주소 폴백).
            ordinance_sigungu = pre_collected.get("ordinance_sigungu")
            if not ordinance_bcr:
                try:
                    from app.services.land_intelligence.ordinance_service import OrdinanceService
                    ord_svc = OrdinanceService()
                    ord_result = await ord_svc.get_ordinance_limits(state.address, zone_type)
                    if ord_result.get("ordinance_bcr") is not None:
                        ordinance_bcr = ord_result["ordinance_bcr"]
                        # ★무날조: 조례 용적률 미제공 시 법정값으로 지어내지 않고 None 유지
                        #   (아래 SSOT가 법정 폴백·정직 표기를 일원 처리).
                        ordinance_far = ord_result.get("ordinance_far")
                        ordinance_source = ord_result.get("source", "조례")
                    _sgg = ord_result.get("sigungu")
                    if _sgg and str(_sgg).strip() and str(_sgg).strip() != "미확인":
                        ordinance_sigungu = str(_sgg).strip()
                except Exception as e:
                    logger.warning("조례 조회 실패, 법정상한 폴백: %s", str(e)[:160])

            # ── ★실효 용적률/건폐율 SSOT 단일경유(WP-U1c) — calc_effective_far 소비(재계산 금지) ──
            # 과거 이 지점의 `min(법정,조례)` 독자 재계산은 ①구조상한(건폐율×층수) 계층 누락으로
            # 자연/생산녹지(건폐 20%×4층=80% < 법정 100%)를 100%로 과대표시하고, ②무자료 시
            # `or 200`/`or 60` 날조 기본값으로 자연녹지에 200%를 발명했다(라이브 실측 재현).
            # 수지(feasibility_v2)·종합(comprehensive)·규제(PR#333)·인허가(PR#334)·90초진단(PR#336)
            # 표면과 동일 SSOT 계층(법정범위→조례→계획상한→인센티브→구조상한)을 소비한다 —
            # "2026-06-19 산/임야 과대표시" 버그클래스의 파이프라인 표면 봉합. 층수제한 없는
            # zone(제2종일반주거 250%·일반상업 1300% 등)은 구조상한 None → 완전 무영향.
            far_basis: str | None = None
            far_reliable = False
            far_basis_detail: dict[str, Any] | None = None
            structural_cap_pct: float | None = None
            floor_cap: int | None = None
            floor_cap_basis: str | None = None
            _ord_payload: dict[str, Any] = {}
            if ordinance_bcr is not None or ordinance_far is not None:
                _ord_payload = {
                    "ordinance_bcr": ordinance_bcr,
                    "ordinance_far": ordinance_far,
                    "source": ordinance_source or "조례",
                }
                if ordinance_sigungu:
                    _ord_payload["sigungu"] = ordinance_sigungu
            eff: dict[str, Any] = {}
            try:
                from app.services.land_intelligence.far_tier_service import calc_effective_far
                eff = calc_effective_far(
                    {
                        "zone_limits": {"max_bcr_pct": national_bcr, "max_far_pct": national_far},
                        "local_ordinance": _ord_payload,
                        "special_districts": (
                            pre_collected.get("special_districts")
                            or comprehensive.get("special_districts")
                            or []
                        ),
                    },
                    zone_type,
                    float(land_area_sqm or 0),
                )
            except Exception as e:  # noqa: BLE001 — SSOT 실패 시 정직강등(far_reliable=False)
                logger.warning("실효 용적률 SSOT 산정 실패 — 정직강등", err=str(e)[:160])
                eff = {}

            _eff_far = eff.get("effective_far_pct")
            _eff_bcr = eff.get("effective_bcr_pct")
            if _eff_far is not None and float(_eff_far) > 0:
                effective_far = float(_eff_far)
                far_reliable = True
            else:
                # SSOT 미산정(zone 미확인/산정 실패) — 날조 금지: 실제 수집값만 보수 적용(min),
                # 전무하면 None(미산정) 정직 전파. 하류 _run_design은 W3-8 계약(assumed_fields
                # 정직 표기 + 보수 기본치 명시 라벨링)으로 0/None을 소비한다.
                _far_cands = [
                    float(v) for v in (national_far, ordinance_far)
                    if v is not None and float(v) > 0
                ]
                effective_far = min(_far_cands) if _far_cands else None
            if _eff_bcr is not None and float(_eff_bcr) > 0:
                effective_bcr = float(_eff_bcr)
            else:
                _bcr_cands = [
                    float(v) for v in (national_bcr, ordinance_bcr)
                    if v is not None and float(v) > 0
                ]
                effective_bcr = min(_bcr_cands) if _bcr_cands else None
            if eff:
                far_basis = eff.get("far_basis")
                far_basis_detail = eff.get("far_basis_detail")
                structural_cap_pct = eff.get("structural_cap_pct")
                floor_cap = eff.get("floor_cap")
                floor_cap_basis = eff.get("floor_cap_basis")
                # 법정/조례 표기값도 SSOT(용도지역 라벨 재확인) 산출을 소비 — 표기·수치 교차 일치.
                if eff.get("national_bcr_pct") is not None:
                    national_bcr = eff["national_bcr_pct"]
                if eff.get("national_far_pct") is not None:
                    national_far = eff["national_far_pct"]
                if eff.get("ordinance_bcr_pct") is not None:
                    ordinance_bcr = eff["ordinance_bcr_pct"]
                if eff.get("ordinance_far_pct") is not None:
                    ordinance_far = eff["ordinance_far_pct"]
                ordinance_source = ordinance_source or str(eff.get("source") or "")

            # ── 사용자 오버라이드 최종 권위 보존(기존 계약 — _apply_site_overrides 주석 참조):
            #    max_bcr/max_far 직접 입력은 SSOT 산정과 무관하게 최종 한도로 적용한다(값 자체가
            #    사용자 명시 입력 — 날조 아님, far_basis로 출처 정직 표기).
            #    national_*/ordinance_* 개별 오버라이드는 하향(min)으로만 참여(보수 방향).
            if applied_site_overrides:
                _uf = self._maybe_float(applied_site_overrides.get("max_far"))
                if _uf is not None and _uf > 0:
                    effective_far = _uf
                    far_basis = "사용자 오버라이드(직접 입력)"
                    far_reliable = True
                else:
                    _ufc = [
                        c for c in (
                            self._maybe_float(applied_site_overrides.get(k))
                            for k in ("national_far", "ordinance_far")
                        ) if c is not None and c > 0
                    ]
                    if _ufc and (effective_far is None or min(_ufc) < effective_far):
                        effective_far = min(_ufc)
                        far_basis = "사용자 오버라이드(법정/조례 한도 직접 입력)"
                _ub = self._maybe_float(applied_site_overrides.get("max_bcr"))
                if _ub is not None and _ub > 0:
                    effective_bcr = _ub
                else:
                    _ubc = [
                        c for c in (
                            self._maybe_float(applied_site_overrides.get(k))
                            for k in ("national_bcr", "ordinance_bcr")
                        ) if c is not None and c > 0
                    ]
                    if _ubc and (effective_bcr is None or min(_ubc) < effective_bcr):
                        effective_bcr = min(_ubc)

            # ★다필지 통합(리뷰 HIGH): 위 SSOT 산정은 대표필지 zone 기준이다. 통합 블록이
            #   면적가중 blended 실효율을 계산해뒀으면(area_basis="integrated_parcels") 그 값으로 대체 —
            #   혼재 용도지역에서 zone 라벨만 우세용도로 바뀌고 FAR/BCR은 대표 zone에 머무는 라벨-숫자
            #   불일치(이 코드베이스가 반복적으로 싸운 버그 클래스)를 다필지 경로에 재도입하지 않는다.
            #   (블렌드는 필지별 SSOT 실효율의 면적가중 집계 — 독자 재계산이 아니라 SSOT 파생값.)
            if pre_collected.get("area_basis") == "integrated_parcels":
                _bf = pre_collected.get("effective_far")
                _bb = pre_collected.get("effective_bcr")
                if _bf is not None and float(_bf) > 0:
                    effective_far = float(_bf)
                    far_basis = "다필지 통합(면적가중 실효율)"
                    far_reliable = True
                if _bb is not None and float(_bb) > 0:
                    effective_bcr = float(_bb)

            # 기부체납 인센티브 계산 — ★무날조: 실효 용적률 미산정이면 임의 200 기준 시뮬 대신 생략.
            far_incentive: dict[str, Any] = {}
            if effective_far is not None:
                try:
                    far_incentive = fic.calculate(
                        zone_type=zone_type,
                        ordinance_far=effective_far,
                        donation_ratio_pct=0.0,
                        # None이면 fic 내부에서 용도지역 라벨로 법정상한 자동 조회(임의 200 주입 금지).
                        national_far=float(national_far) if national_far is not None else None,
                    )
                except Exception:
                    far_incentive = {"error": "인센티브 계산 실패"}
            else:
                far_incentive = {"skipped": "실효 용적률 미산정 — 인센티브 시뮬 생략(무날조)"}

            # 개발 가능 유형 분석 — 법정 상한이 아닌 실효 BCR/FAR(SSOT calc_effective_far 소비값)을
            # 주입해 max_gfa를 실효 기준으로 산출(파이프라인 effective vs dta 법정 비대칭 해소).
            development_types: dict[str, Any] = {}
            try:
                development_types = dta.analyze(
                    zone_type=zone_type,
                    land_area_sqm=float(land_area_sqm),
                    existing_building=pre_collected.get("existing_building"),
                    effective_far_pct=effective_far,
                    effective_bcr_pct=effective_bcr,
                )
            except Exception:
                development_types = {"error": "개발유형 분석 실패"}

            # 특이부지 게이트(결함B) — 진입부에서 1회만 detect_special_parcel 적용해
            # 개발가능성·경고를 development_types에 동반(analyze 자체는 가볍게 유지).
            try:
                from app.services.zoning.special_parcel import detect_special_parcel
                _special = detect_special_parcel({
                    "land_category": pre_collected.get("land_category", ""),
                    "zone_type": zone_type,
                    "special_districts": (
                        pre_collected.get("special_districts")
                        or comprehensive.get("special_districts")
                        or []
                    ),
                    "road_contact": pre_collected.get("road_contact"),
                    "road_width_m": pre_collected.get("road_width_m"),
                    "road_width": pre_collected.get("road_width"),
                })
                if _special:
                    development_types["special_parcel"] = _special
            except Exception:
                pass

            state.site_to_design = SiteToDesignPayload(
                pnu_codes=pnu_codes,
                zone_type=zone_type,
                # 미산정(None)은 0.0 센티널로 전달 — _run_design이 W3-8 계약(가정 표기)으로 소비.
                max_bcr=effective_bcr if effective_bcr is not None else 0.0,
                max_far=effective_far if effective_far is not None else 0.0,
                max_height=max_height,
                land_area_sqm=float(land_area_sqm),
                land_area_gross_sqm=pre_collected.get("land_area_gross_sqm"),
                land_shape=None,
                official_land_price=float(official_land_price),
                address=state.address,
                coordinates=pre_collected.get("coordinates"),
            )

            state.stages["site_analysis"].data = {
                # 구조화된 데이터 (프론트엔드 SiteAnalysisDetail용)
                "basic": {
                    "address": state.address,
                    "pnu": pnu_codes[0] if pnu_codes else "",
                    "zone_type": zone_type,
                    "land_category": pre_collected.get("land_category", ""),
                    "land_area_sqm": float(land_area_sqm),
                    "owner_type": pre_collected.get("owner_type", ""),
                },
                "zoning": {
                    "zone_type": zone_type,
                    # ★무날조(WP-U1c): 미확인 한도는 None 정직 전파(과거 `or 60`/`or 200` 날조 제거).
                    #   프론트(SiteAnalysisDetail 등)는 n()/null 가드로 None 허용 — 표기만 생략.
                    "national_bcr": float(national_bcr) if national_bcr is not None else None,
                    "national_far": float(national_far) if national_far is not None else None,
                    "ordinance_bcr": float(ordinance_bcr) if ordinance_bcr is not None else None,
                    "ordinance_far": float(ordinance_far) if ordinance_far is not None else None,
                    "effective_bcr": effective_bcr,
                    "effective_far": effective_far,
                    "max_height_m": max_height,
                    "ordinance_source": ordinance_source or "pre_collected",
                    "ordinance_sigungu": ordinance_sigungu,
                    "far_incentive": far_incentive,
                    # ★실효 산정 근거·신뢰성 정직 전파(additive) — PR#334/#336과 동일 계약.
                    #   far_basis="구조상한(건폐율×층수)"이면 자연녹지 80%가 조례가 아닌
                    #   층수제한(4층)에서 온 값임을 소비처가 정직 표기할 수 있다.
                    "far_basis": far_basis,
                    "far_reliable": far_reliable,
                    "far_basis_detail": far_basis_detail,
                    "structural_cap_pct": structural_cap_pct,
                    "floor_cap": floor_cap,
                    "floor_cap_basis": floor_cap_basis,
                },
                "development_types": development_types,
                "pricing": {
                    "official_price_per_sqm": float(official_land_price),
                    "nearby_transactions": pre_collected.get("nearby_transactions"),
                },
                "building": pre_collected.get("building_info") or comprehensive.get("building_detail") or comprehensive.get("building_info"),
                "building_lookup_status": comprehensive.get("building_lookup_status") or pre_collected.get("building_lookup_status"),
                "infrastructure": pre_collected.get("infrastructure") or comprehensive.get("infrastructure"),
                "coordinates": pre_collected.get("coordinates") or comprehensive.get("coordinates"),
                "regulations": {
                    "land_use_plan": pre_collected.get("land_use_plan") or comprehensive.get("land_use_plan"),
                    "special_districts": pre_collected.get("special_districts") or comprehensive.get("special_districts", []),
                    "warnings": pre_collected.get("warnings") or comprehensive.get("warnings", []),
                },
                # 하위호환 (기존 평탄 키 유지 — 다른 단계에서 참조)
                "zone_type": zone_type,
                "max_bcr": effective_bcr,
                "max_far": effective_far,
                "land_area_sqm": float(land_area_sqm),
                "official_land_price": float(official_land_price),
                "pnu_codes": pnu_codes,
                "source": "pre_collected+comprehensive",
                # ★다필지 통합 메타(리뷰 MEDIUM) — 면적 출처 정직표기·통합집계 그라운딩을 실제로 노출한다
                #   (설정만 하고 응답에 안 실어 죽은 필드였던 것 봉합). 단일/미전달은 "representative_parcel".
                "area_basis": pre_collected.get("area_basis", "representative_parcel"),
                "parcel_count": pre_collected.get("parcel_count"),
                "integrated_zoning": pre_collected.get("integrated_zoning"),
                # ★A-2(usable 면적 전파, additive) — 다필지 통합 경로에서만 채워짐(gfa=usable/land_cost=gross 병기).
                "land_area_basis": (
                    {"gfa_sqm_basis": "usable", "land_cost_basis": "gross",
                     "gross_sqm": pre_collected["land_area_gross_sqm"], "usable_sqm": float(land_area_sqm)}
                    if pre_collected.get("land_area_gross_sqm") is not None else None
                ),
            }
            if applied_site_overrides:
                state.stages["site_analysis"].data["applied_overrides"] = applied_site_overrides
            # E7: 폴백 기본값 사용 시 가정 사실을 stage data에 노출
            # (UI 경고 배지·saveToStore의 SSOT 시드 제외 판단용 — 수치는 유지).
            if pre_collected.get("data_quality"):
                state.stages["site_analysis"].data["data_quality"] = pre_collected["data_quality"]
                state.stages["site_analysis"].data["assumed_fields"] = list(
                    pre_collected.get("assumed_fields") or []
                )
            # 신뢰 메타데이터(additive): 입지분석(auto_zoning)과 동일한 legal_refs[]·evidence[].
            self._attach_site_trust_blocks(state)
            await self._attach_site_ai(state)
            # W1-7: Project 자동 반영(zone/max_far/면적 등) — 과거 도달불능 분기에만 있어
            # /pipeline/run 후 Project 테이블이 갱신되지 않던 단선 복구.
            await self._save_site_analysis_to_project(state)
            return

        # ── W1-7: 이 아래 있던 '외부 API 직수집' 분기(약 180줄)는 도달불능 사장 코드였다 —
        #    _fetch_real_site_data가 항상 dict를 반환해 위 pre_collected 경로가 항상 실행·return.
        #    유일한 실기능이던 Project 자동저장(_save_site_analysis_to_project)은 위 경로로 이관.
        #    comprehensive_report 첨부는 전 코드베이스 소비처 0건으로 미이관(7섹션 보고서의
        #    정본은 /analysis/comprehensive 엔드포인트). 계약 위반 시 침묵 대신 정직 실패.
        raise RuntimeError(
            "site stage: pre_collected가 None — _fetch_real_site_data 계약(항상 dict 반환) 위반"
        )

    async def _fetch_real_site_data(self, address: str, fallback: dict | None) -> dict:
        """외부 API(VWORLD/MOLIT)를 호출하여 실제 부지 데이터를 수집한다.

        프론트에서 전달한 site_data가 비어있거나 불완전할 때 호출된다.
        실패 시 fallback 데이터 또는 주소 기반 기본값을 반환한다.
        """
        result: dict[str, Any] = dict(fallback) if fallback else {}

        # 0. PNU가 이미 있으면 VWORLD 데이터 API로 면적/공시지가 직접 조회
        # (지오코딩 없이 데이터 API만 호출 — Railway 해외 IP에서도 동작)
        existing_pnu = (result.get("pnu_codes") or [None])[0]
        if existing_pnu and len(existing_pnu) >= 19:
            try:
                import httpx

                from app.core.config import settings

                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LP_PA_CBND_BUBUN",
                    "key": settings.VWORLD_API_KEY,
                    "format": "json",
                    "crs": "EPSG:4326",
                    "attrFilter": f"pnu:=:{existing_pnu}",
                    "geometry": "true",
                    "attribute": "true",
                }
                headers = {"Referer": "https://www.4t8t.net"}
                async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                    resp = await client.get("https://api.vworld.kr/req/data", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        features = data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
                        if features:
                            props = features[0].get("properties", {})
                            geom = features[0].get("geometry")

                            # 공시지가
                            jiga = props.get("jiga")
                            if jiga:
                                result["official_land_price"] = float(jiga)

                            # 면적: geometry에서 Shoelace 공식으로 계산
                            if geom:
                                area = self._calculate_area_from_geometry(geom)
                                if area > 0:
                                    result["land_area_sqm"] = area

                            # 지목
                            jibun_str = str(props.get("jibun", ""))
                            land_cat = jibun_str.split(" ")[-1] if " " in jibun_str else ""
                            if land_cat:
                                result["land_category"] = land_cat

                            import logging
                            logging.getLogger(__name__).info(
                                "VWORLD 데이터 API 성공: pnu=%s, area=%.1f, jiga=%s",
                                existing_pnu, result.get("land_area_sqm", 0), jiga,
                            )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("VWORLD 데이터 API 직접 조회 실패: %s", str(e)[:200])

        # 1. AutoZoningService → 용도지역 + 법적 한도
        try:
            from app.services.zoning.auto_zoning_service import AutoZoningService

            zoning_svc = AutoZoningService()
            zoning = await zoning_svc.analyze_by_address(address)

            if zoning.get("zone_type"):
                result["zone_type"] = zoning["zone_type"]
            if zoning.get("zone_limits"):
                zl = zoning["zone_limits"]
                # ★무날조(WP-U1c): zone_limits에 한도가 없으면 60/200을 지어내지 않고 None 유지 —
                #   아래 E7 블록이 assumed_fields 정직 표기와 함께 보수 기본치를 명시 라벨링한다
                #   (과거엔 여기서 침묵 날조돼 E7 플래그마저 우회됐다).
                result["max_bcr"] = zl.get("max_bcr_pct", zl.get("bcr", result.get("max_bcr")))
                result["max_far"] = zl.get("max_far_pct", zl.get("far", result.get("max_far")))
            if zoning.get("pnu"):
                result["pnu_codes"] = [zoning["pnu"]]
            if zoning.get("land_area_sqm"):
                result["land_area_sqm"] = zoning["land_area_sqm"]
            if zoning.get("official_price_per_sqm"):
                result["official_land_price"] = zoning["official_price_per_sqm"]
            if zoning.get("coordinates"):
                result["coordinates"] = zoning["coordinates"]
            result["special_districts"] = zoning.get("special_districts", [])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("AutoZoningService 호출 실패: %s", str(e)[:200])

        # 2. LandInfoService → 종합 토지정보 (실거래가, 건축물대장, 인프라 등)
        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            land_svc = LandInfoService()
            pnu = result.get("pnu_codes", [None])[0] if result.get("pnu_codes") else None
            comprehensive = await land_svc.collect_comprehensive(address, pnu=pnu)

            # 종합 데이터로 보충
            if comprehensive.get("land_register") and comprehensive["land_register"].get("area_sqm"):
                result["land_area_sqm"] = comprehensive["land_register"]["area_sqm"]
            if comprehensive.get("zone_type") and not result.get("zone_type"):
                result["zone_type"] = comprehensive["zone_type"]
            result["nearby_transactions"] = comprehensive.get("nearby_transactions")
            result["building_info"] = comprehensive.get("building_info")
            result["building_detail"] = comprehensive.get("building_detail")
            result["building_lookup_status"] = comprehensive.get("building_lookup_status")
            result["infrastructure"] = comprehensive.get("infrastructure")
            result["land_use_plan"] = comprehensive.get("land_use_plan")
            result["local_ordinance"] = comprehensive.get("local_ordinance")
            result["warnings"] = comprehensive.get("warnings", [])

            # 조례값 반영
            if comprehensive.get("local_ordinance"):
                ord_data = comprehensive["local_ordinance"]
                if ord_data.get("effective_bcr"):
                    result["ordinance_bcr"] = ord_data["effective_bcr"]
                if ord_data.get("effective_far"):
                    result["ordinance_far"] = ord_data["effective_far"]
                result["ordinance_source"] = ord_data.get("source", "")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("LandInfoService 호출 실패: %s", str(e)[:200])

        # 3. 최소 기본값 보장 — E7: 기본값 주입 사실을 정직하게 기록한다.
        #    수치는 유지해 파이프라인을 중단시키지 않되, assumed_fields/data_quality/warnings로
        #    "실측이 아닌 가정값"임을 소비자(UI 배지·SSOT 시드 가드)가 식별할 수 있게 한다.
        assumed_fields: list[str] = []
        if not result.get("zone_type"):
            result["zone_type"] = "제2종일반주거지역"  # 한국 도시 기본값
            assumed_fields.append("zone_type")
        if not result.get("land_area_sqm") or result["land_area_sqm"] <= 0:
            result["land_area_sqm"] = 500.0  # 기본 대지면적
            assumed_fields.append("land_area_sqm")
        if not result.get("max_bcr"):
            result["max_bcr"] = 60.0
            assumed_fields.append("max_bcr")
        if not result.get("max_far"):
            result["max_far"] = 250.0
            assumed_fields.append("max_far")
        if assumed_fields:
            result["assumed_fields"] = assumed_fields
            result["data_quality"] = "assumed_defaults"
            warnings = result.get("warnings")
            warnings = list(warnings) if isinstance(warnings, list) else []
            warnings.append(
                "외부 데이터 미확보로 기본 가정값을 적용했습니다: " + ", ".join(assumed_fields)
            )
            result["warnings"] = warnings

        return result

    @staticmethod
    def _calculate_area_from_geometry(geom: dict) -> float:
        """WGS84 좌표의 Polygon/MultiPolygon에서 면적(㎡)을 계산한다 (Shoelace 공식)."""
        import math

        def shoelace(coords: list) -> float:
            n = len(coords)
            if n < 3:
                return 0.0
            avg_lat = sum(c[1] for c in coords) / n
            m_lat = 111320.0
            m_lon = 111320.0 * math.cos(math.radians(avg_lat))
            area = 0.0
            for i in range(n):
                j = (i + 1) % n
                area += coords[i][0] * m_lon * coords[j][1] * m_lat
                area -= coords[j][0] * m_lon * coords[i][1] * m_lat
            return abs(area) / 2.0

        geom_type = geom.get("type", "")
        coordinates = geom.get("coordinates", [])

        if geom_type == "MultiPolygon":
            return sum(shoelace(polygon[0]) for polygon in coordinates)
        if geom_type == "Polygon":
            return shoelace(coordinates[0])
        return 0.0

    @staticmethod
    def _site_trust_adapter(data: dict[str, Any]) -> dict[str, Any]:
        """파이프라인 site stage data를 auto_zoning 신뢰헬퍼가 기대하는 형태로 어댑트한다.

        auto_zoning(_build_legal_refs/_build_evidence/_extract_sigungu)는 평탄
        zone_type + zone_limits(*_pct) + local_ordinance 구조를 읽지만, 파이프라인은
        zoning 블록 안에 effective_*/ordinance_*(pct 접미사 없음)를 둔다. 본 어댑터는
        값을 새로 계산하지 않고 키만 재배치한다(데이터 매핑, 계산 0).

        정직성 규칙:
        - 조례 실효값(ordinance_*)이 법정상한(national_*)과 실제로 다를 때만 ordinance_*_pct를
          주입한다. 단순 법정상한 폴백(ordinance==national)을 조례 적용으로 오인(가짜 조례링크)하지
          않기 위함. ordinance_source가 사용자/법정 폴백 신호면 조례로 보지 않는다.
        """
        zoning = data.get("zoning") if isinstance(data.get("zoning"), dict) else {}
        zone_type = data.get("zone_type") or zoning.get("zone_type") or ""

        zone_limits: dict[str, Any] = {}
        eff_far = zoning.get("effective_far")
        eff_bcr = zoning.get("effective_bcr")
        if eff_far is not None:
            zone_limits["max_far_pct"] = eff_far
        if eff_bcr is not None:
            zone_limits["max_bcr_pct"] = eff_bcr

        # 조례 실효값: 법정상한과 다르고, 폴백/사용자오버라이드 신호가 아닐 때만 인정.
        ord_far = zoning.get("ordinance_far")
        ord_bcr = zoning.get("ordinance_bcr")
        nat_far = zoning.get("national_far")
        nat_bcr = zoning.get("national_bcr")
        ord_source = str(zoning.get("ordinance_source") or "")
        _fallback_source = (not ord_source) or ("법정상한" in ord_source) or (
            ord_source in {"pre_collected", "user_override"}
        )
        if not _fallback_source:
            try:
                if ord_far is not None and nat_far is not None and float(ord_far) != float(nat_far):
                    zone_limits["ordinance_far_pct"] = ord_far
                if ord_bcr is not None and nat_bcr is not None and float(ord_bcr) != float(nat_bcr):
                    zone_limits["ordinance_bcr_pct"] = ord_bcr
            except (TypeError, ValueError):
                pass

        adapter: dict[str, Any] = {
            "address": data.get("address") or (data.get("basic") or {}).get("address") or "",
            "zone_type": zone_type,
            "zone_limits": zone_limits,
        }
        # sigungu 추출 보조: 조례 실효값이 있을 때만 조례 컨테이너를 노출(가짜 조례 방지).
        if "ordinance_far_pct" in zone_limits or "ordinance_bcr_pct" in zone_limits:
            lo: dict[str, Any] = {
                "ordinance_far": zone_limits.get("ordinance_far_pct"),
                "ordinance_bcr": zone_limits.get("ordinance_bcr_pct"),
                "source": ord_source or "지자체 조례",
            }
            # 조회된 시군구가 있으면 조례 url 치환에 사용(없으면 주소 폴백 → pending).
            sgg = zoning.get("ordinance_sigungu")
            if sgg and str(sgg).strip():
                lo["sigungu"] = str(sgg).strip()
            adapter["local_ordinance"] = lo
        return adapter

    def _attach_site_trust_blocks(self, state: PipelineState) -> None:
        """site stage data에 legal_refs[]·evidence[]를 additive로 부착(입지분석과 동일).

        - auto_zoning(_build_legal_refs/_build_evidence/_extract_sigungu)을 재사용해
          레지스트리(get_legal_refs) 단일출처 URL만 사용한다(여기서 URL 조립 금지).
        - E7 가정값(assumed_fields/data_quality)이면 legal_refs/evidence를 빈 배열로 둔다
          (가짜 부지에 진짜 법령링크를 붙이지 않음 — 정직성). assumed_fields/data_quality는 유지.
        - 기존 site data 키는 1개도 변경/제거하지 않는다(setdefault). 실패 시 graceful no-op.
        """
        try:
            data = state.stages["site_analysis"].data
            if not isinstance(data, dict):
                return

            self._attach_trust_guard(state)   # P5 T3: 공공데이터 cross_validate 신뢰가드(additive)

            # E7: 가정값(폴백 기본치)이면 진짜 법령링크/근거를 붙이지 않는다(빈 배열).
            if data.get("data_quality") == "assumed_defaults" or data.get("assumed_fields"):
                data.setdefault("legal_refs", [])
                data.setdefault("evidence", [])
                return

            from apps.api.routers.auto_zoning import (
                _build_evidence,
                _build_legal_refs,
            )

            adapter = self._site_trust_adapter(data)
            legal_refs = _build_legal_refs(adapter)
            evidence = _build_evidence(adapter, legal_refs)
            data.setdefault("legal_refs", legal_refs)
            data.setdefault("evidence", evidence)
        except Exception as e:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "부지분석 신뢰블록 부착 스킵: %s", str(e)[:120]
            )

    async def _attach_site_ai(self, state: PipelineState) -> None:
        """부지분석 stage data에 SiteAnalysisInterpreter(LLM) 해석을 부착한다.

        프론트 SiteAnalysisDetail이 ai_interpretation 10개 섹션을 렌더한다.
        LLM 실패 시에도 구조화 데이터는 정상 — 해석만 생략(graceful).
        """
        try:
            data = state.stages["site_analysis"].data
            if not isinstance(data, dict):
                return
            zoning = data.get("zoning") or {}
            pricing = data.get("pricing") or {}
            regulations = data.get("regulations") or {}
            interp_input = {
                "address": state.address,
                "zone_type": data.get("zone_type"),
                "land_area_sqm": data.get("land_area_sqm"),
                "effective_far": {
                    "effective_far_pct": zoning.get("effective_far"),
                    "effective_bcr_pct": zoning.get("effective_bcr"),
                },
                "land_prices": {
                    "official_price_per_sqm": pricing.get("official_price_per_sqm"),
                },
                "transaction_prices": pricing.get("nearby_transactions") or {},
                "development_plans": {
                    "land_use_plan": regulations.get("land_use_plan"),
                    "special_districts": regulations.get("special_districts", []),
                },
            }
            from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

            interp = await SiteAnalysisInterpreter().generate_interpretation(interp_input)
            if isinstance(interp, dict) and interp:
                data["ai_interpretation"] = interp
        except Exception as e:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "부지분석 AI 해석 스킵: %s", str(e)[:120]
            )

    async def _save_site_analysis_to_project(self, state: PipelineState):
        """부지분석 결과를 Project 테이블의 컬럼에 자동 저장.

        pnu_codes, zone_type, max_bcr, max_far, max_height, building_type을 업데이트한다.
        DB 세션을 획득할 수 없으면 경고만 남기고 계속 진행한다.
        """
        if not state.project_id:
            return

        site = state.site_to_design
        if not site:
            return

        try:
            from sqlalchemy import update

            from app.core.database import async_session_factory

            async with async_session_factory() as session:
                # 건물 유형 자동 판정 (설계 단계 전이므로 간이 판정)
                zone = site.zone_type or ""
                land_area = site.land_area_sqm or 0
                gfa_est = land_area * (site.max_far / 100) if site.max_far else 0
                if "주거" in zone:
                    building_type = "아파트" if gfa_est > 3000 else "다세대주택"
                elif "상업" in zone:
                    building_type = "근린생활시설"
                else:
                    building_type = "공동주택"

                # database/models 또는 app/models 중 활성 모델을 사용
                try:
                    from database.models.project import Project
                except ImportError:
                    from app.models.project import Project

                stmt = (
                    update(Project)
                    .where(Project.id == state.project_id)
                    .values(
                        pnu_codes=site.pnu_codes,
                        zone_type=site.zone_type,
                        max_bcr=site.max_bcr if site.max_bcr else None,
                        max_far=site.max_far if site.max_far else None,
                        max_height=site.max_height if site.max_height else None,
                        building_type=building_type,
                        total_area_sqm=site.land_area_sqm if site.land_area_sqm else None,
                        latitude=site.coordinates.get("lat") if site.coordinates else None,
                        longitude=site.coordinates.get("lon") if site.coordinates else None,
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            # DB 저장 실패는 파이프라인을 중단하지 않음
            import logging
            logging.getLogger(__name__).warning(
                "Project 모델 자동 저장 실패 (project_id=%s): %s",
                state.project_id, str(e),
            )

    async def _run_design(self, state: PipelineState, opts: dict):
        """STEP 2: 설계 — 부지 제약조건 기반 건축 개요 자동 생성."""
        site = state.site_to_design or SiteToDesignPayload()
        overrides = self._stage_overrides_for(opts, "design")
        applied_overrides: dict[str, Any] = {}

        # W3-8: 폴백 기본값(500㎡/60%/200%) 사용 시 가정 사실을 stage data에 정직 표기 —
        # site 단계의 assumed_fields 계약(E7)과 동일. 수치·흐름 불변, 표기만 가산.
        design_assumed_fields: list[str] = []
        if not site.land_area_sqm:
            design_assumed_fields.append("land_area_sqm(500㎡ 가정)")
        if not site.max_bcr:
            design_assumed_fields.append("max_bcr(60% 가정)")
        if not site.max_far:
            design_assumed_fields.append("max_far(200% 가정)")
        land_area = site.land_area_sqm or 500.0
        bcr = site.max_bcr or 60.0
        far = site.max_far or 200.0

        # 건축 개요 자동 산출 (사용자 오버라이드가 자동 산출값보다 우선)
        building_area = land_area * (bcr / 100)
        total_gfa = land_area * (far / 100)
        _gfa_ov = self._maybe_float(overrides.get("total_gfa_sqm"))
        if _gfa_ov is not None and _gfa_ov > 0:
            total_gfa = _gfa_ov
            applied_overrides["total_gfa_sqm"] = _gfa_ov
        floor_count = max(1, int(total_gfa / building_area)) if building_area > 0 else 5
        _floor_ov = self._maybe_int(overrides.get("floor_count_above"))
        if _floor_ov is not None and _floor_ov >= 1:
            floor_count = _floor_ov
            applied_overrides["floor_count_above"] = _floor_ov

        # 건물 유형 자동 판정
        zone = site.zone_type or ""
        if "주거" in zone:
            building_type = "아파트" if total_gfa > 3000 else "다세대주택"
        elif "상업" in zone:
            building_type = "근린생활시설"
        else:
            building_type = "공동주택"
        if overrides.get("building_type"):
            building_type = str(overrides["building_type"])
            applied_overrides["building_type"] = building_type

        # ── 전용률: 건물유형별 현실값 (고정 0.75 대체) ──
        # 정본은 unit_standards.get_sellable_efficiency (병합금지 대상인 get_exclusive_ratio·
        # M코드 전용률과는 분모가 다른 별개 물리량 — 파일 상단 주석 참조).
        from app.services.feasibility.unit_standards import get_sellable_efficiency

        efficiency = get_sellable_efficiency(building_type)
        sellable_area = total_gfa * efficiency

        # ── 유닛믹스 최적화 연동 (UnitMixOptimizer) ──
        # crude 추산(고정 25평으로 세대수만 산출) 대신 SLSQP 수익극대화 평형 배분을 사용한다.
        # 평형별 세대수·구성비·주차요구량을 산출하고, 최적화 실패 시에만 폴백 추산을 쓴다.
        avg_unit_area = 25.0  # 폴백 기본값(평)
        unit_count = max(1, int(sellable_area / (avg_unit_area * 3.3058)))
        unit_types: list[dict] = []
        parking_ratio: float | None = None
        unit_mix_method: str | None = None
        unit_mix_revenue_won: float | None = None

        if building_type in _RESIDENTIAL_TYPES and sellable_area > 0:
            try:
                from app.services.feasibility.regional_pricing import (
                    get_regional_base_price_man_won,
                )
                from app.services.feasibility.unit_mix_optimizer import (
                    UnitMixInput,
                    UnitMixOptimizer,
                )

                # 평형별 분양가 = 지역 기준시세(단일 출처) × 평형 프리미엄 (만원/평)
                base_price_man = get_regional_base_price_man_won(address=site.address)
                price_by_type = {
                    code: max(1, round(base_price_man * premium))
                    for code, premium in _UNIT_PRICE_PREMIUM.items()
                }

                mix = UnitMixOptimizer().optimize(
                    UnitMixInput(
                        total_gfa_sqm=sellable_area,  # 전용면적 기준으로 평형 배분
                        max_far_pct=far,
                        max_bcr_pct=bcr,
                        land_area_sqm=land_area,
                        max_floors=floor_count,
                        max_parking_spaces=10_000,  # 상한 미구속(주차는 요구량으로 산출)
                        region=site.zone_type or "서울",
                        price_by_type=price_by_type,
                        enabled_types=_ENABLED_UNIT_TYPES.get(building_type),
                    )
                )

                if mix.get("units"):
                    unit_types = mix["units"]
                    unit_count = mix.get("total_units") or unit_count
                    unit_mix_method = mix.get("method")
                    unit_mix_revenue_won = mix.get("total_revenue_won")
                    total_parking = mix.get("total_parking_required", 0)
                    if unit_count > 0:
                        parking_ratio = round(total_parking / unit_count, 2)
                        avg_unit_area = round(
                            mix.get("total_gfa_used_sqm", sellable_area)
                            / unit_count
                            / 3.3058,
                            1,
                        )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "유닛믹스 최적화 실패, 폴백 추산 사용: %s", str(e)[:200]
                )

        # 세대수·평형 오버라이드는 최적화 산출보다 우선한다
        _unit_ov = self._maybe_int(overrides.get("unit_count"))
        if _unit_ov is not None and _unit_ov >= 1:
            unit_count = _unit_ov
            applied_overrides["unit_count"] = _unit_ov
        _avg_ov = self._maybe_float(overrides.get("avg_unit_area_pyeong"))
        if _avg_ov is not None and _avg_ov > 0:
            avg_unit_area = _avg_ov
            applied_overrides["avg_unit_area_pyeong"] = _avg_ov

        state.design_to_cost = DesignToCostPayload(
            total_gfa_sqm=total_gfa,
            floor_count_above=floor_count,
            floor_count_below=1,
            structure_type="RC",
            building_type=building_type,
            unit_count=unit_count,
            avg_unit_area_pyeong=avg_unit_area,
        )

        state.stages["design"].data = {
            "building_type": building_type,
            "total_gfa_sqm": total_gfa,
            "building_area_sqm": building_area,
            "floor_count_above": floor_count,
            "floor_count_below": 1,
            "unit_count": unit_count,
            "bcr_used_pct": bcr,
            "far_used_pct": far,
            "sellable_efficiency_pct": round(efficiency * 100, 1),
            # 보고서 호환 alias (건축계획/유닛믹스 섹션)
            "floor_count": floor_count,
            "bcr": bcr,
            "far": far,
            "avg_unit_sqm": round(avg_unit_area * 3.3058, 1),
            # 유닛믹스 상세 (보고서 유닛믹스 탭 → UnitTypesTable)
            "unit_types": unit_types,
            "parking_ratio": parking_ratio,
            "unit_mix_method": unit_mix_method,
            "unit_mix_revenue_won": unit_mix_revenue_won,
        }

        if overrides:
            self._patch_remaining_overrides(
                state.stages["design"].data, overrides, applied_overrides,
                handled=frozenset({
                    "total_gfa_sqm", "floor_count_above", "building_type",
                    "unit_count", "avg_unit_area_pyeong",
                }),
            )
        if applied_overrides:
            state.stages["design"].data["applied_overrides"] = applied_overrides
        # W3-8: 폴백 가정치 사용 표기(UI 경고 배지·SSOT 시드 제외 판단용 — site 계약과 동일 키).
        if design_assumed_fields:
            state.stages["design"].data["assumed_fields"] = design_assumed_fields
            state.stages["design"].data["data_quality"] = "assumed_defaults"

        # ── 건축법규 자동 검증 (BuildingCodeRuleEngine) ──
        try:
            from app.services.permit.building_code_rules import BuildingCodeRuleEngine

            rule_engine = BuildingCodeRuleEngine()
            design_params = {
                "building_area_sqm": building_area,
                "total_gfa_sqm": total_gfa,
                "floor_count_above": floor_count,
                "floor_count_below": 1,
                "unit_count": unit_count,
                "building_type": building_type,
            }
            site_check_params = {
                "land_area_sqm": land_area,
                "max_bcr": bcr,
                "max_far": far,
                "max_height": site.max_height,
                "zone_type": site.zone_type,
            }
            compliance_results = rule_engine.check_all(design_params, site_check_params)
            compliance_data = [r.model_dump() for r in compliance_results]
            fail_count = sum(1 for r in compliance_results if r.status == "fail")
            warn_count = sum(1 for r in compliance_results if r.status == "warning")
            pass_count = sum(1 for r in compliance_results if r.status == "pass")

            state.stages["design"].data["compliance"] = {
                "results": compliance_data,
                "summary": {
                    "total_checks": len(compliance_results),
                    "pass": pass_count,
                    "fail": fail_count,
                    "warning": warn_count,
                    "status": (
                        "FAIL" if fail_count > 0
                        else ("WARNING" if warn_count > 0 else "PASS")
                    ),
                },
            }
        except Exception as e:
            state.stages["design"].data["compliance"] = {
                "error": f"법규 검증 실패: {str(e)[:200]}",
            }

    async def _run_design_review(self, state: PipelineState, opts: dict):
        """STEP 2.5: 심의/설계도면 자동분석 — 설계 결과를 심의 엔진 공용 함수로 검토.

        ★D3(감사 이중잣대 제거): BFF 라우터와 동일한 공용 함수 `run_deliberation_analysis`를 경유해
        engine_run_binding 결속 + 해시체인 감사원장 기록 + 무결성/테넌트 격리를 동일 계약으로 강제한다
        (과거엔 `_engine_post_analyze`를 직접 호출해 결속·감사를 건너뛴 무감사 경로였다).
        ★PR#319 리뷰 반영 — 감사 실패(fail-closed 502)는 엔진 미연결/오류(degraded)와 **구분**한다.
        `run_deliberation_analysis`가 감사 기록 실패 시 raise하는 HTTPException(502)을 광범위
        except보다 먼저 캐치해 `status="audit_failed"`(FAILED)로 명시 강등하고, 판정 데이터는 절대
        저장하지 않는다(예외로 중단돼 애초에 없음 — 감사 없는 권위 판정 제공 금지). 반면 엔진 미연결/
        무결성 위반은 종전대로 degraded/SKIPPED 유지(구분 보존). 어느 경우든 예외를 상위로 던지지
        않으므로 cost 등 하류 단계는 영향받지 않는다. 결정론 산출 수치는 변경하지 않는다.
        """
        sr = state.stages.get(PipelineStage.DESIGN_REVIEW.value)
        try:
            site = state.site_to_design or SiteToDesignPayload()
            design = state.design_to_cost or DesignToCostPayload()
            design_data = state.stages["design"].data if "design" in state.stages else {}
            design_data = design_data if isinstance(design_data, dict) else {}

            # 설계 산출 → 엔진 AnalysisInput 입력 구성(검토 규칙: 건폐율·용적률 한도 비교).
            pnu = site.pnu_codes[0] if site.pnu_codes else ""
            building_area = float(design_data.get("building_area_sqm") or 0.0)
            total_gfa = float(design.total_gfa_sqm or design_data.get("total_gfa_sqm") or 0.0)
            land_area = float(site.land_area_sqm or 0.0)
            # ★engine_inputs 공용 헬퍼(build_bcr_far_rules) 재사용 — measured(대지면적으로 산출)와
            #   limit(실효한도)가 둘 다 있을 때만 rule을 넣는다(land_area=0이면 이전엔 measured=0.0을
            #   지어냈다 — 무날조 원칙 위반이라 이제 rule 자체를 생략한다).
            from app.services.agents.engine_inputs import build_bcr_far_rules

            rules = build_bcr_far_rules(
                bcr_measured=round(building_area / land_area * 100, 2) if land_area > 0 else None,
                bcr_limit=site.max_bcr if site.max_bcr else None,
                far_measured=round(total_gfa / land_area * 100, 2) if land_area > 0 else None,
                far_limit=site.max_far if site.max_far else None,
            )
            payload: dict[str, Any] = {
                "pnu": pnu if (pnu and len(str(pnu)) == 19 and str(pnu).isdigit()) else "",
                "address": site.address or state.address or "",
                "calc_targets": [
                    {"target": "building_area"},
                    {"target": "gross_floor_area"},
                ],
            }
            if rules:
                payload["rules"] = rules

            # ★D3(감사 이중잣대 제거): 라우터와 동일한 공용 함수를 경유해 결속(engine_run_binding)·감사원장·
            #   무결성·테넌트 격리를 동일 계약으로 강제한다. 과거엔 `_engine_post_analyze`를 직접 호출해 결속·감사
            #   없이 판정을 산출했다(BFF는 감사 없는 판정 제공을 502로 금지하는데 파이프라인만 무감사 우회였다).
            #   내부에서 build_input_dump·prevalidate·is_deterministic_path를 수행하므로 여기선 payload만 넘긴다.
            #   결속·감사에 필요한 사용자/테넌트 컨텍스트는 요청 스코프 contextvar에서 파생(파이프라인 /run은 인증 게이트).
            from types import SimpleNamespace

            from fastapi import HTTPException

            from app.core.request_context import get_current_tenant_id, get_current_user_id
            from apps.api.app.routers.deliberation import run_deliberation_analysis

            user_id = get_current_user_id()
            tenant_id = get_current_tenant_id()
            if not user_id or not tenant_id:
                # ★비차단 리뷰 반영(PR#319) — 인증 요청 컨텍스트 밖(향후 백그라운드/배치 파이프라인 실행 등)에서는
                #   contextvar가 비어 있을 수 있다. 빈 id/tenant로 결속·감사를 기록하면 서로 다른 무인증 호출이
                #   같은 빈 tenant_id로 충돌·오염할 위험이 있으므로, 엔진 호출 자체를 하지 않고 audit_failed와
                #   동일한 fail-closed 경로로 사전 강등한다(감사 없는 판정 제공 금지 원칙의 사전 가드).
                if sr:
                    sr.data = {"status": "audit_failed", "reason": "no_auth_context"}
                    sr.status = PipelineStatus.FAILED
                    sr.error = "deliberation_audit_failed:no_auth_context"
                return

            audit_user = SimpleNamespace(id=user_id, tenant_id=tenant_id)

            try:
                envelope = await run_deliberation_analysis(payload, audit_user)
            except HTTPException as he:
                if he.status_code == 502:
                    # ★차단 결함 수정(PR#319 리뷰): 감사 기록 실패(fail-closed)는 엔진 미연결/오류(degraded)와
                    #   다른 사건이다 — BFF 경로가 502를 명시 반환하는 것과 동일하게, 파이프라인도 SKIPPED-degraded로
                    #   조용히 뭉개지 않고 FAILED/audit_failed로 명시 구분한다. 판정 데이터는 저장하지 않는다
                    #   (예외로 중단돼 애초에 존재하지 않음 — 감사 없는 결과를 하류로 전파 금지).
                    if sr:
                        sr.data = {"status": "audit_failed", "reason": str(he.detail)[:200]}
                        sr.status = PipelineStatus.FAILED
                        sr.error = f"deliberation_audit_failed:{str(he.detail)[:200]}"
                    return
                # 그 외 HTTPException(예: 422 입력 미러/선검증 실패) — 엔진 호출·감사 이전 단계라 감사 무관.
                # 기존(D3 이전) 계약대로 degraded/SKIPPED 유지(reason 표면화, 무음 아님).
                if sr:
                    sr.data = {"status": "degraded", "reason": f"invalid_input:{str(he.detail)[:180]}"}
                    sr.status = PipelineStatus.SKIPPED
                return

            if not isinstance(envelope, dict) or envelope.get("status") != "ok":
                # 엔진 미연결/오류·무결성 위반(200이지만 degraded 봉투) → degraded SKIPPED(무음 아님·reason 표면화).
                reason = envelope.get("reason") if isinstance(envelope, dict) else "invalid_response"
                if sr:
                    sr.data = {"status": "degraded", "reason": reason or "degraded"}
                    sr.status = PipelineStatus.SKIPPED
                return

            # 정상 — 결속·감사 완료. 평면 필드(complianceScore·finalStatus·findings·sections)와 감사 출처 표면화.
            if sr:
                sr.data = {
                    "status": "ok",
                    "run_id": str(envelope.get("run_id") or ""),
                    "complianceScore": envelope.get("complianceScore"),
                    "finalStatus": envelope.get("finalStatus"),
                    "findings": envelope.get("findings") or [],
                    "sections": envelope.get("sections") or {},
                    "skipped": envelope.get("skipped") or [],
                    "audit_degraded": envelope.get("audit_degraded", False),
                    "audit_skipped": envelope.get("audit_skipped") or [],
                }
        except Exception as e:  # noqa: BLE001 — 심의 검토의 그 외 예기치 못한 실패가 파이프라인을 깨지 않게 흡수.
            if sr:
                sr.data = {"status": "degraded", "reason": f"design_review_error:{str(e)[:140]}"}
                sr.status = PipelineStatus.SKIPPED

    async def _run_cost(self, state: PipelineState, opts: dict):
        """STEP 3: 공사비 — 표준물량 추정 → 원가계산서 엔진 연동."""
        design = state.design_to_cost or DesignToCostPayload()
        overrides = self._stage_overrides_for(opts, "cost")
        applied_overrides: dict[str, Any] = {}
        total_pyeong = design.total_gfa_sqm / 3.3058

        cost_breakdown: dict[str, Any] = {}
        material_quantities: list[dict] = []
        total_cost = 0.0
        direct_cost = 0.0

        try:
            # 1단계: 표준물량 추정 — 건물유형+연면적+층수로 공종별 물량 산출
            from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator

            estimator = StandardQuantityEstimator()
            estimated_items = estimator.estimate(
                building_type=design.building_type or "공동주택",
                total_gfa_sqm=design.total_gfa_sqm,
                floor_count_above=design.floor_count_above,
                floor_count_below=design.floor_count_below,
                structure_type=design.structure_type or "RC",
            )
            material_quantities = estimated_items

            # 2단계: 추정 물량 → OriginCostCalculator 법정요율 체인 적용
            from app.services.cost.origin_cost_calculator import OriginCostCalculator

            calc = OriginCostCalculator()
            result = calc.calculate(items=estimated_items)

            total_cost = result.get("total_project_cost", 0)
            direct_cost = result.get("direct_cost", 0)

            cost_breakdown = {
                "direct_material_cost": result.get("direct_material_cost", 0),
                "direct_labor_cost": result.get("direct_labor_cost", 0),
                "direct_expense_cost": result.get("direct_expense_cost", 0),
                "direct_cost": direct_cost,
                "indirect_labor_cost": result.get("indirect_labor_cost", 0),
                "insurance_total": result.get("insurance_total", 0),
                "safety_health": result.get("safety_health", 0),
                "env_preserve": result.get("env_preserve", 0),
                "net_construction_cost": result.get("net_construction_cost", 0),
                "general_mgmt": result.get("general_mgmt", 0),
                "profit": result.get("profit", 0),
                "vat": result.get("vat", 0),
                "total_project_cost": total_cost,
                "category_totals": result.get("category_totals", {}),
            }
        except Exception:
            # 폴백: 건물유형별 평당 공사비 개산견적
            type_cost_map = {
                "아파트": 550,
                "다세대주택": 500,
                "오피스텔": 600,
                "근린생활시설": 480,
                "공동주택": 530,
            }
            cost_per_pyeong_man = type_cost_map.get(design.building_type, 530)
            direct_cost = cost_per_pyeong_man * 10000 * total_pyeong
            total_cost = direct_cost * 1.35  # 간접비 포함 배율

            cost_breakdown = {
                "direct_cost": round(direct_cost),
                "total_project_cost": round(total_cost),
                "estimation_method": "fallback_per_pyeong",
            }

        # 사용자 오버라이드: 총공사비 교체 시 평당가를 재계산해 정합성을 유지한다
        _total_ov = self._maybe_float(overrides.get("total_construction_cost"))
        if _total_ov is not None and _total_ov > 0:
            total_cost = _total_ov
            applied_overrides["total_construction_cost"] = _total_ov

        cost_per_pyeong = round(total_cost / total_pyeong) if total_pyeong > 0 else 0
        _cpp_ov = self._maybe_float(overrides.get("cost_per_pyeong"))
        if _cpp_ov is not None and _cpp_ov > 0:
            cost_per_pyeong = _cpp_ov
            applied_overrides["cost_per_pyeong"] = _cpp_ov
        construction_months = max(12, int(design.floor_count_above * 1.5) + 6)
        _months_ov = self._maybe_int(overrides.get("construction_months"))
        if _months_ov is not None and _months_ov >= 1:
            construction_months = _months_ov
            applied_overrides["construction_months"] = _months_ov

        state.cost_to_feasibility = CostToFeasibilityPayload(
            total_construction_cost=total_cost,
            cost_per_pyeong=cost_per_pyeong,
            construction_months=construction_months,
            material_quantities=material_quantities,
            cost_breakdown=cost_breakdown,
        )

        state.stages["cost"].data = {
            "total_construction_cost": total_cost,
            "direct_cost": direct_cost,
            "cost_per_pyeong": cost_per_pyeong,
            "total_gfa_pyeong": total_pyeong,
            "construction_months": construction_months,
            "cost_breakdown": cost_breakdown,
            "material_item_count": len(material_quantities),
        }

        if overrides:
            self._patch_remaining_overrides(
                state.stages["cost"].data, overrides, applied_overrides,
                handled=frozenset({
                    "total_construction_cost", "cost_per_pyeong", "construction_months",
                }),
            )
        if applied_overrides:
            state.stages["cost"].data["applied_overrides"] = applied_overrides
            if "total_construction_cost" in applied_overrides:
                # 출처 정직 표기 — 사용자 수정값 기반 재계산임을 명시
                state.stages["cost"].data["cost_source"] = "user_override"

        # ── BOQ 자동초안 힌트(additive) ──
        # 실적 공내역 마스터(services/cost/data/boq_master, 실적 n=1) 기반 파라메트릭
        # 엔진(boq_parametric_engine)이 존재하면 분야별 항목수 요약·정직성 배지만
        # 'boq_draft_hint' 키로 가산한다. 엔진 부재·실패 시 키 자체를 생략해 기존
        # 응답 키·단계 동작을 그대로 유지한다(하위호환). 상세 항목 목록은 stage data에
        # 싣지 않는다(스냅샷 비대 방지) — /api/v1/boq-auto/draft 가 단일 상세 출처.
        self._attach_boq_draft_hint(state, design)

    @staticmethod
    def _attach_boq_draft_hint(state: PipelineState, design: DesignToCostPayload) -> None:
        """cost stage data에 BOQ 초안 요약 힌트를 부착한다(실패 시 graceful no-op).

        정직성: 항목수는 엔진 반환값에서만 집계(여기서 생성 금지), 배지는 엔진 배지를
        우선하되 없으면 마스터 출처 사실(_meta.json sample_count=1)에 근거한 고정
        문구만 사용한다. 가짜 수치·임의 단가 생성 없음(결정론, LLM 0).
        """
        try:
            if not (design.total_gfa_sqm and design.total_gfa_sqm > 0):
                return
            from app.services.cost import boq_parametric_engine as _bpe

            _gen = getattr(_bpe, "generate_draft", None)
            if _gen is None:
                _engine_cls = getattr(_bpe, "BoqParametricEngine", None)
                if _engine_cls is not None:
                    _gen = getattr(_engine_cls(), "generate_draft", None)
            if not callable(_gen):
                return
            try:
                draft = _gen(gfa_sqm=design.total_gfa_sqm)
            except TypeError:
                # 시그니처 차이 허용(키워드명 불일치 등) — 위치 인자 1개로 재시도
                draft = _gen(design.total_gfa_sqm)
            if not isinstance(draft, dict) or not draft:
                return

            # 분야별 항목수 집계 — dict/list 양형 모두 수용(엔진 반환값만 사용)
            disc_counts: dict[str, int] = {}
            disc = draft.get("disciplines")
            if isinstance(disc, dict):
                blocks = [(str(k), v) for k, v in disc.items()]
            elif isinstance(disc, list):
                blocks = [
                    (str(b.get("discipline") or b.get("name") or ""), b)
                    for b in disc if isinstance(b, dict)
                ]
            else:
                blocks = []
            for name, block in blocks:
                if not name or not isinstance(block, dict):
                    continue
                cnt = block.get("item_count")
                if cnt is None and isinstance(block.get("items"), list):
                    cnt = len(block["items"])
                if isinstance(cnt, (int, float)) and int(cnt) > 0:
                    disc_counts[name] = int(cnt)
            if not disc_counts:
                return

            badges = draft.get("badges")
            if not (isinstance(badges, list) and badges):
                # 엔진 배지 부재 시 마스터 출처 사실 기반 고정 배지(가짜값 아님)
                badges = ["실적 1건 기반 표준항목(n=1)", "전문가 검토 필수"]
            state.stages["cost"].data["boq_draft_hint"] = {
                "disciplines": disc_counts,
                "item_total": sum(disc_counts.values()),
                "badges": [str(b) for b in badges],
                "detail": "상세는 /api/v1/boq-auto/draft",
            }
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).info("BOQ 초안 힌트 생략: %s", str(e)[:140])

    async def _run_feasibility(self, state: PipelineState, opts: dict):
        """STEP 4: 수지분석 — 몬테카를로+현금흐름+민감도 통합 분석."""
        site = state.site_to_design or SiteToDesignPayload()
        design = state.design_to_cost or DesignToCostPayload()
        cost = state.cost_to_feasibility or CostToFeasibilityPayload()
        overrides = self._stage_overrides_for(opts, "feasibility")
        applied_overrides: dict[str, Any] = {}

        # ── 기본 수지분석 ──
        # ★A-2(usable 면적 전파): 토지비는 gross(land_area_gross_sqm — 다필지 통합 경로에서만
        #   채워짐, 제외 필지도 실제 매입 대상) 채택, 미설정(단일/미통합)이면 land_area_sqm으로
        #   폴백(기존 동작 무회귀). GFA(design.total_gfa_sqm)는 이미 usable(land_area_sqm) 기준.
        _land_cost_area = (
            site.land_area_gross_sqm if site.land_area_gross_sqm is not None else site.land_area_sqm
        )
        land_cost = _land_cost_area * site.official_land_price * 1.3  # 공시지가 x 1.3 보정

        # 분양가는 시장 시세 기반으로 산정한다. 공사비에서 역산(cost_per_pyeong x 1.3)하면
        # 토지비가 수입에 반영되지 않아 토지비만큼 구조적 적자가 발생한다.
        # regional_pricing(단일 출처)을 사용하고, 조회 실패 시에만 공사비 기반으로 폴백한다.
        from app.services.feasibility.regional_pricing import (
            resolve_regional_sale_price_per_pyeong,
        )

        # W2-1: 매칭 근거(basis)를 함께 받아 전국 기본 폴백을 출처에 정직 표기.
        market_price, market_price_basis = resolve_regional_sale_price_per_pyeong(
            address=site.address
        )

        # F1: 다중출처 신뢰도 가중 시장 재평가(지역표준 + MOLIT 실거래 블렌딩). 있으면 우선.
        market_reval: dict | None = None
        try:
            from app.services.feasibility.market_revaluation_service import MarketRevaluationService
            sa = state.stages.get("site_analysis")
            sa_data = sa.data if sa else {}
            pnu = (sa_data.get("basic", {}) or {}).get("pnu") or sa_data.get("pnu")
            lawd = str(pnu)[:5] if pnu else None
            market_reval = await MarketRevaluationService().revalue(
                address=site.address, building_type=design.building_type,
                lawd_cd=lawd, land_area_sqm=site.land_area_sqm,
            )
        except Exception:  # noqa: BLE001
            market_reval = None

        if market_reval and market_reval.get("available"):
            avg_sale_price = float(market_reval["price_per_pyeong"])
            sale_price_source = "market_blended"
        elif market_price and market_price > 0:
            avg_sale_price = float(market_price)
            # W2-1: 지역 미매칭 전국 기본(1500만/평) 폴백을 지역시세표 출처로 오표기하지 않음.
            sale_price_source = (
                "national_default_fallback" if market_price_basis == "national_default"
                else "regional_market_table"
            )
        else:
            avg_sale_price = cost.cost_per_pyeong * 1.3  # 최후 폴백
            sale_price_source = "cost_based_fallback"

        # 사용자 오버라이드: 분양가 직접 지정 시 출처를 "user"로 정직 표기
        _price_ov = self._maybe_float(overrides.get("avg_sale_price_per_pyeong"))
        if _price_ov is not None and _price_ov > 0:
            avg_sale_price = _price_ov
            sale_price_source = "user"
            applied_overrides["avg_sale_price_per_pyeong"] = _price_ov

        total_gfa_pyeong = design.total_gfa_sqm / 3.3058
        # 전용률은 설계 단계와 동일 단일 출처(건물유형별)를 사용한다.
        design_data = state.stages["design"].data if "design" in state.stages else {}
        efficiency_pct = design_data.get("sellable_efficiency_pct", 75.0)
        sellable_pyeong = total_gfa_pyeong * (efficiency_pct / 100)
        total_revenue = avg_sale_price * sellable_pyeong

        # ── 토지비: 공시지가 미확보 시 주변시세(예상토지비)로 폴백 — '토지비 0' 방지 ──
        land_cost_source = "공시지가×1.3"
        _land_ov = self._maybe_float(overrides.get("land_cost"))
        if _land_ov is not None and _land_ov > 0:
            land_cost = _land_ov
            land_cost_source = "사용자 입력"
            applied_overrides["land_cost"] = _land_ov
        if land_cost <= 0:
            try:
                from app.services.land_intelligence.land_price_estimator import estimate_land_price
                _sa = state.stages.get("site_analysis")
                _sad = (_sa.data if _sa else {}) or {}
                _pnu = (_sad.get("basic", {}) or {}).get("pnu") or _sad.get("pnu")
                est = await estimate_land_price(
                    address=site.address, area_sqm=_land_cost_area, pnu=_pnu,
                )
                if est and est.get("ok") and est.get("estimated_total_won"):
                    land_cost = float(est["estimated_total_won"])
                    land_cost_source = "주변시세 추정(공시지가×지역보정)"
            except Exception:  # noqa: BLE001
                pass
        if land_cost <= 0 and total_revenue > 0:
            land_cost = total_revenue * 0.35  # 최후 폴백: 도심개발 통상 토지비≈매출 35%
            land_cost_source = "매출 대비 35% 추정(공시지가·시세 미확보)"

        # ── 총사업비: 실무 약식 라인아이템(개별 항목 명시) ──
        #  토지비 + 직접공사비 + 설계·감리 + 인허가·분담금 + 분양경비 + 일반관리 + 예비비 + 금융비 + 제세공과
        #  (기존 '일반사업비 매출20%+금융비10%' 뭉뚱그림 → 검토 가능한 항목별 분해)
        direct_construction = float(cost.total_construction_cost or 0)
        proj_months = float(getattr(cost, "construction_months", 0) or 0) or 30.0  # 토지매입~준공 통상 30개월
        interest_rate = 0.065

        design_supervision = direct_construction * 0.05      # 설계·감리비(직접공사비 5%)
        permit_contrib = direct_construction * 0.03          # 인허가·분담금(직접공사비 3%)
        sales_expense = total_revenue * 0.04                 # 분양경비(매출 4%)
        general_admin = (land_cost + direct_construction) * 0.03  # 일반관리비(토지+공사 3%)
        contingency = direct_construction * 0.05             # 예비비(직접공사비 5%)
        # 금융비: PF/브릿지 평균잔액(토지+공사의 절반)×금리×사업기간
        finance_cost = (land_cost + direct_construction) * 0.5 * interest_rate * (proj_months / 12.0)
        # ★세율 SSOT: 제세공과(토지 취득세)율을 tax_reconcile 단일출처와 공유(리터럴 0.046 중복 제거·값 불변).
        from app.services.pipeline.tax_reconcile import LAND_ACQUISITION_RATE
        levies = land_cost * LAND_ACQUISITION_RATE           # 제세공과(취득세 등 토지비 4.6%)

        cost_breakdown = {
            "토지비": round(land_cost),
            "직접공사비": round(direct_construction),
            "설계·감리비": round(design_supervision),
            "인허가·분담금": round(permit_contrib),
            "분양경비": round(sales_expense),
            "일반관리비": round(general_admin),
            "예비비": round(contingency),
            "금융비": round(finance_cost),
            "제세공과(취득세 등)": round(levies),
        }
        total_project_cost = float(sum(cost_breakdown.values()))
        # 일반사업비(소프트코스트 합계 — 토지·공사 제외) — 보고서 표기 호환
        general_expense = (design_supervision + permit_contrib + sales_expense
                           + general_admin + contingency + levies)

        net_profit = total_revenue - total_project_cost
        # 사업이익률(총사업비 대비) + 손익분기 분양률 + 자기자본수익률(ROE, 자기자본=총사업비30% 가정)
        profit_rate = (net_profit / total_project_cost * 100) if total_project_cost > 0 else 0
        breakeven_sale_rate = (total_project_cost / total_revenue * 100) if total_revenue > 0 else 0
        equity = total_project_cost * 0.30
        roe_pct = (net_profit / equity * 100) if equity > 0 else 0

        # 등급 판정
        if profit_rate >= 20:
            grade = "A"
        elif profit_rate >= 10:
            grade = "B"
        elif profit_rate >= 0:
            grade = "C"
        else:
            grade = "D"

        feasibility_data: dict[str, Any] = {
            # 계산 엔진 출처 — 파이프라인 약식 라인아이템(빠른 전주기 개산).
            # 정밀 모듈 엔진(M01~M15)은 /api/v2/feasibility(FeasibilityServiceV2) 별도 경로이며
            # 분양경비·일반관리·금융비 비율 산식이 다를 수 있어 두 결과를 직접 비교 시 주의.
            "calc_engine": "pipeline_simplified",
            "land_cost": land_cost,
            "land_cost_source": land_cost_source,        # 토지비 산정 출처(정직 표기)
            "construction_cost": cost.total_construction_cost,
            "general_expense_won": round(general_expense),  # 일반사업비(소프트코스트 합계)
            "finance_cost_won": round(finance_cost),        # 금융비(PF 평균잔액×금리×기간)
            "cost_breakdown": cost_breakdown,               # ★실무 라인아이템(항목별 총사업비)
            "breakeven_sale_rate_pct": round(breakeven_sale_rate, 1),  # 손익분기 분양률
            "roe_pct": round(roe_pct, 1),                   # 자기자본수익률(자기자본=총사업비30% 가정)
            "project_months": int(proj_months),
            "total_project_cost": total_project_cost,
            "total_cost_won": total_project_cost,  # 보고서 호환 alias
            "total_revenue": total_revenue,
            "total_revenue_won": total_revenue,  # 보고서 호환 alias
            "net_profit": net_profit,
            "net_profit_won": net_profit,  # 보고서 호환 alias
            "profit_rate_pct": round(profit_rate, 2),
            "avg_sale_price_per_pyeong": avg_sale_price,
            "sale_price_source": sale_price_source,
            "sale_price_confidence": (market_reval or {}).get("confidence"),  # 분양가 신뢰도(%)
            "market_revaluation": market_reval,  # 출처별 블렌딩 내역(가정버전·원장 기록용)
            "grade": grade,
        }

        if overrides:
            if "avg_sale_price_per_pyeong" in applied_overrides:
                # 시장 블렌딩 신뢰도는 사용자 지정가에 적용되지 않는다(정직성)
                feasibility_data["sale_price_confidence"] = None
            self._patch_remaining_overrides(
                feasibility_data, overrides, applied_overrides,
                handled=frozenset({"avg_sale_price_per_pyeong", "land_cost"}),
            )
        if applied_overrides:
            feasibility_data["applied_overrides"] = applied_overrides

        # ── 몬테카를로 시뮬레이션 (1,000회) ──
        try:
            from app.services.feasibility.monte_carlo_engine import (
                MCVariable,
                run_monte_carlo,
            )

            base_interest_rate = 0.065

            def mc_profit_fn(vars_dict: dict[str, float]) -> float:
                mc_revenue = vars_dict["sale_price"] * sellable_pyeong
                c = vars_dict["construction_cost"]
                r = vars_dict["interest_rate"]
                # 결정론 라인아이템과 동일 구조(설계감리5%+인허가3%+예비5%=공사 13%, 분양경비4%, 일반관리3%, 제세4.6%, 금융)
                mc_soft = c * 0.13 + mc_revenue * 0.04 + (land_cost + c) * 0.03
                mc_finance = (land_cost + c) * 0.5 * r * (proj_months / 12.0)
                mc_levies = land_cost * 0.046
                mc_cost = land_cost + c + mc_soft + mc_finance + mc_levies
                return mc_revenue - mc_cost

            mc_result = run_monte_carlo(
                calculate_fn=mc_profit_fn,
                variables=[
                    MCVariable(
                        name="sale_price",
                        mean=avg_sale_price,
                        std=avg_sale_price * 0.10,  # ±10%
                        distribution="normal",
                    ),
                    MCVariable(
                        name="construction_cost",
                        mean=cost.total_construction_cost,
                        std=cost.total_construction_cost * 0.15,  # ±15%
                        distribution="normal",
                    ),
                    MCVariable(
                        name="interest_rate",
                        mean=base_interest_rate,
                        std=0.02,  # ±2%p
                        distribution="normal",
                    ),
                ],
                n_simulations=1_000,
                seed=42,
            )

            # VaR 계산 (95% 신뢰수준, 손실 가능 최대 금액)
            var_95 = -mc_result.get("p5", 0) if mc_result.get("p5", 0) < 0 else 0

            feasibility_data["monte_carlo"] = {
                "n_simulations": mc_result.get("n_simulations", 1000),
                "profit_mean": round(mc_result.get("mean", 0)),
                "profit_std": round(mc_result.get("std", 0)),
                "p10": round(mc_result.get("p5", 0)),   # p5 ≈ p10 근사
                "p50": round(mc_result.get("p50", 0)),
                "p90": round(mc_result.get("p95", 0)),   # p95 ≈ p90 근사
                "probability_positive": round(mc_result.get("probability_positive", 0), 4),
                "var_95_won": round(var_95),
                "convergence_ratio": mc_result.get("convergence_ratio", 0),
                "histogram": mc_result.get("histogram", []),
            }
        except Exception as e:
            feasibility_data["monte_carlo"] = {"error": str(e)[:200]}

        # ── 월별 현금흐름 자동 생성 ──
        try:
            from app.services.feasibility.cashflow_generator import CashflowGenerator

            cf_gen = CashflowGenerator()
            sale_start_month = max(0, cost.construction_months - 6)  # 준공 6개월 전 분양 시작

            # ── R1 세후 IRR: 통합 세금엔진(38종) 결과를 시점 매핑해 주입(additive) ──
            # 실패·세금 전무 시 tax_schedule=None → 기존 세전 현금흐름과 완전 동일(graceful).
            tax_schedule = None
            try:
                from app.services.feasibility.cashflow_generator import (
                    build_tax_schedule_from_integrated,
                )
                from app.services.tax.integrated_tax_engine import calculate_all_taxes

                _units = int(design.unit_count or 0)
                tax_result = calculate_all_taxes(
                    purchase_won=int(land_cost),
                    # ★A-2: 취득세 등은 실제 매입(land_cost와 동일 기준) 면적 — gross(_land_cost_area).
                    area_sqm=float(_land_cost_area or 0),
                    official_price_per_sqm=float(site.official_land_price or 0),
                    total_households=_units,
                    total_sale_amount_won=int(total_revenue),
                    total_gfa_sqm=float(design.total_gfa_sqm or 0),
                    building_type=design.building_type or "apartment",
                    total_units=_units,
                    avg_area_sqm=(
                        design.avg_unit_area_pyeong * 3.305785
                        if design.avg_unit_area_pyeong
                        else 85.0
                    ),
                )
                tax_schedule = build_tax_schedule_from_integrated(tax_result)
            except Exception:  # noqa: BLE001
                tax_schedule = None

            cf_result = cf_gen.generate_monthly_cashflow(
                land_cost=land_cost,
                construction_cost=cost.total_construction_cost,
                construction_months=cost.construction_months,
                total_revenue=total_revenue,
                sale_start_month=sale_start_month,
                sale_duration_months=6,
                bridge_loan_rate=0.08,
                pf_loan_rate=0.065,
                equity_ratio=0.3,
                tax_schedule=tax_schedule,
            )

            feasibility_data["cashflow"] = {
                "summary": cf_result.get("summary", {}),
                "phases": cf_result.get("phases", {}),
                "monthly_rows": cf_result.get("rows", []),
            }
        except Exception as e:
            feasibility_data["cashflow"] = {"error": str(e)[:200]}

        # ── Tornado 민감도 분석 ──
        try:
            from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis

            base_interest = 0.065

            def sensitivity_fn(vals: dict[str, float]) -> dict[str, Any]:
                s_revenue = vals["sale_price"] * sellable_pyeong
                s_total_cost = vals["land_cost"] + vals["construction_cost"]
                s_finance = vals["construction_cost"] * vals["interest_rate"] * (vals["project_months"] / 12)
                s_profit = s_revenue - s_total_cost - s_finance
                s_rate = (s_profit / s_total_cost * 100) if s_total_cost > 0 else 0
                return {
                    "profit_rate_pct": round(s_rate, 2),
                    "npv_won": round(s_profit),
                }

            sens_result = run_sensitivity_analysis(
                base_values={
                    "sale_price": avg_sale_price,
                    "construction_cost": cost.total_construction_cost,
                    "land_cost": land_cost,
                    "interest_rate": base_interest,
                    "project_months": float(cost.construction_months),
                },
                calculate_fn=sensitivity_fn,
            )

            feasibility_data["sensitivity"] = {
                "base_result": sens_result.get("base_result", {}),
                "tornado": sens_result.get("tornado", []),
                "scenarios": sens_result.get("scenarios", []),
            }
        except Exception as e:
            feasibility_data["sensitivity"] = {"error": str(e)[:200]}

        state.stages["feasibility"].data = feasibility_data

    async def _run_tax(self, state: PipelineState, opts: dict):
        """STEP 5: 세금 — 취득세/보유세/양도세 + 세후 손익 정합(Fix #4·감사 HIGH).

        취득세 과세표준을 취득가액(토지+건물)으로 좁히고(총사업비 과대과세 제거), 토지 취득세가
        이미 사업비 levies(land×율)에 포함된 이중계상을 제거하며, 세후 이익·등급을 산출해
        헤드라인 ROI(세전)와 별도로 정합되게 한다. 산식은 순수 모듈 tax_reconcile에서 검증.
        """
        from app.services.pipeline.tax_reconcile import compute_project_taxes

        feasibility = state.stages.get("feasibility", StageResult(stage=PipelineStage.FEASIBILITY))
        # W2-3: feasibility 미완료/실패 시 0 입력으로 '완료' 세금이 산출되던 침묵 전파 차단 —
        # design_review와 동일한 degraded SKIPPED 패턴(러너가 상태 보존, 정직 표기).
        if feasibility.status != PipelineStatus.COMPLETED:
            state.stages["tax"].status = PipelineStatus.SKIPPED
            state.stages["tax"].data = {
                "skipped_reason": (
                    f"feasibility 단계 {feasibility.status.value} — 세금 산정 입력(매출·원가) 부재. "
                    "0 합성 산출 금지(무날조)."
                )
            }
            return
        fdata = feasibility.data

        taxes = compute_project_taxes(
            total_revenue=self._as_float(fdata.get("total_revenue", 0)),
            total_project_cost=self._as_float(fdata.get("total_project_cost", 0)),
            net_profit_pretax=self._as_float(fdata.get("net_profit", 0)),
            land_cost=self._as_float(fdata.get("land_cost", 0)),
            construction_cost=self._as_float(fdata.get("construction_cost", 0)),
        )

        tax_data: dict[str, Any] = {
            "acquisition_tax": taxes["acquisition_tax"],  # 취득가액(토지+건물) 기준
            "acquisition_tax_additional": taxes["acquisition_tax_additional"],  # 사업비 levies 제외 추가분
            "acquisition_tax_in_cost": taxes["acquisition_tax_in_cost"],  # 사업비에 이미 포함된 토지 취득세
            "property_tax_annual": taxes["property_tax_annual"],  # 보유세(연간)
            "transfer_tax": taxes["transfer_tax"],
            "vat": taxes["vat"],
            "total_tax": taxes["total_tax"],  # 추가취득 + 보유세 + 양도세
            # 세후 손익(헤드라인 세전 net_profit/grade와 정합되게 별도 제공).
            "net_profit_after_tax": taxes["net_profit_after_tax"],
            "profit_rate_after_tax_pct": taxes["profit_rate_after_tax_pct"],
            "grade_after_tax": taxes["grade_after_tax"],
        }

        overrides = self._stage_overrides_for(opts, "tax")
        if overrides:
            applied_overrides: dict[str, Any] = {}
            self._patch_remaining_overrides(tax_data, overrides, applied_overrides)
            if applied_overrides:
                # 구성 항목 수정 시 총액을 재합산해 정합성 유지(총액 직접 지정 시 그 값 우선).
                if "total_tax" not in applied_overrides and any(
                    k in applied_overrides
                    for k in ("acquisition_tax_additional", "property_tax_annual", "transfer_tax")
                ):
                    tax_data["total_tax"] = (
                        self._as_float(tax_data.get("acquisition_tax_additional"))
                        + self._as_float(tax_data.get("property_tax_annual"))
                        + self._as_float(tax_data.get("transfer_tax"))
                    )
                tax_data["applied_overrides"] = applied_overrides

        state.stages["tax"].data = tax_data

    async def _run_esg(self, state: PipelineState, opts: dict):
        """STEP 6: ESG — 자재-탄소DB 연동 + GRESB 스코어링 + G-SEED 예측 + 저탄소 시나리오."""
        design = state.design_to_cost or DesignToCostPayload()
        gfa = max(design.total_gfa_sqm, 1)
        building_type = design.building_type or "공동주택"

        esg_data: dict[str, Any] = {}

        # ── 1. 자재별 Embodied Carbon 상세 계산 (carbon_material_db 연동) ──
        try:
            from app.services.esg.carbon_material_db import (
                calculate_low_carbon_scenario,
                calculate_material_carbon,
                calculate_operational_carbon,
                predict_gseed_grade,
            )

            mat_result = calculate_material_carbon(building_type, gfa)
            op_result = calculate_operational_carbon(building_type, gfa, years=30)

            embodied = mat_result["total_embodied_carbon_kgCO2eq"]
            operational_30yr = op_result["total_operational_carbon_kgCO2eq"]
            total_carbon = embodied + operational_30yr
            carbon_per_sqm = total_carbon / gfa

            esg_data["embodied_carbon"] = {
                "total_kgCO2eq": embodied,
                "per_sqm_kgCO2eq": mat_result["embodied_carbon_per_sqm"],
                "category_totals": mat_result["category_totals"],
                "material_count": len(mat_result["material_breakdown"]),
                "material_breakdown": mat_result["material_breakdown"],
            }

            esg_data["operational_carbon"] = {
                "total_30yr_kgCO2eq": operational_30yr,
                "per_sqm_kgCO2eq": op_result["operational_carbon_per_sqm"],
                "annual_energy_kwh": op_result["annual_energy_kwh"],
                "annual_carbon_kgCO2eq": op_result["annual_carbon_kgCO2eq"],
                "energy_intensity_kwh_per_sqm": op_result["energy_intensity_kwh_per_sqm"],
                "grid_emission_factor": op_result["grid_emission_factor"],
                "years": 30,
            }

            esg_data["lifecycle_total"] = {
                "total_kgCO2eq": round(total_carbon, 1),
                "per_sqm_kgCO2eq": round(carbon_per_sqm, 2),
                "embodied_share_pct": round(embodied / total_carbon * 100, 1) if total_carbon > 0 else 0,
                "operational_share_pct": round(operational_30yr / total_carbon * 100, 1) if total_carbon > 0 else 0,
            }

            # ── 2. 저탄소 자재 대체 시나리오 ──
            low_carbon = calculate_low_carbon_scenario(building_type, gfa)
            esg_data["low_carbon_scenario"] = low_carbon

            # ── 3. G-SEED 등급 예측 ──
            gseed = predict_gseed_grade(building_type, carbon_per_sqm)
            esg_data["gseed_prediction"] = gseed

        except Exception as e:
            # 폴백: 기존 단순 개산 방식
            embodied_carbon_per_sqm = 350
            operational_carbon_per_sqm = 25
            embodied = gfa * embodied_carbon_per_sqm
            operational_30yr = gfa * operational_carbon_per_sqm * 30
            total_carbon = embodied + operational_30yr
            carbon_per_sqm = total_carbon / gfa

            esg_data["embodied_carbon"] = {
                "total_kgCO2eq": embodied,
                "per_sqm_kgCO2eq": embodied_carbon_per_sqm,
                "estimation_method": "fallback_flat_rate",
            }
            esg_data["operational_carbon"] = {
                "total_30yr_kgCO2eq": operational_30yr,
                "estimation_method": "fallback_flat_rate",
            }
            esg_data["lifecycle_total"] = {
                "total_kgCO2eq": total_carbon,
                "per_sqm_kgCO2eq": round(carbon_per_sqm, 1),
            }
            esg_data["_fallback_reason"] = str(e)[:200]

        # ── 4. GRESB 2025 스코어링 시뮬레이션 ──
        try:
            from app.services.esg.gresb_scoring_service import GresbScoringService

            gresb_svc = GresbScoringService()
            gresb_type_map = {
                "아파트": "apartment",
                "공동주택": "apartment",
                "다세대주택": "apartment",
                "오피스텔": "office",
                "근린생활시설": "commercial",
            }
            gresb_building_type = gresb_type_map.get(building_type, "apartment")

            # 운영 에너지/탄소 밀도를 GRESB 입력으로 전달
            op_data = esg_data.get("operational_carbon", {})
            energy_kwh_per_sqm = op_data.get("energy_intensity_kwh_per_sqm", 120.0)
            ghg_per_sqm = round(carbon_per_sqm, 1) if carbon_per_sqm else None

            gresb_result = gresb_svc.calculate_score(
                building_type=gresb_building_type,
                energy_kwh_per_sqm=energy_kwh_per_sqm,
                ghg_kg_per_sqm=ghg_per_sqm,
                has_esg_policy=False,
                has_green_cert=False,
                green_cert_level="none",
                waste_recycling_pct=0.0,
                renewable_energy_pct=0.0,
                lca_total_carbon_kg=total_carbon,
                floor_area_sqm=gfa,
            )
            esg_data["gresb"] = gresb_result
        except Exception as e:
            esg_data["gresb"] = {
                "estimated_score": min(100, max(0, int(70 - carbon_per_sqm / 50))),
                "estimation_method": "fallback",
                "error": str(e)[:200],
            }

        # 하위 호환: 기존 키 유지
        esg_data["embodied_carbon_kg"] = esg_data.get("embodied_carbon", {}).get("total_kgCO2eq", 0)
        esg_data["operational_carbon_30yr_kg"] = esg_data.get("operational_carbon", {}).get("total_30yr_kgCO2eq", 0)
        esg_data["total_lifecycle_carbon_kg"] = esg_data.get("lifecycle_total", {}).get("total_kgCO2eq", 0)
        esg_data["carbon_per_sqm_kg"] = esg_data.get("lifecycle_total", {}).get("per_sqm_kgCO2eq", 0)
        # 보고서 호환 alias
        esg_data["total_carbon_per_sqm"] = esg_data["carbon_per_sqm_kg"]
        esg_data["operational_carbon_kg"] = esg_data["operational_carbon_30yr_kg"]

        overrides = self._stage_overrides_for(opts, "esg")
        if overrides:
            applied_overrides: dict[str, Any] = {}
            self._patch_remaining_overrides(esg_data, overrides, applied_overrides)
            if applied_overrides:
                esg_data["applied_overrides"] = applied_overrides

        state.stages["esg"].data = esg_data

    async def _run_report(self, state: PipelineState, opts: dict):
        """STEP 7: 통합 보고서 생성."""
        summary: dict[str, Any] = {}
        for stage_name, stage_result in state.stages.items():
            # SKIPPED라도 복원된 이전 data가 있으면 포함한다 —
            # 재실행 시 미재계산 단계(skip)의 결과가 보고서에서 유실되는 것을 방지.
            if stage_result.status == PipelineStatus.COMPLETED or (
                stage_result.status == PipelineStatus.SKIPPED and stage_result.data
            ):
                summary[stage_name] = stage_result.data

        # 보고서 호환 alias — 일부 프론트엔드가 esg_carbon 키를 참조
        if "esg" in summary:
            summary["esg_carbon"] = summary["esg"]

        # 법규검토 요약(설계 단계 산출)을 평탄 키로 노출 — 보고서 호환
        design_stage = state.stages.get("design")
        compliance_summary = (
            (design_stage.data.get("compliance") or {}).get("summary", {})
            if design_stage else {}
        )

        # 입지 지표를 평탄 키로 노출 (infrastructure → 보고서 입지분석 섹션).
        # VWORLD POI 미수집 시 키는 생략되어 "-"로 표시된다.
        site_data = summary.get("site_analysis")
        if isinstance(site_data, dict):
            infra = site_data.get("infrastructure") or {}
            if isinstance(infra, dict):
                subway = infra.get("nearest_subway") or {}
                schools = infra.get("schools") or []
                if isinstance(subway, dict) and subway.get("distance_m") is not None:
                    site_data["distance_subway_m"] = subway.get("distance_m")
                if schools and isinstance(schools[0], dict):
                    site_data["distance_school_m"] = schools[0].get("distance_m")
                # 주변 편의시설 = 학교+병원+마트+편의점+공원+버스 총합
                amenity_keys = ("schools", "hospitals", "marts",
                                "convenience_stores", "parks", "bus_stops")
                amenity_count = sum(
                    len(infra.get(k) or []) for k in amenity_keys
                )
                if amenity_count > 0:
                    site_data["nearby_amenities"] = amenity_count
                # 접도 너비 (토지대장 도로접면 → 추정), 보고서 빈값 해결
                if infra.get("road_width_m") is not None:
                    site_data["road_width_m"] = infra["road_width_m"]
                # 입지 점수·등급 (레이더/종합평가용)
                loc_score = infra.get("location_score")
                if isinstance(loc_score, dict):
                    site_data["location_score"] = loc_score.get("total_score")
                    site_data["location_grade"] = loc_score.get("grade")
                    site_data["location_score_items"] = loc_score.get("items")
                # 상권 분석 (상업/주상복합 — 점포 밀도·업종 다양성)
                commercial = infra.get("commercial_area")
                if isinstance(commercial, dict):
                    site_data["commercial_stores"] = commercial.get("total_stores")
                    site_data["commercial_grade"] = commercial.get("grade")
                    site_data["commercial_vitality_score"] = commercial.get("vitality_score")

        # 종합평가 — 수지분석 수익률에서 파생(외부 데이터 없이 산출).
        feas = summary.get("feasibility") or {}
        overall_grade = feas.get("grade")
        profit_rate = feas.get("profit_rate_pct")
        if isinstance(profit_rate, (int, float)):
            if profit_rate >= 15:
                risk_level, recommendation = "낮음", "사업 추진 권장"
            elif profit_rate >= 0:
                risk_level, recommendation = "보통", "조건부 추진 — 분양가·원가 재검토"
            else:
                risk_level, recommendation = "높음", "사업 재검토 필요 (수익성 미달)"
        else:
            risk_level, recommendation = None, None

        state.stages["report"].data = {
            "report_type": "pipeline_summary",
            "project_address": state.address,
            "pipeline_id": state.pipeline_id,
            "summary": summary,
            "compliance_pass": compliance_summary.get("pass"),
            "compliance_fail": compliance_summary.get("fail"),
            "compliance_total": compliance_summary.get("total_checks"),
            "overall_grade": overall_grade,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "generated_at": datetime.now().isoformat(),
        }

        overrides = self._stage_overrides_for(opts, "report")
        if overrides:
            applied_overrides: dict[str, Any] = {}
            self._patch_remaining_overrides(
                state.stages["report"].data, overrides, applied_overrides
            )
            if applied_overrides:
                state.stages["report"].data["applied_overrides"] = applied_overrides
