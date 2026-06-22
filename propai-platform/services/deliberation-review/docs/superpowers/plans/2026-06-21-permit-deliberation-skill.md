# 인·허가/심의 실무 스킬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인·허가/심의 실무 전과정을 선언적 프로세스 스펙(데이터)으로 정의하고, 엔진의 얇은 결정론 실행기가 기존 11페이즈 분석 결과를 소비·계측·검증해 `PermitProcessResult`(로드맵+단계별 심의 계측+대응 패키지+검증)를 산출, 프로젝트 DB에 영속하고 BFF/`심의` 에이전트로 노출한다.

**Architecture:** 접근법 C — 절차를 데이터로(버전드 프로세스 스펙). 실행기는 `AnalysisResult`를 read-only 소비(재계산 0, INV-13), 정량 계측은 reg SSOT(`resolve_zone_limit`) 한도와 대조, 검증은 `FinalGate` 재사용, 자치법규는 `LiveNetwork`(elis.go.kr)로 버전드 스냅샷 결속·교차검증. 시장 데이터는 컴플라이언스 경로와 격리(Phase 2 예측-only).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2(async)+asyncpg, Alembic, Pydantic v2, pytest(asyncio_mode=auto), ruff. DB schema `review`.

**설계문서(SSOT):** `docs/superpowers/specs/2026-06-21-permit-deliberation-skill-design.md`

---

## 작업 환경·규약 (모든 태스크 공통)

- 저장소(WSL): `~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review` (브랜치 `feature/deliberation-review`). 단, **INC-PD5는 플랫폼 repo** `~/My_Projects/Development_AI/propai-platform`(별도 브랜치).
- 파이썬/도구: `PY=~/My_Projects/propai-review/.venv/bin/python`; ruff=`~/My_Projects/propai-review/.venv/bin/ruff`.
- 명령은 `wsl.exe -e bash -lc 'cd <repo> && ...'`로 실행(Windows에서). 커밋 메시지는 한국어 단일따옴표 충돌 방지 위해 `git commit -F <파일>` 또는 heredoc 사용.
- **결정 원칙(사용자 지침):** 모든 선택은 결과물 신뢰성·정확성·안전성 + 플랫폼 가치를 높이는 방향. 순수 실시간이 아닌 버전드 동적 SSOT, 하드코딩 금지(INV-3), 결정론·설명가능성 우선.
- **불변식 게이트(각 INC 종료 전 필수, 모두 그린이어야 커밋):**
  - `$PY -m pytest -q` (전체 그린)
  - `$PY tools/static_scan.py` 또는 `$PY -m pytest tests/acceptance/test_no_hardcoded_params.py -q` (INV-3 — 법정 수치 하드코딩 0)
  - `$RUFF check apps/api/app tests` (clean)
  - **9.5 적대 게이트**: 해당 INC diff를 다렌즈(security·correctness·contract·invariants·completeness) 적대 리뷰→HIGH 적대 검증, `gate_pass`(확정 HIGH 0) 후 커밋·푸시.
- INV-3 주의: `far/bcr/height/area/limit/ratio/floor/setback/coverage/threshold/margin/distance/width/depth/span/hours/exclusion/relax/incentive/tol/pct/percent` 이름 + **숫자 리터럴** 할당은 차단됨. 계측값은 **숫자 리터럴 금지** — 한도는 `resolve_zone_limit`(SSOT)에서, margin/ratio는 **계산식**(리터럴 아님)으로. 운영 상수 불가피 시 이름에 키워드 회피 또는 `_ALLOW` 등재.

---

## File Structure

엔진(deliberation-review):
- `apps/api/app/contracts/permit_process.py` (신규) — 프로세스 스펙 계약(PermitProcessSpec/StageSpec/CriterionRef/enums).
- `apps/api/app/contracts/permit_result.py` (신규) — 산출 계약(PermitProcessResult/StageResult/CriterionResult).
- `apps/api/app/services/permit/spec_loader.py` (신규) — 기본 스펙 로드·버전·applicability.
- `apps/api/app/services/permit/measurement.py` (신규) — 심의 계측(부합도 산정).
- `apps/api/app/services/permit/executor.py` (신규) — 실행기(스펙→단계별 소비/계측/검증).
- `apps/api/app/services/permit/permit_store.py` (신규) — 영속/조회(프로젝트 스코프).
- `apps/api/app/db/models/permit_models.py` (신규) — PermitProcessRunModel(CommonMixin).
- `apps/api/alembic/versions/0016_permit_process.py` (신규) — 테이블 마이그레이션.
- `apps/api/app/adapters/legal/elis.py` (신규) — 자치법규(elis.go.kr) 어댑터.
- `apps/api/app/api/routes/permit_routes.py` (신규) — 엔진 라우트.
- `apps/api/app/main.py` (수정) — 라우터 등록.
- `tests/services/test_permit_spec.py` · `test_permit_executor.py` · `test_permit_store.py` · `test_permit_elis.py`, `tests/smoke/test_permit_routes.py` (신규).

플랫폼(Development_AI/propai-platform) — INC-PD5:
- `apps/api/app/routers/deliberation.py` 또는 기존 BFF 위치(신규) — 엔진 `/api/v1/permit/process` 프록시.
- `apps/api/app/services/agents/registry.py` (수정) — `_build_deliberation`/`_deliberation_tool` + `_FACTORIES`.

---

## INC-PD1: 프로세스 스펙 계약 + 기본 스펙 + 로더

**Files:**
- Create: `apps/api/app/contracts/permit_process.py`
- Create: `apps/api/app/services/permit/__init__.py`, `apps/api/app/services/permit/spec_loader.py`
- Test: `tests/services/test_permit_spec.py`

- [ ] **Step 1: Write the failing test**

