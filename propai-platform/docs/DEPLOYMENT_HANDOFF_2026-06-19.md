# 배포 핸드오프 — 심의/설계도면 자동분석 엔진 중심엔진 통합 (2026-06-19)

배포 코디 세션 인계. 코드는 완성·9.5 게이트 통과·푸시 완료. **degrade-safe 선배포 → 키/인프라 주입 라이브 승격**
순서로 진행. 모든 단계는 정직성(무음0)·무중단 불변식 준수.

## 배포 대상(푸시 완료)
- **BFF/통합/프런트**: 브랜치 `feature/deliberation-integration` HEAD `d3ae1e8b` (origin kangjh3kang-beep/Development_AI).
- **엔진(propai-review)**: 브랜치 `feature/deliberation-review` HEAD `325babb0` (동 origin). 워크트리 services/deliberation-review.
- alembic: BFF 032(engine_run_binding)·033(shadow_comparison) 정식 마이그레이션 동반.

## A. degrade-safe 선배포 (키 없이 안전 — 즉시 가능)
1. **BFF**: engine_url 미설정 시 모든 /deliberation/* 가 HTTP200·result=null·degraded:true(무음0)로 안전 degrade. 인증·멱등·parity·테넌트격리·circuit-breaker·감사 fail-closed 동작. alembic 032/033 적용 후 배포.
2. **엔진**: 11계층 파이프라인은 mock/결정론 폴백 모드로 기동 가능(라이브 산출 아님). API_TOKEN 미설정 시 개방 — 외부 비노출 전제로 내부망 배포.
3. **프런트**: 운영 카드 4종(EngineHealth·ShadowConvergence·RegDivergence + 콘솔)은 BFF 동일출처 경유 배선 완료.
   ⚠️ **선결 확인**: `apps/web/app/[locale]/(dashboard)/deliberation-review/page.tsx`의 'PREVIEW/통합예정(engineNote)' 표기가
   실제 라이브 배선과 괴리 가능 — 배포 전 표기를 실상과 일치하게 갱신(정직성). 실코드 확인 후 갱신.

## B. 라이브 승격 (키/인프라 주입 — 운영/데이터팀)
1. **키 주입**(엔진 .env): ANTHROPIC_API_KEY · VWORLD(NED/토지이용) · MOLIT/MOLEG_API_KEY(법제처 baseline-staleness) · Qdrant · OpenAI 임베더.
2. **인프라**: Celery worker + redis broker + beat 기동(현 eager 폴백) · LIVE_NETWORK=on.
3. **중심엔진 통합 라이브**: 두 .env에 동일 API_TOKEN(≥32바이트) 수기 동일값 + BFF `deliberation_engine_url`/token 설정 + `deliberation_shadow_enabled=on`.
   - export 방식: 플랫폼 export_scoped_secrets.py --with-db → 엔진 .env.secrets → doctor live(메모리 [[simui-review-engine]] 참조).
4. **다중워커(-w>1) 시**: circuit-breaker가 프로세스 로컬이므로 redis 공유 breaker 필요(현 단일워커 전제). 다중워커 배포면 선결.
5. 승격 검증: 엔진 doctor live 200 · BFF /deliberation/health status:ok · E2E 1건(분석→리포트) 통과 · /reg/divergence 실데이터(42/42 matched 기대).

## C. 배포 후 관측·승격(운영 데이터 누적)
- reg/divergence: 플랫폼 ZONE_LIMITS vs 엔진 1차출처 drift 상시 관측(현 일치). CI drift-가드(test_zone_limits_engine_sync)가 예방.
- shadow: deliberation_shadow_enabled=on 후 도메인별 일치율 누적 → stage3 authoritative 승격(n≥500·match_rate≥0.99, docs/CENTRAL_ENGINE_STAGE3_PROMOTION.md).
- baseline-staleness: MOLEG 키 주입 시 출처 관련 법령 개정 경보. ⚠️시행령 직접 감시는 시행령 법령ID 등록(데이터 작업) 후 — 현재 inconclusive로 정직 표면화.

## D. 배포 금지(미구현 — docs/DELIBERATION_ENGINE_BENCHMARK_2026-06-19.md P5~P10)
업로드 인테이크(INC-17)·OCR(INC-18)·SMT/Z3 형식보장·bi-temporal·authoritative 승격 메커니즘은 코드 부재 — 배포 대상 아님.

## 검증 상태(인계 시점)
BFF deliberation+full_pipeline 168 passed · 엔진 434 passed · 카드 vitest 통과 · ruff(B008 관례 외 0) · INV-3 정적스캔 통과 · 9.5 적대게이트(reg-divergence·CAD·baseline-staleness·drift-가드·프런트) 전부 gate_pass(HIGH 0).
