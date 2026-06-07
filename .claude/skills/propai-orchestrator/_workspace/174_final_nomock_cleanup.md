# 174 — 최종 무목업·잔여 크래시가드 정리 (감사 173 지적)

작업 원칙: 무목업·기능보존, push/배포 금지, git add 명시경로만, 정상 happy-path 렌더 불변.

## MEDIUM

### 1. LandIntelligencePanel — 가짜 0/— 실결과 위장 제거
- 파일: `propai-platform/apps/web/components/projects/LandIntelligencePanel.tsx`
- 전: `mapBackendToModel`이 부분 응답 시 `profit_rate_pct ?? 0`·`roi_pct ?? 0`·`grade ?? "—"`·`total_revenue_won ?? 0` 등으로
  "수익률 0.0% · —등급"을 실분석결과처럼 렌더.
- 후:
  - `RecommendedModel` 타입의 수치/등급 필드를 `number | null` / `string | null`로 변경(nullable 유지).
  - `mapBackendToModel` 폴백을 `?? 0`/`?? "—"` → `?? null`로 교체(가짜 0 금지). 크래시 가드 의도는 유지.
  - 신규 헬퍼 `recommendReason(r)`: 수익률/등급이 null이면 해당 토막을 빼고, 전부 없으면 "분석 데이터 없음" 정직 표기.
  - 렌더 434/443: `r.profit_rate_pct.toFixed(1)`·`r.grade` 직접 호출 → `recommendReason(r)`로 교체.
    score는 `composite_score != null ? Math.round(...) : 0`로 null 가드.
  - 렌더 618(AI 종합 분석): top 추천의 수익률/등급이 없으면 `(...)` 메트릭 괄호 자체를 생략, 모델명만 표기.
- 무목업: 데이터 없을 때 "0.0%·—등급"이 아니라 "분석 데이터 없음"/메트릭 생략으로 정직.

### 2. site-analysis ordinance 시드 — bcr 0% 강제 금지
- 파일: `propai-platform/apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` (~743-757)
- 전: `nationalBcr: bcrFromZone ?? effBcrSeed ?? 0`, `effectiveBcr: effBcrSeed ?? 0` — bcr 미해결 시 건폐율 0%(비현실)를 실값처럼 시드.
- 후: 해당 폴백을 `?? null`로 교체. far만 해결돼도 bcr를 0으로 강제하지 않음.
- 동반 변경: `store/useProjectContextStore.ts` `OrdinanceData`의 `nationalBcr`/`nationalFar`/`effectiveBcr`/`effectiveFar`를
  `number` → `number | null`로 완화(null 시드를 타입 허용). 표시단은 기존부터 null 허용:
  - `ProjectAnalysisSummary` `pct(v: number|null|undefined)` → "—"
  - `LifecycleStageViews`/`AutoRecommendPanel` `?? null`
  - `ProjectLegalWorkspaceClient` `?? designData?.bcr ?? null`
  - `SiteAnalysisDetail`은 `n()`로 number|null 파싱, `!= null` 가드 후 렌더 → 영향 없음.
- 무목업: 미해결 한도는 0%가 아닌 "—".

## LOW

### 3. ParcelBoundaryMap primaryZone 명칭 정합
- 파일: `propai-platform/apps/web/components/map/ParcelBoundaryMap.tsx`
- `import { normalizeZoning } from "@/lib/kr-building-regulations"` 추가.
- 주 필지 라벨을 `normalizeZoning(primaryZone) ?? primaryZone`로 표준화("일반상업" → "일반상업지역"). 매칭 실패 시 원문 유지.
- 지도 라벨과 계산 측(법규 DB 표준키) 명칭 정합.

### 4. 잔여 무가드 .map 가드 (부분 응답 잠재 크래시)
- `ProjectLegalWorkspaceClient.tsx:873` `ruleResult.results.map` → `(ruleResult.results ?? []).map`
- `EnergyOperationsWorkspaceClient.tsx:728` `certificationResult.recommendations.map` → `(certificationResult.recommendations ?? []).map`
- 결과 빈배열이면 자연스러운 빈상태(무목업: 가짜 항목 주입 없음).

### 5. v2_feasibility.py 타입주석 혼선 제거
- 파일: `propai-platform/apps/api/app/routers/v2_feasibility.py` (line 40 부근)
- `current_user: User`의 실 런타임 타입은 `get_current_user`가 반환하는
  `apps.api.database.models.user.User`(tenant_id 보유). 모듈 import 교체는 순환참조 리스크가 있어
  감사 지침의 안전옵션("위험하면 주석만")을 따라 **주석만** 추가:
  실 런타임 모델/`tenant_id` 접근 정상/`from __future__ import annotations`로 힌트 미평가임을 명시.
- 런타임 무영향(주석/힌트 변경뿐).

## 검증
- 프론트: `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- 백엔드: `python3 -m py_compile app/routers/v2_feasibility.py` → **PY_COMPILE_OK**.
- import 보존 확인: `normalizeZoning` import 유지·사용 중. git diff 7파일, import 삭제 없음.

## 미진/주의
- 5번은 보수적으로 주석만 처리(런타임 동일). 추후 모듈 import를 실 런타임 모델로 교체하려면
  순환참조 검증 필요. 현재는 `from __future__ import annotations`로 힌트 미평가라 기능 영향 없음.
- 1번 nullable 전환은 `mapBackendToModel`/`recommendReason`/렌더 3곳에만 영향. 다른 소비처(roi_pct, total_revenue_won 등)는
  현재 화면 렌더에서 직접 소비하지 않아 tsc 0으로 확인됨.