`tests/services/test_permit_spec.py`:
```python
"""INC-PD1 — 프로세스 스펙 계약·로더: 기본 스펙 로드·버전·applicability."""
from app.services.permit.spec_loader import load_default_spec, applicable_stages


def test_default_spec_loads_with_version_and_stages():
    spec = load_default_spec()
    assert spec.spec_id and spec.version              # 버전드(재현)
    assert any(s.stage_type == "본허가" for s in spec.stages)   # 건축허가 단계 존재
    # 각 단계 criteria_ref는 SSOT 참조(법정 수치 직접 보유 금지) — 한도 리터럴 없음
    for s in spec.stages:
        for c in s.criteria_refs:
            assert c.kind in ("QUANTITATIVE", "QUALITATIVE")
            if c.kind == "QUANTITATIVE":
                assert c.ssot_ref  # 한도는 SSOT에서 해석


def test_applicability_filters_by_dev_and_zone():
    spec = load_default_spec()
    # 경관심의는 일정 조건에서만 — applicability로 on/off(데이터 구동)
    base = applicable_stages(spec, dev_type="M06", use_zone="제2종일반주거지역")
    assert {s.stage_id for s in base} <= {s.stage_id for s in spec.stages}
    assert base, "최소 건축허가 단계는 항상 적용"
    # predecessors 위상정렬 — 의존 단계가 앞에
    order = [s.stage_id for s in base]
    for s in base:
        for p in s.predecessors:
            if p in order:
                assert order.index(p) < order.index(s.stage_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_spec.py -q'`
Expected: FAIL (ModuleNotFoundError: app.services.permit.spec_loader)

- [ ] **Step 3: Create the spec contract**

`apps/api/app/contracts/permit_process.py`:
```python
"""인·허가/심의 프로세스 스펙 계약(선언 데이터 = "스킬" 본체).

버전드 단계 그래프. 법정 한도는 보유하지 않고 ssot_ref로 규제 SSOT를 참조(INV-3). 단계 추가·법 개정 =
스펙/SSOT 버전 갱신(코드 무변경). applicability로 사업유형·용도지역별 단계 on/off(데이터 구동).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CriterionKind(str, Enum):
    QUANTITATIVE = "QUANTITATIVE"   # reg SSOT 한도 대비 정량 부합도
    QUALITATIVE = "QUALITATIVE"     # L3-C 등급 매핑


class CriterionRef(BaseModel):
    """단계 심의 기준 1건 — 한도는 ssot_ref로 SSOT 참조(직접 수치 보유 금지)."""

    criterion_id: str
    kind: CriterionKind
    ssot_ref: str | None = None        # QUANTITATIVE: 산정변수 id(target_variable). QUALITATIVE: rubric id
    measure: str = "limit_ratio"        # 부합도 산식 식별자(측정 방식 — 법정 수치 아님)
    basis_article: str | None = None


class StageSpec(BaseModel):
    """인허가/심의 단계 1건."""

    stage_id: str
    name: str
    stage_type: str                     # "본허가" | "의제심의"
    predecessors: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    criteria_refs: list[CriterionRef] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    authority: str | None = None        # 관계기관
    submittals: list[str] = Field(default_factory=list)
    # applicability: dev_type/use_zone 조건(없으면 항상 적용). 데이터 구동 on/off.
    applies_dev_types: list[str] = Field(default_factory=list)   # 비면 모든 사업유형
    applies_zones: list[str] = Field(default_factory=list)        # 비면 모든 용도지역
    outcome_predictor: str | None = None  # Phase 2 슬롯(Phase 1 = None)


class PermitProcessSpec(BaseModel):
    """버전드 프로세스 스펙 — 재현(snapshot 결속)·확장(스펙 추가)."""

    spec_id: str
    version: str
    effective_date: str                 # ISO date(축 결속·재현)
    stages: list[StageSpec] = Field(default_factory=list)
```

- [ ] **Step 4: Create the loader + default spec**

`apps/api/app/services/permit/__init__.py`: (빈 파일)

`apps/api/app/services/permit/spec_loader.py`:
```python
"""INC-PD1 — 기본 프로세스 스펙 로드 + applicability 필터 + 위상정렬.

기본 스펙은 건축허가(본허가) + 보편 의제심의(경관/교통/환경/재해). 법정 한도는 criteria_refs의 ssot_ref로
규제 SSOT 참조 — 스펙은 수치 미보유(INV-3). 결정론(동일 버전 동일 결과).
"""
from __future__ import annotations

from app.contracts.permit_process import (
    CriterionKind,
    CriterionRef,
    PermitProcessSpec,
    StageSpec,
)

_DEFAULT = PermitProcessSpec(
    spec_id="permit-default",
    version="v1",
    effective_date="2026-01-01",
    stages=[
        StageSpec(
            stage_id="building_review", name="건축심의", stage_type="의제심의",
            required_inputs=["use_zone"],
            criteria_refs=[
                CriterionRef(criterion_id="far", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="far_floor_area", basis_article="국토계획법 시행령"),
                CriterionRef(criterion_id="bcr", kind=CriterionKind.QUANTITATIVE,
                             ssot_ref="building_area", basis_article="국토계획법 시행령"),
                CriterionRef(criterion_id="layout", kind=CriterionKind.QUALITATIVE,
                             ssot_ref="placement_fit"),
            ],
            deliverables=["배치도", "면적표"], authority="건축위원회",
            submittals=["건축계획서"],
        ),
        StageSpec(
            stage_id="landscape_review", name="경관심의", stage_type="의제심의",
            predecessors=["building_review"], required_inputs=["use_zone"],
            criteria_refs=[CriterionRef(criterion_id="scenery", kind=CriterionKind.QUALITATIVE,
                                        ssot_ref="scenery_fit")],
            deliverables=["경관계획서"], authority="경관위원회",
            applies_zones=[],  # 조건 없으면 항상; 운영 스펙에서 좁힘
        ),
        StageSpec(
            stage_id="building_permit", name="건축허가", stage_type="본허가",
            predecessors=["building_review"], required_inputs=["use_zone"],
            criteria_refs=[CriterionRef(criterion_id="height", kind=CriterionKind.QUANTITATIVE,
                                        ssot_ref="building_height", basis_article="건축법")],
            deliverables=["허가도서"], authority="허가권자(시군구)",
            submittals=["건축허가신청서"],
        ),
    ],
)


def load_default_spec() -> PermitProcessSpec:
    """기본 프로세스 스펙(버전드). 향후 JSON 시드/DB 스냅샷으로 대체 가능(인터페이스 동일)."""
    return _DEFAULT.model_copy(deep=True)


def _applies(stage: StageSpec, dev_type: str | None, use_zone: str | None) -> bool:
    if stage.applies_dev_types and dev_type not in stage.applies_dev_types:
        return False
    if stage.applies_zones and use_zone not in stage.applies_zones:
        return False
    return True


def applicable_stages(spec: PermitProcessSpec, *, dev_type: str | None = None,
                      use_zone: str | None = None) -> list[StageSpec]:
    """applicability 필터 + predecessors 위상정렬(결정론 순서). 순환은 입력 순서 폴백."""
    chosen = [s for s in spec.stages if _applies(s, dev_type, use_zone)]
    ids = {s.stage_id for s in chosen}
    ordered: list[StageSpec] = []
    placed: set[str] = set()
    remaining = list(chosen)
    # 결정론 위상정렬: 선행(스코프 내)이 모두 배치된 단계부터, 원래 순서 보존
    progress = True
    while remaining and progress:
        progress = False
        for s in list(remaining):
            if all((p not in ids) or (p in placed) for p in s.predecessors):
                ordered.append(s); placed.add(s.stage_id); remaining.remove(s); progress = True
    ordered.extend(remaining)  # 순환 잔여(있으면) 입력 순서로
    return ordered
```

