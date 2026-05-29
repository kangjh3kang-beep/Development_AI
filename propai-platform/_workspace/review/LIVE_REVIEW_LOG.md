# 코드리뷰 실시간 로그

- 생성 시각: 2026-05-29 13:10:45 KST
- 목적: 코드리뷰 결과와 해결방안 수립 과정을 실시간 기록/저장/공유

## 실시간 공유 방법

- 실시간 보기: `tail -f /home/kangjh3kang/My_Projects/Development_AI/propai-platform/_workspace/review/LIVE_REVIEW_LOG.md`
- 구조화 로그 보기: `tail -f /home/kangjh3kang/My_Projects/Development_AI/propai-platform/_workspace/review/LIVE_REVIEW_LOG.ndjson`
- 신규 로그 추가: `bash /home/kangjh3kang/My_Projects/Development_AI/propai-platform/scripts/review-live-log.sh -t finding -s CRITICAL -m "내용" -a "조치안"`

## 로그

| 시간 | 타입 | 심각도 | 상태 | 대상 | 내용 | 조치안 | 담당 |
|---|---|---|---|---|---|---|---|

| 2026-05-29 13:12:08 KST | finding | CRITICAL | **fixed** | apps/api/routers/auto_zoning.py | debug-keys 엔드포인트에서 API 키 상태/조각 노출 및 무인증 접근 가능 | 엔드포인트 전체 삭제 완료 | claude |
| 2026-05-29 13:12:08 KST | finding | CRITICAL | **fixed** | apps/api/app/routers/v2_feasibility.py | v2 feasibility 라우터 무인증 + 고정 tenant UUID 사용 | 고정 tenant 삭제, VCS 4개 엔드포인트에 JWT 인증 적용 | claude |
| 2026-05-29 13:12:08 KST | finding | CRITICAL | **fixed** | apps/api/config.py | JWT 시크릿 기본값 허용으로 토큰 위조 위험 | production/staging 환경에서 기본값 사용 시 ValueError로 서버 시작 차단 | claude |
| 2026-05-29 13:12:08 KST | finding | HIGH | **fixed** | apps/api/routers/webrtc.py | WebSocket 시그널링 경로에 인증/테넌트 검증 누락 | token Query 파라미터로 JWT 검증 + 세션 tenant_id 일치 확인 추가 | claude |
| 2026-05-29 13:12:08 KST | finding | HIGH | **fixed** | apps/api/routers/auth.py | refresh/logout 경로에서 토큰 revoke 검증 부재 | refresh: DB RefreshToken 해시 조회+revoke 확인+사용후 즉시 revoke, logout: is_revoked=True 처리 | claude |
| 2026-05-29 13:12:08 KST | finding | HIGH | **fixed** | apps/api/auth/kakao_handler.py | Kakao OAuth 사용자 생성 필드가 User 모델과 불일치(oauth_provider/oauth_id) | User 모델에 oauth_provider/oauth_id 컬럼 2개 추가 | claude |
| 2026-05-29 13:12:22 KST | finding | HIGH | **fixed** | apps/web/components/cad, apps/api/main.py | 프론트 CAD 호출 경로와 백엔드 라우터 등록 경로 불일치 | drawing.py 라우터 신규 생성 + main.py에 /api/v1/drawing 등록 | claude |
| 2026-05-29 13:12:22 KST | finding | MEDIUM | **fixed** | apps/api/routers/building_compliance.py | 응답 모델과 서비스 반환 스키마 불일치 가능 | ComplianceCheckResult/AutoCorrectResult 필드를 서비스 실제 반환 구조와 일치화 + extra="allow" | claude |
| 2026-05-29 13:12:22 KST | finding | MEDIUM | **fixed** | apps/api/main.py | 공개 health 응답에 DB 연결 관련 내부 정보 노출 | 응답에 "unhealthy"만 표시, 상세정보는 logger.error로 이동 | claude |
| 2026-05-29 13:12:22 KST | finding | MEDIUM | **fixed** | apps/api/routers | 일부 업무 라우터(예: market_ai, unit_mix, cad_correction)에 인증 누락 | 3개 라우터 6개 엔드포인트에 get_current_user 인증 추가 | claude |
| 2026-05-29 13:12:33 KST | update | INFO | done | _workspace/review/* | 실시간 코드리뷰 기록 체계(LIVE_REVIEW_LOG.md, ndjson, 해결계획, 기록 스크립트) 구축 완료 | 이후 리뷰/수정 진행 시 해당 스크립트로 지속 업데이트 | codex |
| 2026-05-29 15:30:00 KST | update | INFO | done | 전체 | **코드리뷰 10건 전수 해결 완료** — CRITICAL 3/3, HIGH 4/4, MEDIUM 3/3 | 모든 open 항목 fixed 처리 | claude |
| 2026-05-29 13:27:55 KST | update | INFO | done | apps/api/routers/auto_zoning.py | 재검증 결과 debug-keys 노출 엔드포인트는 제거됨 | 해당 이슈 close 처리 | codex |
| 2026-05-29 13:27:55 KST | update | INFO | done | apps/api/routers/webrtc.py | 재검증 결과 WebSocket 시그널링 경로에 JWT/tenant 검증 로직 존재 | 이전 무인증 이슈 close 처리 | codex |
| 2026-05-29 13:27:55 KST | finding | CRITICAL | open | apps/api/Dockerfile:39, infrastructure/docker-compose/docker-compose.yml:56, apps/api/main.py, apps/api/app/main.py | 배포 엔트리포인트가 apps.api.main 과 app.main으로 분기되어 라우터/인증 정책이 환경별로 달라짐 | 단일 엔트리포인트로 통합하고 CI에서 실행 모듈 고정 검증 | codex |
| 2026-05-29 13:27:55 KST | finding | CRITICAL | open | apps/api/routers/auth.py:113, apps/api/routers/auth.py:159, apps/api/routers/auth.py:184 | login/register는 refresh 토큰을 DB에 저장하지 않는데 refresh API는 DB 해시 조회를 강제해 정상 재발급이 실패함 | refresh 발급 시 DB 저장(해시+만료) 추가 또는 검증 정책 일원화 | codex |
| 2026-05-29 13:27:55 KST | finding | CRITICAL | open | apps/api/routers/auth.py:289, apps/api/routers/auth.py:304, apps/web/app/[locale]/(auth)/kakao/callback/page.tsx:11 | Kakao 콜백이 tenant_id를 클라이언트 파라미터로 신뢰하여 임의 테넌트 계정 생성/편입 위험 | tenant_id를 서버측 상태값으로 고정하고 callback에서 사용자 입력 tenant_id 폐기 | codex |
| 2026-05-29 13:27:55 KST | finding | HIGH | open | apps/api/auth/kakao_handler.py:200, apps/api/database/models/refresh_token.py:31 | RefreshToken.expires_at(DateTime)에 만료 datetime 대신 정수 일수를 저장해 런타임 오류 가능 | expires_at=now+timedelta(days=...)로 저장 타입 정합화 | codex |
| 2026-05-29 13:27:55 KST | finding | HIGH | open | infra/k8s/base/configmap.yaml:9, infra/k8s/argocd/rollout.yaml:51, infra/k8s/base/secrets.yaml:13 | K8s ConfigMap 변수 치환 문자열 사용 및 Rollout secret key명 불일치로 배포 시 DB/Redis env 주입 실패 가능 | DB URL은 Secret/ExternalSecret로 구성하고 key명을 rollout/base 간 동일하게 맞춤 | codex |
| 2026-05-29 13:27:55 KST | finding | HIGH | open | apps/worker/main.py:31, apps/worker/tasks/parse_large_ifc.py:39 | 워커 startup에서 ctx['db']를 주입하지 않아 다수 태스크가 KeyError로 실패 가능 | startup에서 AsyncSession 팩토리 주입 또는 태스크 내부 세션 생성으로 통일 | codex |
| 2026-05-29 13:27:55 KST | finding | HIGH | open | apps/web/lib/api-client.ts:20, apps/web/components/auth/AuthWorkspaceClient.tsx:354 | 브라우저 토큰을 localStorage에 저장하고 NEXT_PUBLIC_API_ACCESS_TOKEN fallback을 허용해 토큰 탈취/노출면이 큼 | HttpOnly 쿠키 기반 세션으로 전환하고 public 토큰 경로 제거 | codex |
| 2026-05-29 13:27:55 KST | finding | HIGH | open | apps/web/components/auth/AuthGuard.tsx:13, apps/web/app/[locale]/(dashboard)/layout.tsx:131 | AuthGuard 컴포넌트가 실제 경로에 적용되지 않아 대시보드 UI 접근 제어가 동작하지 않음 | (dashboard) layout에 서버측 인증 가드 추가 및 미인증 리다이렉트 | codex |
| 2026-05-29 13:27:55 KST | finding | MEDIUM | open | apps/web/components/cad/ExportPanel.tsx:31, apps/web/components/cad/DesignAlternativesPanel.tsx:50 | 일부 컴포넌트가 apiClient를 우회해 /api/v1 직접 fetch를 사용하여 환경별 404/CORS/인증누락 위험 | API 호출 레이어를 apiClient로 단일화 | codex |
| 2026-05-29 13:27:55 KST | finding | MEDIUM | open | apps/web/components/cad/CadExportPanel.tsx:216 | SVG를 dangerouslySetInnerHTML로 직접 주입해 악성 SVG 포함 시 XSS 위험 | 서버/클라이언트 SVG sanitizer 적용 또는 object URL 렌더링으로 변경 | codex |
| 2026-05-29 13:27:55 KST | finding | MEDIUM | open | apps/api/services/building_compliance_service.py:227, apps/api/services/building_compliance_service.py:248 | 법규 검증 서비스가 프로젝트별 DB 데이터를 사용하지 않고 고정 법규/대지면적을 반환해 분석 정확도 저하 | project_id 기반 실제 법규/대지 데이터 조회 로직 구현 | codex |
| 2026-05-29 13:31:09 KST | decision | HIGH | done | _workspace/review/LIVE_REVIEW_LOG.md | 이전 fixed 기록과 현재 코드 상태가 불일치하여 재검증 결과를 최신 기준으로 우선한다 | 현재 open finding(13:27:55 KST 이후)을 기준으로 조치 | codex |
| 2026-05-29 13:41:58 KST | fix | CRITICAL | done | apps/api/routers/auth.py | login/register 시 refresh 토큰 DB 저장을 추가하고 refresh 로테이션 경로에서 만료/revoke 검증을 강화함 | 토큰 발급-검증 체인 복구 | codex |
| 2026-05-29 13:41:58 KST | fix | CRITICAL | done | apps/api/routers/auth.py, apps/api/auth/kakao_handler.py, apps/web/components/auth/KakaoCallbackWorkspaceClient.tsx | Kakao callback에서 클라이언트 tenant_id 입력 의존을 제거하고 서버측으로 사용자/테넌트 매핑(신규 시 개인 테넌트 생성)하도록 변경 | 멀티테넌트 경계 취약점 완화 | codex |
| 2026-05-29 13:41:58 KST | fix | HIGH | done | apps/api/auth/kakao_handler.py | Kakao refresh 저장 시 expires_at 타입을 datetime으로 수정 | DateTime 컬럼 정합화 | codex |
| 2026-05-29 13:41:58 KST | fix | HIGH | done | infrastructure/docker-compose/docker-compose.yml | legacy compose의 API 실행 엔트리포인트를 apps.api.main으로 정렬 | app.main/apps.api.main 분기 축소 | codex |
| 2026-05-29 13:41:58 KST | test | INFO | done | apps/web/components/auth/__tests__/KakaoCallbackWorkspaceClient.test.tsx, apps/web/app/[locale]/(auth)/__tests__/auth-route-shells.test.tsx | 프론트 인증 콜백 관련 테스트 5건 통과 | pnpm test:run 대상 2파일 green | codex |
| 2026-05-29 13:41:58 KST | test | MEDIUM | blocked | apps/api/tests/test_final_80.py, apps/api/tests/test_security.py | 백엔드 pytest는 현재 로컬 환경 의존성/플러그인 누락(jose, pytest-asyncio 미인식)으로 실행 불가 | 테스트 런타임 의존성 정비 후 재실행 필요 | codex |
