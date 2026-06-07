# QA 검증 — CM Phase 1 MVP 백엔드 (커밋 8ce18b8)

검증일: 2026-06-06 / 검증자: Verifier(QA) / 방식: 읽기 검증 + .venv 로컬 재현(프로덕션 PYTHONPATH=.:apps/api)

## 종합 판정: **GO** (조건부 — WARN 2건은 비차단)

커밋 8ce18b8 (feat(cost): CM 상세적산 기반)은 멱등·안전·SSOT 회귀0·BOQ 영속화·D1·D4 모두
실제 재현으로 PASS. 기존 cost 엔드포인트/계산 무파괴(테스트 8 passed). 배포 가능.

---

## 판정표

| # | 검증 항목 | 판정 | 근거(file:line / 재현) |
|---|----------|------|------------------------|
| 1 | 멱등성·안전 | **PASS** | 아래 1번 |
| 2 | 단가 SSOT 회귀0(핵심) | **PASS** | 아래 2번 — 재현으로 동일값 입증 |
| 3 | BOQ 영속화 | **PASS** | 아래 3번 — save→get 라운드트립 일치 |
| 4 | D1 대안비교 | **PASS** | 아래 4번 — SRC +12.26% 재현 |
| 5 | D4 시장가 3중 | **PASS** | 아래 5번 — KCCI market 107,903 재현 |
| 6 | 정직성 | **PASS** | 아래 6번 |
| 7 | 회귀/품질·라우트 | **PASS** | 아래 7번 — 8 tests pass, 5 라우트 등록 |
| W1 | 시드 개수 문서 불일치 | **WARN** | 계약 "42" vs 실제 30/24(프로덕션 노트와 일치) |
| W2 | D4 market의 CWD 의존 | **WARN** | apps.api 임포트 — 루트 CWD/PYTHONPATH 필수 |

---

## 1. 멱등성·안전 — PASS

- `cost_tables_bootstrap.py:20-152` 모든 테이블 `CREATE TABLE IF NOT EXISTS`, UNIQUE/INDEX도 `IF NOT EXISTS`.
- 시드 `_seed_unit_prices` `cost_tables_bootstrap.py:198` / `_seed_work_types:226` 모두 `ON CONFLICT (...) DO NOTHING`.
- `analysis_ledger_service._ensure`(`:85`) 패턴 일치. 단, cost판은 `await db.commit()`(`:181`)을 자체 수행 → DDL 멱등성에 더 안전(차이는 개선 방향).
- 파괴적 구문 없음: DROP/ALTER/TRUNCATE/DELETE **0건**. `sales_*` 등 무관 테이블 참조 **0건**. CREATE TABLE 대상은 정확히 6개(material_unit_prices, cost_work_types, bim_quantities, progress_billings, cost_estimate, cost_estimate_item).
- 프로세스 1회 가드 `_ENSURED`(`:163,172`).
- **재현(프로덕션 DB)**: `_ENSURED` 리셋 후 재-시드 → material_unit_prices 30/30, cost_work_types 24/24 (중복 0). 기존데이터 무영향 확정.

## 2. 단가 SSOT 회귀0 — PASS (핵심)

- 동기 엔진 경로(기존 산출 경로): `geometry_qto.py:15,64-67` 와 `standard_quantity_estimator.py:206,210...281`
  은 모두 `resolve_unit_price_sync()` 사용. 이 함수(`unit_price_repository.py:133-139`)는 **항상**
  `fallback_price()` 반환 = `UNIT_PRICES_2026` 동일값(DB 무관).
- **재현 1**: 전 키 대해 `resolve_unit_price_sync(k)`의 spec/unit/mat/labor/exp == `UNIT_PRICES_2026[k]` → `True`.
- **재현 2(중요)**: DB가 시드된 상태에서도 `StandardQuantityEstimator` 콘크리트 단가 = 85000/35000/12000
  (= fallback). 즉 **기존 산출 경로는 DB 유무와 무관하게 전환 전과 정확히 동일** → 회귀 0 확정.
- DB-present 우선 경로는 **신규 `build_boq` 전용**(async `repo.get_price`, `unit_price_repository.py:96-119`).
  기존 엔드포인트(`estimate-overview`/`calculate`)는 이 경로를 타지 않음 → 기존 회귀 영향 없음.
- fallback `float()` 캐스팅(`:49-51`)은 원본 int를 float로 — 곱셈 입력이라 수치 동일(무해).
- `_KEY_TO_MATERIAL_CODE`(`:26-33`) 매핑 타당: concrete→RC-001, rebar→RC-004, formwork→RC-008,
  waterproof→WP-002, window→WW-001, masonry는 미대응→fallback. 시드 코드와 일치 확인.

## 3. BOQ 영속화 — PASS

- `cost_estimate_repository.save_estimate`(`:17`)/`get_estimate`(`:74`)/`list_estimates`(`:114`) DB CRUD.
- ORM↔라우터: `cost.py:471 create_boq`→save, `:524 get_boq`→get, `:534 list_boq`→list.
- **재현**: build_boq→save_estimate(ok=True, eid 발급)→get_estimate. items 8개 복원, summary.total 저장값과
  완전 일치, market_unit_price(107903.07)·actual(None) 영속·복원 확인. (생성한 테스트행 1건은 검증 후 삭제 완료)
- 예외는 흡수하고 `ok=False`/`None` 반환 → 산정결과 자체는 graceful(`:69-71`).

## 4. D1 대안비교 — PASS

