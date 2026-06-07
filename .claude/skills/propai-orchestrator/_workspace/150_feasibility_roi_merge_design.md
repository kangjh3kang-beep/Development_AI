# 150 — 수지/ROI 통합 정밀설계 (SSOT 정합)

## 근본원인 (architect 확정)
- 두 수지 surface가 **동일 백엔드** `/v2/feasibility/calculate`를 쓰나 **별개 상태**.
- **A(정본)**: `FeasibilityEditorV2` + `use-feasibility-v2-store` → `updateFeasibilityData` 호출(모세혈관 연결됨).
- **B(문제)**: `InvestmentFeasibilityClient`(analytics/investment) → store를 **읽기만** 하고 `updateFeasibilityData`를 **안 씀** → 같은 프로젝트가 두 화면서 다른 숫자(SSOT 붕괴).
- 백엔드 **무변경**.

## store 사실(코드 확인)
- `updateFeasibilityData(data)`는 **replace**(`feasibilityData: data`), merge 아님.
- 다운스트림 reader `DevelopmentFinancePanel`은 `totalCostWon == null`이면 차단(:72/:101/:106).
- 부분 writer 2곳(`UnitMixOptimizerPanel:204`, `AutoRecommendPanel:318`)이 `totalCostWon: null`로 **A가 산출한 cost를 파괴** → 금융 패널 회귀.

## 설계 결정
1. **정본 = A**. B를 정본 store 구독 read-only ROI 뷰로 강등.
2. `FeasibilityData`에 `equityWon? / roiPct? / npvWon?` **옵셔널** 추가(하위호환, reader 무영향, persist round-trip 보존).
3. `updateFeasibilityData`를 **merge**(`Partial<FeasibilityData>`)로 전환 → 부분 writer가 기존 `totalCostWon` 보존. 모든 기존 호출(전체 객체)도 그대로 동작.
4. B의 입력폼/calc/costStale 자동재계산 **제거** → store의 `feasibilityData` 구독 표시. ROI/ROE/실효LTV·총사업비 분해(cost_breakdown은 store에 없으므로 totalCost만)·VerificationBadge·ExpertPanelCard 보존. 수지 미산출 시 "프로젝트 수지분석으로 이동"(`projects/[id]/feasibility`) CTA. ROE는 `equityWon` 있으면 표시, 없으면 "—".

## 단계
- 단계0(원안 응급 writer)은 단계2(B read-only)로 자연 흡수 → 별도 구현 불필요.
- 단계1: 타입 확장 + A writer가 equity/roi/npv 채움.
- 단계2: B read-only 전환.
- 단계3: merge writer + 부분 writer 2곳 교정(null 덮어쓰기 제거).

## 기능손실 0
- 보존: ROI/ROE/실효LTV, 총사업비(요약), VerificationBadge, ExpertPanelCard.
- A 고유(몬테카를로/버전관리/모듈선택/baseline/완성도) 불변.
- analytics `InvestmentAnalyticsWorkspace`(/finance/monte-carlo)는 별개 분석 → 유지.

## 회귀 점검 대상
DevelopmentFinancePanel·BankReadyReportBuilder·CashflowDcfPanel·ProjectAnalysisSummary·DigitalTwinAiCard·ProjectHealthBoard·projectSync persist.
