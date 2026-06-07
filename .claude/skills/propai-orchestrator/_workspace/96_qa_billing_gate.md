# 96 QA — 백엔드 과제1(과금게이트 402 사전차단 + use_llm 토글 + UserSubscription ORM) 교차검증

검증일: 2026-06-07 / 검증자: Verifier(코드 무수정, 검증·보고만) / 루트: /home/kangjh3kang/My_Projects/Development_AI
백엔드: propai-platform/apps/api / venv: apps/api/.venv (Python 3.12)

## 종합 판정: PASS (Critical 0건, WARN 2건)

신선한 증거 기준 6개 검증 포인트 전부 PASS. 정상/무료/비로그인 사용자 흐름 무파괴를 런타임 introspection·소스·테스트로 3중 확인. WARN 2건은 모두 배포 절차/사전조건(멀티헤드, alembic 미설치)이며 코드 결함 아님.

---

## 검증 포인트별 결과

### 1. enforce_llm_quota 부착 — PASS
FastAPI 라우터 런타임 introspection(`route.dependencies`에 `enforce_llm_quota` 콜러블 존재)으로 전수 확인. 6개 라우터 9개 엔드포인트 모두 게이트 부착.

| 라우터 | 엔드포인트(실경로) | gated | 근거 |
|---|---|---|---|
| routers/market_report.py | POST /api/v1/market/report, /report/pdf, /report/pptx | True×3 | market_report.py:43,52,67 (데코레이터 dependencies) |
| routers/regulation.py | POST /api/v1/regulation/analyze | True | regulation.py:36-40 |
| routers/esg.py | POST /api/v1/esg/assessment | True | esg.py:16-20 |
| routers/permits.py | POST /api/v1/permits/compliance-check, /ai-analysis | True×2 | permits.py:48-52, 208 |
| app/routers/v2_feasibility.py | POST /api/v2/feasibility/calculate, /auto-recommend | True×2 | v2_feasibility.py:77-81, 313 |
| app/routers/pipeline.py | POST /api/v2/pipeline/run | True | pipeline.py:89-93 |

런타임 덤프 발췌: `/api/v1/market/report POST gated=True`, `/api/v2/feasibility/calculate POST gated=True`, `/api/v2/feasibility/auto-recommend POST gated=True`, `/api/v2/pipeline/run POST gated=True` (그 외 동일 라우터의 미대상 엔드포인트 compare/optimize/finalize/interpret 등은 gated=False로 오부착 없음 = 정밀 부착 확인).

### 2. is_blocked 회귀안전성 (Critical) — PASS
정상/무료/비로그인 사용자 무중단을 소스+테스트로 확정.

- `is_metered_tier(tier)` = `tier in TIER_BILLING` (app/core/billing.py:151-153). `TIER_BILLING = _CONFIG["tiers"]`의 기본 키는 **{power, superpower, master}** 뿐(billing.py 기본 _DEFAULT_CONFIG tiers 확인). 따라서:
  - `is_metered_tier("guest")` = False, `is_metered_tier("free")` = False, `is_metered_tier(None)` = False → **비metered는 절대 차단 안 됨**.
- `is_blocked()` (billing_service.py:180-185): `row = await ensure_cycle(...)` → row 없으면(=DB에 사용자행 無/비회원) `return False`(통과). 있으면 `return is_metered_tier(tier) and billed >= budget` → metered AND 한도초과일 때만 True.
- `enforce_llm_quota` (billing_deps.py:15-27):
  - `uid` 없으면(비로그인) **early return**=통과(line 17-18).
  - `is_blocked` 조회 중 예외 발생 시 `except Exception: return`=통과(line 21-22, 서비스 무중단).
  - `blocked`가 True일 때만 402 raise(line 23-27).
- ensure_cycle 선행(월 롤오버 리셋, billing_service.py:107-133)으로 신규 사이클 한도 정상 반영.
- 테스트 증거: `tests/test_billing_metering.py` → **10 passed in 0.21s** (과금 회귀 0).

