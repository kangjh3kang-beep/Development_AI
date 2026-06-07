# 164 · P1 인허가 화면 — 용도지역 전파 + AI 진단 무한로딩 근본수정

대상: `propai-platform/apps/web/app/[locale]/(dashboard)/projects/[id]/permit/page.tsx`
범위: permit 페이지 단일 파일 수정(다른 executor 담당 DesignStudio·site-analysis 미접촉).

## 증상(E2E 2차 라이브)
1. 개발방식 가능성 매트릭스(`/permits/feasibility-matrix`)가 "용도지역 없음" — zone_type 미전파.
2. AI 진단(`/permits/ai-analysis`)이 백엔드 200 정상인데 프론트가 무한 "분석중".

## 근본원인
AI 진단 `useEffect`가 **`siteAnalysis` 객체 전체를 의존성**으로 사용(`[id, siteAnalysis]`).
- Zustand 셀렉터가 반환하는 `siteAnalysis` 객체 참조가 다른 store 변경(예: feasibility-matrix 결과 저장 등 무관한 리렌더)으로 새 참조가 되면 effect가 재실행 → 이전 effect의 cleanup이 `cancelled=true` 실행.
- 동시에 `ranRef`(주소+pnu key) 가드가 동일 컨텍스트 재실행을 차단 → 진행중이던 fetch의 성공 핸들러가 `if (cancelled) return`으로 bail → `setAnalysisState("done")` 미실행.
- 결과: `analysisState`가 `"loading"`에 영구 고착(무한 분석중). 백엔드 200·응답 형상 일치에도 렌더 불가.
- 부수효과: `analysis`가 영원히 null → store `zoneCode`가 비어있는 경우 `zoneType` 폴백(`analysis?.site?.zone_type`)도 못 살아나 "용도지역 없음" 동반.

응답 형상 검증: 백엔드 `PermitAnalysisService.analyze()` 반환(`ai/summary/methods[]/recommendation/site{zone_type,max_far,...}`)은 프론트 `PermitAnalysis` 타입과 정확히 일치 → 파싱 불일치 아님. **순수 라이프사이클(effect cleanup × ranRef 가드) 고착 버그.**

## 수정 내용
`permit/page.tsx` AI 진단 effect 재작성:
1. **원시값 의존성으로 전환**: `siteAddress`/`sitePnu`(+`siteZoneCode`)를 셀렉터에서 파생, effect deps를 `[id, siteAddress, sitePnu]`로 변경. → `siteAnalysis` 객체 참조 변동에 의한 불필요한 재실행/cleanup 제거(stranding 원천 차단).
2. **요청 토큰(`active`) 패턴**: cleanup은 stale state set만 차단. 원시값 deps 하에서 effect 재실행은 주소/pnu 실변경 시뿐 → 그때는 새 요청이 정상적으로 state를 해소(고착 없음). 마운트 해제 시에는 어차피 set 불필요.
3. **site 스냅샷 캡처**: effect 시작 시점 `siteAnalysis`(주소 일치 시) 직접 캡처해 body 구성 — 요청 도중 store 참조 변동 영향 차단.
4. **zone_type 전파**: `zoneType = siteZoneCode || analysis?.site?.zone_type`. feasibility-matrix effect는 `zoneType` 의존이라, store `zoneCode` 부재 시에도 AI 진단 완료 후 폴백 zone으로 매트릭스 재조회 → "용도지역 없음" 해소. (zoneCode는 site-analysis 단계에서 store에 적재됨: ProjectSiteAnalysisWorkspaceClient.tsx, projects/[id]/page.tsx)
5. **무목업 유지**: `zoneType` null이면 기존 "부지분석을 먼저 진행하세요" 안내 그대로(가짜 표시 없음). AI 진단 미전파 시 `no-site` 안내.

try/catch는 모든 경로(성공/402 gated/에러)에서 `analysisState`를 확정 상태로 전이 → `"loading"` 잔류 경로 제거. (별도 finally 불필요: 3분기 전부 명시 set.)

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- `git diff` import 라인 변동 0건(린터 import 트랩 회피 확인).
- diff: 1 file, +23 / -11.
- push/배포 안 함. git add 미실행(명시 경로 외 변경 없음).

## 미진 / 후속
- 라이브 확인은 백엔드 SSH 배포(Oracle) 미실행으로 본 세션 미수행 — 프론트 변경만으로 동작하므로 Cloudflare 자동배포(main 푸시) 후 라이브 검증 권장.
- store `zoneCode`가 site-analysis 스냅샷 복원 경로에서 누락되는 별도 케이스가 있다면 site-analysis 담당 executor 영역(본 파일 범위 외).
