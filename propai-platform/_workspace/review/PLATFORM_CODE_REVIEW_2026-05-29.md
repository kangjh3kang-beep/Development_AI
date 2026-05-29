# 플랫폼 전체 코드리뷰 (2026-05-29)

- 범위: `apps/api`, `apps/web`, `apps/worker`, `infra`, `infrastructure`, `contracts`
- 방식: 정적 리뷰(코드/설정/배포 정의), 라인 근거 수집
- 상태: 실시간 로그 반영 완료 (`_workspace/review/LIVE_REVIEW_LOG.md`)

## CRITICAL

1. 엔트리포인트 분기로 환경별 보안/동작이 달라짐
- 근거:
  - `apps/api/Dockerfile:39` (`apps.api.main:app`)
  - `infrastructure/docker-compose/docker-compose.yml:56` (`app.main:app`)
  - `apps/api/main.py` 와 `apps/api/app/main.py`는 라우터/미들웨어/인증 구성이 다름
- 영향: 동일 배포라고 생각해도 실제 노출 API/인증 정책이 달라져 보안/기능 회귀 발생
- 해결: 실행 모듈 단일화 + CI에서 OpenAPI diff/route diff 검사

2. Refresh 토큰 발급-검증 체인 단절
- 근거:
  - 발급만 수행: `apps/api/routers/auth.py:113`, `apps/api/routers/auth.py:159`
  - 검증은 DB hash 필수: `apps/api/routers/auth.py:184-195`
- 영향: login/register 직후 refresh 재발급이 실패하여 세션 갱신 불가
- 해결: refresh 발급 시 DB 저장(해시/만료/device) 추가, revoke 로직과 일관화

3. Kakao OAuth에서 클라이언트 `tenant_id` 신뢰
- 근거:
  - 요청 스키마에 `tenant_id` 필수: `apps/api/routers/auth.py:289`
  - 콜백 처리에 그대로 전달: `apps/api/routers/auth.py:304`
  - 프론트가 URL query의 `tenant_id`를 그대로 전달: `apps/web/app/[locale]/(auth)/kakao/callback/page.tsx:11`, `apps/web/components/auth/KakaoCallbackWorkspaceClient.tsx:133`
- 영향: URL 조작으로 임의 테넌트 편입 시도 가능(멀티테넌트 경계 약화)
- 해결: OAuth state/nonce 서버검증으로 tenant를 서버에서 확정, body tenant_id 제거

## HIGH

4. Kakao refresh 저장 타입 오류
- 근거:
  - `expires_at`은 datetime 필드: `apps/api/database/models/refresh_token.py:31`
  - 실제 저장값은 정수 일수: `apps/api/auth/kakao_handler.py:200`
- 영향: OAuth 콜백 시 DB insert/type 오류 가능
- 해결: `datetime.now(UTC) + timedelta(days=...)`로 저장

5. 워커 태스크가 공통적으로 `ctx["db"]` 의존하지만 주입 누락
- 근거:
  - startup에서 `ctx["settings"]`만 주입: `apps/worker/main.py:31`
  - 태스크는 `ctx["db"]` 직접 참조: `apps/worker/tasks/parse_large_ifc.py:39` (동일 패턴 다수)
- 영향: 배치/백그라운드 태스크 실행 시 KeyError로 실패
- 해결: startup에서 세션 팩토리 주입 또는 태스크 내부 세션 생성 패턴 통일

6. K8s 환경변수/시크릿 참조 불일치
- 근거:
  - ConfigMap에 셸 치환 문자열 사용: `infra/k8s/base/configmap.yaml:9`
  - Rollout은 `database-url`, `redis-url` 키 참조: `infra/k8s/argocd/rollout.yaml:51`, `infra/k8s/argocd/rollout.yaml:56`
  - base secret은 `database-password`, `redis-password`만 정의: `infra/k8s/base/secrets.yaml:13`, `infra/k8s/base/secrets.yaml:14`
- 영향: pod 부팅 시 DB/Redis 연결정보 누락 또는 잘못된 값 주입
- 해결: Secret key 스키마 단일화 + ConfigMap에서 민감값 제거

