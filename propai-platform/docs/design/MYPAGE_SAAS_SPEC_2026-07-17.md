# 마이페이지(SaaS 계정·코인·결제) 스펙 — 2026-07-17

> 목표: 사용자가 **잔여코인·코인내역·사용내역·결제(충전)·프로필·동의/약관**을 한 곳에서
> 조회·수정·관리할 수 있는 SaaS 기본 골격을 구축한다. 보안 최우선, 기존 코인 엔진 보존(가산적).

## 0. 실측 전제(정찰 확정 — 무날조)

| 항목 | 현황 | 근거 |
|---|---|---|
| 코인 엔진 | **이미 존재** — 월기본(monthly_base_krw)+충전(topup_krw), 차감순서 월기본→충전 | `app/services/billing/billing_service.py` |
| 사용내역(AI) | **이미 존재** — `llm_usage_log` 실계측, `/billing/token-usage` 집계 | 동 파일 `token_usage()` |
| 충전 | `/billing/topup` **시뮬레이션 즉시증액 — 이력·주문·결제기록 없음** | `routers/billing.py:81` |
| 코인 거래 원장 | **없음** — 충전/서비스료/월부여의 append-only 이력 부재 | (부재 확인) |
| 결제 주문/기록 | **없음** — 전상법 §6(대금결제 기록 5년 보존) 대상 데이터 부재 | (부재 확인) |
| PG 연동 | **없음**(토스 등 미연동) | (부재 확인) |
| 프로필 수정 API | **없음**(GET /auth/me만) | `routers/auth.py:533` |
| 동의이력 조회 | **없음**(register가 UserConsent 저장만) | `routers/auth.py:357` |
| 마이페이지 프론트 | **없음** — /account(비번변경·탈퇴)만, 나비 레지스트리 밖 | `app/[locale]/(dashboard)/account` |

## 1. 조사 근거(유사 플랫폼)

- SaaS 빌링 표준 IA: 잔여크레딧 배너+충전 버튼 / 기간선택 사용량 차트 / 결제수단 / 결제·인보이스 이력. 청구 명세의 투명성이 신뢰의 핵심.
- OpenAI 선불 크레딧: 프리페이드 잔액→차감, 사용 페이지(일별 차트+기간 선택), 인보이스 다운로드.
- 전자상거래법 시행령 §6: **대금결제·계약 기록 5년, 분쟁 3년, 표시광고 6개월 보존**(동의 철회·탈퇴에도 보존 가능, 열람방법 미제공 시 과태료) → 결제기록은 탈퇴 익명화와 **분리 보존** 설계 필요.
- 토스페이먼츠 빌링키: 가맹점은 **카드번호를 절대 저장하지 않음**(빌링키+customerKey만) → PCI 부담 없음. 본 증분은 PG 미연동이므로 결제수단 저장 자체를 하지 않는다(연동점만 명시).

## 2. 설계 — 데이터 파이프라인

```
[충전 주문 coin_orders] --paid--> [users.topup_krw 증액] --+--> [coin_ledger_events 원장 append(동일 트랜잭션)]
[서비스료 charge_service] ------> [users.service_fee_krw] --+--> [원장 append(관측·graceful)]
[월기본 리셋 ensure_cycle] ------> [users.monthly_base_krw] -+--> [원장 append(monthly_grant)]
[LLM 사용 record_usage_usd] ----> [llm_usage_log(기존 이력)]     (원장 중복기록 안 함 — 고빈도)
                         코인내역 API = 원장 ∪ llm_usage_log 통합 타임라인
```

- **원장 `coin_ledger_events`**: append-only + 정통 해시체인(`disbursement_ledger_service` 패턴 준용,
  체인 단위=user_id). entry_type: `topup | order_paid | service_fee | monthly_grant | tier_change | admin_adjust`.
  잔액 SSOT는 기존 users 컬럼(원장은 이력·감사·설명가능성 용도) — 단 **주문 지급(order_paid)은 잔액
  증액과 같은 트랜잭션**으로 append(지급-이력 원자성).
- **주문 `coin_orders`**: pending→paid|canceled|failed. 금액은 **서버가 결정**(패키지 프리셋+자유금액
  1,000~1,000,000원). `provider_ref` 부분 유니크(중복지급 방지), 확정은
  `UPDATE … WHERE status='pending'` 원자 전이(멱등). **법정보존 스냅샷**(buyer_name/buyer_email)을
  주문 행에 내장 — 탈퇴 익명화(users)와 독립적으로 5년 보존, 개인정보처리방침 §보존기간과 연계.
- **결제 확정 경로 3종(정직)**:
  1) `simulated` — `BILLING_SIMULATED_PAYMENTS=true`(기본 **false**)일 때만 소유자 self-confirm(개발/데모).
  2) `manual` — super_admin 수동 확정(계좌이체 대응). tier 기반 판별(role 신뢰 금지).
  3) `toss`(후속) — 빌링키/결제창 연동점. 미연동 상태에서 사용자 confirm 시도는 **501 정직 응답**.
- Alembic **043**(down_revision=042) + 서비스 lazy DDL(IF NOT EXISTS, 기존 관례) 병행 — DDL 문면 동일 유지.

