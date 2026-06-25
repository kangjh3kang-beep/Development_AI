# 🗂️ WORK_STATUS — Phase 4 (apiClient 제거) : 폐기됨 (SUPERSEDED)

> ⚠️ **이 문서의 Phase 4 계획(apiClient 제거 → `({} as T)` 치환)은 더 이상 유효하지 않습니다.**
> 2026-06-19 빌드안정화 세션에서 **폐기 확정**. 새 작업의 기준 문서가 아닙니다.
> (원래 이 파일은 2026-05-28 Antigravity AI가 IDE 간 충돌 방지용으로 쓰던 실시간 작업판이었습니다.)

---

## ❌ 폐기 사유 (2026-06-19 검증)

2026-05-28 진행하던 **"apiClient import 제거 → `apiClient.get<T>()`/`post<T>()`를 빈 객체 `({} as T)`로 치환"** 계획은,
프로젝트가 그 직후 **Mock → Live(실데이터) 전환**으로 방향을 바꾸면서 **의도적으로 폐기·역전**되었습니다.

검증으로 확인된 사실:

- `apiClient`는 제거되지 않았고 오히려 **라이브 데이터 레이어로 유지·강화**됨 (최근 2026-06-17 "폴백 단일화" 등 활발히 유지보수 중).
- 현재 `main`에서 **apiClient를 import하는 파일 184개 / 실제 API 호출 536곳**(get 277·post 234·put 8·delete 14·patch 3)이 운영 중.
- 이 계획을 지금 마저 수행하면 536개 라이브 호출이 전부 빈 객체가 되어, **전 플랫폼 실데이터가 죽고 프로젝트 핵심 원칙 "무목업·라이브검증"을 정면으로 위반**함.
- 당시 "대기 중" 파일들(`FeasibilityWorkspaceClient`, `ProjectSiteAnalysisWorkspaceClient` 등)은 이후 *"빌드 크래시 수정 — 파일 복원"*, *"빌드 깨짐 복구"* 커밋으로 **라이브 버전으로 복원**됨 → Phase 4 일괄 치환이 빌드를 깨뜨려 되돌려졌다는 증거.

➡️ **결론: apiClient는 그대로 유지한다. Phase 4(제거)는 진행하지 않는다.**

---

## ✅ 빌드 안정성 (2026-06-19 검증 결과)

- `pnpm type-check` (Next 16 typegen + `tsc --noEmit`) : **타입 에러 0건.**
  - 전제: `pnpm install`로 node_modules 동기화 + `.next` 초기화.
- 과거에 보이던 타입 에러는 전부 **stale 상태**가 원인이었음(코드 결함 아님):
  | 증상 | 진짜 원인 | 해소 |
  |------|-----------|------|
  | `react-pdf` / `livekit-client` "모듈 없음" | 워크트리 node_modules 미동기화 (루트 lockfile엔 이미 존재) | `pnpm install --frozen-lockfile` (lockfile 무변경) |
  | `(dashboard)/sales/.../workspace` validator 참조 에러 | 라우트 그룹이 `(fieldapp)`로 이동한 뒤 남은 `.next` stale 아티팩트 | `rm -rf .next` 후 재실행 |
- **현재 main은 빌드 안정 상태이며, Phase 4용 코드 수정은 필요 없음.**

---

## 📌 다른 세션 참고 — build gotcha

- 새 워크트리/머지 직후 `react-pdf`·`livekit-client` 등 **"모듈 없음" 타입에러**가 보이면 → **`pnpm install` 미실행**이 원인 (lockfile은 이미 동기화돼 있음).
- `type-check` 스크립트는 `.next/cache`만 지우므로, 라우트 이동 후 **stale validator**가 남을 수 있음 → `rm -rf .next` 후 재실행.
- `lint` 스크립트(`eslint . --no-cache`)가 `.open-next`/`.vercel`/`.next` 빌드 산출물까지 스캔해 매우 느림 → eslint ignore 정리 여지(비차단, 후속 개선 권장).

---

(이전 Phase 4 진행 기록은 git 이력 `b395cf5`, `8f1505e` 등에 보존되어 있습니다.)