7. 프론트 인증 토큰 저장/주입 방식이 취약
- 근거:
  - localStorage 저장: `apps/web/components/auth/AuthWorkspaceClient.tsx:354`, `apps/web/components/auth/KakaoCallbackWorkspaceClient.tsx:81`
  - public env token fallback: `apps/web/lib/api-client.ts:20`, `apps/web/lib/api-client.ts:77`
- 영향: XSS/브라우저 확장/공용PC 시 토큰 탈취면 확대, public 토큰 오배포 위험
- 해결: HttpOnly Secure SameSite 쿠키 세션 전환 + public access token 경로 제거

8. 대시보드 인증 가드 미적용
- 근거:
  - `AuthGuard` 정의만 존재: `apps/web/components/auth/AuthGuard.tsx:13`
  - 대시보드 레이아웃에 사용되지 않음: `apps/web/app/[locale]/(dashboard)/layout.tsx:131`
- 영향: UI 레벨에서 비로그인 접근 차단이 동작하지 않음
- 해결: 서버 컴포넌트 단계 인증 검사 + 미인증 리다이렉트

9. `app.main` 경로의 인증/보안 강도가 `apps.api.main` 대비 약함
- 근거:
  - CORS fallback `*` + credentials: `apps/api/app/main.py:37-39`
  - refresh가 DB revoke 없이 재발급: `apps/api/app/routers/auth.py:65-79`
- 영향: 엔트리포인트 분기 시 약한 정책이 운영에 반영될 위험
- 해결: 인증 모듈 통합, refresh/revoke 정책 단일화

## MEDIUM

10. 프론트 API 호출 레이어 혼재 (`apiClient` vs 직접 `/api/v1` fetch)
- 근거:
  - 직접 fetch 예: `apps/web/components/cad/ExportPanel.tsx:31`, `apps/web/components/cad/DesignAlternativesPanel.tsx:50`
  - 프록시 라우트는 별도 경로(`/api/proxy`)만 존재: `apps/web/app/api/proxy/[...path]/route.ts:4`
- 영향: 환경별 404/CORS/인증 헤더 누락 등 일관성 붕괴
- 해결: 모든 호출을 `apiClient`로 통일

11. SVG 직접 주입 XSS 면 존재
- 근거: `apps/web/components/cad/CadExportPanel.tsx:216` (`dangerouslySetInnerHTML`)
- 영향: 외부/오염 SVG가 섞이면 스크립트 실행 가능
- 해결: SVG sanitizer 또는 안전한 렌더링 파이프라인 적용

12. Building compliance 서비스가 실제 프로젝트 데이터 미사용
- 근거:
  - 법규값 하드코딩: `apps/api/services/building_compliance_service.py:227`
  - 대지면적 하드코딩: `apps/api/services/building_compliance_service.py:248`
- 영향: 프로젝트별 실제 법규/대지 조건이 반영되지 않아 분석 정확도 저하
- 해결: project/zone 기반 DB 조회로 대체

13. `app.main` 헬스체크가 실제 의존성 체크 없이 고정 healthy 응답
- 근거: `apps/api/app/main.py:75-89`
- 영향: 장애 탐지 실패(가짜 정상)
- 해결: DB/Redis/외부 의존성 실측 체크로 변경

14. 저장소 산출물 추적 과다
- 근거:
  - 테스트 결과물 추적: `apps/web/test-results/*` (git tracked)
  - 스마트컨트랙트 빌드 산출물 추적: `contracts/artifacts/build-info/*`, `contracts/cache/*`
- 영향: 리뷰 노이즈 증가, 저장소 비대화, 변경 추적 신뢰도 저하
- 해결: CI 산출물은 ignore/아티팩트 스토리지로 분리

## 재검증으로 해소 확인

1. `debug-keys` 노출 엔드포인트는 현재 코드 기준 제거됨
2. WebRTC signaling WS 경로는 JWT + tenant 소유권 검증 존재

## 우선 실행 순서

1. P0: 엔트리포인트 단일화 + refresh 체인 복구 + Kakao tenant 주입 차단
2. P1: 워커 DB 컨텍스트 + Kakao expires_at 타입 + K8s secret/config 정합화
3. P2: 웹 인증 저장소 전환 + 대시보드 서버측 가드 + API 호출 레이어 통일
4. P3: compliance 정확도 개선 + health/proxy 운영품질 정리