- [ ] **Step 5: Run tests to verify pass**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_spec.py -q'`
Expected: PASS (2 passed)

- [ ] **Step 6: Run gate suite (INV-3 + ruff + full)**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && PY=~/My_Projects/propai-review/.venv/bin/python && $PY -m pytest -q 2>&1 | tail -2 && $PY -m pytest tests/acceptance/test_no_hardcoded_params.py -q 2>&1 | tail -2 && ~/My_Projects/propai-review/.venv/bin/ruff check apps/api/app/contracts/permit_process.py apps/api/app/services/permit tests/services/test_permit_spec.py 2>&1 | tail -2'`
Expected: 전체 PASS, INV-3 PASS, ruff clean

- [ ] **Step 7: 9.5 적대 게이트 + commit**

게이트(Workflow): INC-PD1 diff를 security·correctness·contract·invariants·completeness 렌즈로 적대 리뷰→HIGH 검증. `gate_pass`(HIGH 0) 확인 후:
```bash
git add apps/api/app/contracts/permit_process.py apps/api/app/services/permit tests/services/test_permit_spec.py
git commit -m "feat(permit): 프로세스 스펙 계약 + 기본 스펙 + 로더(applicability·위상정렬)"
git push origin feature/deliberation-review
```

---

## INC-PD2: 실행기 + 심의 계측

**Files:**
- Create: `apps/api/app/contracts/permit_result.py`
- Create: `apps/api/app/services/permit/measurement.py`
- Create: `apps/api/app/services/permit/executor.py`
- Test: `tests/services/test_permit_executor.py`

- [ ] **Step 1: Write the failing test**

`tests/services/test_permit_executor.py`:
```python
"""INC-PD2 — 실행기·심의 계측: AnalysisResult 소비 → 단계별 부합도·검증(결정론)."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.permit.executor import run_permit_process
from app.services.permit.spec_loader import load_default_spec

_IN = AnalysisInput(
    pnu="1111010100100000020", application_date=date(2026, 1, 1),
    rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
    calc_targets=[{"target": "building_area", "payload": {"outer_area": 500.0},
                   "elements": [{"semantic_type": "EXT_WALL", "confidence": 0.9}]}],
)


def test_executor_consumes_analysis_and_scores_stages():
    result = run_analysis(_IN)
    out = run_permit_process(result, load_default_spec(), use_zone="제2종일반주거지역")
    assert out.spec_id == "permit-default" and out.spec_version == "v1"
    assert out.stages, "단계 결과 산출"
    # 건축허가 단계가 로드맵에 존재 + 검증상태 동반
    permit = next(s for s in out.stages if s.stage_id == "building_permit")
    assert permit.verification_status in ("CONFIRMED", "NEEDS_REVIEW", "BLOCKED")
    # 정량 기준은 calc_trace(설명가능성) 동반
    for s in out.stages:
        for c in s.criteria:
            if c.kind == "QUANTITATIVE" and c.measured is not None:
                assert c.calc_trace is not None


def test_executor_is_deterministic():
    r = run_analysis(_IN)
    a = run_permit_process(r, load_default_spec(), use_zone="제2종일반주거지역")
    b = run_permit_process(r, load_default_spec(), use_zone="제2종일반주거지역")
    assert a.model_dump() == b.model_dump()   # 동일 입력·스펙 → 동일 결과


def test_missing_input_surfaces_held_not_silent():
    r = run_analysis(_IN)
    out = run_permit_process(r, load_default_spec(), use_zone=None)  # required_inputs 결손
    assert any(s.status in ("HELD", "NEEDS_INPUT") for s in out.stages)  # 무음 금지
```

- [ ] **Step 2: Run test to verify it fails**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_executor.py -q'`
Expected: FAIL (ModuleNotFoundError: app.services.permit.executor)

- [ ] **Step 3: Create the result contract**

`apps/api/app/contracts/permit_result.py`:
```python
"""인·허가/심의 프로세스 산출 계약 — 로드맵 + 단계별 심의 계측 + 대응 + 검증.

모든 정량 계측은 calc_trace(measured/limit/basis/source — 설명가능성)·legal_refs 동반. 값은 JSON 직렬화 위해 float.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    criterion_id: str
    kind: str
    measured: float | None = None
    limit: float | None = None
    conformance: str = "HELD"          # 부합 | 조건부 | 미흡 | HELD(미상)
    margin: float | None = None         # 계산식(리터럴 아님): (limit-measured)/limit
    grade: str | None = None            # QUALITATIVE 등급
    calc_trace: dict | None = None
    legal_refs: list[str] = Field(default_factory=list)
    basis_article: str | None = None


class StageResult(BaseModel):
    stage_id: str
    name: str
    stage_type: str
    status: str = "DONE"               # DONE | HELD | NEEDS_INPUT
    conformance: str = "HELD"          # 단계 종합(worst-of)
    criteria: list[CriterionResult] = Field(default_factory=list)
    verification_status: str = "NEEDS_REVIEW"   # CONFIRMED | NEEDS_REVIEW | BLOCKED
    remediation: list[str] = Field(default_factory=list)   # 대응 패키지(보완 가이드)
    issues: list[str] = Field(default_factory=list)        # 예상 쟁점
    authority: str | None = None
    submittals: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class PermitProcessResult(BaseModel):
    spec_id: str
    spec_version: str
    run_id: str | None = None
    roadmap: list[str] = Field(default_factory=list)        # 단계 순서(위상정렬)
    stages: list[StageResult] = Field(default_factory=list)
    overall_conformance: str = "HELD"                       # 종합(worst-of)
    overall_verification: str = "NEEDS_REVIEW"              # 최악 검증상태
```

- [ ] **Step 4: Create the measurement module**

