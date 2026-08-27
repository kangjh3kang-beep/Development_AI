# 토스페이먼츠 결제 체계 연동 — 계획서 (2026-08-27)

> **범위**: 결제 승인만이 아니라 **취소·환불·중복방지·보안·오류복구·관리자 매출관리**까지 한 체계.
> 사용자 요구: *"결제뿐 아니라 취소, 환불과 보안시스템이 완벽하게 구축되어야 하고 다양한 경우에도
> 오류가 발생하지 않고 중복결제되거나 오류 발생 시 해결방안 제공까지 체계적으로"*
> \+ *"관리자에 결제관련 관리페이지 … 매출관리부터 체계적인 관리시스템과 토스페이먼츠 API키 입력 필드"*

---

## 0. 옵시디언 조회 결과 (계획 게이트 §0)

`obsidian-brain` query — 주제어 `토스페이먼츠 · 결제창 · PG 연동 · 빌링키 · coin_orders`.

| 찾을 것 | 결과 |
|---|---|
| **이미 기각된 접근** | **없음**. 결제·PG 관련 설계나 기각 기록이 볼트에 없다 |
| **같은 클래스의 앞선 결함** | **있음** — §유료·비가역 산출물 규율(4얼굴 1뿌리: 다시 샀다·잃었다·사유를 버렸다·실패를 성공으로 셌다). **이 계획의 설계 원칙이 그것에서 나왔다** |
| **미결·부채** | **없음**(결제 관련) |
| **이전 판단의 근거** | `2026-08-12_PropAI_배포가_celery에_3주간_닿지_않았다.md`:305 — **프로덕션 `coin_orders` 테이블 이미 존재**(당시 0행), `coin_ledger_events` 40행. 서비스의 lazy DDL 이 alembic 043 보다 먼저 만들었다 |

★**대조군**: 같은 방법으로 `성장루프` 조회 시 **102파일** — 조회기는 살아 있다. 따라서 위 "없음"은
조회 실패가 아니라 **실제 부재**다.

---

## 1. 전제 표 — 각 전제의 *확인 방법*과 *실제 측정값*

★"확인 방법"이 없는 줄은 전제가 아니라 추측이다. 아래는 전부 실측이다.

