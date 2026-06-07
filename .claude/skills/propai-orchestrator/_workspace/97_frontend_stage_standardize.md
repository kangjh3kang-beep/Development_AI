# 97 · 프로젝트 단계 서브페이지 3구역 표준화

**목표:** SSOT 10단계(+contracts/drone) 서브페이지를 「①컨텍스트헤더(ModulePlaceholder) + ②위젯(기존 실패널 유지) + ③다음단계CTA(NextStageCta)」 구조로 통일.

**원칙 준수:** 무목업(기존 실데이터 위젯/WorkspaceClient 그대로 유지, 신규 목업 0). push/배포 안 함. 단계명·라벨은 `lib/lifecycle-stages` SSOT + i18n dict에서 취득(하드코딩 중복 제거). 린터 import 삭제 트랩 git diff로 확인 완료(12개 파일 전부 ModulePlaceholder/NextStageCta import 보존).

## 수정 파일 목록(절대경로 기준은 propai-platform/apps/web)

### i18n 사전(feasibility modulePlaceholder 신규 — 기존에 키 없었음)
- `public/locales/ko/common.json` — modulePlaceholders.feasibility 추가
- `public/locales/en/common.json` — 동(영문 카피)
- `public/locales/zh-CN/common.json` — 동(중문 카피)

### 표준화 필요(SSOT 10단계) — ①③ 신규 추가/교체
- `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` — 과도한 Hero(section) 제거 → ModulePlaceholder로 ①통일, 최하단 NextStageCta ③추가. ②(LandIntelligencePanel·L3카드·Terrain·Environment·DigitalTwin·WorkspaceClient) 전부 유지. Icons.Map은 결과 요약바에서 계속 사용(불용 import 없음).
- `app/[locale]/(dashboard)/projects/[id]/design/page.tsx` — 14줄 얇은 페이지 → useDictionary 도입, ① ModulePlaceholder 래핑 + ② DesignStudio 유지 + ③ NextStageCta.
- `app/[locale]/(dashboard)/projects/[id]/feasibility/page.tsx` — 과도한 Premium Hero Header → ModulePlaceholder ①통일(getDictionary). TrustBadge·FeasibilityEditorV2 정보손실 0. ③ NextStageCta.
- `app/[locale]/(dashboard)/projects/[id]/permit/page.tsx` — plain h2 타이틀 → ModulePlaceholder ①통일(useDictionary, dict 로드 전 헤더만 조건부). ② 기존 위젯(진행프로세스·체크리스트·AI알림·EnvironmentSummaryCard·DesignChangePredictPanel·WorkspaceClient) 유지. ③ NextStageCta.

### 이미 ①(ModulePlaceholder) 존재 — ③ NextStageCta만 추가
- `legal/page.tsx`, `bim/page.tsx`, `construction/page.tsx`, `finance/page.tsx`, `esg/page.tsx`, `report/page.tsx`, `contracts/page.tsx`, `drone/page.tsx`

## 3구역 충족 전/후 표

| 페이지 | ① 헤더(전→후) | ② 위젯 | ③ CTA(전→후) |
|--------|---------------|--------|---------------|
| site-analysis | 커스텀 Hero → ModulePlaceholder | 유지 | 없음 → NextStageCta |
| design | 없음 → ModulePlaceholder | DesignStudio 유지 | 없음 → NextStageCta |
| feasibility | 커스텀 Hero → ModulePlaceholder | 유지 | 없음 → NextStageCta |
| permit | h2 텍스트 → ModulePlaceholder | 유지 | 없음 → NextStageCta |
| legal | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| bim | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| construction | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| finance | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| esg | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| report | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta(최종단계 "라이프사이클 완료" 표기) |
| contracts | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |
| drone | ModulePlaceholder(유지) | 유지 | 없음 → NextStageCta |

## NextStageCta 동작 확인
- props는 `locale`만 필요. 현재 단계는 store의 `getNextRecommendedStage()`가 자동 판정 → 현재 단계 prop 전달 불필요(컴포넌트 무수정).
- `projectId` 없으면 null 렌더(컨텍스트 미바인딩 시 안전).

## 검증
- `npx tsc --noEmit` → **EXIT 0**.
- `npx eslint --no-cache <touched 12 files>` → **0 errors, 1 warning**. 유일 warning = site-analysis:813 `'i' is defined but never used`(analyzing 단계 step 맵 콜백, **내가 건드리지 않은 기존 코드** — diff 비포함 확인). 신규 위반 0.
- `git diff` → 12개 페이지 전부 ModulePlaceholder/NextStageCta import 보존(린터 삭제 트랩 없음).

## 미진사항 / 주의
- permit 페이지 ②에 기존부터 존재하던 「AI 규제 검토 알림」 하드코딩 더미(경고문구·PDF버튼)는 이번 범위(①③ 추가)가 아니라 **제거하지 않음**. 무목업 원칙상 후속 별도 작업에서 실데이터 연동 또는 제거 검토 권장.
- en/zh-CN의 finance modulePlaceholder 등 일부 기존 항목이 한국어 미번역 상태(기존부터 그러함) — feasibility 신규 항목은 각 언어로 번역 작성함.
- 비-SSOT·목업 라우트(operations/agent/cad/blockchain/multi-parcel/supervision/cost)는 지시대로 **미터치**.
