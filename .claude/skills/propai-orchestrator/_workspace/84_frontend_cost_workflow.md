# 84 · 공사비 분석 단계별 통합 워크플로우 (frontend)

루트: `propai-platform/apps/web`

## 1. 변경/삭제 파일
- 수정 `components/analytics/CostEstimationClient.tsx` — Step1~4 단계별 통합 워크플로우로 확장(몬테카를로 흡수·프로젝트명·툴팁·BIM CTA).
- 수정 `app/[locale]/(dashboard)/analytics/cost/page.tsx` — overview에서 중복 위젯 제거, 탭 명칭 쉬운말+괄호설명.
- **삭제** `components/analytics/CostAnalyticsWorkspaceClient.tsx` — overview 외 사용처 0(grep 확인) → 미사용 삭제, import 정리.

## 2. 단계별 워크플로우(Step1~4)
- **Step1 프로젝트 정보(자동연동)**: 프로젝트명(`useProjectContextStore.projectName`, UUID 아님) 헤더 표시. 건축유형·연면적·구조·지상/지하 층수를 designData/siteAnalysis에서 자동 로드, 전부 수정 가능. "프로젝트에서 자동" 배지(AutoBadge). 프로젝트 없으면 "프로젝트 정보 없음 — 부지/설계 먼저" 안내.
- **Step2 개략 공사비 산정**: `/cost/estimate-overview` 1회 호출(SSOT) → 총공사비·최저~최대 레인지·항목분해·QTO 요약·기하 적산. 결과 → `updateCostData(source:"overview")` (수지·ROI 연동, staleness 유지).
- **Step3 리스크 시뮬레이션**: 몬테카를로(P10/P50/P90·평균·표준편차·90% 신뢰구간·히스토그램)를 Step2 결과의 기대값+최저/최대 레인지로 구동. 별도 워크스페이스 위젯 흡수·제거.
- **Step4 정밀 적산(BIM 연계)**: 개략(여기) vs 정밀(BIM) 관계 명확 안내 + `/{locale}/bim-studio` CTA. 부위별 정밀 QTO/물량은 BIM 스튜디오에 위임(중복 제거).

## 3. 중복위젯 제거·몬테카를로 흡수
- overview가 두 위젯 동시 렌더(60% 중복)하던 것을 CostEstimationClient 단일 컴포넌트로 통합.
- 몬테카를로: 기존 `CostAnalyticsWorkspaceClient` 로컬 시뮬을 Step3로 흡수. 하드코딩 입력(5000/15/RC조/10000) 제거 → Step1·2 자동연동값 구동.

## 4. 로그인버그·UUID·전문용어·자동연동
- **로그인버그 제거**: `hasAccessToken:false`/`tokenHint`("로그인 필요") 상수·표시 전체 제거(컴포넌트 삭제). 인증 게이팅 불필요 — 관리자/로컬 정상 동작.
- **UUID 제거**: 프로젝트 ID 노출(구 L379) 제거 → 프로젝트명만 표시.
- **전문용어 풀이**: `Term` 컴포넌트(라벨 옆 ⓘ 호버 title+aria-label) — 연면적(GFA), 구조(RC/SRC/SC/PC), 개략 적산(QTO), 정밀 적산(BOQ), 시뮬레이션 횟수. 구조 셀렉트는 "철근콘크리트(RC)" 등 쉬운말 라벨.
- **자동연동**: 건축유형·GFA·구조·지상층수에 AutoBadge, 사용자 수정 시 배지 해제(수정됨 표시).

## 5. BIM 보완통합
- Step4에 개략 vs 정밀 2카드 비교 + "3D 모델·공사물량(BIM·적산)으로 정밀 적산하기 →" CTA(→`/{locale}/bim-studio`).
- 부위별 정밀 물량은 BIM 스튜디오에 두고 여기선 개략 QTO 요약/링크만 → 중복 제거, 단계 상승 관계 명시.

## 6. 무파괴(엔드포인트)
- `/cost/estimate-overview` 호출·`updateCostData`·staleness 유지. BOQ/대안/EVM 탭 컴포넌트 무변경(명칭만 쉬운말). feasibility/ROI 연동 경로 무변경.

## 7. tsc/eslint·import 보존
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint`(변경 2파일) → EXIT 0.
- import 전수 보존(apiClient 포함). debug/console/TODO 스캔 none.

## 8. 커밋
- 메시지: `feat(cost): 공사비 단계별 통합 워크플로우 — 중복위젯 제거·로그인버그 수정·프로젝트명 표시·자동연동/수정·전문용어 풀이·BIM 정밀적산 연계`
- 해시: (본 문서 하단/보고 참조)

## 9. 미진/후속
- 탭(BOQ·대안·EVM)은 후속 단계로 유지(명칭만 정비). 향후 Step5+로 흡수 검토 가능.
- 구조(structure) 값은 estimate-overview body에 전달되나 백엔드 반영 범위는 백엔드 소관.