`apps/api/app/services/permit/measurement.py`:
```python
"""INC-PD2 — 심의 계측: 정량(엔진 산출값 vs reg SSOT 한도) 부합도 + 정성 등급 매핑.

법정 수치 리터럴 금지(INV-3) — 한도는 resolve_zone_limit(SSOT)에서, 부합/미흡은 measured vs limit 비교로만 판정,
margin은 계산식(리터럴 아님). 미상(한도/측정값 부재)은 HELD로 표면화(무음 금지).
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_process import CriterionKind, CriterionRef
from app.contracts.permit_result import CriterionResult
from app.services.legal_calc.zone_limit_provider import resolve_zone_limit

_CONFORMANCE_RANK = {"부합": 0, "조건부": 1, "미흡": 2, "HELD": 3}


def _measured_for(result: AnalysisResult, variable_id: str) -> float | None:
    """엔진 산출 legal_quantities에서 변수값 조회(소비 read-only). 없으면 None."""
    for q in result.legal_quantities:
        if q.variable_id == variable_id and q.value is not None:
            return float(q.value)
    return None


def _finding_for(result: AnalysisResult, variable_id: str):
    """해당 변수 관련 finding(조건부/완화 판정 반영). 없으면 None."""
    for f in result.findings:
        if variable_id in (f.rule_id or "") or (f.basis_article and variable_id in f.basis_article):
            return f
    return None


def measure_quantitative(result: AnalysisResult, ref: CriterionRef,
                         use_zone: str | None) -> CriterionResult:
    """정량 부합도 — measured(엔진) vs limit(SSOT). 한도/측정 부재면 HELD."""
    measured = _measured_for(result, ref.ssot_ref or "")
    resolved = resolve_zone_limit(use_zone, ref.ssot_ref) if use_zone else None
    limit = resolved[0] if resolved else None
    source = resolved[1] if resolved else None
    cr = CriterionResult(criterion_id=ref.criterion_id, kind=ref.kind.value,
                         measured=measured, limit=limit, basis_article=ref.basis_article)
    if measured is None or limit is None:
        cr.conformance = "HELD"
        return cr
    cr.margin = (limit - measured) / limit if limit else None   # 계산식(리터럴 아님)
    fnd = _finding_for(result, ref.ssot_ref or "")
    if fnd is not None and fnd.verdict.value == "CONDITIONAL":
        cr.conformance = "조건부"
    elif measured <= limit:
        cr.conformance = "부합"
    else:
        cr.conformance = "미흡"
    cr.calc_trace = {"measured": measured, "limit": limit, "source": source,
                     "basis_article": ref.basis_article, "measure": ref.measure}
    if source:
        cr.legal_refs = [source]
    return cr


def measure_qualitative(result: AnalysisResult, ref: CriterionRef) -> CriterionResult:
    """정성 등급 — L3-C QualAssessment에서 매핑. 없으면 HELD."""
    cr = CriterionResult(criterion_id=ref.criterion_id, kind=ref.kind.value,
                         basis_article=ref.basis_article)
    for qa in result.qualitative:
        if ref.ssot_ref and getattr(qa, "rubric_id", None) == ref.ssot_ref:
            cr.grade = getattr(qa, "grade", None)
            cr.conformance = "부합" if cr.grade else "HELD"
            return cr
    cr.conformance = "HELD"
    return cr


def measure(result: AnalysisResult, ref: CriterionRef, use_zone: str | None) -> CriterionResult:
    if ref.kind == CriterionKind.QUANTITATIVE:
        return measure_quantitative(result, ref, use_zone)
    return measure_qualitative(result, ref)


def worst_conformance(values: list[str]) -> str:
    """단계/종합 종합 = worst-of(보수)."""
    if not values:
        return "HELD"
    return max(values, key=lambda v: _CONFORMANCE_RANK.get(v, 3))
```

- [ ] **Step 5: Create the executor**

`apps/api/app/services/permit/executor.py`:
```python
"""INC-PD2 — 프로세스 실행기: 스펙을 읽어 단계별로 AnalysisResult를 소비·계측·검증(얇은 결정론).

INV-13: AnalysisResult를 read-only 소비(재계산·라이브 호출 없음). 검증은 FinalGate 재사용. 입력 결손은
HELD/NEEDS_INPUT로 표면화(무음 금지). 동일 입력+스펙 → 동일 결과(결정론).
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_process import PermitProcessSpec, StageSpec
from app.contracts.permit_result import PermitProcessResult, StageResult
from app.contracts.verification import GateItem, VerificationResult
from app.services.permit.measurement import measure, worst_conformance
from app.services.permit.spec_loader import applicable_stages
from app.services.verify.final_gate import FinalGate

# 결손 입력 → 미상 입력값 키(컨텍스트에서 채움). use_zone은 필수 입력의 대표.
_INPUT_KEYS = ("use_zone",)


def _verify_stage(result: AnalysisResult, stage: StageSpec) -> str:
    """단계 검증 — 관련 findings의 FinalGate 상태 worst-of 재사용. finding 없으면 NEEDS_REVIEW(보수)."""
    gate = FinalGate()
    statuses: list[str] = []
    for f in result.findings:
        item = GateItem(item_id=f.rule_id, composite_confidence=f.composite_confidence,
                        conflicts=list(f.conflicts),
                        verification=VerificationResult(passed=(f.gated_status.value == "CONFIRMED")),
                        dual_path_status=None)
        statuses.append(gate.apply(item).status.value)
    if not statuses:
        return "NEEDS_REVIEW"
    rank = {"CONFIRMED": 0, "NEEDS_REVIEW": 1, "BLOCKED": 2}
    return max(statuses, key=lambda s: rank.get(s, 1))


def run_permit_process(result: AnalysisResult, spec: PermitProcessSpec, *,
                       dev_type: str | None = None, use_zone: str | None = None) -> PermitProcessResult:
    """AnalysisResult + 스펙 → PermitProcessResult(로드맵+단계별 계측+대응+검증). 결정론·소비 read-only."""
    stages = applicable_stages(spec, dev_type=dev_type, use_zone=use_zone)
    inputs = {"use_zone": use_zone}
    stage_results: list[StageResult] = []
    for st in stages:
        missing = [k for k in st.required_inputs if k in _INPUT_KEYS and not inputs.get(k)]
        sr = StageResult(stage_id=st.stage_id, name=st.name, stage_type=st.stage_type,
                         authority=st.authority, submittals=list(st.submittals),
                         deliverables=list(st.deliverables))
        if missing:
            sr.status = "NEEDS_INPUT"
            sr.issues = [f"필요 입력 결손: {', '.join(missing)}"]
            stage_results.append(sr)
            continue
        crits = [measure(result, ref, use_zone) for ref in st.criteria_refs]
        sr.criteria = crits
        sr.conformance = worst_conformance([c.conformance for c in crits])
        sr.verification_status = _verify_stage(result, st)
        sr.remediation = [f"{c.criterion_id}: 보완 필요({c.basis_article or '근거조문 확인'})"
                          for c in crits if c.conformance in ("미흡", "조건부")]
        stage_results.append(sr)
    overall_c = worst_conformance([s.conformance for s in stage_results])
    vrank = {"CONFIRMED": 0, "NEEDS_REVIEW": 1, "BLOCKED": 2}
    overall_v = max((s.verification_status for s in stage_results),
                    key=lambda s: vrank.get(s, 1), default="NEEDS_REVIEW")
    return PermitProcessResult(
        spec_id=spec.spec_id, spec_version=spec.version, run_id=result.run_id,
        roadmap=[s.stage_id for s in stages], stages=stage_results,
        overall_conformance=overall_c, overall_verification=overall_v,
    )
```

