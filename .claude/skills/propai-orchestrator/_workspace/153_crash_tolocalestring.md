# 153 — 페이지 크래시 근본원인 규명: `Cannot read properties of undefined (reading 'toLocaleString')`

작성: 2026-06-07 · 조사자: Debugger 에이전트 · 코드 수정 없음(근본원인+수정위치만)

## 결론 요약

- **merge 회귀 아님.** 수지/ROI SSOT 통합(`a19d68e`)·Phase1~2 변경의 회귀가 **아니다**. feasibilityData/costData를 읽는 모든 컴포넌트(InvestmentFeasibilityClient·BankReadyReportBuilder·ProjectAnalysisSummary·DigitalTwinAiCard·UnitMixOptimizerPanel·ProjectHealthBoard)는 전부 `?? / != null / typeof number / fmt 헬퍼`로 가드되어 있음을 코드·라이브로 확인. store merge는 항상 `null`을 채우지 `undefined`를 만들지 않으며, 모든 reader가 null을 처리한다.
- **실제 근본원인 = 부지분석 페이지의 잠재(latent) 프론트 버그.** 인근 실거래가 카드에서 `formatPriceKr(undefined)` 호출 시 크래시.

## 크래시 라우트

`/{locale}/projects/{id}/site-analysis` (부지분석) — 분석 실행 후 `stage === "result"`에서 렌더되는 `L3EnhancedCards`의 "인근 아파트 실거래가" 카드.

## 정확한 파일:라인 (undefined.toLocaleString)

크래시 함수: `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx`

```
153  function formatPriceKr(amount10k: number): string {
154    if (amount10k >= 10000) { ... }
159    return `${amount10k.toLocaleString()}만`;   // ← amount10k===undefined 이면 여기서 크래시
```

호출처(가드 부족): 같은 파일

```
429  {tx?.apt && tx.apt.count > 0 && (              // ← count>0만 검사, 가격필드 미검사
444    {formatPriceKr(tx.apt.avg_price_10k)}        // ← avg_price_10k 미존재 시 undefined 전달 → 크래시
448    {formatPriceKr(tx.apt.max_price_10k)}
452    {formatPriceKr(tx.apt.min_price_10k)}
```

타입 거짓말(런타임 보장 없음): 같은 파일

```
type NearbyTransactionSummary = {
  avg_price_10k: number;   // number로 단언하지만 응답에 키가 빠질 수 있음
  max_price_10k: number;
  min_price_10k: number;
  count: number;
  items: [...]
};
```

`formatPriceKr`는 `number`를 받는다고 선언되어 있어 `undefined`를 거르지 못한다. `undefined >= 10000`은 `false`라 두 if를 모두 통과해 line 159 `undefined.toLocaleString()`에서 크래시.

### 같은 파일 추가 잠재 후보(동일 패턴, 우선순위 낮음)
- `page.tsx:595-596` `infra.nearest_subway.distance_m.toLocaleString()` — `nearest_subway` 존재하나 `distance_m`이 빠지면 크래시. (현재 백엔드 형상에선 동시 존재하므로 즉시 위험 낮음)

## 근본원인 (데이터 흐름)

프론트 호출: `POST /api/v1/zoning/comprehensive` (page.tsx:770)
→ 라우터 `apps/api/routers/auto_zoning.py:151 comprehensive_land_analysis`
→ `LandInfoService.collect_comprehensive` → `_fetch_nearby_transactions`
(`apps/api/app/services/land_intelligence/land_info_service.py:803-914`)

- **이 정본 빌더는 내부 정합:** `count>0`이면 항상 `avg/max/min_price_10k` 동반(line 877-903). 즉 `/zoning/comprehensive` 정상 경로 단독으로는 크래시 형상을 만들지 못함. → 라이브 재현에서 정상 데이터/빈데이터 모두 크래시 없음 확인.

