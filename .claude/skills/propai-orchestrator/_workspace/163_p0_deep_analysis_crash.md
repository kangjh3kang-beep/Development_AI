# P0 — 부지분석 "심층 분석" 크래시 근본원인·수정 (163)

## 결론 요약
- **`/site-analysis/analyze 404` 보고는 오인이다.** 프론트엔드 전수 grep 결과 `site-analysis/analyze` 문자열은 코드베이스에 **존재하지 않는다**. 실제 "심층 분석" 버튼 핸들러(`triggerDeepAnalysis`)는 `POST /api/v2/feasibility/auto-recommend`를 호출하며, 이 엔드포인트는 백엔드에 정상 존재하고 **라이브 200**을 반환한다.
- **라이브 재현 불가:** test@4t8t.net 로그인 후 실프로젝트 2건(역삼동) 부지분석에서 "심층 분석" 클릭 → 정상 결과 렌더("최적 사업모델: 일반분양 …"), 에러바운더리/콘솔에러/네트워크 실패 0건. 스크린샷 확인.
- 따라서 보고된 크래시는 (a) 스테일 빌드이거나 (b) **백엔드 부분/오류 응답 시 동기 throw하는 무가드 매핑·렌더** 경로의 데이터 조건부 크래시일 가능성이 높다. 이 유일한 진짜 크래시 벡터를 근본 차단했다.

## 404 엔드포인트 — 근본원인·정정
- 보고 `/site-analysis/analyze`: 미존재(전수 grep exit 1).
- 심층 분석 실제 호출: `apiClient.postV2("/feasibility/auto-recommend")` → `https://api.4t8t.net/api/v2/feasibility/auto-recommend`.
- 백엔드 라우트 확인: `apps/api/app/routers/v2_feasibility.py:42` prefix `/api/v2/feasibility`, `:580 @router.post("/auto-recommend")`. → 경로 정합, **404 아님**.
- 라이브 검증: 강남 역삼동/평창/파주/신안 4개 주소 모두 HTTP 200, `recommendations`·`feasibility`·`unit_summary`·`input_used`·`permit` 전부 채워짐.
- **정정 불필요(엔드포인트 정상).** 死엔드포인트 아님.

## toLocaleString 크래시 — 무가드 위치·가드
실거래/L3 카드(`page.tsx`)와 `formatPriceKr`는 이미 `?? "—"`/`Number.isFinite` 가드됨. 부지분석 결과 렌더 트리에서 **진짜 무가드 크래시 벡터 2종**을 근본 차단:

1. **`LandIntelligencePanel.tsx` `mapBackendToModel`** (구 L101–119):
   - 구코드는 `item.feasibility.profit_rate_pct`, `item.unit_summary.total_gfa_sqm`, `item.permit.complexity_label`를 무가드 접근. 백엔드가 오류/부분 아이템(중첩 객체 누락)을 1건이라도 돌려주면 `scenarioItems` useMemo·AI 종합 분석 렌더 경로(try/catch 미보호)에서 **동기 throw → 전체 페이지 에러바운더리 크래시**.
   - 수정: 중첩 객체 옵셔널 선언 + `?? {}` 폴백 + 필드별 `?? 0/"—"`. 정상 응답 동작 불변.
   - 타입 `BackendRecommendItem` 중첩 필드를 옵셔널로(런타임 가드와 일치).

2. **`ProjectSiteAnalysisWorkspaceClient.tsx`** (AVM, page.tsx 결과뷰에서 동일 화면 마운트):
   - `parcelResult.area_sqm.toLocaleString()` (L803), `comp.area_sqm.toLocaleString()` (L885) — 타입은 `number`지만 런타임 null 가능(공공API 면적 미확보). 무가드.
   - 수정: `!= null && Number.isFinite(...) ? \`${...toLocaleString()} m2\` : "—"`.

## 무목업
- 404/무자료 시 가짜값 대신 기존 정직 안내 유지(`"—"`, 에러배지). 가드는 크래시만 막고 데이터는 위조하지 않음.

## 라이브 확인
- 로그인 OK, 실프로젝트 2건 "심층 분석" 클릭 → 정상 결과 렌더, 크래시 0(스크린샷). 수정 전에도 현 배포는 정상이었음(스테일/데이터조건부 크래시 근본 차단).

## tsc
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0** (2회: 매핑 수정 후, AVM 가드 후).
- import 보존 확인(api-client/ai-analyze-client 등 그대로). diff: LandIntelligencePanel +26/-20, ProjectSiteAnalysisWorkspaceClient +2/-2.

## 변경 파일
- `propai-platform/apps/web/components/projects/LandIntelligencePanel.tsx`
- `propai-platform/apps/web/components/projects/ProjectSiteAnalysisWorkspaceClient.tsx`

## 후속(범위 외)
- 보고된 정확한 크래시 주소·프로젝트가 있으면 그 데이터로 1회 재현하면 잔여 조건 확정 가능. 현재 테스트한 주소에서는 재현 안 됨.
