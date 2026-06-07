# Phase3 — 프로젝트 완성도 헬스보드 + 가이디드 next-action (additive)

## 범위
혁신계획 132의 Phase3. 사용자가 "프로젝트가 어디까지 됐고 다음에 뭘 할지" 한눈에. additive(기존 보존), 무목업(실데이터), push/배포 금지.
**제외(범위 밖):** 수지/ROI 통합, AI인사이트 인라인(고위험·별도).

## 산출물(변경 파일)
- `components/projects/ProjectHealthBoard.tsx` (신규) — 완성도 헬스보드 카드.
- `app/[locale]/(dashboard)/projects/[id]/page.tsx` — 헬스보드 배치(dynamic import, ssr:false).
- `components/projects/ProjectAddressBar.tsx` — 완성도% 칩 보강.

## 1) 헬스보드 구성·배치
- **컴포넌트** `ProjectHealthBoard({ locale })`. `"use client"`, dynamic(ssr:false)로 코드분할(1102 부하 완화 패턴 준수).
- **배치**: 프로젝트 개요 페이지 hero 직후, `ProjectAnalysisSummary` 앞. 기존 진행레일/요약과 역할 분리(헬스보드=완성도+가이드, 요약=분석값, NextStageCta=개요 하단 순수 진입).
- **구성**:
  - 도넛 게이지(SVG circle stroke-dasharray, 토큰색 `--accent-strong`/`--line`) 중앙에 전체 % + "완성도" 라벨.
  - "doneCount / total 단계 완료" 텍스트.
  - 7단계 칩(done=✓ accent-soft / partial=◐ / todo=○ hint). 각 칩은 해당 단계 라우트로 Link(진입).
  - 하단 가이디드 next-action 영역(아래 2).

## 2) projectCompleteness 사용(Read 확인)
- 시그니처: `projectCompleteness(): ProjectCompleteness` (store L242, 구현 L701).
- 반환: `{ stages: ProjectCompletenessStage[]; doneCount; total; pct }`.
- `ProjectCompletenessStage = { key: ProjectCompletenessKey; label; done; partial? }`.
- `ProjectCompletenessKey = "site"|"design"|"cost"|"compliance"|"finance"|"esg"|"permit"` (7단계, 균등 가중).
- done 판정(무목업): site=landAreaSqm>0(주소만=partial), design=totalGfaSqm>0, cost=totalConstructionCostWon>0, compliance=complianceData 판정 존재, finance=updatedAt.finance stamp, esg=탄소>0, permit=completedStages 포함.
- 타입은 store에서 `export`됨 → `import { type ProjectCompletenessKey }`로 가져옴. store는 셀렉터/타입 Read만(편집 0).

### 키→SSOT 단계 매핑(라우트/라벨/아이콘)
셀렉터 키 일부가 라우트명과 달라 `KEY_TO_STAGE`로 정규화 후 `STAGE_META`(lib/lifecycle-stages SSOT) 사용:
- site→site-analysis, design→design, **cost→construction(시공계획)**, **compliance→legal(법규검토)**, finance→finance, esg→esg, permit→permit.
- 칩 라벨은 셀렉터의 `st.label`(부지/설계/공사비/법규/금융/ESG/인허가) 그대로, 라우트/아이콘만 STAGE_META에서.

## 3) 가이디드 next-action
- `getNextRecommendedStage()`(store, 데이터준비도 기반) 사용 → `LifecycleStage | null`.
- 결과 있으면 STAGE_META로 "다음 추천 작업: ○○ 진행하기" + 진입 CTA(accent-strong 버튼, nowrap).
- `null`(전 단계 완료)이면 "모든 추천 단계를 완료했습니다 — 라이프사이클 완료" 안내.
- NextStageCta(개요 하단)와 중복이 아니라 보완: 헬스보드는 완성도 컨텍스트 안에서 데이터준비도 기반 추천, CTA는 워크플로우 순서상 다음 단계. 둘 다 SSOT(getNextRecommendedStage/STAGE_META) 재사용.

## 4) 컨텍스트 칩바 보강
- `ProjectAddressBar`에 `projectCompleteness().pct` "완성도 N%" 칩 추가(ml-auto, accent 토큰). 기존 주소/용도지역/건폐율·용적률 표시·링크 동작 전부 보존(변경 힌트만 ml-auto→일반 흐름으로 이동, 칩이 우측 정렬 담당).

## 5) 디자인·무목업
- 디자인 토큰만 사용(다크 대비): `--accent-strong/--accent-soft/--line/--surface-soft/--surface-muted/--text-*/--shadow-*`. 하드코딩 색 0.
- 무목업: 모든 수치는 셀렉터 실데이터 파생, 데이터 없으면 0%/미완료(○)로 정직 표기.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: 3개 파일 import 보존 확인(린터 트랩 없음). ProjectHealthBoard는 신규 untracked.
- 기존 페이지 회귀: 추가만(배치 1줄+dynamic import), 기존 컴포넌트 미수정 → 회귀 0.
- StageIcon size prop·icon id(STAGE_META) 정합 확인.

## 미진/후속(범위 밖)
- 수지/ROI 통합·AI인사이트 인라인: 고위험으로 의도적 제외(별도 작업).
- 라이브 시각 검증(배포 금지 지시로 미수행) — 다음 배포 시 화면 확인 권장.
- partial(주소만 입력) 상태는 현재 site 키만 셀렉터에서 제공(다른 단계 partial은 셀렉터 확장 시 자동 반영).
