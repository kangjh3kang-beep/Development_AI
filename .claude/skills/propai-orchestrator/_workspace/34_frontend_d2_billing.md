# D2 — 기성고 EVM + 과다청구 이상탐지 (프론트엔드)

## 1. 신규/변경 파일 · 배치
- **신규** `apps/web/components/cost/BillingDashboard.tsx` (client)
  - 기성 청구 등록 폼 + EVM 시각화 + 과다청구 이상탐지 + 청구내역/해시 무결성.
- **변경** `apps/web/components/cost/cmTypes.ts`
  - D2 타입 추가: `BillingClaim`, `EvmCurvePoint`, `EvmSummary`(spi/cpi `number|null`),
    `BillingAnomaly`, `BillingBadges`, `BillingSummaryResponse`, `BillingRegisterResponse`, `BillingRegisterRequest`.
- **변경** `apps/web/app/[locale]/(dashboard)/analytics/cost/page.tsx`
  - TABS에 `["billing","기성·EVM"]` 추가 + `{tab==="billing" && <BillingDashboard />}`.
  - pid는 컴포넌트 내부에서 `useProjectContextStore.projectId` 사용(Track A 패턴 동일).

## 2. EVM 시각화 · null 가드 · 이상탐지 표시
- **등록 폼**: 회차·공종·계약액·청구액·진행률·기간 필수, 청구단가/계약단가 선택.
  POST `/cost/{pid}/billing` → 성공 시 `anomalies_triggered` 즉시 경고(0건이면 정상 표기),
  폼 회차 자동 +1, 목록·EVM 재조회.
- **EVM**: PV/EV/AC 요약 카드 + `LineChart`(recharts, curve[] 회차별 누적 3선 PV/EV/AC).
- **SPI/CPI 게이지 배지**: `IndexBadge` — `value==null`이면 "산정불가"(PV/AC=0 안내),
  `value<0.9`이면 경고색(rose), 그 외 emerald. ★null 가드 핵심.
- **계약총액 대비 누적청구 바**: 누적청구/계약총액 비율 바, 초과 시 rose + 경고 문구.
- **과다청구 이상탐지**: `anomalies[]` 리스트 — `level==="high"` 빨강 / `warn` 주황.
  `ANOMALY_LABEL` 한글 매핑(청구단가 과다/누적청구 계약초과/일정 지연/원가 초과/청구액 급증) +
  `detail` 쉬운 설명 + `evidence` 근거 한 줄(`evidenceText`로 객체/문자/숫자 정규화).
- **무결성**: 청구 내역 테이블에 `ledger_hash` 앞 10자 + 툴팁(전체 해시), 미적재 정직 표기.
- **정직성 배지**: badges.note·unit_price_source 노출, 상단 "검토 권장 · 확정 아님".
- **상태 처리**: loading / err(조회 실패) / ok:false / no_data(badges.data 또는 claims.length===0) 분기.

## 3. 검증
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint` (BillingDashboard.tsx, cmTypes.ts, cost/page.tsx) → EXIT 0.
- apiClient import 보존, console.log/TODO/HACK/debugger 없음.
- 다크·토큰색(var(--surface-*)/--accent-strong/--line-*), 의미색 일관(high=rose/warn=amber), recharts 재사용, 기존 무파괴.

## 4. 커밋
- (회신 본문 해시 참조)

## 5. 백엔드 정합사항
- 응답 스키마 33_backend_d2_billing.md §6과 1:1 정합.
- ★`evm.spi/cpi`가 PV/AC=0일 때 `null` → `number|null` 타입 + IndexBadge null 가드 적용.
- POST body는 apiClient의 `Record<string,unknown>` 시그니처상 안전 캐스팅(`body as unknown as Record`).
- `anomaly` 단독 엔드포인트는 미사용(summary 응답에 anomalies 포함되어 충분).
