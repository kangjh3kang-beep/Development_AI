# P0 단가 수지경로 SSOT 통합 (회귀 0 비파괴)

## 목표
공사비 단가 이원화 해소 — 수지경로(₩/㎡ 개산상수)를 단가 SSOT(`unit_price_repository`)로
일원화하되, 기존 수지 결과값을 **한 푼도 바꾸지 않는다(회귀 0)**.

## 구현 방식(방향 1 채택 — 가장 안전)
`construction_cost_engine.DEFAULT_DIRECT_COST_PER_SQM`(건물유형별 ₩/㎡ 개산상수)를
`unit_price_repository`에 **동일값**으로 등록하고, 엔진이 repository에서 조회하도록 일원화.
조회/임포트 실패 시 기존 상수로 fallback → DB·repo가 비어도 100% 동일값.

방향 2(use_boq_total 우선) **미적용** — 시간/위험 대비 방향 1만으로 SSOT 일원화 충족.
(향후 필요 시 기본 False 플래그 뒤로 추가)

## 변경/신규 파일
1. `app/services/cost/unit_price_repository.py`
   - 신규 `_DIRECT_SQM_FALLBACK`(건물유형별 ₩/㎡, 기존 상수와 동일값)
   - 신규 `direct_sqm_fallback(building_type)` — 미존재 유형은 apartment 폴백(기존 동작)
   - 신규 `resolve_direct_sqm_sync(building_type)` — 동기·무DB 경로 SSOT(항상 fallback)
   - 신규 `UnitPriceRepository.get_direct_sqm()` — DB(material_code=`DIRECT_SQM_<type>`) 우선·미존재 시 fallback (옵션, 미사용해도 무영향)
2. `app/services/feasibility/construction_cost_engine.py`
   - 신규 `_resolve_direct_unit_cost(building_type)` — repository sync 조회, 실패 시 상수 fallback
   - `calculate_direct_cost`의 단가 결정부를 `_resolve_direct_unit_cost`로 교체
   - `DEFAULT_DIRECT_COST_PER_SQM` **상수 유지**(routers/cost.py 등 기존 참조 무파괴, fallback 출처)
3. `app/services/seed/v61_seed_data.py`
   - `seed_standard_prices_2026()`에 `DIRECT_SQM_<type>` 7행 멱등 시드 추가
     (material_price=₩/㎡ 동일값, ON CONFLICT DO NOTHING). DB에 없어도 엔진은 동기 fallback로 동일값.

## SSOT 이관 방식 · fallback
- 단일 출처: `unit_price_repository._DIRECT_SQM_FALLBACK`
- 엔진 경로: `calculate_direct_cost` → `_resolve_direct_unit_cost` → `resolve_direct_sqm_sync`(SSOT)
  → import/조회 실패 시 `DEFAULT_DIRECT_COST_PER_SQM`(동일값) fallback
- DB 경로(옵션): `get_direct_sqm`이 `material_unit_prices.material_code='DIRECT_SQM_<type>'`의
  `material_price`를 우선 사용, 미존재 시 fallback. 엔진은 동기 fallback만 쓰므로 DB 유무와 무관하게 동일.

## ★회귀검증 결과 (변경 전 = 변경 후, 차이 0)
변경 전 baseline 캡처 → 변경 후 동일 입력 9케이스 **비트단위 동일**:

| 케이스 | unit ₩/㎡ | direct_won | total_won | 결과 |
|---|---|---|---|---|
| apartment 10000 | 2,400,000 | 24,000,000,000 | 27,600,000,000 | OK |
| officetel 10000 | 2,600,000 | 26,000,000,000 | 29,900,000,000 | OK |
| commercial 7500.5 ×1.03 | 2,266,000 | 16,996,133,000 | 19,545,552,950 | OK |
| unknown_type 5000 (→apartment) | 2,400,000 | 12,000,000,000 | 13,800,000,000 | OK |
| warehouse 12345 ×1.07 | 1,284,000 | 15,850,980,000 | 18,228,627,000 | OK |
| office 8000 | 2,500,000 | 20,000,000,000 | 23,000,000,000 | OK |
| townhouse 3000 | 2,000,000 | 6,000,000,000 | 6,900,000,000 | OK |
| single_house 4200 | 2,100,000 | 8,820,000,000 | 10,143,000,000 | OK |
| apartment 9999 (unit_cost 명시) | 3,000,000 | 29,997,000,000 | 34,496,550,000 | OK |

→ **REGRESSION_DIFF_ZERO**

- fallback 동일성: 7개 건물유형 전부 `resolve_direct_sqm_sync == direct_sqm_fallback == _resolve_direct_unit_cost == DEFAULT_DIRECT_COST_PER_SQM` → **FALLBACK_IDENTICAL**
- 미존재 유형 → apartment 폴백 동일 확인
- seed 값 == 상수 7개 전부 일치 → **SEED_IDENTICAL**
- 수지 실경로(`compute_construction_cost` via ModuleInput) apartment 10000 → 27,600,000,000 동일
- override 경로(`construction_cost_override_won`) 무영향 확인

## use_boq_total 옵션
미적용(방향 1만). 기존 동작 불변.

## 로컬 검증
- 로컬 `.venv`: AST 구문 OK(3파일), import OK, 회귀 9케이스 차이 0, fallback/seed 동일성 PASS
- `routers/cost.py`의 `apps.api...` import 에러는 **사전 존재**(clean tree에서도 동일) — 본 변경과 무관.
  cost.py는 `DEFAULT_DIRECT_COST_PER_SQM`만 참조하며 상수 유지로 무파괴.

## 커밋
`refactor(cost): 단가 수지경로 SSOT 일원화(unit_price_repository) — 회귀0 비파괴`

## QA/배포 유의 (회귀 범위)
- 회귀 위험 영역: 모든 `/v2/feasibility` 산출(공사비·ROI), `/cost/estimate-overview`, 수지 기반 모듈 전부.
  → 9케이스 + 실경로 차이 0으로 비파괴 입증.
- DB 시드(`DIRECT_SQM_*` 7행)는 멱등(ON CONFLICT DO NOTHING), 기존 데이터 무영향.
  엔진은 동기 fallback만 사용하므로 시드 미적용이어도 동일동작 → 배포 순서 무관.
- 신규 DB 테이블 불필요(기존 material_unit_prices 재사용).
- SSH 배포·push 미수행(지시 준수). 프로덕션 반영은 별도 백엔드 배포 시.
