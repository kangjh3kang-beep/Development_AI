# 라이프사이클 8단계 종합 감사 + 리팩토링 계획 (2026-06-07)

## 공통 근본원인 (cross-cutting)
**두 개의 분리된 그래프**: UI 진행(LIFECYCLE_STAGES 10단계, 순서만) ↔ 데이터 의존(MODULE_UPSTREAM 6노드, 전파만). 키·개수 불일치, 서로 모름.
→ 결과: ① 단계 완성이 데이터 정교화를 트리거 못함 ② **리치 백엔드 엔진이 라이프사이클 탭에 미연결(dead path)** ③ 여러 단계에 하드코딩 목업 ④ staleness 6모듈 중 2개만 소비·pull한정.

## 단계별 진단 (핵심)
| 단계 | 문제 | 미연결된 리치 자산 |
|------|------|-------------------|
| 설계 | DesignStudio가 store에 designData/markStageComplete 미기록 → **BIM이 연면적 대신 대지면적 사용(구조적 버그)**. 매싱효율·이격 하드코딩 | design_v61(/mass·glb·IFC 풀스택)은 design-studio 별도페이지에만 |
| BIM | 라이프사이클 탭=저수준 박스 IFC, 3D뷰어·부위별적산(QtoBreakdown) 없음 | bim-studio(BIMViewer3D·QtoBreakdown)·design_v61 |
| 시공 | CostAndQuantityDashboard·ScheduleSupervisionPanel = **백엔드 하드코딩 목업**(project_dashboard.py 고정배열, 프로젝트 무관) | 실 QTO엔진 /cost/estimate-overview(items_qto·geometry) |
| 수지 | FeasibilityEditorV2 별도store=모세혈관 단절. baseline 자동산출X·분양가 표준seed X·완성도표시X | 점진모델이 InvestmentFeasibilityClient(ROI화면)엔 이미 작동 |
| 금융 | AVM+전세위험만. **PF/이자/DSCR 없음**, 수지 총사업비 미수신 | finance_cost_engine·/v2/feasibility(PF/브릿지/DSCR)·risk_scoring(DSCR/LTV) |
| ESG | LCA카드·AI Insight **하드코딩 목업**. GresbScoreCard 고아(미렌더)+프론트/백엔드 산식 이원화. B6에너지 고정120(BEEC 단절) | gresb_scoring_service(/gresb/score)·energy_service(BEEC) |
| 인허가 | 상단 진행바·서류·"AI 규제 검토 알림" = **하드코딩 목업**(permits.py:120 고정) | permit_validator(용도매트릭스)·/permits/ai-analysis(LLM 7방식) |
| 보고서 | BankReadyReportBuilder = **store-only 목업**(window.print, 백엔드·원장·reportlab 우회). 보고서 산출물 3종 병존 | bank_report.py(원장 권위병합)·bank_ready_report_service(10섹션)·/reports/generate(reportlab) |

## 모세혈관 점수: B
- 데이터모델·의존성선언 A- / 전파자동화 실효 C+(인프라대비 33%·pull한정) / SSOT B-(도메인값 폼복제) / 백엔드영속·원장분리 A-.
- **즉시 버그**: projectSync.ts CTX_KEYS에 `costData` 누락 → 비-UUID 로컬프로젝트 기기간 공사비 유실.

## 수지 점진 정교화 모델 (사용자 핵심요구) 설계
부지직후 baseline(시장표준)→단계별 정밀화→완성도 표시.
- 있는 자산: MODULE_UPSTREAM(feasibility←site,design,cost), isStale, /cost/estimate-overview 설계매스 자동흡수, DEFAULT_DIRECT_COST_PER_SQM 표준단가.
- 격차: baseline 자동산출 트리거 없음, 분양가 표준seed 없음(base_module 기본0), 수지페이지 staleness 미배선, 완성도/신뢰도 UI 없음, 입력시드 별도store에 갇힘.
- 설계: (1)POST /v2/feasibility/baseline 신설(부지만→FAR/BCR 역산 GFA+nearby-map 분양가+표준공사비) (2)FeasibilityEditorV2를 모세혈관 소비자로 승격(InvestmentFeasibilityClient 패턴 이식: designData GFA 자동시드·costData override·isStale 1회 재계산) (3)완성도 셀렉터(부지30%/설계60%/공사비85%/금융100%)+신뢰도 배지. 신규store 0.

## 리팩토링 계획 (우선순위)
**P0 즉시 버그(저위험·고가치)**
1. projectSync CTX_KEYS에 costData 추가(공사비 유실 버그).
2. DesignStudio→store(updateDesignData GFA/층수/건폐·용적+markStageComplete) → BIM 연면적 오류 해소.

**P1 목업 제거→실엔진 연결(무목업 원칙·신뢰성)**
3. 시공: CostAndQuantityDashboard/Schedule을 /cost/estimate-overview(items_qto) 실엔진으로 재결선.
4. 인허가: permits.py:120 status 목업·"AI 규제검토 알림" 카드 제거 → /permits/ai-analysis(LLM 7방식)·permit_validator 연결.
5. ESG: 하드코딩 LCA/AI카드 제거→lcaResult 실데이터, GresbScoreCard 페이지 배치+/gresb/score 호출(산식 일원화), B6에 BEEC 에너지 주입.
6. 보고서: BankReadyReportBuilder→POST /bank-report/generate(원장 권위병합)+reportlab PDF. 산출물 3종 통합 검토.

**P2 수지 점진모델(사용자 핵심)**
7. /v2/feasibility/baseline + FeasibilityEditorV2 모세혈관 승격 + 완성도/신뢰도 표시.

**P3 금융 단계 정의·연결**
8. finance 페이지에 PF/이자/DSCR(finance_cost_engine/v2_feasibility) 연결+수지 총사업비 자동주입. (금융 단계 책임 재정의 필요)

**P4 모세혈관 일반화(구조)**
9. 단계↔모듈 그래프 통합(10단계 전부 staleness), getNextRecommendedStage를 데이터준비도 기반으로.
10. staleness 소비 일반화(design/cost/esg) + 공통훅 useAutoRecalc/useStageInputs 추출.
11. 타입계약 강화(as never 제거), GFA SSOT 단일참조.

## 비고
- 모든 단계에 "리치 백엔드 엔진은 이미 존재하나 라이프사이클 탭이 얕은 쪽에 배선" 패턴 반복 → 주작업은 신규개발이 아니라 **재결선 + 목업제거 + 모세혈관 표준화**.
- 라이브검증·무목업·배포패턴(블루그린/A1·sw bump) 준수.
