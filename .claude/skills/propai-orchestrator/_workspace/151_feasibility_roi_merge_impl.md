# 151 — 수지/ROI 통합 구현 결과

## 변경 파일·라인
| 단계 | 파일 | 라인 | 변경 |
|---|---|---|---|
| 1 | `store/useProjectContextStore.ts` | FeasibilityData(~88) | `equityWon? / roiPct? / npvWon?` 옵셔널 추가(하위호환) |
| 1 | `components/feasibility/FeasibilityEditorV2.tsx` | useStore(~37), writer(~63) | `input` 구독 + writer가 `roiPct/npvWon/equityWon(=input.equity_won)` 채움 |
| 3 | `store/useProjectContextStore.ts` | action 시그니처(~221), 구현(~575) | `updateFeasibilityData: (data: Partial<FeasibilityData>)` + **merge**(기존값 보존 후 patch) |
| 3 | `components/feasibility/UnitMixOptimizerPanel.tsx` | ~204 | `totalCostWon:null/profitRatePct:null/grade:null` 제거 → `{ totalRevenueWon }`만 merge |
| 3 | `components/feasibility/AutoRecommendPanel.tsx` | ~318 | `totalCostWon:null` 제거 → revenue/profit/grade만 merge |
| 2 | `components/analytics/InvestmentFeasibilityClient.tsx` | 전면 | 입력폼·calc·costStale·자동로드 useEffect 제거 → `feasibilityData` 구독 read-only ROI 뷰. 422→107행 |

## merge 전환 정합
- store `updateFeasibilityData`가 replace→merge. 전체 객체를 넘기던 기존 호출 4곳(projects/[id]/page, ProjectPipelinePanel, FeasibilityEditorV2, page 복원)은 모든 필드를 넘기므로 동작 동일.
- 부분 writer 2곳(UnitMix/AutoRecommend)은 이제 `totalCostWon`을 건드리지 않음 → A/수지가 산출한 cost 보존.

## 기능손실 0 매핑(B 화면)
| 기능 | 처리 |
|---|---|
| 순이익·수익률·ROI·NPV·총사업비·등급 | store 값 표시(read-only) |
| ROI/ROE/실효 LTV 파생 | `derived`로 보존. ROE는 `equityWon` 있을 때만, 없으면 "—" + 안내문(무목업) |
| 총사업비 분해(cost_breakdown) | store에 분해값 없음 → 총사업비/자기자본/타인자본/LTV 요약으로 대체(분해 막대는 cost_breakdown 미보유로 제거, 데이터 없는 막대 표기 방지=정직) |
| 공사비 정밀 연동 표시 | costData 구독으로 보존 |
| VerificationBadge | 보존(context=result+derived) |
| ExpertPanelCard(7전문가) | 보존 |
| 수지 미산출 | "프로젝트 수지분석으로 이동" CTA(`/${locale}/projects/{id}/feasibility`, 미선택 시 `/projects`) |

A 고유(몬테카를로/버전관리/모듈선택/baseline/완성도) 불변. analytics `InvestmentAnalyticsWorkspace`(/finance/monte-carlo)는 별개 → 미수정.

## ROE/equity 처리
- A writer가 `input.equity_won`을 `equityWon`으로 영속. B는 `equityWon`이 있으면 ROE/타인자본/LTV 표시, 없으면 "—"(가짜 0 금지).

## reader 회귀 점검
- `DevelopmentFinancePanel`(`totalCostWon==null` 차단): 부분 writer가 더 이상 null로 덮지 않으므로 회귀 해소.
- `BankReadyReportBuilder`·`CashflowDcfPanel`·`ProjectAnalysisSummary`·`DigitalTwinAiCard`·`projectSync`: feasibilityData 필드 이름 불변, 신규 필드는 옵셔널 → 무영향.
- persist round-trip: 옵셔널 필드 추가만, snapOf/projectSync 그대로.

## 검증
- `npx tsc --noEmit` → **EXIT 0**
- `vitest run lib/useProjectContextStore.cascade.test.ts` → **8 passed**
- git diff: import 보존(analytics에 useParams/Link/isValidLocale 추가, 기존 import 유지)
- push/배포 없음.
