# 코드리뷰 해결방안 계획 (2026-05-29 재검증)

- 기준 로그: `_workspace/review/LIVE_REVIEW_LOG.md`
- 목적: 보안/가용성 리스크를 즉시 차단하고, 엔트리포인트/인증/운영 일관성을 단일화

## P0 (즉시 차단, 24시간)

1. API 실행 엔트리포인트 단일화
- 대상: `apps/api/main.py` vs `apps/api/app/main.py`, 배포 스크립트/컴포즈/K8s
- 조치: 단일 모듈로 통합하고 Docker/compose/k8s command를 하나로 고정
- 완료 조건: 모든 환경(dev/stage/prod)에서 동일 OpenAPI와 동일 인증 정책 확인

2. Refresh 토큰 발급/검증 체인 복구
- 대상: `apps/api/routers/auth.py`
- 조치: login/register 시 refresh 해시/만료를 DB에 저장, refresh 시 DB 검증/로테이션 유지
- 완료 조건: 로그인 직후 refresh 성공, revoke된 토큰 재사용 401

3. Kakao OAuth 테넌트 주입 취약점 차단
- 대상: `apps/api/routers/auth.py`, `apps/web/app/[locale]/(auth)/kakao/callback/page.tsx`
- 조치: callback body의 `tenant_id` 입력 제거, 서버측 state/nonce 기반 tenant 고정
- 완료 조건: URL 조작으로 타 테넌트 편입 불가

4. 민감 키 로테이션
- 대상: 로컬/운영 시크릿 저장소(특히 계약 배포용 키)
- 조치: 노출 가능성이 있는 키 전체 폐기/재발급
- 완료 조건: 구키 비활성화 확인

## P1 (고위험 안정화, 3일)

1. 워커 DB 컨텍스트 주입 보강
- 대상: `apps/worker/main.py`, `apps/worker/tasks/*`
- 조치: startup에서 `ctx["db"]` 주입 또는 각 태스크가 자체 세션 획득
- 완료 조건: `embed_regulations`, `parse_large_ifc`, `generate_report_pdf` 정상 실행

2. Kakao refresh 만료 타입 오류 수정
- 대상: `apps/api/auth/kakao_handler.py`
- 조치: `expires_at`에 `datetime` 저장(현재 정수 일수 저장 로직 제거)
- 완료 조건: OAuth 로그인 시 refresh row insert 에러 없음

3. K8s 시크릿/ConfigMap 정합화
- 대상: `infra/k8s/base/configmap.yaml`, `infra/k8s/base/secrets.yaml`, `infra/k8s/argocd/rollout.yaml`
- 조치: ConfigMap 내 `$(...)` 제거, secret key명을 rollout 참조와 일치
- 완료 조건: rollout pod 환경변수 주입 성공, 부팅 실패 재현 불가

## P2 (보안경계/품질 일관화, 1주)

1. 웹 인증 저장소 전환
- 대상: `apps/web/components/auth/*`, `apps/web/lib/api-client.ts`
- 조치: localStorage 토큰 저장 제거, HttpOnly 쿠키 기반 세션으로 전환
- 완료 조건: XSS 가정 하 토큰 탈취 불가

2. 대시보드 라우트 서버측 인증 가드 적용
- 대상: `apps/web/app/[locale]/(dashboard)/layout.tsx`
- 조치: 서버 컴포넌트 단계에서 인증 검사/리다이렉트
- 완료 조건: 비로그인 접근 시 SSR 단계에서 접근 차단

3. API 호출 레이어 단일화
- 대상: `apps/web/components/cad/*` 등 직접 `fetch("/api/v1/...)
- 조치: `apiClient` 경유로 통일 + base URL/인증헤더 공통화
- 완료 조건: 환경별 404/CORS/인증 누락 재현 불가

4. SVG 렌더링 XSS 방어
- 대상: `apps/web/components/cad/CadExportPanel.tsx`
- 조치: SVG sanitizer 또는 안전 렌더링 경로 사용
- 완료 조건: 악성 SVG payload 스크립트 실행 불가

## P3 (정확도/운영개선, 2주)

1. Building compliance 실제 데이터 연동
- 대상: `apps/api/services/building_compliance_service.py`
- 조치: 고정 site_area/limits 제거, project/zone 기반 조회 연동
- 완료 조건: 프로젝트별 입력 데이터에 따라 결과가 달라짐을 테스트로 보장

2. app/api/proxy 환경 독립성 개선
- 대상: `apps/web/app/api/proxy/[...path]/route.ts`
- 조치: 하드코딩된 `http://api:8000` 제거, 환경변수 기반 구성
- 완료 조건: 로컬/도커/클라우드에서 동일 동작

3. 산출물/테스트 결과물 버전관리 정책 정리
- 대상: `apps/web/test-results`, `contracts/artifacts`, `contracts/cache`
- 조치: CI 산출물 추적 제외 및 릴리즈 브랜치 최소화
- 완료 조건: 불필요 대용량 파일 추적 제거

## 참고

- 이전 이슈 중 `debug-keys` 노출, WebSocket 무인증은 재검증 기준으로 해소됨(로그에 close 업데이트 반영).