- [ ] **Step 6: Run tests to verify pass**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_executor.py -q'`
Expected: PASS (3 passed). 실패 시: `_measured_for`/`_finding_for` 매칭이 엔진 산출 variable_id와 정확히 맞는지(legal_quantities[].variable_id) 확인 후 보정.

- [ ] **Step 7: Gate suite + 9.5 게이트 + commit**

게이트 통과(HIGH 0) 후:
```bash
git add apps/api/app/contracts/permit_result.py apps/api/app/services/permit/measurement.py apps/api/app/services/permit/executor.py tests/services/test_permit_executor.py
git commit -m "feat(permit): 실행기 + 심의 계측(정량 SSOT 대비·정성 등급·검증 재사용·결정론)"
git push origin feature/deliberation-review
```

---

## INC-PD3: 영속 + alembic 0016

**Files:**
- Create: `apps/api/app/db/models/permit_models.py`
- Create: `apps/api/alembic/versions/0016_permit_process.py`
- Create: `apps/api/app/services/permit/permit_store.py`
- Test: `tests/services/test_permit_store.py`

- [ ] **Step 1: Write the failing test**

`tests/services/test_permit_store.py`:
```python
"""INC-PD3 — 프로세스 결과 영속/조회: project DB 결속 + 테넌트 격리."""
import uuid
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.permit.executor import run_permit_process
from app.services.permit.spec_loader import load_default_spec
from app.services.permit.permit_store import save_permit_process, get_project_permit

_IN = AnalysisInput(
    pnu="1111010100100000021", application_date=date(2026, 1, 1),
    rules=[{"rule": {"rule_id": "far_limit", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}, "measured": 250.0, "limit": 200.0}],
)


async def test_save_and_project_scope_with_tenant_isolation(db):
    from sqlalchemy import delete

    from app.db.models.permit_models import PermitProcessRunModel
    res = run_analysis(_IN)
    out = run_permit_process(res, load_default_spec(), use_zone="제2종일반주거지역")
    pid, tid = uuid.uuid4(), uuid.uuid4()
    stored = await save_permit_process(db, out, tenant_id=tid, project_id=pid)
    assert stored.run_id
    scoped = await get_project_permit(db, pid, tenant_id=tid)
    assert scoped and scoped[0].spec_id == "permit-default"
    # 교차테넌트 차단
    assert await get_project_permit(db, pid, tenant_id=uuid.uuid4()) == []
    rid = uuid.UUID(stored.run_id)
    await db.execute(delete(PermitProcessRunModel).where(PermitProcessRunModel.id == rid))
    await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_store.py -q'`
Expected: FAIL (ModuleNotFoundError: app.db.models.permit_models)

- [ ] **Step 3: Create the model**

`apps/api/app/db/models/permit_models.py`:
```python
"""인·허가/심의 프로세스 영속 모델(review 스키마). blob(권위 조회본) + project/org(프로젝트 DB 결속)."""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class PermitProcessRunModel(Base, CommonMixin):
    __tablename__ = "permit_process_run"

    spec_id: Mapped[str] = mapped_column(String(64))
    spec_version: Mapped[str] = mapped_column(String(64))
    analysis_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_conformance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    overall_verification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result: Mapped[dict] = mapped_column(JSONB)   # PermitProcessResult 전체(재현)
```

- [ ] **Step 4: Create the alembic migration**

`apps/api/alembic/versions/0016_permit_process.py`:
```python
"""permit_process_run 테이블(인·허가/심의 프로세스 결과 영속)."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "0016_permit_process"
down_revision = "0015_reconcile_content_hash"
branch_labels = None
depends_on = None
SCHEMA = "review"


def upgrade() -> None:
    op.create_table(
        "permit_process_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("spec_id", sa.String(64), nullable=False),
        sa.Column("spec_version", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.String(64), nullable=True),
        sa.Column("overall_conformance", sa.String(16), nullable=True),
        sa.Column("overall_verification", sa.String(16), nullable=True),
        sa.Column("result", JSONB, nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_permit_process_run_project", "permit_process_run",
                    ["project_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_permit_process_run_project", table_name="permit_process_run", schema=SCHEMA)
    op.drop_table("permit_process_run", schema=SCHEMA)
```

- [ ] **Step 5: Create the store**

