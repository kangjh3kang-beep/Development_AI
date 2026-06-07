# P3 — 금융분석 단계 개발금융(PF/브릿지/이자/DSCR/LTV) 고도화 + 수지 총사업비 자동주입

## 요약
금융 단계를 기존 "AVM 시세 + 전세위험" 보조 분석에서 **개발금융(PF·브릿지·이자·LTV·DSCR)을 主**로 전환.
수지(P2)에서 흘러온 **총사업비를 컨텍스트에서 자동주입**해 진입 시 클릭 없이 자동 산출. 기존 AVM/전세 패널은 하단에 보존.
**새 금융계산 로직 미작성** — 기존 `finance_cost_engine` 재사용, LTV/DSCR은 표준 비율식만.

## 백엔드 — 엔드포인트(신설)
- **`POST /api/v2/feasibility/development-finance`** (신설, `app/routers/v2_feasibility.py`)
  - 기존 라우터/엔진 점검 결과:
    - `risk.py` / `risk_scoring_engine.py` → DB+auth+tenant 필수, DSCR/LTV는 **입력값**(계산 안 함). 자동주입 무클릭 패널에 부적합 → 미사용.
    - `/v2/feasibility/cashflow` → 브릿지/PF 금리는 쓰나 LTV/DSCR을 직접 반환하지 않음 → 보완 불가.
    - `finance.py`(두 곳) → 전세/조합분담금/feasibility만. PF/DSCR 없음.
  - 결론: 신설하되 **finance_cost_engine 재사용**.
- 요청(JSON):
  ```json
  {
    "total_project_cost_won": 100000000000,   // 필수(수지 총사업비)
    "equity_ratio": 0.3,                      // 선택(기본 0.3)
    "equity_won": null,                       // 선택(있으면 비율보다 우선)
    "land_cost_won": 30000000000,             // 선택(없으면 총사업비×0.3)
    "construction_cost_won": null,            // 선택
    "annual_noi_won": 6000000000,             // 선택(없으면 DSCR null=분양형)
    "credit_grade": "A", "presale_ratio": 0.5,
    "bridge_months": 12, "pf_months": 30
  }
  ```
- 응답: `{ total_project_cost_won, equity_won, equity_ratio, pf_loan{amount_won,rate,interest_won,guarantee_fee_won,months,total_cost_won}, bridge_loan{...,arrangement_fee_won...}, total_debt_won, ltv, dscr, annual_debt_service_won, total_financing_cost_won }`

### finance_cost_engine / 비율식 재사용
- 이자·수수료: `calculate_pf_loan`, `calculate_bridge_loan`(만기일시상환 복리, get_pf_rate 신용등급/분양률 동적금리).
- 자금구조: `cashflow_generator` 관례 차용 — 자기자본=총사업비×ratio, 브릿지=토지비×(1-ratio), PF=나머지.
- LTV = 총부채/총사업비 (표준 비율식, 신규 모델링 아님).
- DSCR = 연 NOI / 연 부채상환액(PF잔액×PF금리 + 브릿지잔액×브릿지금리). NOI 없으면 null(분양형).

## 프론트 — 자동주입·isStale
- 신규 `components/analytics/DevelopmentFinancePanel.tsx`:
  - 컨텍스트 자동주입: `feasibilityData.totalCostWon`(총사업비), `costData.totalConstructionCostWon`(공사비), `siteAnalysis.estimatedValue`(토지). 토지 없으면 총사업비-공사비 근사. NOI=매출×0.04 근사.
  - **진입 시 자동 산출**(useEffect, 클릭 불필요). `apiClient.postV2("/feasibility/development-finance")`.
  - **isStale 가드**: `lastComputedCostRef`로 마지막 산출 총사업비 기억 → 수지 갱신(값 변동)시만 재계산, **동일값 재호출 차단(무한루프 가드)**.
  - 결과: PF대출액·금리·총이자·LTV·DSCR·자기자본비율 + PF/브릿지 세부(이자·수수료·합계).
  - **수지 미완료 정직 안내**(무목업): "수지분석을 완료하면 … 자동 산출" 점선 카드.
- `ProjectFinanceWorkspaceClient.tsx`: 히어로 카드 직후 `<DevelopmentFinancePanel />` 主 배치. **기존 AVM/전세 패널 전부 보존**(하단).

## 라이브검증
- 백엔드 `py_compile` OK.
- TestClient(PYTHONPATH=루트+apps/api) HTTP 호출:
  - 총사업비 1000억 → **STATUS 200**, PF 490억@5.3%, 브릿지 210억@5%, **LTV 0.70, DSCR 1.65**, 총금융비 89.5억 (전부 비-0·현실값).
  - 분양형(NOI 없음) → 200, dscr=null, ltv=0.70 (graceful).
  - 총사업비 0 → **422**(검증).
- 프론트 `npx tsc --noEmit` → **EXIT 0**. import 보존(git diff 확인), 신규 의존성 0, 디버그 코드 0.

## 미진 / 후속
- IDE 경고(불필요 `float()` 캐스트 4건)는 방어적 가드라 유지(린터 import 트랩 회피 위해 미삭제). 기능 무영향.
- `/health` 의존 없음. 실 배포(Oracle SSH)는 본 작업 범위 외(push/배포 금지 준수).
- DSCR NOI는 매출×0.04 근사. 임대형 정밀 NOI 연동(공실·운영비)·다기간 DSCR은 후속.
- risk_scoring_engine과의 통합(개발금융 LTV/DSCR → 통합리스크 입력 연결)은 후속 가능.