- `cost.py:541 /alternatives` → `_merge_params`(`:451` allowed 키만 병합) → variant별 `build_boq` 재산정.
- 델타(`:568`), 델타%(`:581`), 영향공종(`:571-574` 금액변화 > base×0.5% 임계), rationale(`:575`) 정확.
- **재현**: base(RC, GFA10000) total 7,115,784,445 vs SRC variant 7,988,281,238 → delta +872,496,793, **+12.26%**.
  구조변경이 콘크리트/철근 물량계수에 반영되어 합리적.
- 계약 응답 스키마 `{ok, base{total}, variants[{label,total,delta,delta_pct,affected_work_types[],rationale}], note}` 일치(`:585-590`).
- `total_gfa_sqm<=0` 시 422 가드(`:548`).

## 5. D4 시장가 3중 — PASS

- `boq_builder.py:96-110` 각 항목 standard/market/actual 3중. actual은 **항상 None**(정직).
- market = `_kcci_market_unit`(`:40-56`) — KCCI 변동모델 현재월 단가. `_KEY_TO_KCCI`(`:31`) concrete/rebar/window만 대응.
- **재현(프로덕션 PYTHONPATH)**: concrete market = **107,903.07원** 실산출. build_boq 항목·get 복원에 영속.
- 미대응 키(masonry 등)·import 실패 시 None로 graceful(`:55`).

## 6. 정직성 — PASS

- `_HONESTY_NOTE`(`boq_builder.py:37`) "참고용 개산 — 전문 적산사 검토 권장 … 실적단가(actual)는 미보유".
- qto_source 신뢰구간 `_QTO_BAND`(`:36`) bim ±5% / derived ±12%, confidence_grade B/C(`:118`).
- 단가 출처(price_source)·기준연도(price_basis_year)·region 부착. actual 항상 null + badges.actual_data "실적 데이터 없음".
- `/alternatives` note "추정(±12%)·전문 적산사 검토 권장"(`:589`). `/unit-prices` note 3중 출처 명시(`:612`).

## 7. 회귀/품질·라우트 — PASS

- `py_compile` 7개 파일 전부 OK. 전체 앱 부팅 OK(`apps.api.main:app` import 성공).
- **신규 5 라우트 등록 확인**: POST `/cost/{pid}/boq`, GET `/cost/estimate/{eid}`, GET `/cost/{pid}/estimates`,
  POST `/cost/{pid}/alternatives`, GET `/cost/unit-prices`. 정적/동적 경로 충돌 없음.
- 기존 import 무파괴: `cost.py:17-19` origin_cost_calculator/cost_monte_carlo/bim_service 그대로. 기존 7개 엔드포인트 유지.
- **기존 테스트 회귀 0**: `pytest tests/test_cost_router.py` → **8 passed**.

---

## WARN(비차단) 상세

### W1 — 시드 개수 문서 불일치
계약(`23_..._contract.md:8`)은 "42개" 명시. 실제 시드는 material 30 + work_type 24.
프로덕션 노트(material_unit_prices 30·cost_work_types 24)와는 일치. **코드 버그 아님 — 계약 문서 표기 오차.**
조치: 계약/보고 문서의 "42" 표기를 "30(단가)+24(공종)"로 정정 권장.

### W2 — D4 market의 CWD/PYTHONPATH 의존
`boq_builder._kcci_market_unit`이 `from apps.api.services.kcci_material_price_service import ...`(`:46`)
절대경로 사용. `app.services...`와 `apps.api...`를 동시에 임포트하므로 **둘 다 sys.path에 필요**.
프로덕션은 `docker-compose.yml:32 PYTHONPATH=/app:/app/apps/api`로 충족 → 정상 동작 확인.
리스크: 다른 실행 컨텍스트(예: apps/api 단독 CWD)에선 ImportError가 except로 흡수되어 market이 조용히
None로 떨어질 수 있음(정직성 유지되나 D4 market 축 소실). **현 배포 경로에선 문제 없음.**
조치(선택): 추후 상대 임포트(`app.../services...`) 또는 동적 임포트 가드 일원화 권장.

---

## 검증 명령/증거 요약

| 검증 | 명령 | 결과 |
|------|------|------|
| 구문 | `py_compile` 7파일 | OK |
| SSOT 동일값 | venv 재현 | fallback == UNIT_PRICES_2026 True |
| 동기경로 DB무관 | venv 재현(DB시드 후) | SQE concrete 85000/35000/12000 |
| 멱등 재시드 | venv 재현 | 30/30, 24/24 (중복 0) |
| BOQ 라운드트립 | venv 재현 | save ok, get total 일치, market 영속 |
| D1 델타 | venv 재현 | SRC +872M (+12.26%) |
| D4 market | venv(PYTHONPATH 프로덕션) | concrete 107,903.07 |
| 기존 테스트 | `pytest test_cost_router.py` | 8 passed |
| 라우트 등록 | app 부팅 + route dump | 신규 5 + 기존 유지 |

## 검증 중 부수효과(고지)
- 로컬 .venv가 `.env`의 실DB에 연결되어 `_ensure_cost_tables`가 1회 실행됨(테이블 멱등 생성+시드).
  멱등(IF NOT EXISTS/ON CONFLICT)이며 프로덕션 노트상 이미 생성·시드된 상태와 동일 → 무해.
- 검증용 BOQ 테스트행 1건 생성 후 즉시 DELETE로 정리 완료. **코드 수정/커밋/푸시/배포는 일절 없음.**