판정: 정상/무료/비로그인/조회예외 4개 경로 모두 통과, metered 한도초과자만 402. **회귀 위험 없음.**

### 3. 402(Payment) vs 403(Auth) 구분 — PASS
- 게이트는 `status_code=402`만 raise(billing_deps.py:25). 인증/권한은 별도 의존성(RequirePermission/get_current_user)이 403 담당(esg.py:23, permits.py:211 등). 두 관심사 분리 명확. 게이트가 403을 내지 않음 = 인증흐름 오염 없음.

### 4. use_llm 토글 (graceful) — PASS
4개 스키마 use_llm 필드(default True) + 호출부 시그니처 전달 정합 + 서비스 분기 확인.

| 스키마 | 위치 | False 분기 | 호출부 전달 |
|---|---|---|---|
| ESGAssessmentRequest | packages/schemas/models.py:928 (`use_llm: bool = True`) | esg.py:49 `if not body.use_llm: raise→ai={}` 폴백, 평가 수치는 service.assess 정상반환 | (인터프리터 게이트, 수치 무관) |
| AIPermitAnalysisRequest | routers/permits.py:205 | permit_analysis_service.py:120-125 `else self._fallback(site)`; 다필지 :210-213 규칙기반 폴백 | permits.py:222-223 `analyze(..., use_llm=req.use_llm)` |
| FeasibilityCalculateRequest | app/schemas/feasibility_v2.py:34 | /calculate 규칙기반이라 무영향(명시·전방호환) | (수치 무관) |
| AutoRecommendRequest | app/routers/v2_feasibility.py:310 | feasibility_service_v2.py:204-215 `if use_llm: ... else: result["ai_interpretation"]=None`, Top3 수치 정상 | v2_feasibility.py:317-322 `auto_recommend_top3(..., use_llm=req.use_llm)` |

서비스 시그니처: `PermitAnalysisService.analyze(..., use_llm: bool=True)` (permit_analysis_service.py:110-116), `_analyze_multi_parcel(..., use_llm)` (:185-186), `_fallback`/`_multi_parcel_fallback` static 폴백(:277,:339). `FeasibilityServiceV2.auto_recommend_top3(..., use_llm: bool=True)` (:89-95). 전부 정합. use_llm=False 시 LLM 생략·규칙기반 수치/None(graceful) 반환 확인.

### 5. UserSubscription ORM 메타데이터 분리 — PASS
- 신규 `BillingBase(DeclarativeBase)` 독립 베이스 위 `UserSubscription`(__tablename__="users") 매핑(user_subscription.py:28-41).
- **결정적 증거(canonical import 경로)**: `apps/api/.venv/bin/python -c "from apps.api.database.models.user import User; from apps.api.database.models.user_subscription import UserSubscription, BillingBase"` →
  - `OK both imported`
  - `User.metadata is BillingBase.metadata? **False**` (메타데이터 완전 분리 = 동일 'users' 테이블 이중매핑 충돌 없음)
  - `BillingBase tables: ['users']`
  - 매핑 컬럼 9개: id, tier, llm_billed_krw, billing_budget_krw, billing_cycle_start, monthly_base_krw, topup_krw, analysis_count, service_fee_krw (과금 컬럼만, 비과금 미매핑).
- `database/models/__init__.py:110,144` 에서 `apps.api.database.models.user_subscription import UserSubscription` + `__all__` 추가(additive). 메인 Base.metadata.create_all 흐름 무영향.
- billing_service는 여전히 raw SQL 사용(_SEL billing_service.py:44-48 등) → ORM과 동일 컬럼이라 정합, 동기화 부담 0.
- ★주의(WARN-1 참조): 비-canonical `database.models.*` PYTHONPATH로 import 시 'Table users already defined' 충돌이 나지만 이는 **신규 파일과 무관한 기존 듀얼패키지(database vs apps.api.database) 레이아웃 한계**다(user_subscription을 import하지 않고 `database.models.user` 단독 import만 해도 동일 충돌 재현 — app/models/auth.py와 database/models/user.py가 동일 'users' 정의). 앱 실제 import 경로(apps.api.* 또는 dual PYTHONPATH)에서는 정상.

