# 91. LLM 사용량 실계측 + 마진(50/40/30%) + 월기본/충전 코인분리 + 사용량/잔액 API (백엔드)

## 1. 변경/신규 파일·테이블·컬럼
- 수정 `app/core/billing.py`: 마진 조정 + `tier_multiplier` 비구독 1.5 반환.
- 수정 `app/services/billing/billing_service.py`: 스키마 멱등 보장, 코인분리 차감, service 귀속 계측, 집계/잔액 API. **버그 수정**: `record_usage_usd`가 `ensure_cycle` 5튜플을 잘못 인덱싱(row[4]/[5]) → row[3]/[4]로 교정.
- 수정 `app/services/ai/base_interpreter.py`: `_record_llm_billing(..., service)` + 호출부 `service=self.name` + 토큰0 정직 미기록.
- 수정 `routers/billing.py`: `GET /token-usage`, `GET /balance` 신설.
- 신규 `tests/test_billing_metering.py`: 단위검증 10건.
- **신규 테이블** `llm_usage_log`(id bigserial, user_id text, service text, model text, input_tokens int, output_tokens int, cost_usd numeric(14,6), cost_krw numeric(14,2), created_at timestamptz). 인덱스 (user_id,created_at)·(service,created_at).
- **신규 컬럼** `public.users.monthly_base_krw numeric(14,2)`, `public.users.topup_krw numeric(14,2)` — `ensure_schema()`가 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`로 멱등 생성(프로덕션DB 미변경, 앱 최초 사용 시 자동).

## 2. 마진 50/40/30 매핑 (낮은등급 높은마진)
| 등급 | 기존 | 변경 | 마크업 |
|------|------|------|--------|
| power(파워, 낮은유료) | 2.0 | **1.5** | +50% |
| superpower(슈퍼파워) | 1.4 | **1.4** | +40% |
| master(마스터) | 1.3 | **1.3** | +30% |
| free/guest(비구독) | 1.0 | **1.5** | +50% |
- `tier_multiplier`: 구독등급은 `TIER_BILLING` 설정값, 그 외(free/guest/미상)는 `_NON_SUB_MULTIPLIER=1.5`. 청구식 `billed_krw = $ × 환율 × multiplier`에 그대로 반영.

## 3. llm_usage_log · service 귀속 (인터프리터 매핑)
- 모든 LLM 호출 단일 경유점 `BaseInterpreter._invoke` → `_record_llm_billing(model, in, out, service=self.name)`.
- service = 인터프리터 `name`: `site_analysis / market / feasibility / esg / permit / report / tax / cost / design / avm / digital_twin`(11개).
- 비-인터프리터 경로(규칙기반 G2B 등)는 LLM 미사용이라 미기록. 인터프리터 외 직접 `_invoke` 미경유 호출은 service 기본값 `"llm"`.
- 차감 누적과 동시에 `llm_usage_log` 1건 INSERT(input/output tokens, cost_usd 원가, cost_krw=마진·환율 적용 최종).
- **정직성**: 토큰 0(캐시 적중·계측 누락)이면 INSERT/차감 모두 스킵.

## 4. 월기본/충전 차감순서 · 월리셋
- `monthly_base_krw`: 월 제공 기본(매월 `tier_included_budget_krw`로 리셋).
- `topup_krw`: 충전 잔액(영속, 월리셋 무관).
- 차감 우선순위: **월기본 먼저** → 누적 청구액이 월기본 초과 시 초과분만 `topup_krw`에서 차감. `record_usage_usd`가 `topup_draw = max(0, billed_after-base) - max(0, billed_before-base)`로 계산.
- `/topup`: `topup_krw` 증액(월기본 불변).
- 월리셋(`ensure_cycle`): 달이 바뀌면 `llm_billed_krw=0`, `monthly_base_krw=tier_included`로 리셋, **`topup_krw` 보존**.
- 하위호환: `billing_budget_krw = monthly_base_krw + topup_krw`로 항상 동기(`_sync_budget`).
- `set_tier`도 월기본만 재설정, 충전 보존.

## 5. token-usage / balance API
- `GET /api/v1/billing/token-usage?days=30`(본인) → `{days, total_tokens, total_cost_krw, by_service:[{service,tokens,cost_krw}], daily:[{date,tokens,cost_krw}]}`. days 1~365 클램프. user_id 격리.
- `GET /api/v1/billing/balance`(본인) → `{tier, tier_label, monthly_base_krw, monthly_base_remaining, topup_krw, topup_remaining, used_this_cycle_krw, markup_pct, cycle_start}`.

## 6. 무목업 · 하위호환
- 무목업: `llm_usage_log` 실 INSERT 데이터만 집계. 마진·실시간 환율 실제 적용. 비구독 무료횟수 로직 불변.
- 하위호환: `record_usage_usd`/`topup` 신규 인자 전부 키워드+기본값 → 기존 단일 호출부(base_interpreter, billing 라우터) 무파괴. `billing_budget_krw` 컬럼 유지·동기.

## 7. 단위검증 (10/10 PASS, 외부LLM·실DB 미사용 페이크 세션)
- tier_multiplier(power1.5/super1.4/master1.3/free1.5/guest1.5), billed_krw 마진·환율.
- 월기본 우선 차감(topup 보존), 월기본 초과→충전 차감, service 미지정 시 usage_log 스킵, 비구독 무과금.
- balance(마진율30·코인분리), token-usage 집계(total/by_service/daily), 월리셋(월기본 리셋·충전 보존).
- `pytest tests/test_billing_metering.py` → **10 passed**. 회귀 `test_ai_usage_tracker` 동반 **21 passed**.
- py_compile 4파일 OK. 앱부팅 OK(746 routes), `/token-usage`·`/balance` 등록 확인.

## 8. 커밋해시
- (본문 하단 기재)

## 9. 프론트 계약
```ts
// GET /api/v1/billing/token-usage?days=30
type TokenUsage = {
  days: number; total_tokens: number; total_cost_krw: number;
  by_service: { service: string; tokens: number; cost_krw: number }[];
  daily: { date: string; tokens: number; cost_krw: number }[];
};
// GET /api/v1/billing/balance
type Balance = {
  tier: string; tier_label: string;
  monthly_base_krw: number; monthly_base_remaining: number;
  topup_krw: number; topup_remaining: number;
  used_this_cycle_krw: number; markup_pct: number; cycle_start: string | null;
};
```
- AiTokenUsageDashboard(목업)를 위 두 엔드포인트로 교체하면 실계측 표시 가능.

## 10. 미진
- 비-인터프리터 LLM 경로(현재 없음)·향후 신규 service는 `name`/service 인자 매핑 필요.
- `markup_pct`는 balance에서 노출(사용자 정책상 노출 여부는 프론트 결정). status/quote는 기존대로 배수 비노출 유지.
- ruff SIM105/UP017/I001은 코드베이스 기존 컨벤션(try/except/pass+noqa, timezone.utc) 일치 위해 미수정.
- 프로덕션DB 스키마는 앱 최초 호출 시 `ensure_schema` 자동 생성(SSH/수동 마이그레이션 불필요), 단 권한상 ALTER 가능해야 함.
