# 95 백엔드 — 분석 명시실행 + 과금게이트(402 사전차단) + UserSubscription ORM

작업일: 2026-06-07 / 원칙: 무목업·실데이터·additive·기존 흐름 무파괴. push/배포 미수행.

## A. 과금게이트 402 사전차단

### enforce_llm_quota 부착 엔드포인트(라우터 decorator `dependencies=[Depends(enforce_llm_quota)]`)
| 라우터 파일 | 엔드포인트(메서드) | 비고 |
|---|---|---|
| routers/market_report.py | POST /api/v1/market/report, /report/pdf, /report/pptx | use_llm 토글 기존재 |
| routers/regulation.py | POST /analyze (prefix /api/v1/regulation) | use_llm 기존재 |
| routers/esg.py | POST /assessment (prefix /api/v1/esg) | use_llm 신규 추가 |
| routers/permits.py | POST /compliance-check, /ai-analysis (prefix /api/v1/permits) | /compliance-check는 규칙기반(LLM무)이나 과제 명시목록이라 부착(무해: 한도초과 metered만 차단) |
| app/routers/v2_feasibility.py | POST /api/v2/feasibility/calculate, /auto-recommend | /calculate는 규칙기반·/auto-recommend가 실제 LLM소비 → 둘 다 부착 |
| app/routers/pipeline.py | POST /api/v2/pipeline/run | |

라이브 검증(import 후 라우트 dependencies 주사): 6개 라우터 모두 의도 경로에 enforce_llm_quota 부착 확인.

### is_blocked 로직 확인 결과 (billing_service.py:180-185)
```
is_blocked = is_metered_tier(tier) AND billed >= budget
```
- ensure_cycle 선행(월 롤오버 리셋) 후 판정. row 없으면(=비회원) False=통과.
- **비metered(guest/free 등)는 항상 통과**(is_metered_tier False). metered(구독자)도 잔액(budget=monthly_base+topup) 미초과면 통과.
- enforce_llm_quota(billing_deps.py:15-27): user_id 없으면(비로그인) early return=통과 / is_blocked 조회 예외 시 통과(서비스 무중단) / blocked True일 때만 402 + 메시지("LLM 사용 한도를 초과했습니다. 추가결제 후 계속 이용하실 수 있습니다.").
- 인증실패(403, RequirePermission/get_current_user)와 분리: 게이트는 402만 발생. 정상/무료 사용자 흐름 무파괴.
- 사전(게이트=차단판정)과 사후(_record_llm_billing 실차감)는 별개 → 이중과금 아님.

## B. 명시실행(use_llm) 토글 일관화
use_llm=False면 LLM 내러티브 생략, 규칙기반 수치결과만 반환(graceful, 무목업).

| 스키마 | 위치 | 서비스 전달 |
|---|---|---|
| ESGAssessmentRequest | packages/schemas/models.py:928 (use_llm 추가) | routers/esg.py: `if not body.use_llm: raise→폴백` 으로 interpreter 생략, 평가 수치는 정상 반환 |
| AIPermitAnalysisRequest | routers/permits.py (use_llm 추가) | analyze(...use_llm=req.use_llm). PermitAnalysisService.analyze: False면 `_fallback(site)` 사용, 다필지도 `_multi_parcel_fallback(blended)`(가중평균 규칙기반) |
| FeasibilityCalculateRequest | app/schemas/feasibility_v2.py (use_llm 추가) | /calculate는 규칙기반이라 무영향(명시·전방호환). |
| AutoRecommendRequest | app/routers/v2_feasibility.py (use_llm 추가) | auto_recommend_top3(...use_llm). FeasibilityServiceV2: False면 ai_interpretation=None, Top3 수치는 정상 |

서비스 변경:
- app/services/permit/permit_analysis_service.py: analyze/_analyze_multi_parcel에 use_llm 파라미터, `_multi_parcel_fallback` static 추출(LLM 미사용/실패 공용 폴백).
- app/services/feasibility/feasibility_service_v2.py: auto_recommend_top3에 use_llm, Step5 AI해석을 `if use_llm`로 게이트.

## C. UserSubscription ORM
- 신규: database/models/user_subscription.py — `BillingBase`(독립 MetaData) 위에 `users` 테이블의 과금 컬럼만 매핑(id PK + tier/llm_billed_krw/billing_budget_krw/billing_cycle_start/monthly_base_krw/topup_krw/analysis_count/service_fee_krw).
- 설계: 별도 테이블 신설 대신 **public.users 동일 컬럼을 그대로 매핑** → billing_service raw SQL과 항상 정합(동기화 부담 0). 메인 User와 같은 테이블 충돌 회피 위해 독립 Base 사용(metadata 분리 검증 완료). 비과금 컬럼 미매핑, 모든 과금컬럼 nullable(레거시 행 안전).
- __init__.py: import + __all__에 "UserSubscription" 추가(additive). 메인 Base.metadata 무영향(autogenerate target_metadata=Base.metadata).
- 마이그레이션(작성만, **실행 안 함**): database/migrations/versions/023_user_subscription_columns.py
  - revision=023_user_subscription_columns, down_revision=v62_4_p6_tables(현 최신 head 중 하나; 멀티헤드는 기존부터 존재).
  - upgrade: 8개 과금컬럼 `ADD COLUMN IF NOT EXISTS`(billing_service.ensure_schema 런타임 DDL과 멱등 공존). downgrade: 데이터 보존 위해 컬럼 미삭제(무손실).

## 검증 결과
- py_compile: 12개 수정/신규 파일 전부 OK.
- import 스모크(PYTHONPATH=propai-platform:apps/api, apps/api/.venv):
  - User+UserSubscription 동시 import OK, metadata 분리 확인, 9개 컬럼 매핑 확인.
  - 6개 라우터 import OK, enforce_llm_quota 부착 경로 전수 확인.
  - 4개 스키마 use_llm 필드(default True) 확인. 서비스 시그니처 use_llm 전달 확인.
  - 마이그레이션 revision 체인·upgrade/downgrade 구조 검증(ast).
- git diff: enforce_llm_quota import 라인 6개 라우터 전부 보존(린터 import삭제 트랩 회피). diff stat 11파일 +98/-40.
- 테스트: apps/api/tests/test_billing_metering.py 10 passed(과금 회귀 0).
- 신규 의존성 추가 0.

## 미진사항 / 주의
- alembic은 이 .venv에 미설치 + 로컬 alembic/ 디렉터리가 패키지를 가림 → 본 환경에서 `from alembic import op` 직접 import 불가(기존 모든 마이그레이션과 동일 환경 제약). 마이그레이션은 배포 환경(Oracle)에서 alembic upgrade로 실행 필요. **사용자가 직접 실행**.
- 멀티헤드(021_v62_design_tables / 022_user_project_store / v62_4_p6_tables) 기존 존재. 023은 v62_4 위에 적층. 배포 시 `alembic heads` 확인·필요시 merge 권장.
- /compliance-check는 LLM 미소비(정적 참조표)지만 과제 명시목록이라 게이트 부착(metered 한도초과자만 402, 그 외 무영향).
- UserSubscription ORM은 표현·조회용으로 추가했고 billing_service는 여전히 raw SQL 사용(요청대로 기존 흐름 무파괴). 향후 ORM 경유 전환은 별도 과제.