| # | 전제 | 확인 방법 | **결과(실측)** |
|---|---|---|---|
| P1 | 기존 PG 연동이 없다 | `git grep -ril 'tosspayments\|iamport\|portone\|결제창'` 전수 | **문서 2건만**(코드 0건). 신규 연동이 맞다 |
| P2 | 그러나 **연동점은 설계돼 있다** | `docs/design/MYPAGE_SAAS_SPEC_2026-07-17.md:48,87` 원문 | *"`toss`(후속) — 빌링키/결제창 연동점. 미연동 상태에서 사용자 confirm 시도는 **501 정직 응답**"* · §6 범위 밖에 *"실 PG(토스) 연동·웹훅 — 연동점(provider='toss', provider_ref)만 준비"* |
| P3 | 주문 테이블에 PG 컬럼이 있다 | `coin_orders_service.py` `_DDL` 원문 | `provider text`, `provider_ref text` **존재** |
| P4 | ★**멱등키가 이미 있다** | 같은 파일 `_IDX` 원문 | `CREATE UNIQUE INDEX ux_coin_orders_provider_ref ON coin_orders(provider_ref) WHERE provider_ref IS NOT NULL` — 주석에 *"PG 웹훅/재시도 중복 확정 방지(멱등 키)"* 명문 |
| P5 | 확정이 원자적이다 | `confirm_order()` SQL 원문 | `UPDATE … WHERE id=:id AND user_id=:u AND status='pending' AND user_id IN (SELECT id FROM users WHERE deleted_at IS NULL) RETURNING` — 경쟁 시 **한 번만 성립** |
| P6 | 금액을 서버가 정한다 | `resolve_order_amount()` | 프리셋 키 또는 custom(범위·단위·NaN 검증). **클라이언트 금액을 그대로 안 쓴다** |
| P7 | `payment_mode` 계약이 프론트까지 흐른다 | `routers/billing.py:269,323` + `CoinsClient.tsx:117-126,138-144` | 현재 값 **2종**(`simulated`/`manual_only`). 주문 응답이 `/packages` 값을 **덮어쓴다**(단일 출처) |
| P8 | ★**CSP 가 SDK 를 막지 않는다** | 라이브 프로브 `curl -D - https://4t8t.net/ko/mypage/coins` | `content-security-policy` **0건**. 대조군 `x-frame-options` **1건**(SAMEORIGIN) → 프로브 생존. 저장소 파생 스윕·`find _headers` 도 0 |
| P9 | `next/script` 는 안 쓴다 | `grep -rn "from ['\"]next/script['\"]"` 전수 | **0건**. 표준은 수동 주입 — 정답 기준선 `lib/kakao-map.ts:25-53`(`onerror` 로 싱글턴 해제) |
| P10 | ★`ApiClientError.message` 는 사유가 아니다 | `lib/api-client.ts:432-436` | HTTP 오류의 `message` 는 **항상 상수** `"API 요청 처리에 실패했습니다."` — 사유는 `payload.detail` |
| P11 | vitest 가 새 테스트를 수집한다 | `vitest.config.ts:37` | `include: ["**/*.test.ts","**/*.test.tsx"]` — **파생형**. 어디에 두든 수집된다 |
| P12 | 키 입력 UI 를 새로 만들 필요가 없다 | `secret_store.CATALOG` + `ApiKeyManagementPanel.tsx` | CATALOG 에 항목을 넣으면 기존 패널이 **그룹별로 자동 렌더**. 추가 후 **41 → 43키 · 5 → 6그룹**(실측) |
| P13 | 코드→조치 매핑 패턴이 있다 | `lib/field-audit.ts:127-171` | `FINDING_COPY: Record<string, FindingCopy>` — 코드 키 → {문구, 심각도, 갈 곳}. **이 형태를 따른다** |
| P14 | 성장루프 이벤트 타입은 양쪽 동시 변경 | `event-collector.ts:23-42` ↔ `growth.py:34-41` + parity 테스트 | 한쪽만 바꾸면 **서버가 조용히 버린다**. → 새 타입을 **안 만들고** 기존 `api_error` 를 쓴다 |
| P15 | 토스 승인 API 계약 | `docs.tosspayments.com/reference` 실조회 | `POST /v1/payments/confirm` · `Authorization: Basic base64(secret:)` · `Idempotency-Key` 지원 · body `{paymentKey, orderId(6-64, [a-zA-Z0-9-_]), amount}` · 오류 `{code, message}` |
| P16 | 취소 API 계약 | 같은 출처 | `POST /v1/payments/{paymentKey}/cancel` · `cancelReason`(필수·200자) · `cancelAmount`(부분) · `refundReceiveAccount`(가상계좌 필수) |
| P17 | 우리 `order_no` 가 토스 규격에 맞나 | `_new_order_no()` = `CO{YYYYMMDD}-{8hex}` | **19자 · `[A-Za-z0-9-]`** → 6-64자 규격 **충족**. 추측 불가(`secrets.token_hex(4)`) |
| P18 | 웹훅 서명 검증이 가능한가 | 토스 v2 웹훅 문서 | ★**서명 없음**. → 웹훅 본문을 신뢰하지 않고 **재조회로 확정**하는 설계가 강제된다 |

---

## 2. 변경 내용과 그것이 회귀가 아닌 근거

### 2-1. 신규 (기존 동작 불변)

| 파일 | 역할 |
|---|---|
| `app/services/billing/toss_payments.py` | 벤더 클라이언트 — **모든 토스 호출의 단일 길목**(`_request`) |
| `app/services/billing/payment_receipts.py` | 영수증 원장(append-only, **독립 세션**) |
| `app/services/billing/toss_orders_service.py` | 승인/취소 오케스트레이션 — 세 결과(승인·거절·**미확정**) 분기 |
| `app/services/billing/revenue_service.py` | 매출 집계(관리자) |
| `routers/billing.py` **추가분** | `/payments/toss/config` · `/payments/toss/confirm` · `/payments/toss/webhook` · `/admin/payments/*` |
| `apps/web` 신규 | 결제 리다이렉트 2라우트 + 결제 훅 + 관리자 결제·매출 패널 |

### 2-2. 기존 수정 (회귀 아님의 근거)

| 변경 | 회귀가 아닌 근거 |
|---|---|
| `secret_store.CATALOG` += TOSS 2키 | 순수 추가. 기존 41키의 name/group/secret 불변(테스트가 파생으로 확인) |
| `payment_mode` 에 `"toss"` 추가 | 프론트가 `=== "simulated"` 로 **동등 비교**(`CoinsClient.tsx:369`)라 새 값은 기존 분기를 안 건드린다. 토스 미설정 시 **종전 두 값 그대로** |
| `/orders/{id}/confirm` 의 501 | **유지**. 토스 경로는 **별도 엔드포인트**다 — 기존 계약을 안 바꾼다 |

★**`payment_mode` 우선순위**: `toss`(키 짝 정상) > `simulated`(플래그) > `manual_only`.
토스가 설정되지 않으면 **오늘과 완전히 동일**하게 동작한다 → 미설정 환경에서 회귀 0.

---

## 3. ★검증하지 못한 것 (반드시 별도 항목 — 비워 두지 않는다)

