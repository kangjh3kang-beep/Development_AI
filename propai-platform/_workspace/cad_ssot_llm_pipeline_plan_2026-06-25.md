# 하향식 자동설계: 기하 SSOT 통합 + 평면 브리지 + LLM 부지맞춤 조정(검증게이트)

작성일: 2026-06-25 · 브랜치: `deploy/cad-ssot-llm` · iteration 1

## 배경(OMC 감사 확정)
두 설계 스택이 단절돼 있었다.
- `design_ingest`(orchestrator.generate_design_proposals — 1~4단계+검색조합) : 라우터 노출 부족(설계 스튜디오 경로 미노출).
- `design_v61`/`auto_design_engine`(평면·3D, /mass 노출) : 편집기/2D/3D가 각자 스칼라로 따로 그려 **기하 SSOT 부재**.
- 평면 폴리곤 생성기 `unit_plan_generator.generate_unit_plan(area,bays,core_type)`(rooms/boundaries/openings 실폴리곤 보유)을 **compose가 호출하지 않음 = D3 최대단절**. compose는 평형 '개수'까지만 알았다.

## 5단계 구현(전부 additive·기존 블록 재사용·신규 최소)

### 1. 기하 SSOT 스키마 `DesignGeometry`(신규 1파일·m 단위 정본)
`app/services/design_ingest/design_geometry.py` 신규.
- 필드: `site`(polygon·width/depth·orientation) · `mass`(compute_optimal_mass 출력 그대로+north_step_profile) · `dongs[]`(compose placement.blocks 그대로) · `floors[]` · `cores[]`(compute_core_layout 그대로) · `units[]{type,area,plan}` · `provenance`.
- ★`units[].plan`은 `generate_unit_plan` 반환(as_dict) **형식 그대로 재사용** — 신규 평면 스키마 정의 안 함.

### 2. 신규 소형 3종(같은 파일)
- `orientation_from_polygon(geometry)` — 필지 폴리곤 최장변 방위각 → 주 입면 법선 향(정남=0·서=+). shapely 기반(dims_from_polygon과 동일 등거리 미터근사). 남향 채택.
- `core_type_for_units(units_per_core)` — 2호↓=계단실형 / 3~5호=복도형 / 6호↑=타워형. UNIT_CORE_TYPES enum 계약 보증.
- `ALLOWED_USES_BY_ZONE`(국토계획법 별표 확인분만) + `allowed_uses(zone_type)->list|None` — 양허 방식·코드/한글명 매핑·미확정 None(무날조).

### 3. ★평면 브리지(D3 해소·핵심)
- `build_unit_plans(unit_breakdown, core_type)` — compose unit_breakdown(평형 type/area/count) → 평형별 `generate_unit_plan` 호출 → `units[].plan`(rooms/boundaries/openings 실폴리곤) 적재.
- 면적 범위밖(20~250㎡)·룰 미보유 평형은 `plan=None`+사유(가짜 평면 금지·정직).
- 밴드별 유효 베이 자동선택(기본 3베이·전 밴드 공통).
- ★`/layout`에서 **참조 도면 없이도** 평면이 나오도록: compose 빈 결과 시 확정 매스 연면적으로 `compute_unit_breakdown`(정본) 직접 분해 → 브리지 입력 보장(D3 해소가 도면 유무와 무관).

### 4. ★LLM 부지맞춤 유기적 조정층(검증게이트·RLVR: LLM proposes / rules verify)
- `llm_adjust_unit_plan(unit_entry, site_context, similar_seeds)` — 결정론 평면 위 LLM 미세조정 패스.
- 입력: 결정론 layout(plan.rooms) + 부지맥락(형상·향·접도·인접) + 유사 시드평면.
- LLM 인프라 **재사용**: `BaseInterpreter._get_llm()`(get_llm 단일경유) — 신규 인프라 0.
- ★검증게이트 `verify_adjusted_plan`(결정론 룰): 형식·음수/과대 거부·무중첩(AABB)·최소면적·면적합≤전용(+5%) — **위반 시 폐기→결정론 원안 폴백**(가짜 통과 금지). 검증결과 정직표기.
- opt-in(기본 off)·best-effort: LLM 미가용/실패/검증실패 모두 결정론 원안 유지+정직 note.

### 5. /layout + /proposals 엔드포인트(`design_v61.py`)
- `POST /api/v1/design/{id}/layout` — /mass 내부호출(매스 SSOT 단일화)+compose+평면 브리지+코어/향 합성 → DesignGeometry 전체 반환. /mass 하위호환 필드 포함. `allowed_uses`·`llm_adjustment` 동반.
- `POST /api/v1/design/{id}/proposals`(W1) — `generate_design_proposals` 노출(설계 스튜디오 경로). tenant_id 인증강제·project_id 경로. design-gen /generate와 동일 오케스트레이터 재사용(중복 로직 0).

## DRY(재사용 블록 / 신규 최소)
재사용: `compute_optimal_mass`·`compose`/`compute_unit_breakdown`/`compute_placement`·`compute_core_layout`·`generate_unit_plan`·`site_context_from_zone`·`BaseInterpreter._get_llm`·`dims_from_polygon` 패턴.
신규 파일: `design_geometry.py` 1개. 신규 테이블: `ALLOWED_USES_BY_ZONE`(확인분만). 그 외 전부 기존 함수 조합.

## 검증게이트(RLVR) 동작
- 원안 rooms → PASS(통과). 중첩/음수/과대/빈 → 폐기·원안 폴백(fell_back=True).
- LLM 미가용 환경(monkeypatch _llm_propose_rooms 실패) → applied=False·원안 유지.
- 유효 조정안 → applied=True. 무효(중첩) → applied=False·폴백.

## 테스트·무회귀
- py_compile: design_geometry.py / design_v61.py / test_design_geometry.py 전부 OK.
- 신규 `tests/test_design_geometry.py` 24개 PASS(브리지·SSOT·LLM게이트 폴백·allowed_uses·orientation·core_type).
- 무회귀: test_design_compose(기존)·test_design_orchestrator·test_unit_plan_generator·test_auto_design_engine 전부 PASS(합계 186 passed/9 skipped).
- /mass·generate-full-set·BIM·기존 키 보존(전부 additive). compute_optimal_mass=매스 SSOT 단일화.

## 불확실점(라이브 미검증)
- **LLM 라이브 미검증**: 이 환경엔 ANTHROPIC 키·fastapi·qdrant_client·Python3.11(StrEnum) 미설치 → `/layout`·`/proposals`의 HTTP 경로와 `llm_adjust=True` 실 LLM 호출은 라이브 미검증(엔드포인트 본문 로직은 서비스 함수 단위로 직접 검증함). 배포 후 실 키로 라이브검증 필요.
- orientation_from_polygon은 직사각형 근사 향(부정형 폴리곤은 convex_hull 최장변) — 정밀 도로사선/접도면은 후속.
- LLM 조정은 단위세대 평면 1건(추천 평형)에 적용 — 전 평형/동 단위 확장은 후속.

## 다음
- 프론트 SiteCanvas/CAD 스튜디오가 /layout geometry(SSOT)를 2D/3D/편집기 단일소비로 전환(현재 각자 스칼라).
- 라이브 LLM 키로 `llm_adjust=True` 검증게이트 동작·폴백 라이브확인.