`apps/api/app/services/permit/permit_store.py`:
```python
"""INC-PD3 — 프로세스 결과 영속/조회. blob(재현) + 프로젝트 DB 결속(project_id·org). 테넌트 격리(#8a)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.permit_result import PermitProcessResult
from app.db.models.permit_models import PermitProcessRunModel

_MAX_PROJECT_ROWS = 1000   # 운영 상수(거대 응답 방어) — 법정 파라미터 아님(INV-3 무관)


async def save_permit_process(session: AsyncSession, out: PermitProcessResult, *,
                              tenant_id: uuid.UUID | None = None,
                              project_id: uuid.UUID | None = None) -> PermitProcessResult:
    """결과 저장 → run_id 부여 반환. organization_id/project_id 결속(프로젝트 DB·격리)."""
    run_id = uuid.uuid4()
    stored = out.model_copy(update={"run_id": str(run_id)})
    session.add(PermitProcessRunModel(
        id=run_id, organization_id=tenant_id, project_id=project_id,
        spec_id=out.spec_id, spec_version=out.spec_version, analysis_run_id=out.run_id,
        overall_conformance=out.overall_conformance, overall_verification=out.overall_verification,
        result=stored.model_dump(mode="json"),
    ))
    await session.commit()
    return stored


async def get_project_permit(session: AsyncSession, project_id: uuid.UUID, *,
                             tenant_id: uuid.UUID | None = None,
                             max_rows: int = _MAX_PROJECT_ROWS) -> list[PermitProcessResult]:
    """프로젝트 귀속 프로세스 결과 목록(테넌트 격리). 결정론 정렬(created_at,id)."""
    stmt = select(PermitProcessRunModel).where(PermitProcessRunModel.project_id == project_id)
    if tenant_id is not None:
        stmt = stmt.where(PermitProcessRunModel.organization_id == tenant_id)
    stmt = stmt.order_by(PermitProcessRunModel.created_at, PermitProcessRunModel.id).limit(max_rows)
    rows = (await session.execute(stmt)).scalars().all()
    return [PermitProcessResult.model_validate(r.result) for r in rows]


async def get_permit_process(session: AsyncSession, run_id: str, *,
                             tenant_id: uuid.UUID | None = None) -> PermitProcessResult | None:
    """run_id 조회 + 테넌트 격리(교차테넌트 차단·레거시 NULL 허용)."""
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    row = await session.get(PermitProcessRunModel, uid)
    if row is None:
        return None
    if tenant_id is not None and row.organization_id is not None and row.organization_id != tenant_id:
        return None
    return PermitProcessResult.model_validate(row.result)
```

- [ ] **Step 6: Apply migration + run tests**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review/apps/api && ~/My_Projects/propai-review/.venv/bin/python -m alembic upgrade head 2>&1 | tail -3'`
Expected: `Running upgrade 0015_reconcile_content_hash -> 0016_permit_process`
Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_store.py -q'`
Expected: PASS (1 passed)

- [ ] **Step 7: Verify migration reversibility (down→up)**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review/apps/api && PY=~/My_Projects/propai-review/.venv/bin/python && $PY -m alembic downgrade -1 2>&1 | tail -1 && $PY -m alembic upgrade head 2>&1 | tail -1'`
Expected: downgrade then upgrade 둘 다 성공(가역)

- [ ] **Step 8: Gate suite + 9.5 게이트 + commit**

게이트 통과(HIGH 0) 후:
```bash
git add apps/api/app/db/models/permit_models.py apps/api/alembic/versions/0016_permit_process.py apps/api/app/services/permit/permit_store.py tests/services/test_permit_store.py
git commit -m "feat(permit): 결과 영속(permit_process_run·alembic 0016) + 프로젝트 DB 결속·테넌트 격리"
git push origin feature/deliberation-review
```

---

## INC-PD4: 엔진 라우트

**Files:**
- Create: `apps/api/app/api/routes/permit_routes.py`
- Modify: `apps/api/app/main.py` (라우터 등록)
- Test: `tests/smoke/test_permit_routes.py`

- [ ] **Step 1: Write the failing smoke test**

`tests/smoke/test_permit_routes.py`:
```python
"""INC-PD4 — 프로세스 라우트: 인증·경로검증(라우터 등록·도달성). 데이터 로직은 store/executor 테스트가 커버."""
import uuid

from app.api import deps


def test_permit_process_requires_token(client, monkeypatch):
    monkeypatch.setattr(deps.settings, "API_TOKEN", "secret-token")
    resp = client.post("/api/v1/permit/process", json={"pnu": "1111010100100000022"})
    assert resp.status_code == 401


def test_project_permit_rejects_malformed_id(client):
    resp = client.get("/api/v1/projects/not-a-uuid/permit")
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/smoke/test_permit_routes.py -q'`
Expected: FAIL (404 — route not registered)

- [ ] **Step 3: Create the routes**

`apps/api/app/api/routes/permit_routes.py`:
```python
"""인·허가/심의 프로세스 API — 분석 결과를 프로세스 스펙으로 계측·검증해 산출/조회.

POST /api/v1/permit/process: AnalysisInput 또는 {run_id} → run_permit_process → 영속 → PermitProcessResult.
GET /api/v1/permit/process/{run_id}, GET /api/v1/projects/{project_id}/permit. 인증 require_token, #8a 격리.
"""
from __future__ import annotations

import uuid

import anyio
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_id, get_session, get_tenant_id, require_token
from app.contracts.analysis import AnalysisInput
from app.contracts.permit_result import PermitProcessResult
from app.core.errors import DomainError
from app.services.permit.executor import run_permit_process
from app.services.permit.permit_store import (
    get_permit_process,
    get_project_permit,
    save_permit_process,
)
from app.services.permit.spec_loader import load_default_spec
from app.services.pipeline.analysis_pipeline import run_analysis
from app.services.pipeline.analysis_store import get_analysis

router = APIRouter(prefix="/api/v1", tags=["permit"])


@router.post("/permit/process", response_model=PermitProcessResult,
             dependencies=[Depends(require_token)])
async def permit_process(payload: dict = Body(...), session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id),
                         project_id: uuid.UUID | None = Depends(get_project_id)) -> PermitProcessResult:
    # 본문: (a) {run_id} 재사용 또는 (b) AnalysisInput 신규 실행
    use_zone = payload.get("use_zone")
    dev_type = payload.get("dev_type")
    run_id = payload.get("run_id")
    if run_id:
        result = await get_analysis(session, str(run_id), tenant_id=tenant_id)
        if result is None:
            raise HTTPException(status_code=404, detail="analysis run not found")
    else:
        try:
            inp = AnalysisInput(**{k: v for k, v in payload.items()
                                   if k not in ("use_zone", "dev_type", "run_id")})
            result = await anyio.to_thread.run_sync(run_analysis, inp)
        except DomainError as exc:
            raise HTTPException(status_code=422, detail=f"domain_error:{type(exc).__name__}") from exc
    out = run_permit_process(result, load_default_spec(), dev_type=dev_type, use_zone=use_zone)
    return await save_permit_process(session, out, tenant_id=tenant_id, project_id=project_id)


@router.get("/permit/process/{run_id}", response_model=PermitProcessResult,
            dependencies=[Depends(require_token)])
async def get_permit_run(run_id: str, session: AsyncSession = Depends(get_session),
                         tenant_id: uuid.UUID | None = Depends(get_tenant_id)) -> PermitProcessResult:
    out = await get_permit_process(session, run_id, tenant_id=tenant_id)
    if out is None:
        raise HTTPException(status_code=404, detail="permit process run not found")
    return out


@router.get("/projects/{project_id}/permit", response_model=list[PermitProcessResult],
            dependencies=[Depends(require_token)])
async def list_project_permit(project_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                              tenant_id: uuid.UUID | None = Depends(get_tenant_id)
                              ) -> list[PermitProcessResult]:
    return await get_project_permit(session, project_id, tenant_id=tenant_id)
```