1. **라이브 결제 미실행** — 토스 API 키가 이 환경에 **없다**(`TOSS_SECRET_KEY` 미설정, 실측).
   따라서 실제 승인/취소 왕복은 **미측정**이다. 벤더 계약은 **문서 실조회**로만 확인했다.
   → 관리자가 테스트 키를 등록한 뒤 `/admin/payments/health` 로 **실호출 진단**할 수 있게 만들었다.
2. **웹훅 실수신 미측정** — 토스 콘솔에 URL 을 등록해야 오는데 그것은 소유자 작업이다.
   서명이 없으므로 우리 설계는 *"본문을 안 믿고 재조회"* 이고, **그 로직은 단위 테스트로만 검증**했다.
3. **`Idempotency-Key` 의 벤더측 TTL 미상** — 문서에서 확인하지 못했다. 우리 설계는 벤더 멱등에
   **의존하지 않는다**(우리 쪽 유니크 인덱스 + 원자 전이가 1차 방어) — 벤더 멱등은 2차다.
4. **부분 취소 반복 횟수 상한 미상** — `balanceAmount`/`isPartialCancelable` 로 판정하도록 짰으나
   횟수 상한이 있는지는 미확인.
5. **환불 시 코인이 이미 소진된 경우의 정책** — 아래 §6 참조. **제품·법무 판단**이며 내가 정할 수 없다.
   현재 구현은 **잔액 범위 내에서만 환불 가능**하고 초과분은 **거절 + 관리자 안내**다.
6. **현금영수증·세금계산서** — 미구현. 토스 `cashReceipt` 필드가 있으나 발급 정책은 소유자 판단.
7. **프론트 vitest 실행** — 이 워크트리에 `node_modules` 없음. `pnpm install` 후 실행 필요.

---

## 4. 되돌리기 경로

- **가장 빠른 무해화**: 관리자 키 금고에서 `TOSS_SECRET_KEY` 삭제 → `is_configured()` false →
  `payment_mode` 가 종전 값으로 복귀 → **결제창이 뜨지 않고 기존 동작 그대로**. 배포 불필요.
- **코드 되돌리기**: PR revert. 신규 파일이 대부분이고 기존 수정은 §2-2 의 3건뿐.
- **데이터**: `payment_receipts` 는 append-only 신규 테이블 — 기존 데이터 미변경.
  `coin_orders` 는 **스키마 변경 없음**(기존 컬럼만 사용).

---

## 5. 잠금 — 이 변경을 지키는 검사

| # | 무엇을 잠그나 | 검사 |
|---|---|---|
| L1 | **단일 길목** — 토스 호출이 `_request` 밖으로 새지 않는다 | `test_toss_single_chokepoint.py`(ast 로 `httpx` 사용처 파생) |
| L2 | **금액 검증** — 클라이언트 금액이 벤더로 흐르지 않는다 | `test_toss_confirm_amount_verification.py`(두 모집단: 일치/불일치) |
| L3 | **IDOR** — 남의 주문을 승인할 수 없다 | 같은 파일(소유자 일치/불일치가 **다른 결과**) |
| L4 | **★미확정 ≠ 실패** | `test_toss_outcome_unknown.py`(타임아웃이 `PaymentRejected` 가 아니라 `PaymentUnresolved`) |
| L5 | **영수증이 롤백에 안 지워진다** | 독립 세션 사용을 **행위로** 확인 |
| L6 | **오류 사유가 표면까지 간다** | 코드마다 문구+조치가 **비어 있지 않다**(파생형 — 표 전수) |
| L7 | **키 위생** — 비밀키가 응답·오류에 안 실린다 | `config_status()` 반환 전수 검사 + `_redact` 행위 |
| L8 | **CATALOG 파생** | 두 TOSS 키가 그룹과 함께 존재 · 기존 41키 불변 |
| L9 | **중복 확정 불가** | 같은 payment_key 두 번 → 두 번째가 **이미 처리됨**으로 성공(멱등) · 다른 주문에 재사용 → **거절** |

---

## 6. ★소유자 판단이 필요한 사항 (내가 정하지 않았다)

1. **환불 정책** — 코인을 이미 쓴 뒤 환불 요청 시. 현재 구현: **잔액 내에서만** 환불, 초과분 거절.
   대안: 미사용분만 환불 / 전액 환불 후 음수 잔액 / 환불 불가. **법령·약관 검토 필요**.
2. **사용자 셀프 취소 허용 범위** — 현재: 결제 후 **미사용 상태**에서만 사용자가 직접 취소 가능.
   그 외는 관리자 처리.
3. **테스트 키의 프로덕션 사용** — 현재: 차단하지 않고 **관리자 화면에 크게 표시**한다.
   (차단하면 소유자가 의도적으로 테스트할 방법이 없어진다)
4. **현금영수증 발급** 여부·시점.