마이그레이션 023(database/migrations/versions/023_user_subscription_columns.py):
- 8개 과금컬럼 전부 `ADD COLUMN IF NOT EXISTS`(:29-38) → 멱등, billing_service.ensure_schema 런타임 DDL과 공존.
- revision="023_user_subscription_columns", down_revision="v62_4_p6_tables"(:23-24). **v62_4_p6_tables 실재 확인**(v62_4_p6_tables.py에 revision 정의).
- 체인 무결성: 후속 `024_project_analysis_snapshot`(다른 과제)가 down_revision="023_user_subscription_columns"로 적층(024:17). 따라서 현 체인 `v62_4_p6_tables → 023 → 024` 정상.
- downgrade는 컬럼 미삭제(무손실, :46-49) — 안전.

### 6. import 스모크 + 린터 import 삭제 트랩 — PASS
- py_compile: 수정/신규 14파일(+ packages/schemas/models.py) 전부 exit 0.
- import 스모크(dual PYTHONPATH = repo root + apps/api, 앱 실제 런타임 레이아웃): `app.core.billing_deps`, `routers.market_report/regulation/esg/permits`, `app.routers.v2_feasibility/pipeline` 7모듈 전부 **OK (ALL_OK)**.
- 린터 import 삭제 트랩 회피: staged diff에 `+from app.core.billing_deps import enforce_llm_quota` **6건** 추가 확인(esg/permits/v2_feasibility/pipeline 신규 + market_report/regulation 기존). 워킹트리 grep도 6개 라우터 전부 import 라인 보존(billing_deps.py:12 import 포함). 삭제 흔적 없음.
- 테스트: tests/test_billing_metering.py **10 passed**.

---

## WARN (배포 사전조건 — 코드 결함 아님)

- **WARN-1 (멀티헤드)**: 현재 alembic heads 5개(019_spatial, 021_v62_design_tables, 022_user_project_store, 024_project_analysis_snapshot, 015_patch_s06_backup_logs). 023은 v62_4_p6_tables 위 → 024로 이어져 단일 가지로 정리됨. 그러나 전체 트리는 다중헤드(기존부터 존재). 배포 시 `alembic heads` 확인 후 필요하면 merge revision 권장. 023 자체 down_revision 타깃은 유효.
- **WARN-2 (alembic 실행 미검증)**: 본 .venv에 alembic 미설치 + 로컬 alembic/ 디렉터리가 패키지를 가려 `from alembic import op` 직접 import 불가(기존 모든 마이그레이션과 동일 제약). 023 구조는 ast/소스로 검증했으나 실제 `alembic upgrade`는 **배포 환경(Oracle)에서 사용자 직접 실행** 필요. ADD COLUMN IF NOT EXISTS 멱등이라 ensure_schema 런타임 DDL과 충돌 없음.

## 회귀 위험 평가
- 정상/무료/비로그인 사용자: 무중단 확정(포인트 2). **위험 low.**
- 기존 과금 로직(record_usage_usd/topup/get_status 등): test_billing_metering 10 passed로 회귀 0. **위험 low.**
- ORM 추가: 독립 메타데이터로 메인 흐름 무영향. **위험 low.**
- use_llm 기본 True: 기존 호출자(필드 미전송)는 True로 동작 = 기존 동작 유지(전방호환). **위험 low.**

## 권고: APPROVE
6개 검증 포인트 전부 신선한 증거로 PASS, Critical 0건. 배포 전 (a) `alembic heads`/필요시 merge, (b) Oracle에서 `alembic upgrade head` 직접 실행 2가지 운영 절차만 수행하면 됨.