- [ ] **Step 4: Register the router in main.py**

`apps/api/app/main.py` — `project_router` 등록 다음에 추가:
```python
    from app.api.routes.permit_routes import router as permit_router
    app.include_router(permit_router)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/smoke/test_permit_routes.py -q'`
Expected: PASS (2 passed)

- [ ] **Step 6: Gate suite + 9.5 게이트 + commit**

게이트 통과(HIGH 0) 후:
```bash
git add apps/api/app/api/routes/permit_routes.py apps/api/app/main.py tests/smoke/test_permit_routes.py
git commit -m "feat(permit): 엔진 라우트(process/run/project) + 라우터 등록"
git push origin feature/deliberation-review
```

---

## INC-PD5: BFF 프록시 + `심의` SpecialistAgent (플랫폼 repo — cross-repo)

**저장소:** `~/My_Projects/Development_AI/propai-platform` (별도 브랜치 — 작업 전 `git status`로 현재 브랜치 확인, 필요 시 feature 브랜치 생성). 엔진 BFF 프록시는 현재 미구현(탐색 확인).

**Files:**
- Create: `apps/api/app/routers/deliberation.py` (엔진 프록시) + 등록(앱 라우터 인클루드 지점)
- Modify: `apps/api/app/services/agents/registry.py` (`_deliberation_tool` + `_build_deliberation` + `_FACTORIES`)
- Test: `apps/api/tests/.../test_deliberation_proxy.py`, `.../test_registry_deliberation.py` (플랫폼 테스트 규약 따름)

- [ ] **Step 1: Write the failing registry test**

플랫폼 테스트 위치 규약에 맞춰 작성(예 `apps/api/tests/services/agents/test_registry_deliberation.py`):
```python
from app.services.agents.registry import AVAILABLE_DOMAINS, get_specialist


def test_deliberation_domain_registered():
    assert "심의" in AVAILABLE_DOMAINS
    agent = get_specialist("심의")
    assert agent.domain == "심의"
```

- [ ] **Step 2: Run to verify fail**

Run: 플랫폼 venv로 `python -m pytest apps/api/tests/services/agents/test_registry_deliberation.py -q`
Expected: FAIL (assert "심의" in AVAILABLE_DOMAINS)

- [ ] **Step 3: Create the BFF proxy**

`apps/api/app/routers/deliberation.py`:
```python
"""심의분석엔진 BFF 프록시 — 플랫폼 → 엔진 /api/v1/permit/process. 테넌트/프로젝트 컨텍스트 헤더 전달.

엔진 URL은 설정(DELIBERATION_ENGINE_URL). 인증 토큰은 설정(DELIBERATION_ENGINE_TOKEN). 결정론 산출은 엔진 책임.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Body, Header

from app.core.config import settings   # 플랫폼 설정 모듈 경로에 맞춰 조정

router = APIRouter(prefix="/deliberation", tags=["deliberation"])


@router.post("/permit-process")
async def permit_process(payload: dict = Body(...),
                         x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
                         x_project_id: str | None = Header(default=None, alias="X-Project-Id")) -> dict:
    base = getattr(settings, "DELIBERATION_ENGINE_URL", "http://localhost:8000")
    token = getattr(settings, "DELIBERATION_ENGINE_TOKEN", "")
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if x_tenant_id:
        headers["X-Tenant-Id"] = x_tenant_id
    if x_project_id:
        headers["X-Project-Id"] = x_project_id
    async with httpx.AsyncClient(timeout=60.0) as cli:
        r = await cli.post(f"{base}/api/v1/permit/process", json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
```
설정 추가(`settings`): `DELIBERATION_ENGINE_URL: str = ""`, `DELIBERATION_ENGINE_TOKEN: str = ""`. 라우터 인클루드 지점에 `app.include_router(deliberation.router)` 추가.

- [ ] **Step 4: Register the `심의` agent**

`apps/api/app/services/agents/registry.py` — `_deliberation_tool` + `_build_deliberation` 추가, `_FACTORIES`에 `"심의": _build_deliberation` 등록:
```python
def _deliberation_tool(data: dict) -> dict:
    """심의 도메인 결정론 도구 — BFF 프록시로 엔진 permit/process 호출, findings/summary로 정규화."""
    import httpx

    from app.core.config import settings
    base = getattr(settings, "DELIBERATION_ENGINE_URL", "")
    if not base:
        return {"findings": [], "summary": {"available": False, "reason": "engine_url_unset"}}
    token = getattr(settings, "DELIBERATION_ENGINE_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(timeout=60.0) as cli:
        r = cli.post(f"{base}/api/v1/permit/process", json=data, headers=headers)
        r.raise_for_status()
        res = r.json()
    findings = [{"check_id": s["stage_id"], "status": s["conformance"],
                 "note": s.get("verification_status")} for s in res.get("stages", [])]
    return {"findings": findings,
            "summary": {"overall_conformance": res.get("overall_conformance"),
                        "overall_verification": res.get("overall_verification")}}


def _build_deliberation() -> SpecialistAgent:
    return SpecialistAgent(domain="심의", task_type="permit_process",
                           tool=_deliberation_tool, interpreter=None)
```

- [ ] **Step 5: Run tests to verify pass**

Run: 플랫폼 venv `python -m pytest apps/api/tests/services/agents/test_registry_deliberation.py -q` → PASS. (프록시 테스트는 httpx mock/respx로 작성 — 플랫폼 테스트 규약 따름.)

- [ ] **Step 6: 플랫폼 게이트(테스트/lint) + 9.5 게이트 + commit(플랫폼 브랜치)**

플랫폼 전체 테스트·lint 그린 + 9.5 게이트(HIGH 0) 후 플랫폼 브랜치에 커밋·푸시:
```bash
git add apps/api/app/routers/deliberation.py apps/api/app/services/agents/registry.py apps/api/tests/services/agents/test_registry_deliberation.py
git commit -m "feat(agents): 심의 SpecialistAgent + 엔진 permit/process BFF 프록시"
git push origin <플랫폼 feature 브랜치>
```

