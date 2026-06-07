# 108 — 법규검토 자동 로드 (용도지역 컨텍스트 진입 시 법정 한도 자동 표시)

## 목표
법규검토 페이지가 진입 시 부지분석 용도지역 컨텍스트로 **자동 로드**되어, 수동 클릭 없이 법정 한도(건폐율/용적률/높이 제한)를 표시한다. 무목업·실데이터.

## 대상 파일
- `propai-platform/apps/web/components/projects/ProjectLegalWorkspaceClient.tsx` (단일 파일, 92행 추가 / 2행 삭제)

## 변경내역
1. **import**: `react`에 `useRef` 추가 (다른 import 보존, 신규 의존성 0).
2. **상태 추가**:
   - `isAutoLoading` — 자동 로드 진행 상태(로딩 UI).
   - `limitsOnly` — 자동 로드 결과(계획값=0, 법정 한도만)임을 표시하는 플래그.
   - `autoLoadedKeyRef`(useRef) — `주소::용도지역` 조합당 자동호출 1회 가드.
3. **라벨 추가**(ko/en): `autoLoading`, `autoMissingZone`, `limitsOnly Note`.
4. **자동 로드 useEffect 추가**(AVM auto-run 패턴 참조):
   - 입력 출처: `siteAnalysis?.zoneCode` / `siteAnalysis?.address`(부지분석 컨텍스트, 폼 state 아님 → 폼 변경에 따른 재호출/루프 방지).
   - `POST /building-compliance/legal-check`를 계획값 0(`planned_bcr/far/height_m/floors = 0`)으로 1회 호출 → 백엔드가 planned=0이면 pass=true로 **법정 한도만** 반환.
   - cancelled 가드, finally에서 로딩 해제.
   - 성공 시 `setComplianceResult` + `setLimitsOnly(true)`.
   - 실패 시 가드 ref 해제(다음 변경에서 재시도 가능) + graceful 에러 표기(무목업, 가짜 수치 없음).
5. **수동 폼 유지**: 기존 `handleSubmit` 그대로. 수동 제출 성공 시 `setLimitsOnly(false)`로 한도-only 안내를 계획대조 결과로 전환. 컨텍스트 store 업데이트(updateComplianceData/markStageComplete/addAnalysisResult)는 수동 경로에서만 수행(자동=한도 표시 전용).
6. **결과 렌더**:
   - 결과 있음 + `limitsOnly` → 상단에 "용도지역 기준 법정 한도" 안내 배너.
   - 결과 없음 + `isAutoLoading` → SkeletonLoader + 로딩 문구.
   - 결과 없음 + 비로딩 → 용도지역 있으면 기존 placeholder, 없으면 `autoMissingZone`(미상 안내).

## 자동 로드 트리거 조건 / 중복 가드
- **트리거**: `canUseLiveApi` && `siteAnalysis.zoneCode` 존재 && `siteAnalysis.address` 존재.
- **중복 가드(무한루프 방지)**:
  - `autoLoadedKeyRef.current === key`(동일 주소+용도지역 조합) → skip.
  - `complianceResult` 이미 있음 → skip.
  - `isSubmitting`(수동 제출 진행) → skip (수동/자동 충돌 방지).
- **deps**: `[canUseLiveApi, autoZoneCode, autoAddress]` (안정적 파생값. complianceResult/isSubmitting은 deps 제외 + ref/조기반환으로 가드 → 호출 후 setComplianceResult로 인한 재실행 시 ref 일치로 즉시 skip).
- **보류**: zoneCode 미상이면 자동호출 안 함 + `autoMissingZone` 안내(기존 graceful 동작 유지).

## legal-check 엔드포인트 특이사항
- 인증 불필요·규칙기반, body에 `project_id` 없음 → 비-UUID/로컬 프로젝트 graceful(422 우려 없음). AVM과 달리 UUID 가드 불필요.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- 무한루프 점검: deps 안정 파생값 + ref 1회 가드 + 조기반환 → setComplianceResult로 인한 리렌더 시 동일 key ref 일치로 재호출 차단.
- 수동/자동 충돌: 자동은 `isSubmitting`/`complianceResult`로 skip, 수동 성공은 `limitsOnly=false`로 전환.
- import 보존: git diff 확인, `apiClient`/`SkeletonLoader` 유지, `useRef`만 추가. 신규 의존성 0.
- git diff stat: 1 file changed, 92 insertions(+), 2 deletions(-).

## 미진사항
- 자동 호출은 부지분석에서 `siteAnalysis.zoneCode`가 채워진 경우에만 동작. 부지분석 미실행 프로젝트는 한도-only 자동표시 불가(설계상 정직 안내).
- 자동 로드 결과는 컨텍스트 store에 반영하지 않음(한도 표시 전용). 단계 완료(markStageComplete)는 계획 대조 수동 제출 시에만 기록 — 의도된 동작.
- push/배포 미수행(지시대로). git add는 미수행(명시경로만 add 원칙).
