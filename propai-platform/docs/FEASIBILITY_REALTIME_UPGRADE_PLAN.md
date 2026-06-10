# 수지분석 실시간·동적 고도화 — 엔지니어링 리팩토링 계획

작성 2026-06. 목표: 정적 pro forma → **실시간 시장반영·다층·다각·동적(진행중 변화 학습)** 수지분석.

## 0. 현황(이미 보유)
도급현실 수지(매출=추정가×낙찰가율·실원가율0.87·손익분기87%), 몬테카를로(1000회), 현금흐름, 토네이도 민감도, ROE, 전문가패널, 토지/공사/금융/세금 분해, MOLIT 실거래·청약홈 분양가 연동, 분석원장(해시체인), 분석캐시, staleness 자동재계산(공사비→수지), 분석이력(방금 복구).

## 1. 경쟁·방법론 결론(조사)
- 글로벌은 **사전 피저빌리티(ARGUS/TestFit/Deepblocks)** ↔ **실행단계 동적 비용관리(Northspyre/Rabbet/Built)** 가 분리, CoStar가 실시간 시장 백본. 우리 강점=**전주기 단일 모세혈관 연속 운영**.
- 표준: DCF+Monte Carlo(VaR) + 가정 버저닝 + EVM(EAC/ETC) + 흡수율(absorption) + 시나리오/exit 다각 + Bayesian 갱신 + Real Options.

## 2. 빈 칸 4개 = 고도화 로드맵(순차 구현)

### F1. 신뢰도 가중 시장 재평가 엔진 + 가정 버저닝
- 시장가 다중소스(MOLIT 실거래·청약홈 분양가·AVM·시세지수)를 **신뢰도점수(0~100)** 로 블렌딩(comps 풍부·최신=高).
- 모든 가정에 timestamp·source·시나리오 라벨 → **분석원장(해시체인)에 가정버전 append**(변조불가·델타표시).
- 재평가 주기: 실거래/분양가=신규발생시, 시세지수/AVM=주기 리프레시. "언제·무슨 근거로 재평가" 기록.
- 산출물: `market_revaluation_service`(블렌딩+신뢰도), 수지 입력의 sale_price를 동적 시장가로 교체.

### F2. 동적 몬테카를로 — Bayesian 흡수율(분양 actuals 학습)
- 청약홈 경쟁률·실분양률 actuals로 **absorption 사후분포 갱신**(rolling Bayesian) → 몬테카를로 입력분포를 정적→학습형.
- 진행중 프로젝트는 실현 분양률·실거래로 매 주기 재추정 → "그때그때 현실 반영".
- 산출물: `bayesian_absorption`(prior+actuals→posterior), monte_carlo_engine에 흡수율 변수 주입.

### F3. EVM 기반 cost-to-complete(EAC/ETC) — 전주기 추적
- 도급원가모델 위에 **EAC = AC + (BAC−EV)/(CPI×SPI), ETC = EAC−AC** 얹어 추정 vs 실투입 추적.
- 입찰추정→착공→준공 cost-to-complete를 단일 모세혈관에서(글로벌은 분리). variance 알림.
- 산출물: `evm_service`(CPI/SPI/EAC/ETC), 진행단계 actuals 입력 폼.

### F4. 다각 exit 워터폴 + Real Options
- exit 3종(분양/임대/매각) 병치 — exit별 워터폴·IRR·equity multiple 비교.
- **Real options**: 연기/단계화(인허가·분양 타이밍, 투찰여부)의 "기다릴 권리" 가치화.
- 산출물: `exit_waterfall`(3 exit), `real_options`(deferral value).

### F5(공통). 다층 시나리오 + variance 알림 + 가정 버저닝 UI
- 비관/기준/낙관 side-by-side, 분기(시공)/월(분양) 케이던스 자동 재계산(staleness 확장)을 EVM variance·시장 재평가와 묶어 **예측형 알림**.

## 3. 구현 원칙
- 결정론 엔진이 진실원(수치), 시장가·actuals는 신뢰도 가중·버전 기록. 무목업·라이브검증.
- 기존 자산(monte_carlo/cashflow/sensitivity/expert_panel/원장/캐시) 보존·확장. 각 F는 독립 증분(구현→검증→배포).
- 계정별 캐시·이력은 이미 영속(원장+localStorage). 재분석 비효율은 staleness 기반 "변경시에만 재계산"으로 최소화.

## 4. 순차
F1(시장 재평가) → F2(Bayesian 흡수율) → F3(EVM) → F4(exit/options) → F5(다층·알림). 각 단계 라이브 검증.

출처: docs 본문 + 조사(Northspyre/ARGUS/CoStar/TestFit, MDPI real-options, EVM EAC/ETC, Bayesian BVAR, absorption modeling).
