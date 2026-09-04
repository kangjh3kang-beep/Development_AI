# 투자분석 STEP1 개략수지 → STEP2/3 배선 단절 — 근본수정 기록 (2026-07-10)

## 증상
/ko/analytics/investment (PR#219 단일 워크플로우)에서 STEP 1 개략수지(RoughScenarioPanel)가
토지비·공사비·분양수입·ROI·NPV·월별 DCF까지 완전 산출되어도:
- STEP 2 투자수익성 요약: "개략수지 생성하러 가기" 게이트 지속
- STEP 3 리스크 시뮬(몬테카를로): "먼저 수지 base가 필요합니다 — 결측: total_gfa_sqm, avg_sale_price_per_pyeong"

## 근본원인 (write-path 기아)
RoughScenarioPanel이 결과를 **로컬 state(setResult)에만** 보관 — SSOT(feasibilityData) 커밋 부재.
- STEP 2 게이트: feasibilityData.totalRevenueWon/totalCostWon > 0 (읽기만 함)
- STEP 3 base 2순위: buildNodeBody("feasibility") — total_gfa_sqm←designData.totalGfaSqm(설계 없으면 결측),
  avg_sale_price_per_pyeong←feasibilityData.salePricePerPyeongWon(커밋 없어 결측)
- 페이지 독스트링("각 단계는 앞 단계 결과를 이어받음")·assembleBase 주석("SSOT(개략수지·부지·설계)")이
  명시한 계약이 write 부재로 허구화. 정답 기준선=FeasibilityEditorV2 L68~88 커밋 이펙트.

## 수정 (fix/investment-rough-ssot-wiring)
1. `rough-scenario-commit.ts`(신규): 순수 매핑 `roughResultToFeasibilityPatch` — 8필드
   (totalCost/totalRevenue/roi/npv/grade/profitRate/salePricePerPyeong/totalGfaSqm), 무날조
   (없는 값 생략), equity 3필드 절대 미접촉(자동파생 보존), 전부 없으면 null.
2. RoughScenarioPanel: 기준선 패턴 커밋 이펙트 + 인플라이트 오염가드(result.project_id≠ctxProjectId면 skip).
3. FeasibilityData.totalGfaSqm 신설(optional·하위호환) — 개략수지 산정 GFA.
4. buildNodeBody feasibility 노드: GFA 폴백(설계 우선 → 개략수지). qto 노드는 설계 전용 유지(블라스트 최소).

## 전역스윕 결과 (write-path 기아 패턴, apps/web 전수)
- 진짜버그 1건 = 본 건(RoughScenarioPanel)뿐.
- 정상 배선 확인: CostEstimationClient(updateCostData)·UnitMixOptimizer/AutoRecommend(updateFeasibilityData/updateDesignData)·DevelopmentFinance(markFinanceUpdated stamp).
- 비해당(소비처 부재): CashflowDcfPanel(보조 what-if 도구 — 커밋하면 오히려 base 오염)·몬테카를로 분포·탄소계산기(프로젝트 미바인딩).
- ★후속조사(미확증·보드 기록): DAG 경로(useNodeRunner)는 feasibility 노드 ssotInputs에 feasibilityData
  미선언 → 이번 GFA 폴백은 DAG에서 무동작(무회귀)이며, 기존 C-1 developmentType·C-2
  salePricePerPyeongWon 읽기도 DAG 실행에선 dead-path 가능성.

## 검증
- eslint 0문제 · tsc 0에러 · vitest 44/44(신규 rough-scenario-commit 11케이스 + bodyBuilder 폴백 3케이스) · next build 성공
- QA 1차 REQUEST CHANGES(백엔드 교차추적):
  - [H1·차단] GFA 폴백이 설계 없는 상태에서 STEP3를 열지만 /calculate 매출은 total_households 기반
    → revenue=0 → 손실확률 100% 오탐(정직 게이트를 오탐으로 바꿈). ★핵심 통찰: bodyBuilder의
    avg_area=GFA×전용률÷세대수 산식에서 세대수가 매출에서 소거 → 세대수 가정만 채우면 매출이
    GFA×전용률×단가로 개략수지 기준 재현. 완전수정=백엔드 rough 응답에 세대수 가정
    (GFA÷unit_standards 표준 전용면적, /baseline 동일 관례) additive 노출 + 프론트 SSOT 소비
    + assembleBase 정직 게이트 벨트&브레이스.
  - [M1] 자동파생 equity(총사업비×10%) 재전송으로 "다시 생성" 비멱등 → equityIsManual만 전송.
  - [M2] 인플라이트 가드가 약식(project_id=null)→프로젝트 전환 레이스를 못 막음 → 요청시점 ref 비교.
  - [L1] cost/revenue 0 커밋 허용 불일치 → 양수만.
- QA 2차 **APPROVE**: H1 백엔드 SSOT 완전수정 확인(세대수 대수적 소거 → 매출=GFA×전용률×단가 정합,
  degraded 정직게이트 작동, M2 가드 전 분기 라인검증, 재커밋 루프 무). 게이트: 프론트 vitest 50/50 ·
  백엔드 pytest 22/22(메인 venv) · tsc/eslint 0 · build 성공.
- [LOW·후속] STEP2 표시매출(개략수지 GFA×0.70) vs STEP3 base매출(프론트 기본 전용률 0.75) ~7% 기준차 —
  차단 아님(리스크 분포 용도). 추후 전용률 상수 정렬로 완전 일치 가능.
- 커밋 dbaeb3ab (fix/investment-rough-ssot-wiring)
