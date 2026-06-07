# CM Phase 1 MVP — 구현 계약

## ★DB 전략(확정): Alembic 아님 — 멱등 CREATE TABLE IF NOT EXISTS
프로덕션 DB에 alembic_version 테이블 없음(런타임 생성 패턴). v61_cost 테이블 미생성(sales_*만 존재).
→ `app/services/ledger/analysis_ledger_service.py:_ensure` 패턴 그대로 `_ensure_cost_tables()` 신설:
  - material_unit_prices, cost_work_types, bim_quantities, progress_billing, cost_estimate(BOQ 헤더), cost_estimate_item(BOQ 항목) 등 v61_cost.py ORM에 대응하는 테이블을 CREATE TABLE IF NOT EXISTS로(기존 데이터 무영향).
  - 라우터 첫 사용 시 lazy 호출(analysis_ledger와 동일). 배포되면 자동 생성, 수동 마이그레이션 불필요.
- 단가 시드: app/services/seed/v61_seed_data.py 42개를 INSERT ... ON CONFLICT DO NOTHING(멱등).

## 백엔드 작업(executor, 커밋)
1. `_ensure_cost_tables()` + 시드 멱등 적재(위).
2. **UnitPriceRepository SSOT** (app/services/cost/unit_price_repository.py 신설): material_unit_prices 조회 → 미존재시 하드코딩 fallback(price_source="fallback" 표기). 기존 하드코딩 4곳(standard_quantity_estimator.py:109, geometry_qto.py:15, construction_cost_engine.py:14, kcci_material_price_service.py:17)을 이 repo 경유로 전환(회귀 0 — 동일값 fallback). 출처/기준일/지역 필드.
3. **cost.py ↔ ORM 연결**: BOQ/원가계산서 결과를 cost_estimate(+item) 테이블에 영속화(현재 stub/메모리). 조회 엔드포인트도 DB.
4. **D1 대안설계 A/B 원가비교** — POST /api/v1/cost/{pid}/alternatives. Req:{base_params, variants:[{label, overrides:{structure?, floors?, ...}}]}. geometry_qto/standard_quantity_estimator 재호출로 변형별 원가 → 델타·영향공종. "추정" 배지.
5. **D4 시장가 3중비교** — BOQ/단가 응답에 {standard_unit_price, market_unit_price(KCCI 변동모델), actual_unit_price: null("실적 데이터 없음")} 3중 표기.
6. **D6 AI 해설** — 기존 cost_interpreter 연결 확인(BOQ 결과 해석). 신규 LLM 최소.
7. 정직성: 단가 출처·기준일, qto_source(bim ±5%/derived ±12%), "참고용·전문 적산사 검토 권장". 데이터 부재 정직표기(0/추정으로 가리지 말 것).

### 응답 스키마(프론트 정합 — 프론트는 Batch2)
- POST /cost/{pid}/boq → { ok, estimate_id, items:[{code,name,work_type,quantity,unit,unit_price,amount,price_source,price_basis_year,qto_source}], summary{direct,indirect,total,confidence_grade}, badges{note} }
- POST /cost/{pid}/alternatives → { ok, base{total}, variants:[{label,total,delta,delta_pct,affected_work_types[],rationale}], note }
- GET /cost/unit-prices → { ok, items:[{code,name,unit,standard,market,actual:null,source,basis_year}], note }

## 제약/검증
- 멱등·안전(CREATE IF NOT EXISTS·ON CONFLICT). 기존 cost 계산 회귀 0(SSOT fallback 동일값). 기존 엔드포인트 무파괴(증분).
- 로컬 .venv: import/라우트, _ensure_cost_tables를 로컬DB(또는 sqlite 불가시 구문/로직 검증), 단가 SSOT 조회 단위호출, D1 더미 변형 산출 확인. (프로덕션 DB 직접 변경 금지 — _ensure는 배포 후 자동. 단 가능하면 로컬에서 로직 검증.)
- 커밋: git add 명시경로만(-A 금지)+commit. 메시지 `feat(cost): CM 상세적산 기반 — 단가DB SSOT·BOQ 영속화·대안설계 원가비교(D1)·시장가3중(D4)`. footer Co-Authored-By: Claude Opus 4.8 (1M context).
- ★프로덕션 테이블 생성은 배포 후 _ensure_cost_tables 자동 실행으로(오케스트레이터가 배포·검증). git push·SSH배포는 오케스트레이터.

## 반환 보고
1. 변경/신규 파일·엔드포인트. 2. _ensure 테이블 목록·시드 멱등성. 3. SSOT 전환 4곳·회귀0 근거. 4. D1/D4 로직. 5. 로컬검증·커밋해시. 6. 프론트/QA 정합사항.
또한 _workspace/24_backend_cm_mvp.md 저장.
