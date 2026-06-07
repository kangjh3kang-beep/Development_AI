# 100. 프론트엔드 — site-analysis 부지분석 입력폼 중복 제거 + AVM 자동실행 편입

## 목표
site-analysis 페이지에 공존하던 부지분석 2벌(상단 신형 흐름 / 하단 레거시 WorkspaceClient 입력폼)을
단일화. 하단의 중복 Hero·프로젝트정보 카드·입력폼·AutoZoningBadge·ParcelBoundaryMap은 제거하되,
AVM ML 시세추정(`/avm/estimate`)·필지정보(`/external/parcel/info`)·비교거래 결과는 보존하여
상단이 확정한 주소/PNU/면적으로 자동실행해 카드로만 표시(입력 2번 금지).

## 변경 파일
1. `propai-platform/apps/web/components/projects/ProjectSiteAnalysisWorkspaceClient.tsx`
2. `propai-platform/apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx`

## auto 모드 동작 (컴포넌트)
- props 확장: optional `address?: string; pnu?: string; areaSqm?: number`.
- `autoMode = Boolean(address.trim())`. autoArea = areaSqm가 유한 양수일 때만 채택(아니면 null).
- auto 모드일 때 렌더 생략: **Hero / 프로젝트정보+입력폼 카드 / AutoZoningBadge / ParcelBoundaryMap**.
  대신 상태 배너(면적없음 안내 · 로딩 · 에러)만 + 기존 결과 카드(AVM·필지·비교거래) 렌더.
- useEffect 자동호출: `autoMode && canUseLiveApi && autoArea`일 때만
  `/avm/estimate`(body: address, area_sqm, pnu?) 호출 → 성공 시 setAvmResult.
  autoPnu 있으면 `/external/parcel/info`(body: pnu)도 호출 → setParcelResult.
  결과를 useProjectContextStore(updateSiteAnalysis + addAnalysisResult)에 반영(모세혈관).
  cleanup `cancelled` 플래그로 언마운트/주소변경 시 stale setState 방지.
- 면적 없음(autoArea null): 자동호출 보류 + "면적 정보가 있으면 AVM 자동감정이 표시됩니다" 정직 안내(무목업).
- 로딩/에러 graceful: isAutoLoading 배너, workspaceError는 extractErrorMessage(401/403=로그인 안내).
- AVM 카드 제목을 "AVM 시세 추정 (ML 자동감정)"으로 변경 + 부제 "주변 실거래(상단)와 별개의
  머신러닝 자동감정 추정치입니다."로 상단 L3 실거래와 명확 구분. EN 라벨도 동일 취지로 추가.
- 결과 카드 플레이스홀더는 모드별 분기(`resultPlaceholder`): auto 모드는 로딩/면적안내, 수동은 기존 폼 제출 안내.

## page.tsx
- 기존 898행 무조건 렌더 `<ProjectSiteAnalysisWorkspaceClient locale projectId/>` 제거.
- result stage 블록 내부 DigitalTwinScene 다음으로 이동, auto props 주입:
  `address={siteData.address} pnu={siteData.pnu}
   areaSqm={siteData.landAreaSqm ? Number(siteData.landAreaSqm) : undefined}`.
- init/analyzing stage에선 미렌더(분석 전이므로 정상). NextStageCta 최하단 유지.
- (참고) 이 파일은 세션 시작 시 이미 M 상태였음 — 상단 ModulePlaceholder 헤더 교체·import 추가는
  본 작업과 무관한 기존 미커밋 변경이며 그대로 보존함.

## 다른 사용처 grep 결과
`grep -rn ProjectSiteAnalysisWorkspaceClient` 결과 = site-analysis/page.tsx(import+사용 1곳) +
컴포넌트 정의 1곳뿐. **다른 사용처 없음.** 따라서 수동 폼 경로는 사실상 미사용이나,
하위호환을 위해 address prop이 없을 때의 기존 수동 폼 경로는 **보존**(최소 diff, 회귀 위험 0).

## 보존 / 제거 항목
- 보존: AVM 시세추정 카드, 필지정보 카드, 비교거래 테이블, MetricTile, 컨텍스트 스토어 연동, 수동 폼 경로(비활성).
- auto 모드에서 제거(미렌더): Hero, 프로젝트정보 카드, 입력폼(GlobalAddressSearch/NumberInput/Input/Button),
  AutoZoningBadge, ParcelBoundaryMap → 모두 상단 신형 흐름이 이미 커버.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: import 전부 보존(린터 트랩 통과). 신규 의존성 0. console.log/debugger/TODO/HACK 없음.
- 무목업: 면적 미존재 시 자동호출 보류+정직 안내, API 실패 시 graceful 에러만 표기.

## 미진사항
- 라이브 E2E(브라우저 실행) 미수행 — push/배포는 사용자 별도 진행 예정.
- 수동 폼 경로는 비활성 상태로 남김(사용처 0). 향후 완전 제거 가능하나 회귀 방지 위해 미삭제.