- **위험 원천(불일치 빌더):** `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py:527-545`
  ```
  540  "count": len(raw),                # raw 전체 건수
  541  "avg_price_10k": ... if amounts else 0,   # amounts = 가격필드 있는 항목만(534-538 필터)
  ```
  `count`는 `len(raw)`(전건), 가격은 필터된 `amounts` 기반 → 가격 파싱 0건이어도 0으로 채우긴 함(여기까진 undefined 아님). 단 이 서비스는 키가 **한글("아파트"/"오피스텔"/"연립다세대")**이라 프론트 `apt`/`land`와 불일치 → 프론트 `tx.apt`가 undefined가 되어 line 429 가드에 걸려 미렌더(크래시 회피).
  이 한글키 형상이 **파이프라인 경로**(`project_pipeline.py:310-311,415`)로 store/응답에 섞여 들어오거나, 캐시·다른 소스가 `apt` 키에 부분 형상(count만 채워진 dict)을 넣는 순간 크래시.

- **요약:** 백엔드 두 빌더(정합형 land_info vs 한글키 comprehensive_analysis)와 파이프라인 주입이 공존하고, 프론트가 가격필드 존재를 검증하지 않는 **계약 불일치**가 잠재 크래시의 근본. 사용자 환경에서 특정 부지(가격 파싱 0건 / 부분응답 / 캐시혼입)일 때 발현.

## merge 회귀 여부 판정

**회귀 아님 — 기존 잠재버그가 특정 데이터 상태에서 드러난 것.**
- 근거1: 크래시 함수/호출처(`formatPriceKr`, `tx.apt.*`)는 `a19d68e`·Phase1~2 변경 대상이 아님(site-analysis page.tsx, L3 카드).
- 근거2: feasibilityData merge는 `null`만 생성하고 모든 reader가 null 가드 보유(라이브+코드 확인). 부분병합 상태(totalCostWon=null 등)를 localStorage에 주입해 feasibility/finance/report/cost/esg/site-analysis/analytics·investment 전 라우트 순회 — 크래시 0건.
- 근거3: 신규 옵셔널 필드(equityWon/roiPct/npvWon) 모든 reader가 `?? / != null` 가드.

## 수정안 (옵셔널 가드 — 코드 미적용, 위치만)

최소 변경 2곳:

1) `page.tsx:153` `formatPriceKr` 시그니처·가드 강화(입력을 신뢰하지 않음):
```ts
function formatPriceKr(amount10k: number | null | undefined): string {
  if (amount10k == null || !Number.isFinite(amount10k)) return "—";
  ...
}
```
이 한 줄 가드로 호출처(444/448/452/461) 전부 즉시 안전.

2) (선택, 방어강화) `page.tsx:429` 렌더 가드를 가격필드까지 확장:
```ts
{tx?.apt && tx.apt.count > 0 && tx.apt.avg_price_10k != null && ( ... )}
```

3) (선택, distance 방어) `page.tsx:595-596` `infra.nearest_subway.distance_m`에 `?? 0` 또는 `!= null` 가드. 같은 파일 591-596 블록을 `infra.nearest_subway?.distance_m != null` 조건으로 보강.

4) (근본·백엔드 정합, 별도 작업) `NearbyTransactionSummary` 타입을 가격필드 `number | null`로 정직화 + 백엔드 `comprehensive_analysis_service`/`land_info_service` 두 빌더의 키(apt/land)·필드 계약 통일. 단 1)만으로 크래시는 즉시 해소.

## 검증 방법(수정 후)

- 부지분석 실행 → `/zoning/comprehensive` 응답을 `{"nearby_transactions":{"apt":{"count":5,"items":[...]}}}`(가격필드 누락)로 네트워크 mock 후 결과화면 진입 시 크래시 미발생·"—" 표기 확인.
  (본 조사에서 agent-browser `network route --body`로 해당 형상이 line 159 크래시 경로를 타는 것을 코드 추적으로 확정)

## 참조
- `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx:159` — 크래시 지점(`amount10k.toLocaleString()`)
- `…/site-analysis/page.tsx:429-452` — 가드 부족 호출처(count만 검사)
- `…/site-analysis/page.tsx`(NearbyTransactionSummary 타입) — number 단언이 런타임과 불일치
- `apps/api/app/services/land_intelligence/land_info_service.py:877-912` — 정합형 빌더(현 라이브 경로, 크래시 미발생)
- `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py:527-545` — 한글키·count/price 비대칭 위험 빌더
- `apps/api/app/services/pipeline/project_pipeline.py:310-311,415` — nearby_transactions 주입 경로
- `apps/web/store/useProjectContextStore.ts:577-592` — feasibility merge(null만 생성, 회귀 아님)
