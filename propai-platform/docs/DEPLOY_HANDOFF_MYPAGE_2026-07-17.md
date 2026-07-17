# 배포 인계 — 마이페이지 SaaS 계정(코인·결제·사용내역·프로필·개인정보)

> **인계 대상: main 머지·배포 담당(통합자/배포 코디)**. 작성자는 배포 권한 없음(불변규칙) —
> 아래는 기능 정체·검증 상태·배포 체크리스트다. 배포 자체는 이 문서 범위 밖.

## 1. 기능 정체 (실코드 근거)

사용자가 **잔여코인·코인내역·사용내역·결제(충전)·프로필·동의/약관**을 한 곳에서 조회·수정·관리하는
마이페이지. 기존 코인 엔진(월기본/충전 잔액·LLM 실계측) 보존하고 가산적 구축.

- **신규 백엔드**: `apps/api/app/services/billing/coin_ledger_service.py`(해시체인 원장),
  `coin_orders_service.py`(충전 주문·전상법 §6 5년 보존), `routers/billing.py`(마이페이지 엔드포인트),
  `routers/auth.py`(PATCH /me·GET /me/consents·POST /me/consents/marketing),
  `app/tasks/member_tasks.py`+`celery_app.py`(PII 파기 배치).
- **신규 마이그레이션**: `apps/api/database/migrations/versions/043_mypage_coin_orders_ledger.py`
  (down_revision=042, coin_orders·coin_ledger_events 2테이블; 서비스 lazy DDL과 문면 동일).
- **신규 프론트**: `apps/web/app/[locale]/(dashboard)/mypage/**`(5페이지), `components/mypage/**`(6컴포넌트),
  `route-registry.ts`('my' 섹션 6항목).
- **PR**: https://github.com/kangjh3kang-beep/Development_AI/pull/362 (feature/mypage-saas-account)

## 2. 검증 상태 (그린 증거)

- **성장루프 4렌즈 적대검증 14라운드 → gate_pass=true**(보안 9.6·개인정보 9.6·계약 9.6·프론트 9.6,
  확정 결함 0). R1 이후 프로덕션 착취 결함 0.
- 무-DB 전체 `pytest tests/` **7,163 passed·무-hang**(로컬 5432 기동 시 `test_disbursement_ledger::
  test_graceful_when_db_unavailable` 1건 실패는 무-DB 전제 아티팩트 — 본 브랜치 diff 무관, CI(무 5432) 통과).
- 프론트 vitest 10 + eslint·tsc clean, Next 빌드 그린, ruff clean, alembic 단일 head·업다운 가역.
- **CI(PR #362)**: Backend(pytest)·Frontend가 실제 게이트. Cloudflare Pages/Workers는 오라클 이전 후
  매 PR 실패하는 레거시(비차단, main 브랜치 보호 없음).

## 3. main 머지·배포 체크리스트

- [ ] PR #362 CI: **Backend(pytest) pass · Frontend pass** 확인(Cloudflare는 무시).
- [ ] main squash 머지.
- [ ] **DB 마이그레이션(필수)**: 프로덕션 DB에 **alembic 043 적용** — `alembic upgrade head`
      (042→043). 신규 2테이블(coin_orders·coin_ledger_events) 생성. 서비스가 lazy DDL로도
      자가 프로비저닝하나(첫 사용 시), 정식 경로는 alembic. 배포 스크립트가 `alembic upgrade`를
      포함하면 자동(참조: [[backend-a1-deploy-mechanism]] `~/deploy.sh`).
- [ ] **env(선택)**: `BILLING_SIMULATED_PAYMENTS`는 **기본 false 유지**(프로덕션). 절대 true로
      설정하지 말 것 — true는 무결제 self-충전(dev/demo 전용)을 연다.
- [ ] **celery(선택)**: 신규 beat 잡 `purge-order-pii-daily`(03:40, 구매자 PII 5년 경과·미결제
      탈퇴자 파기)는 celery worker+beat 가동 시 활성. 미가동이어도 코어 기능 무영향(파기만 지연).
- [ ] 프론트(A1)·백엔드 재배포 후 `/ko/mypage` 접근·`/api/v1/billing/packages` 200 확인.

## 4. 후속(범위 밖)

실 PG(토스 빌링키/결제창)·웹훅 연동(연동점 provider='toss'·provider_ref만 준비), 결제수단 저장 UI
(카드정보 무저장 원칙), 이메일 변경·인보이스 PDF·자동충전.

## 5. 알아둘 설계 사항

- **결제는 아직 시뮬/수동만**: 프로덕션에서 사용자 self-confirm은 501, 레거시 /topup은 403.
  실충전은 계좌이체 후 **관리자(super_admin) 수동 확정**(`POST /billing/admin/orders/{id}/confirm`)
  또는 후속 PG 연동. 마이페이지는 주문 생성 후 그 안내를 정직하게 표시한다.
- **전상법 §6/개인정보보호법 정합**: 결제기록(coin_orders)은 구매자 스냅샷 내장으로 탈퇴 익명화와
  독립 5년 보존, 경과 후 파기 배치. 마케팅 수신동의 철회(정보통신망법 §50④) 화면 제공.
- 코인 잔액 SSOT는 여전히 `users`(monthly_base_krw/topup_krw). 원장(coin_ledger_events)은 이력·감사용.
