# D2 — 기성고 EVM 실구현 + 과다청구 이상탐지 (백엔드)

## 1. 변경/신규 파일 · 엔드포인트
- **신규** `apps/api/app/services/cost/billing_service.py`
  - `register_billing()` 회차별 기성 영속(progress_billings) + 해시체인 + 등록후 트리거 경고 반환
  - `get_billing_summary()` 목록 + EVM summary + 누적곡선 + 이상경고
  - `get_anomalies()` 과다청구 이상탐지 단독
  - `compute_evm()` / `detect_anomalies()` 순수함수(단위테스트 가능)
  - `_ensure_billing_columns()` progress_billings 멱등 컬럼 보강(ALTER … ADD COLUMN IF NOT EXISTS)
- **수정** `apps/api/app/routers/cost.py`
  - 신규 `BillingRegisterRequest` 스키마
  - `POST /api/v1/cost/{project_id}/billing` (기성 등록·영속)
  - `GET  /api/v1/cost/{project_id}/billing` (목록 + EVM + 곡선 + 이상경고)
  - `GET  /api/v1/cost/{project_id}/billing/anomaly` (과다청구 이상탐지 단독)
  - ★기존 stub `POST /billing/create`·`GET /billing/summary` 무파괴(시그니처 유지, 신규 경로 추가)

## 2. EVM 산식 · 이상탐지 규칙(임계치)
- **PV** = 누적 계획 공정률(progress_pct%) × 계약총액
- **EV** = 누적 청구액(계약단가 기반 완료액 근사)
- **AC** = 누적 실제 투입(청구액 누적)
- **SPI** = EV/PV, **CPI** = EV/AC (PV/AC=0 시 None)
- 곡선: 회차별 누적 {round, pv, ev, ac}
- 이상탐지 임계치(`billing_service` 상수):
  - ① 청구단가 이탈 `UNIT_PRICE_DEVIATION_PCT=15%` (계약단가 우선, 없으면 표준단가 SSOT). +30% 초과는 level=high
  - ② 누적 청구 > 계약총액 → level=high `cumulative_over_contract`
  - ③ `SPI_CPI_WARN=0.9` 미만 → `low_spi`/`low_cpi`
  - ④ 전회比 청구 `CLAIM_SURGE_PCT=50%` 급증 → `claim_surge`
- 각 경고: `{level, type, detail, evidence(근거수치)}`

## 3. 해시체인 적재
- 기성 등록 시 `analysis_ledger_service.append_analysis(analysis_type="progress_billing", project_id, payload)` best-effort
- 반환 `content_hash` → progress_billings.ledger_hash 컬럼 + 응답 `ledger_hash` (변조탐지 기반, 실패해도 영속은 진행)

## 4. 로컬 시나리오 검증(.venv)
- AST OK / 라우트 3개 등록 확인 / billing_service import OK
- 단위 시나리오 전부 PASS:
  - [정상] 계획대로·단가정상 → SPI/CPI=1.0, anomalies=[] (곡선 누적값 정확)
  - [단가과다] 청구단가 계약단가 +20% → `unit_price_overclaim` (deviation 20.0)
  - [누적초과] 누적청구>계약총액 → `cumulative_over_contract` (high)
  - [SPI저조] 계획60% 청구저조 → SPI=0.333 `low_spi`
  - [표준단가이탈] work_type 키→표준단가 SSOT 비교 정상
- ★프로덕션 DB는 _ensure 멱등(IF NOT EXISTS)만, 테스트행 미생성(순수함수 단위검증)

## 5. 커밋
- (아래 회신 본문 해시 참조)

## 6. 프론트/QA 정합(응답 스키마)
- `GET /{pid}/billing` → `{ ok, status, contract_total, claims:[{round,work_type,contract_amount,claimed_amount,claimed_qty?,unit_price?,contract_unit_price?,progress_pct,period,ledger_hash?}], evm:{pv,ev,ac,spi,cpi,curve:[{round,pv,ev,ac}]}, anomalies:[{level,type,detail,evidence}], badges{note,unit_price_source,thresholds,data} }`
- `POST /{pid}/billing` → `{ ok, claim_id, ledger_hash?, anomalies_triggered:[...] }`
- `GET /{pid}/billing/anomaly` → `{ ok, status, contract_total, anomalies:[...], evm, badges }`
- 정직성: badges.note "경고는 검토 권장 사항·확정 아님", unit_price_source(표준품셈2025/계약단가), thresholds 명시, data no_data 정직표기
