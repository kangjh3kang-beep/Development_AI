# 전체 모듈 AI LLM 연동 작업 로그

## 작업 개요
- **일시**: 2026-05-30
- **목표**: 10개 모듈 중 미연동 8개에 AI LLM 연동 (CRITICAL 3 + HIGH 2 우선)
- **상태**: 진행 중

## AI 연동 현황 (작업 전)

| # | 모듈 | 현재 상태 | AI 연동 | 우선순위 |
|---|------|---------|---------|---------|
| 1 | 부지분석 | Claude 해석 | 완료 | - |
| 2 | 설계 검토 | Claude 리포트 | 완료 | - |
| 3 | **수지분석/추천** | 규칙 6개만 | **미연동** | CRITICAL |
| 4 | **시장분석** | 데이터만 | **미연동** | CRITICAL |
| 5 | **보고서 생성** | 데이터 집계 | **미연동** | CRITICAL |
| 6 | **공사비** | 룩업 테이블 | **미연동** | HIGH |
| 7 | **인허가** | 규칙 체크 | **미연동** | HIGH |
| 8 | ESG | 수식 기반 | 미연동 | MEDIUM |
| 9 | 세금 | 세율표 | 미연동 | LOW |
| 10 | AVM | XGBoost | 미연동 | LOW |

## 에이전트 배정

| 에이전트 | 담당 | 생성 파일 |
|---------|------|---------|
| Agent A | CRITICAL-1: 수지분석 AI | `ai/feasibility_interpreter.py` |
| Agent B | CRITICAL-2: 시장분석 AI | `ai/market_interpreter.py` |
| Agent C | CRITICAL-3 + HIGH-4,5 | `ai/report_interpreter.py`, `ai/cost_interpreter.py`, `ai/permit_interpreter.py` |

## 각 서비스 설계

### 1. FeasibilityInterpreter (수지분석)
- **페르소나**: PF 전문 투자 자문가
- **입력**: auto_recommend_top3 결과 (Top 3 사업모델 + 점수)
- **출력**: 종합 추천, 모델별 분석, 리스크, 수익 극대화 전략, 자금조달 구조

### 2. MarketInterpreter (시장분석)
- **페르소나**: 부동산 시장 분석 전문가
- **입력**: 실거래가, 공시지가, 분양가 데이터
- **출력**: 시장 현황, 가격 추이, 비교 분석, 투자 시사점, 매수 적기

### 3. ReportInterpreter (보고서)
- **페르소나**: PF 대출 심사역 + 투자 분석가
- **입력**: 파이프라인 7단계 전체 결과
- **출력**: 경영진 요약, 부지 평가, 재무 분석, 리스크, 최종 추천

### 4. CostInterpreter (공사비)
- **페르소나**: 건설 원가관리 전문가 + VE 컨설턴트
- **입력**: 공사비 분석 결과 (공종별, 자재별)
- **출력**: 비용 분석, VE 절감 방안 3~5개, 자재 대안, 공기 영향

### 5. PermitInterpreter (인허가)
- **페르소나**: 건축 인허가 전문 행정사
- **입력**: 인허가 검증 결과 (적합/조건부/부적합)
- **출력**: 난이도 평가, 예외 조항, 규제 완화 가능성, 소요 기간, 전략

## 공통 설계 원칙
- langchain-anthropic ChatAnthropic 사용
- timeout 10초, temperature 0.3
- LLM 실패 시 폴백 (None 반환, 기존 결과 유지)
- 토큰 절약: compact data 추출
- 한국어 전문가 페르소나
