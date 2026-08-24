# 사통맵 연결 프로젝트 필지 미반영 — 근본수정 기록 (2026-07-10)

## 증상
/ko/precheck 사통팔땅 멀티지도에서 "연결 프로젝트"를 선택해도 해당 프로젝트에 등록된 필지가
좌측 선택 목록·지도 폴리곤에 반영되지 않음. 스크린샷 증거: 프로젝트=용인 신봉동인데 지도에는
이전 세션의 의정부 필지 폴리곤이 잔존하고, 선택 필지는 "아직 선택된 필지가 없습니다".

## 근본원인 (SatongMapShell.tsx)
1. **레이스+읽기단선**: `handleSelectProject` → `setProject`(동기, 로컬 스냅샷만) + `restoreSnapshot`(비동기,
   백엔드 `/projects/{id}` GET). 프로젝트 전환 이펙트(L1075)는 `[projectId]`만 의존(exhaustive-deps 비활성)
   → 백엔드 스냅샷 도착 **전에 1회만** 실행 → `storeParcels`가 비어 `setSelectedParcels([])`로 종료.
   늦게 도착한 필지를 소비할 재실행 경로가 없음.
2. **원샷 래치**: 초기 하이드레이션 이펙트(L1046)는 `hydratedRef` 원샷 가드 — sessionStorage에 이전
   선택이 있으면 이미 true로 latch되어 late seed 차단.
3. **교차 프로젝트 오염**: 프로젝트 전환 시 sessionStorage(`satong_map_selection`) 무효화 없음 →
   이전 프로젝트(의정부) 필지가 새 프로젝트(용인) 화면·재마운트에 잔존.
4. **부수결함 A**: 마운트 시 projectId=null이면 L1077이 `setSelectedParcels([])` → 약식(무프로젝트) 모드에서
   sessionStorage 복원 선택이 마운트마다 전멸.
5. **부수결함 B**: `removeParcel`의 `if (next.length > 0)` 가드 → 마지막 필지 삭제 시 sessionStorage 미갱신(잔존 부활).
6. **부수결함 C**: 레거시 단일필지 프로젝트는 `siteAnalysis.parcels[]` 부재(top-level 주소·좌표·면적만) → 시드 영원히 불가.

## 패턴 일반화 (전파방지 스윕 기준)
- P1: restoreSnapshot(비동기 복원) 직후 `[projectId]` 원샷 이펙트로 스토어를 1회만 읽는 구조
- P2: 프로젝트 전환 시 세션 캐시(선택/필지) 무효화 부재
- P3: 원샷 ref 래치가 late-arrival 스토어 데이터를 영구 차단

## 수정 (fix/satong-project-parcel-hydration)
- 공용 헬퍼 `siteAnalysisToSelection`(satong-map-selection.ts): parcels[] → 필지별 복원, 부재 시
  레거시 대표필드 1필지 폴백(무날조 — 주소 없으면 []).
- 전환 이펙트를 `[projectId, storeSiteAnalysis]` 반응형으로 재설계: 전환 감지(prevProjectIdRef 센티널)
  시 선택·sessionStorage 즉시 무효화(P2) + armed 플래그로 늦은 스냅샷 도착 시 시드(P1),
  사용자 직접 편집(추가·삭제·전체취소) 시 disarm(자동시드가 사용자 선택을 안 덮음).
  첫 마운트는 개입 안 함(부수결함 A 해소 — sessionStorage 우선순위 보존).
- removeParcel 가드 제거: 빈 배열도 sessionStorage 동기화(키 제거).

## 검증
- 단위테스트: satong-map-selection.test.ts에 siteAnalysisToSelection 4케이스 추가 → precheck 29/29 통과
- eslint 0문제(죽은 snapshots 구독도 제거) · tsc --noEmit 0에러 · next build 성공
- 전역스윕(Explore 에이전트, apps/web 전수): **P1/P2/P3 재발 0건**. 오탐 3건 트리아지
  (CADEditor seededRef=설계기하 경로라 비해당 · PreCheckWorkspace=무프로젝트 도구라 비해당 ·
  precheck handoff=read 즉시 소비). LandScheduleClient L206-246은 late-arrival을 명시 처리하는 모범 패턴.
- QA 리뷰(code-reviewer): 1차 REQUEST CHANGES — [HIGH] removeParcel 마지막 필지 삭제 시
  commitParcelsToContext([])가 no-op이라 store 필지 잔존→재마운트 부활 회귀 적발.
  → 공용 통로 `syncParcelsToStores`(빈 목록이면 updateSiteAnalysis({parcels:[],parcelCount:0}) 명시
  정리)로 add/remove/clear 3경로 통일해 해소. + 지도 튐 방지(lastSeedKeyRef 내용지문 디둡,
  projectFocusPendingRef 전환당 포커스 1회) 선제 보강.
- QA 2차 REQUEST CHANGES — [HIGH] 새 헬퍼의 주소 폴백이 parcels:[](명시적 clear)에도 발동해
  재마운트 시 주소 채널로 삭제필지 부활. → parcels 필드 존재=권위 출처(빈 배열→[]),
  부재(undefined)만 레거시 폴백으로 가드 + 회귀 테스트 추가.
- QA 3차 **APPROVE** (CRITICAL/HIGH 잔존 0, vitest 30/30).

## 결과
- 커밋 2d64949a, PR#221 (fix/satong-project-parcel-hydration)
- 세션 메모리: project_satong_project_parcel_seed_race
