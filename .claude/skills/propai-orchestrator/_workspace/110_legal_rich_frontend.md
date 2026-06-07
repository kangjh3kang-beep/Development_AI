# 110 · 법규검토 페이지 종합 규제분석 고도화 (프론트)

## 목표
법규검토 페이지를 "다양한 법령·조례·상/하위법령 종합 + 항목별 이유·관련조항·분류별 + LLM 해석" 상세분석으로 고도화. 무목업·실데이터.

## 공용 컴포넌트 추출
- 신규: `propai-platform/apps/web/components/regulation/RegulationHierarchyView.tsx`
  - `RegulationsWorkspaceClient`의 다음 렌더를 **1:1 동일하게** 추출(회귀 0):
    - `RegResult`/`LimitTrio`/`HierItem`/`HierLevel`/`District`/`RegAI` 타입(전부 `export`)
    - 부지 요약 + 정량 한도(LimitCard: 법정 vs 조례 vs 실효, 조례강화 표기)
    - AI 통합 해석(AiList 4분면: 핵심제약/대응전략/기회/리스크 + summary + dev_impact)
    - 규제 계층 스택(상위법령→도시·군계획→조례→개별규제, 들여쓰기·LEVEL_META·관련조항 ref)
    - 적용 규제·지구·구역 전수(영향도 칩 상/중/하)
  - props: `{ result: RegResult, locale: Locale }`. `IMPACT_STYLE`/`LEVEL_META`/`pyeong`/`LimitCard`/`AiList` 모두 내부 이동.

## RegulationsWorkspaceClient 리팩토링(개발규제 메뉴)
- 중복 타입·렌더·서브컴포넌트(LimitCard/AiList/LEVEL_META/IMPACT_STYLE/pyeong) 제거.
- `import { RegulationHierarchyView, type RegResult }`로 대체, 본문 4개 카드 블록 → `<RegulationHierarchyView result={result} locale={locale} />` 한 줄.
- Hero/입력폼·AnalysisVerdict·ParcelBoundaryMap·ExpertPanelCard는 그대로 유지. `locale` prop을 실제 사용(기존 `_locale`).
- **동작 동일**(orphan 참조 0 확인, tsc 통과).

## 법규검토 페이지 고도화 (ProjectLegalWorkspaceClient)
- 구조: ①Hero(컨텍스트헤더, 기존 유지) → ②컨텍스트+폼(기존 유지) → ③**종합 규제분석(주, RegulationHierarchyView)** → ④정량 적합성(보조, legal-check) 순.
- **주 분석 자동 호출**: 부지분석 주소(autoAddress) 있으면 진입 시 1회 `/regulation/analyze` 호출.
  - `regLoadedKeyRef`로 `{address::zoneCode}` 조합당 1회 가드(무한루프 방지). 실패 시 가드 해제 → 재시도 가능.
  - pnu는 siteAnalysis.pnu 있으면 동봉(정확도↑), zoneCode 없어도 주소만으로 호출.
- **LLM 402 폴백**: `use_llm:true` 먼저 시도 → `ApiClientError && status===402`면 `setRegLlmGated(true)` 후 `use_llm:false` 재호출.
  - 게이트 시 계층·정량·영향도는 표시, 헤더에 "AI 통합 해석은 잔액/구독 필요" 정직 안내(무목업).
  - 402 외 에러는 throw → graceful 에러 표기.
- graceful: 주소 없음/로딩/에러/무자료 각 상태 정직 안내.

## 보조(기존 유지, 제거 금지)
- building-compliance/legal-check 자동로드(v77)·수동폼·store 환류(updateComplianceData·markStageComplete("legal")·addAnalysisResult) 전부 보존.
- 카드 라벨만 "계획값 대조 (보조)"로 명확화. 계산/환류 로직 무변경.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- import 보존 git diff 확인: 양 파일 import 블록 정상(린터 트랩 없음).
- orphan 참조(LimitCard/AiList/LEVEL_META/IMPACT_STYLE/pyeong/타입) grep → none.
- 신규 의존성 0. push/배포 안 함.

## 미진사항
- 라이브 화면 검증(브라우저)은 미수행(배포 금지 제약). `/regulation/analyze` rule-check 라우터 보강은 별도 백엔드 executor 담당(본 작업은 프론트만, 백엔드 파일 미변경).
- ProjectLegalWorkspaceClient의 영어/중국어 라벨은 신규 종합분석 섹션 헤더에 미적용(한국어 고정 — 기존 페이지도 다수 한국어 하드코딩). 필요 시 후속 i18n.
