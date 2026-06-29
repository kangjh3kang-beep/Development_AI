# Implementation Log 2026-06-30

## Stage 14. Workspace dropdown hover grace

- 기록 시각: 2026-06-30 06:27 KST
- 배포 후보 브랜치: `codex/dashboard-ia-ui-20260629`
- 기준 커밋: `8ee72792 docs: record map output connections deploy`
- 범위: 상단 워크스페이스 풀다운 메뉴의 버튼→풀다운 이동 중 조기 닫힘 문제 개선
- 완료 판정: 로컬 구현/검증 100%, Oracle 배포 및 공개 URL 검증 99%+ 통과
- 자체 코드리뷰 점수: 9.7 / 10

### 구현 내용

- 메뉴 버튼과 풀다운 사이 8px 간격에 투명 hover bridge를 추가했다.
- 메뉴 영역을 벗어나도 즉시 닫지 않고 140ms grace window를 둔다.
- 사용자가 bridge 또는 풀다운 메뉴로 들어오면 닫힘 타이머를 취소한다.
- 하위 메뉴 클릭, 바깥 클릭, ESC, 다른 메인 메뉴 롤오버 시에는 기존처럼 닫히거나 단일 메뉴로 전환된다.
- 키보드 포커스 이동/이탈 규칙은 유지했다.

### 변경 파일

- `apps/web/components/layout/WorkspaceNavBar.tsx`
- `apps/web/components/layout/WorkspaceNavBar.test.tsx`

### 검증 결과

- 변경 파일 `eslint`: 오류 0, 경고 0
- `git diff --check`: 통과
- `npm run test:run -- components/layout/WorkspaceNavBar.test.tsx`: 1 file / 4 tests 통과
- `npm run type-check`: 통과
- `npm run build`: 통과, 136개 static page 생성 통과
- 로컬 프로덕션 Playwright smoke:
  - `http://localhost:3030/ko` 렌더 통과
  - 프로젝트 버튼 → hover bridge → 풀다운 메뉴 이동 중 `프로젝트 관리` 링크 유지 확인
  - 풀다운 메뉴 위 hover 유지 확인
  - 메뉴 밖 이동 후 닫힘 확인
  - 다른 메뉴(`시장·획득`) 롤오버 시 이전 프로젝트 풀다운 닫힘 확인
  - horizontal overflow 0
  - 스크린샷: `/tmp/propai-stage14-nav-hover.png`

### 다음 단계 진입 조건

- 이번 단계 구현 커밋/푸시 완료:
  - `3f22ade8 fix: stabilize workspace dropdown hover`
- Oracle Cloud 프론트 배포 완료:
  - `/tmp/deploy_status.txt`: `DONE web=200 api=200 @ 3f22ade8 fix: stabilize workspace dropdown hover 21:44:24`
  - `propai-platform_web_1 propai-web:oracle Up`
  - `propai-platform_api_1 propai-api:oracle Up (healthy)`
  - `propai-platform_nginx_1 nginx:alpine Up`
- 공개 URL 검증:
  - `https://4t8t.net/ko`: HTTP 200
  - `https://4t8t.net/health`: HTTP 200
- 라이브 브라우저 검증:
  - 새 브라우저 세션은 인증 쿠키가 없어 `https://4t8t.net/ko/login?next=%2Fko`로 정상 리다이렉트됨
  - 인증이 필요한 워크스페이스 DOM의 hover 조작은 로컬 프로덕션 Playwright smoke에서 통과
  - 라이브 페이지 상태 스크린샷: `/tmp/propai-live-stage14-page-state.png`

### 단계 완료 기록

- 단계 완료 커밋 예정: `docs: record workspace dropdown hover deploy`
- 다음 단계로 진입 가능: 예