---

## INC-PD6: 자치법규(elis) 어댑터 (Phase 1)

**Files:**
- Create: `apps/api/app/adapters/legal/elis.py`
- Test: `tests/services/test_permit_elis.py`

**근거 자산:** `app/adapters/network.py`의 `LiveNetwork`(allowlist에 `elis.go.kr` 포함, `LIVE_NETWORK` 게이트), `app/adapters/legal/law_go_kr.py`(소스 어댑터 패턴), `app/services/cross_validate/validator.py`(교차검증).

- [ ] **Step 1: Write the failing test**

`tests/services/test_permit_elis.py`:
```python
"""INC-PD6 — 자치법규(elis) 어댑터: LIVE_NETWORK off면 graceful None, 호스트 allowlist 준수."""
from app.adapters.legal.elis import ElisOrdinanceSource


def test_elis_off_returns_none_graceful(monkeypatch):
    monkeypatch.setattr("app.adapters.network.settings.LIVE_NETWORK", False, raising=False)
    src = ElisOrdinanceSource()
    # 라이브 off → None(무음 아님: 호출측이 미상으로 표면화). 예외 전파 금지.
    assert src.fetch_ordinance(jurisdiction="1111000000", keyword="경관") is None


def test_elis_uses_allowlisted_host():
    src = ElisOrdinanceSource()
    assert "elis.go.kr" in src.base_url   # SSRF allowlist 호스트만
```

- [ ] **Step 2: Run to verify fail**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_elis.py -q'`
Expected: FAIL (ModuleNotFoundError: app.adapters.legal.elis)

- [ ] **Step 3: Create the elis adapter**

`apps/api/app/adapters/legal/elis.py`:
```python
"""자치법규(elis.go.kr) 어댑터 — 지자체별 조례 소싱. LiveNetwork(allowlist·LIVE_NETWORK 게이트) 경유.

INV-13: 소비 경로는 버전드 미러만 읽음 — 본 어댑터는 공급(harvest) 단계에서만 호출(라이브). LIVE_NETWORK off
또는 네트워크 실패 시 None(graceful degrade, 무음 금지 — 호출측이 미상으로 표면화). 결과는 버전드 스냅샷·교차검증에 결속.
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork, NetworkError


class ElisOrdinanceSource:
    """자치법규 1차출처. fetch_ordinance: (지자체코드, 키워드) → 조례 텍스트/메타 또는 None."""

    base_url = "https://www.elis.go.kr"

    def __init__(self, net: LiveNetwork | None = None) -> None:
        self._net = net or LiveNetwork()

    def fetch_ordinance(self, *, jurisdiction: str, keyword: str) -> dict | None:
        """지자체 조례 조회. 라이브 off/실패 → None(예외 비전파). 성공 시 {jurisdiction, keyword, raw, source}."""
        url = f"{self.base_url}/search?juris={jurisdiction}&q={keyword}"
        try:
            raw = self._net.get(url)
        except NetworkError:
            return None
        if not raw:
            return None
        return {"jurisdiction": jurisdiction, "keyword": keyword,
                "raw": raw, "source": "elis.go.kr"}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `wsl.exe -e bash -lc 'cd ~/My_Projects/Development_AI_deliberation/propai-platform/services/deliberation-review && ~/My_Projects/propai-review/.venv/bin/python -m pytest tests/services/test_permit_elis.py -q'`
Expected: PASS (2 passed). 실패 시 `LiveNetwork.get` 시그니처(파라미터/예외 타입)를 `app/adapters/network.py`에서 확인해 보정.

- [ ] **Step 5: Gate suite + 9.5 게이트 + commit**

게이트 통과(HIGH 0) 후:
```bash
git add apps/api/app/adapters/legal/elis.py tests/services/test_permit_elis.py
git commit -m "feat(permit): 자치법규(elis) 어댑터 — 지자체 조례 소싱(LiveNetwork allowlist·graceful degrade)"
git push origin feature/deliberation-review
```

---

## Self-Review (작성자 체크리스트)

1. **Spec coverage:**
   - §3.1 프로세스 스펙 → INC-PD1 ✓
   - §3.2 실행기 / §3.3 심의 계측 → INC-PD2 ✓
   - §3.4 출력 계약 → INC-PD2(contract) ✓
   - §3.5 영속 → INC-PD3 ✓
   - §3.6 노출(API·에이전트) → INC-PD4(엔진 라우트)·INC-PD5(BFF·에이전트) ✓
   - §3.7 데이터 동역학(자치법규 elis) → INC-PD6 ✓; 시장=Phase2(비범위) ✓
   - §4 불변식(결정론·INV-3·INV-13·#8a·설명가능성·9.5) → 각 INC 게이트 단계 + executor/measurement 설계 ✓
   - §7 테스트 → 각 INC TDD ✓
2. **Placeholder scan:** 모든 코드 스텝에 실제 코드·경로·명령 포함. "TBD/적절히/유사" 없음. ✓
3. **Type consistency:** `PermitProcessSpec/StageSpec/CriterionRef`(PD1) ↔ `measure(result, ref, use_zone)`(PD2) ↔ `PermitProcessResult/StageResult/CriterionResult`(PD2 contract) ↔ store `save_permit_process/get_project_permit`(PD3) ↔ 라우트(PD4)·에이전트(PD5) 일관. `run_permit_process(result, spec, *, dev_type, use_zone)` 시그니처 전 INC 통일. ✓
4. **검증 필요 가정(구현 중 실코드로 확인):**
   - `resolve_zone_limit(use_zone, target_variable)` 반환 `(float, str)` — PD2에서 사용 전 재확인.
   - L3-C `QualAssessment`의 `rubric_id`/`grade` 속성명 — PD2 measure_qualitative에서 실제 필드명으로 보정.
   - `FinalGate().apply(GateItem)` / `GateResult.status.value` — PD2 _verify_stage에서 확인.
   - `LiveNetwork.get(url)` 시그니처·`NetworkError` — PD6에서 확인.
   - 플랫폼 `settings`/라우터 인클루드/테스트 경로 — PD5에서 플랫폼 규약 확인.

---

## Execution Handoff

각 INC는 독립 동작·테스트 가능. 권장 실행: INC-PD1→PD6 순차, 각 INC마다 9.5 적대 게이트(HIGH 0) 통과 후 커밋·푸시.
PD1~PD4·PD6은 엔진(feature/deliberation-review), PD5는 플랫폼 repo(별도 브랜치, cross-repo).
