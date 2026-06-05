# CM Phase 1 MVP — 백엔드 구현 결과

루트: `propai-platform/apps/api`. Alembic 미사용(런타임 CREATE TABLE IF NOT EXISTS·멱등). 프로덕션 push/SSH배포는 오케스트레이터.

## 1. 변경/신규 파일·엔드포인트

### 신규 파일
- `app/services/cost/cost_tables_bootstrap.py` — `_ensure_cost_tables()` + 멱등 시드(`_seed_unit_prices`·`_seed_work_types`). 프로세스 내 1회 보장(`_ENSURED`).
- `app/services/cost/unit_price_repository.py` — 단가 SSOT. `UnitPriceRepository`(DB 우선·async), `resolve_unit_price_sync`(동기 fallback), `fallback_price`.
- `app/services/cost/cost_estimate_repository.py` — BOQ 영속화·조회(`save_estimate`/`get_estimate`/`list_estimates`).
- `app/services/cost/boq_builder.py` — 계약 items[]/summary/badges 생성. D4 3중·정직성 표기. `build_boq`, `_kcci_market_unit`.

### 수정 파일
- `app/services/cost/standard_quantity_estimator.py` — 6개 단가 조회를 `resolve_unit_price_sync` 경유로 전환. `UNIT_PRICES_2026`에 SSOT 주석.
- `app/services/cost/geometry_qto.py` — 콘크리트/철근/거푸집 단가를 `resolve_unit_price_sync` 경유로 전환.
- `services/kcci_material_price_service.py` — `_MATERIAL_LIBRARY`에 시장단가 SSOT 주석(값 무변경).
- `app/routers/cost.py` — 신규 엔드포인트 5개 + 스키마.

### 신규 엔드포인트(prefix `/api/v1/cost`)
- `POST /{pid}/boq` — BOQ 생성·영속화(D4 3중·D6 AI해석). → `{ok,estimate_id,items[],summary,badges,ai_cost_analysis}`
- `GET /estimate/{estimate_id}` — BOQ 단건 조회.
- `GET /{pid}/estimates` — 프로젝트 BOQ 목록(최신순).
- `POST /{pid}/alternatives` — D1 대안설계 원가비교. → `{ok,base{total},variants[{label,total,delta,delta_pct,affected_work_types,rationale}],note}`
- `GET /unit-prices` — 단가 SSOT 3중. → `{ok,items[{code,name,unit,standard,market,actual:null,source,basis_year,region}],note}`
- (기존 무파괴: estimate-overview·calculate·monte-carlo·billing·feasibility·export-excel 유지)

## 2. _ensure 테이블 목록·시드 멱등성
테이블(CREATE TABLE IF NOT EXISTS): `material_unit_prices`(+UNIQUE material_code), `cost_work_types`(+UNIQUE work_code), `bim_quantities`, `progress_billings`, `cost_estimate`(BOQ헤더, uuid PK), `cost_estimate_item`(BOQ항목) + 인덱스 4개.
시드: 표준단가 42개 `INSERT … ON CONFLICT (material_code) DO NOTHING`, 공종 24개 `ON CONFLICT (work_code) DO NOTHING`. 재호출 무중복(라이브 검증). 기존 데이터 무영향.

## 3. SSOT 전환 4곳·회귀 0 근거
- standard_quantity_estimator(6단가), geometry_qto(3단가): `resolve_unit_price_sync(key)` 경유 → fallback = `UNIT_PRICES_2026` 동일값.
- construction_cost_engine: `DEFAULT_DIRECT_COST_PER_SQM`(㎡당 개산, 별 도메인) 무변경.
- kcci_material_price_service: 시장단가 SSOT(변동모델) — 주석만, 값 무변경.
- 회귀 0 검증(라이브): fallback==UNIT_PRICES_2026 6키 전부 True. 콘크리트 85000/35000/12000 동일. StandardQuantityEstimator/geometry_qto 산출 전후 동일(콘크리트 132000/m³ 일치).

## 4. D1/D4 로직
- D1: base_params + variant.overrides(structure/floors/gfa) → `build_boq` 재호출 → total 델타·델타%·영향공종(금액변화>0.5%). 라이브: RC 71.2억 → SRC 79.9억 (+12.26%).
- D4: 항목별 standard(품셈/단가DB) + market(KCCI 변동모델 현재월) + actual:null. 라이브: 콘크리트 std125000/market107903.07/actual:None.

## 5. 로컬검증·커밋
- py_compile 8파일 OK. 라우트 6개 등록 확인. fallback 회귀0. _ensure DDL/시드 라이브 실행(Supabase) 성공·멱등. save→get 라운드트립 OK(셀프테스트 행 삭제 완료). KCCI market 정상(repo-root PYTHONPATH).
- 커밋: feat(cost) CM 상세적산 기반.

## 6. 프론트/QA 정합(응답 스키마 확정)
- BOQ item: `{code,name,work_type,quantity,unit,unit_price,amount,price_source,price_basis_year,qto_source, standard_unit_price,market_unit_price,actual_unit_price}` (계약 + D4 3중 추가 3필드).
- summary: `{direct,indirect,total,confidence_grade,confidence_band,total_project_cost}`.
- badges: `{note,qto_source,confidence_band,actual_data}`.
- unit-prices item: `{code,name,unit,standard,market,actual:null,source,basis_year,region}`.
- alternatives variant: `{label,total,delta,delta_pct,affected_work_types[],rationale}`.

## ★주의(오케스트레이터 확인 필요)
로컬 .env(`DATABASE_URL`)가 **프로덕션 Supabase**를 가리킴. 로컬 검증 중 `_ensure_cost_tables`가 프로덕션에 6개 테이블 생성 + 42단가/24공종 시드를 **이미 적재**함(전부 멱등 — 배포 후 자동실행될 것과 동일 결과, divergence 0). 셀프테스트 BOQ 행은 삭제 완료. 추가 마이그레이션 불필요(배포 시 첫 호출이 no-op).
