# 152 — 수지/ROI 통합(단계0~3) 회귀검증 보고

검증자: Verifier · 코드 수정 없음(검증·보고만) · 2026-06-07
대상 산출물: `151_feasibility_roi_merge_impl.md`
프론트 루트: `propai-platform/apps/web`

## 판정 요약

| # | 항목 | 판정 | 핵심 근거 |
|---|------|------|-----------|
| 1 | merge writer 정합(Critical) | **PASS** | `store/useProjectContextStore.ts:577-592` merge 구현, 5 writer 전수 무결 |
| 2 | reader 회귀0 | **PASS** | 6개 reader 기존 필드 불변·신규 필드 미참조 |
| 3 | B 읽기전용 전환 | **PASS** | `InvestmentFeasibilityClient.tsx` writer 0건, 기능 보존, graceful CTA |
| 4 | A 정본 불변 | **PASS** | `FeasibilityEditorV2.tsx` 고유기능 유지, writer가 roi/npv/equity 채움 |
| 5 | persist/snapshot 하위호환 | **PASS** | 옵셔널 추가만, snapOf/projectSync 투명 통과 |
| 6 | tsc / vitest | **PASS** | `tsc --noEmit` EXIT 0, cascade 8 passed |

**최종 verdict: PASS (배포 가). Critical 회귀 없음.**
단, 테스트 적정성 1건(WARN-low)·이력복원 경로 1건(WARN-low) — 배포 차단 아님, 후속 보강 권고.

---

## 1. merge writer 정합 (Critical) — PASS

### merge 구현 (근거: `store/useProjectContextStore.ts:577-592`)
```ts
updateFeasibilityData: (data) => {
  set((state) => withSnap(state, {
    feasibilityData: {
      totalCostWon: null, totalRevenueWon: null, profitRatePct: null, grade: null, // 베이스라인
      ...(state.feasibilityData ?? {}),  // 기존값 보존
      ...data,                            // patch 적용
    } as FeasibilityData,
    updatedAt: stampedAt(state, "feasibility"),
  }));
},
```
- 시그니처 `Partial<FeasibilityData>` (`:224`)로 부분 write 허용.
- 병합 순서가 정확: 베이스라인(전 필드 null) → 기존 state → patch. **부분 write가 기존 totalCostWon을 보존**한다.

### 회귀 해소 검증(핵심 시나리오)
- A/수지가 `totalCostWon=50억` 산출 → UnitMix가 `{totalRevenueWon}`만 patch → merge로 `totalCostWon=50억` **유지**. 이전 replace였다면 `totalCostWon` 누락(undefined)으로 `DevelopmentFinancePanel`의 `totalCostWon==null` 차단이 재발했을 것 → **해소 확인**.

### 5개 writer 전수 무결
| writer | 경로:라인 | write 형태 | merge 적합성 |
|--------|-----------|-----------|--------------|
| A (FeasibilityEditorV2) | `FeasibilityEditorV2.tsx:64-73` | 7필드 전체(cost/rev/profit/grade + roi/npv/equity) | OK — 정본, 전 필드 채움 |
| ProjectPipelinePanel | `ProjectPipelinePanel.tsx:389-394` | 4핵심필드 전체 교체 | OK — 전체 객체 동등 |
| page.tsx 이력복원 | `projects/[id]/page.tsx:110` | 4핵심필드 | OK(주: WARN-low 아래) |
| UnitMix | `UnitMixOptimizerPanel.tsx:205-207` | `{totalRevenueWon}`만 | OK — totalCostWon 보존 |
| AutoRecommend | `AutoRecommendPanel.tsx:318-322` | `{revenue, profit, grade}` | OK — totalCostWon 보존 |

### 이전 replace 의존 코드 깨짐 여부
- replace 기대(전체 교체로 옛 필드 제거) 패턴 부재. 전체 객체를 넘기던 3 writer(A/Pipeline/page)는 핵심 필드를 모두 지정하므로 merge 후 결과 동일. **깨짐 없음.**

---

## 2. reader 회귀0 — PASS

전수 reader 6종 + projectSync 점검(grep 기반):

| reader | 경로:라인 | 참조 필드 | 신규 필드 영향 |
|--------|-----------|-----------|----------------|
| DevelopmentFinancePanel | `:47,52,72,106` | `totalCostWon`(null 가드) | 무영향. 부분 writer가 더 이상 null로 덮지 않아 **차단 회귀 해소** |
| BankReadyReportBuilder | `:285-290,324` | rev/cost/profit/grade | 무영향, 기존 필드만 |
| CashflowDcfPanel | `:39,44` | `totalCostWon` 폴백 | 무영향 |
| ProjectAnalysisSummary | `:91-94,192` | cost/rev | 무영향 |
| DigitalTwinAiCard | `:49,54` | `profitRatePct` | 무영향 |
| ProjectHealthBoard | `ProjectHealthBoard.tsx:46,53` | feasibilityData 직접참조 **없음**(projectCompleteness 셀렉터만) | 무영향 |
| projectSync | `lib/projectSync.ts:36,143` | feasibilityData 객체 통째 | 옵셔널 필드 투명 통과 |