## 3. API (전부 인증 필수, user_id 스코프)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | /billing/packages | 충전 패키지(서버 정의 금액) |
| GET | /billing/orders | 내 결제내역(주문 목록) |
| POST | /billing/orders | 주문 생성(pending, 미결제 5건 초과 409) |
| POST | /billing/orders/{id}/confirm | 시뮬레이션 모드 한정 self-confirm(꺼짐=501) |
| POST | /billing/orders/{id}/cancel | pending 취소(소유자) |
| POST | /billing/admin/orders/{id}/confirm | 관리자 수동 지급(super_admin) |
| GET | /billing/ledger | 코인내역(원장∪llm_usage 통합, 기간·타입 필터, 페이지네이션) |
| GET | /billing/ledger/verify | 해시체인 무결성 셀프검증 |
| GET | /billing/ledger/export | CSV(포뮬러 인젝션 방어) |
| PATCH | /auth/me | 프로필 수정(name·phone, active-user 가드) |
| GET | /auth/me/consents | 동의 이력 + 현재 정책버전 |

## 4. 프론트 IA (route-registry SSOT, §5 절차 준수)

- 신설 L1 섹션 `my`(마이페이지, order 55) — 하위: 개요 `/mypage` · 코인·결제 `/mypage/coins` ·
  사용내역 `/mypage/usage` · 프로필 `/mypage/profile` · 개인정보·약관 `/mypage/privacy` ·
  계정 보안 `/account`(기존 검증 화면 재사용).
- 개요: 잔여코인(월기본/충전 분리)+충전 버튼, 잔액 부족 경고, 최근 내역 5건, 프로필 요약.
- 코인·결제: 통합 코인내역(필터·CSV·무결성 검증 배지), 충전(패키지→주문→상태 정직 표기), 결제내역.
- 사용내역: 기간선택 일별 차트 + 서비스별 집계(+각 수치의 산출근거 문구 — 설명가능성 기본).
- 개인정보·약관: 동의 이력, 약관/개인정보처리방침 링크(`/legal/terms`·`/legal/privacy`),
  **법정보존 안내 카드**(전상법 §6 — 탈퇴해도 결제기록 5년 보존), 탈퇴 링크.

## 5. 보안 요구(성장루프 검증 렌즈)

인증 필수·IDOR(user_id 스코프 강제)·삭제계정 차단(변이는 active-user 가드)·금액 서버 결정·
확정 멱등(pending 원자 전이+provider_ref 유니크)·시뮬레이션 프로드 차단(기본 off)·
관리자=tier 판별·원장 위변조 탐지(해시체인+verify)·CSV 포뮬러 인젝션 방어·PII 최소화
(카드정보 무저장·마스킹)·법정보존 vs 익명화 충돌 해소(주문 행 스냅샷).

## 6. 범위 밖(후속 명시)

- 실 PG(토스 빌링키/결제창) 연동·웹훅 — 연동점(provider='toss', provider_ref)만 준비.
- 결제수단(빌링키) 저장·관리 UI — PG 연동 후(카드정보는 어떤 형태로도 저장하지 않음).
- 이메일 변경(재인증 플로우 필요)·인보이스 PDF·자동충전.

## 7. 성장루프 적대검증 수렴 이력(7라운드, 보안 최우선 9.5 게이트)

4렌즈(보안·개인정보/법령·계약회귀·프론트) 적대검증을 반복. 확정 결함 추이 15→3→1→3→1→1→…,
보안·계약 렌즈는 6라운드 연속 9.6(착취 결함 0). 수렴한 주요 결함·수정:

- **HIGH(보안)**: 레거시 `POST /billing/topup`가 무게이트 자가충전으로 신규 결제 fail-closed 게이트
  우회 → `billing_simulated_payments` 게이트(프로덕션 403)+활성계정 가드 적용.
- **MEDIUM(계약)**: `/topup` 403화가 기존 `BillingMeter` 충전 버튼을 무음 파손 → 실패 시 마이페이지
  코인 충전 안내 배너.
- **MEDIUM(밀폐성)**: 코인원장 관측 훅이 무-DB 테스트에서 실 세션을 열던 문제 → `_record_coin_event`가
  호출자 세션 재사용(비차단·graceful).
- **MEDIUM(개인정보)**: 미결제 주문 buyer PII 과보존 → 탈퇴 회원 미결제 주문 즉시 파기 배치(§21).
- **MEDIUM(프론트 정직성)**: 오류를 '0원/내역 없음'으로 위장 → 5개 컴포넌트에 명시 오류 상태.
- **MEDIUM(프론트)**: 프로덕션에서 100% 실패하는 '결제 완료 처리' 죽은 버튼 → payment_mode 게이트.
- **LOW 다수**: 활성계정 가드(변이), 주문 상한 TOCTOU(advisory lock), CSV 401 refresh, 차트 접근성
  (sr-only 표), 마케팅 수신동의 **철회 경로**(정보통신망법 §50④), 동의이력 열람 완전성(필수동의 원본
  보장 포함), unlimited 등급 잔액 분해 은닉, 사용내역 기간전환 stale, 코인내역 필터 경합 가드.

**결과**: 착취 가능 결함 0(보안·계약 견고), 잔여는 한계적 완전성/UX LOW. 무-DB 전체 pytest 7,151 passed
무-hang, 프론트 vitest/eslint/tsc·Next 빌드 그린.