- 신규 옵셔널(`equityWon/roiPct/npvWon`)은 B(InvestmentFeasibilityClient) 외 어떤 reader도 참조하지 않음 → 기존 reader 전부 무영향.

---

## 3. B 읽기전용 전환 — PASS

근거: `components/analytics/InvestmentFeasibilityClient.tsx` 전면(147행)
- writer(`update*`) 호출 **0건** grep 확인 → 입력/calc/costStale/자동로드 useEffect 제거 완료.
- store 4개 셀렉터 구독(`:34-37`): siteAnalysis/feasibilityData/costData/projectId.
- 기능 보존:
  - ROI(`:101` roiPct), 수익률(`:100` profitRatePct), NPV(`:103` npvWon), 순이익/매출/사업비/등급(`:99-106`).
  - ROE/타인자본/실효 LTV `derived`(`:47-63`)로 보존. **ROE는 equity>0 일 때만**(`:57`), 없으면 "—"(`:102`) + 안내문(`:124-126`) — 무목업 준수.
  - VerificationBadge(`:137`)·ExpertPanelCard 7전문가(`:138-142`) 보존.
- graceful: `hasResult`(`:40-44`, revenue 또는 cost>0) false 시 CTA(`:79-91`).
- projectId 안전: `feasibilityHref`(`:65-67`) projectId 없으면 `/${locale}/projects`로 폴백. locale은 `isValidLocale` 가드(`:33`).

기능손실 0 확인. cost_breakdown 막대 제거는 store 미보유 데이터의 정직 표기(무목업)로 타당.

---

## 4. A 정본 불변 — PASS

근거: `components/feasibility/FeasibilityEditorV2.tsx`
- 고유기능 TABS 유지(`:21-26`): Intelligence Input/Analysis Report/Risk Simulation(몬테카를로)/History Ledger(버전관리).
- baseline 자동산출(`:79-90`) 시그니처 가드 유지.
- writer(`:62-77`)가 결과 산출 시 `roiPct=result.roi_pct`, `npvWon=result.npv_won`, `equityWon=input.equity_won` 채움 → A를 단일 진실원으로 ROI/NPV/equity 영속. `input` 구독 확인(`:33`).
- 완성도(`feasibilityCompleteness`) 셀렉터 구독 유지(`:47`).

---

## 5. persist/snapshot 하위호환 — PASS

- `FeasibilityData`에 옵셔널 3필드만 추가(`store:94-96`), 기존 4필드 시그니처 불변.
- `snapOf`(`:307-319`)·`ProjectSnapshot`(`:150`)은 feasibilityData를 통째로 보관 → 옵셔널 필드 자동 포함, round-trip 무손실.
- `setProject` 복원(`:511`)·`projectSync`(`:36,143`)는 `?? null` 폴백 → 구 스냅샷(신규 필드 없음)도 안전 hydrate. 하위호환 보존.

---

## 6. 빌드/타입/테스트 증거 (fresh)

| 검사 | 명령 | 결과 |
|------|------|------|
| 타입 | `npx tsc --noEmit` | **EXIT 0** (에러 0) |
| 단위 | `npx vitest run lib/useProjectContextStore.cascade.test.ts` | **8 passed / 8** (EXIT 0) |

---

## Gaps (배포 차단 아님 · 후속 권고)

- **[WARN-low] 테스트 적정성**: cascade 테스트(8건)는 staleness/isReadyForFirstCompute만 검증. **이번 Critical 변경인 merge 보존 시맨틱(부분 write 시 totalCostWon 유지)을 직접 검증하는 자동 테스트 부재.** 코드 인스펙션으로 PASS 판정했으나, 회귀 보호를 위해 `updateFeasibilityData({totalRevenueWon})` 후 `totalCostWon` 유지 단언 테스트 1건 추가 권고. — Risk: low
- **[WARN-low] 이력복원 경로(`page.tsx:110`)**: 4핵심필드만 patch하므로, 직전 state에 A가 채운 `roiPct/npvWon/equityWon`이 남아 있으면 merge로 stale 잔존 가능. 단 이 필드는 이번에 신설(이전 의존 없음)이고 이력복원은 동일 프로젝트 재진입 맥락이라 실害 경미. 원천 정합을 원하면 복원 시 `{roiPct:null, npvWon:null, equityWon:null}` 명시 권고. — Risk: low
- SSOT 이중 writer 잔존: **없음**(B는 read-only 확정, A가 정본).

## 권고

**APPROVE — 배포 가.** Critical 회귀(merge 보존·reader 차단 해소·기능손실·SSOT 이중writer) 전부 통과, tsc/vitest fresh PASS. WARN 2건은 low risk로 배포 차단 아님이며 후속 테스트 1건 추가를 권고한다.
