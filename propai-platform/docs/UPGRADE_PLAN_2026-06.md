이 작업은 SOTA 딥리서치 결과를 바탕으로 한 전략적 고도화 계획 문서 작성입니다. 코드 구현이 아닌 아키텍처 설계 문서이므로 직접 작성합니다. 제공된 12개 모듈 데이터를 분석하여 작성하겠습니다.

(참고: 데이터에는 9개 모듈 JSON이 제공되었으나 본문에서 12개 모듈로 언급되었습니다. 제공된 9개 모듈 + CLAUDE.md/메모리에서 확인되는 기존 모듈을 종합해 작성합니다.)

# PropAI 플랫폼 SOTA 고도화·리팩토링 마스터플랜

> 수석 아키텍트 작성 / 기준일 2026-06-02 / 딥리서치 9개 핵심 모듈 + 운영 보조 3개(보고서·검증·G2B) 통합

---

## 1. 총평 — 모듈별 경쟁 포지션

분류 기준: **선도**(글로벌/국내 SOTA 동급 이상) / **추격**(골격은 있으나 핵심 기법 미달) / **낙후**(SOTA 핵심 메커니즘 부재).

| 모듈 | 포지션 | 한 줄 평 |
|------|--------|---------|
| 부지·입지 인텔리전스 | **추격** | 한국 공공데이터 연동은 선도급이나 학습형 SiteScore·isochrone·위험레이어 부재로 점수화가 규칙기반에 머묾 |
| 용도지역·법규 컴플라이언스 | **추격** | 한국 규제 계층 모델링은 강점, 빌더블 인벨로프·허용용도 룰엔진 부재가 결정적 격차 |
| 생성형 설계·CAD·BIM | **추격** | IFC 풀스택 연결은 우수하나 sqrt 단일박스·환경분석·진짜 최적화 부재로 "AI 설계"는 규칙분할 수준 |
| 공사비·적산(QTO) | **추격** | 단일데이터원 정합·정밀도 계층은 모범, 단가 하드코딩·ML 보정 부재가 PF 신뢰 병목 |
| 수지·사업성·ROI | **낙후** | NPV가 단일기간 근사, IRR 미산출, MC가 결정론적 — 다기간 DCF 부재는 기관급 미달 |
| 부동산 조세 | **낙후** | 엔진 이원화·취득세 매트릭스 오류·종부세 flat 0.5% — 정확성 자체가 훼손 |
| ESG·탄소 | **추격** | LCA 골격·한국 현지화는 진지, A1-A3+B6만 산출로 whole-life 반쪽·EPD 동적연동 부재 |
| 시장분석·AVM | **낙후** | R²0.94 하드코딩·미학습 폴백·신뢰구간 0 — 할루시네이션 리스크 최대 |
| 인허가 자동화 | **추격** | 한국 법체계 정합·Top3 연동 강점, LLM 자유판정 의존(비결정성)이 신뢰 한계 |
| 등기·권리분석 | **추격** | 공급자 추상화·캐시 견고, 말소기준권리 룰엔진·신탁탐지 부재로 LLM 단일추론 위험 |
| 공공입찰(G2B) | **추격** | 8엔진 수직통합은 유일 차별점, 적정투찰가가 avg±std 통계 — 적격심사 메커니즘 누락 |
| 검증·할루시네이션 방지 | **추격** | 2단 구조·메타데이터는 방향 정확, 결정론적 수치 재계산·claim 분해 부재가 핵심 갭 |

**핵심 진단:** 데이터 연동(입력)은 선도급이나, **추론·계산·검증 레이어**가 결정론/학습/불확실성 정량화 3축에서 일제히 SOTA에 미달. 특히 **수지·세금·AVM**(숫자가 핵심인 3개)이 가장 낙후 — 이는 PF심사·은행제출 신뢰의 직접 병목이며 최우선 교정 대상.

---

## 2. 혁신 베팅 Top 5 — 경쟁사 추월 차별화 기능

### 베팅 1 — 결정론적 수치-원장 검증 (Deterministic Calc Ledger)
- **왜 혁신적인가:** 경쟁사(빅밸류·밸류맵·랜드북)는 "예측력 90%"를 마케팅하나 **계산 환각**을 잡는 절대 검증이 없다. interpreter가 `값+산식+입력변수` 트리플을 emit → verifier가 Python으로 재실행(용적률=연면적/대지×100, 매출-원가=이익, 취득세=과표×세율구간)해 ε오차 대조. 한국 부동산 산식은 결정론적이라 적중률 ~100%.
- **필요기술:** 산식 레지스트리(YAML), 구조화 emit 스키마, Python 재계산 엔진, ε-비교. (기존 calculation_metadata.py / validator.py 재사용)
- **데이터원:** 자체 산식 + 법정 세율·용적률 테이블(국가법령정보센터).
- **난이도:** 중. (LLM 무관, 순수 결정론)
- **예상효과:** 수지/세금/용적률 계산 환각 0 → PF·은행제출 신뢰성 압도적. 전 모듈 횡단 적용.

### 베팅 2 — 한국 법규 폴리곤 일조 엔진 + 빌더블 인벨로프
- **왜 혁신적인가:** Forma·Zoneomics는 **한국 정북일조사선·인동간격을 모른다.** shapely+numpy로 정북사선(건축법 제61조)·도로사선·인동간격(0.5H~0.8H)·채광사선을 필지 단면에서 정밀 차감 → 실제 최대 빌더블 볼륨 산출 + 동지 9-15시 ray-cast 일영. VWorld 실측 PARCEL GeoJSON 직결로 부정형 필지 대응. "한국형 일조 SOTA"로 정면 추월.
- **필요기술:** shapely(폴리곤 buffer/차감), numpy ray-cast 일영, IfcGenerator 결합.
- **데이터원:** VWorld 지적도 PARCEL(보유), 건축법 시행령 일조규정.
- **난이도:** 상. (기하 연산 + 규제 정확도)
- **예상효과:** 설계 모듈을 규칙분할→규제반응형 SOTA로 격상. 인허가 도면검증과 시너지.

### 베팅 3 — 입찰-개발 수직통합 + 사정율 분포 시뮬레이터
- **왜 혁신적인가:** 고비드·디마툴즈는 **투찰가만** 예측. PropAI는 낙찰 가정 하에 QTO·실원가·용도지역·인허가·ESG·PF수지를 한 화면에 통합한 **유일** 구조. 여기에 한국 적격심사의 정답인 **사정율 분포 시뮬**(복수예비가 15개 중 4개 추첨 ±2/3% 몬테카를로→예정가격 분포→법정하한율 적용→당첨확률 최대 구간 역산)을 얹어 통계 대시보드→킬러 예측 엔진으로 전환.
- **필요기술:** 몬테카를로 사정율 시뮬, LightGBM/CatBoost quantile + 비대칭 손실, SHAP.
- **데이터원:** 조달청 낙찰정보서비스(복수예비가·예비가격·개찰순위 - 미수집 중), 법정 하한율 테이블.
- **난이도:** 중상.
- **예상효과:** 경쟁사 핵심을 8엔진 위에 올려 동시 추월. "낙찰 후 실제 마진" 시뮬.

### 베팅 4 — 신뢰구간 동반 멀티모달 한국 AVM (Conformal Prediction)
- **왜 혁신적인가:** 현재 R²0.94 하드코딩·미학습 폴백은 **할루시네이션**. 실거래+VWorld지적도+공시지가+로드뷰 CNN+텍스트 임베딩을 LightGBM/CatBoost로 결합하고, **공간가중 Conformal Prediction(SWCP)**으로 모든 시세에 보장된 신뢰구간(예: 평당 4,200만원, 90% 구간 3,900~4,500, FSD 7%) 부착. 한국 프롭테크 어디도 분포가정 없는 보장 구간을 안 줌. 토지·빌라(밸류맵·빅밸류 핵심영역) 대응.
- **필요기술:** LightGBM/CatBoost, SWCP, MLflow, CNN(로드뷰), 텍스트 임베딩.
- **데이터원:** MOLIT 실거래(보유), VWorld·NED(보유), 카카오/구글 로드뷰.
- **난이도:** 상. (학습 파이프라인 실가동 + 멀티모달)
- **예상효과:** 수지·분양가·PF 전 모듈의 단일 진실원 신뢰 회복. 은행제출 보고서 정량 우위.

### 베팅 5 — 시간상 월단위 현금흐름 + 한국형 PF 적정성 스코어
- **왜 혁신적인가:** NPV 단일기간 근사를 폐기하고 공사비/토지비 S-curve 월분산→차입 인출연동→**이자자본화→XIRR/MIRR/DSCR** 산출(ARGUS급). 여기에 2024.11 PF제도개선 기준(자기자본비율·DSCR·책임준공·분기 사업성등급 양호/보통/유의/부실우려)을 자동판정한 **은행제출용 PF 심사카드** 출력 — 글로벌툴에 없는 한국 차별화.
- **필요기술:** numpy_financial(XIRR), S-curve(베타분포), 상관 MC(Cholesky), 워터폴.
- **데이터원:** 자체 + FSC/국토부 PF 기준.
- **난이도:** 중상.
- **예상효과:** "수지=의사결정 엔진" 격상. 투자유치·PF심사 시나리오 분석 가능.

---

## 3. 단계별 구현·구축 로드맵

기존 P1~P5 골격에 리서치 혁신을 통합 재구성. 공수는 인-주(person-week) 추정.

### Phase 1 — 신뢰성 위기 진화 + 결정론 인프라 (4~6주)
> 목표: "숫자가 틀린" 치명 결함 제거 + 결정론 검증 토대. 기존 P1(하드코딩 실데이터화) + P2(검증배지) 통합·선행.

| 모듈 | 작업 | 산출물 | 검증기준 | 공수 |
|------|------|--------|---------|------|
| 검증(베팅1) | calc_verifier.py 신설, 산식 레지스트리, 구조화 emit 스키마 | `app/services/verification/calc_verifier.py`, `rules/calc_formulas.yaml` | 골든셋 50건 계산 환각 적발률 ≥95% | 2.5 |
| 조세 | 엔진 일원화(tax_ai_service↔tax/*), 원(KRW) 정수 통일, 취득세 매트릭스 교정(6/9억 누진·중과율) | 단일 SSOT tax 엔진, rates.yaml(effective-dated) | 국세청 계산기 30케이스 ±0원 | 3 |
| AVM | R²0.94 하드코딩 제거→MLflow run metrics 동적, 미학습시 `model_type=IDW_only`·`validation_r2=None` 정직표기 | avm_service.py 패치 | 미학습 폴백시 R² 미표기 100% | 1 |
| 부지 | auto_zoning 키워드 휴리스틱 제거→토지이음/NED PNU 직조회, 폴백시 `confidence`+'추정' 라벨 | auto_zoning_service.py 리팩토링 | PNU 실패시 '추정' 라벨 노출 100% | 1.5 |
| 공사비 | UNIT_PRICES 하드코딩→UnitPriceRepository(DB) 추출, source/as_of 메타 | UnitPriceRepository | 3개 호출처 단일 단가원 주입 | 2 |

**Phase 1 게이트:** 세금·용적률·매출수지 골든셋 전수 통과. AVM 정직표기 배포.

### Phase 2 — 계산 엔진 SOTA화 (6~8주)
> 목표: 수지 다기간 DCF·AVM 학습 실가동·라이브 단가. 기존 P1 후반 + P4(모듈별 검증규칙).

| 모듈 | 작업 | 산출물 | 검증기준 | 공수 |
|------|------|--------|---------|------|
| 수지(베팅5) | cashflow_engine 신설(월단위 S-curve→이자자본화→XIRR/MIRR/DSCR), aggregation 2계층 분리 | cashflow_engine.py | XIRR vs Excel ±0.1%p | 4 |
| 수지 | monte_carlo for-loop 제거→numpy 벡터화 + Cholesky 상관 + lognormal/PERT | monte_carlo_engine 재작성 | 1만회 ≤150ms, P(IRR>hurdle)·VaR/CVaR 산출 | 2.5 |
| AVM(베팅4) | 학습 DAG 실가동(MOLIT out-of-time split→MLflow 등록), comp_selector 자동선정, conformal_avm 신뢰구간 | dag_avm_retrain, comp_selector.py, conformal_avm.py | PE10·median APE 리포트, 구간 커버리지 ≥90% | 5 |
| 공사비 | 라이브 단가(국토부 표준시장단가+KICT 지수+조달청), AACE Class 자동라벨+정확도밴드 | LiveUnitPriceService | 단가 source+as_of 100% 첨부 | 3 |
| 조세 | 종부세 엔진 신설(공정시장가액비율→공제→누진→세부담상한), 양도세 중과/한시배제 날짜분기 | tax 엔진 확장 | flat 0.5% 제거, 종부세 10케이스 검증 | 3 |
| 검증 | prescan 룰 데이터화(K-RegRules), Trust Score 단일지표, 골든셋 회귀 CI | K-RegRules DB, VerificationBadge 확장 | RAGAS faithfulness 측정 가동 | 2.5 |

**Phase 2 게이트:** 수지 XIRR/DSCR 출력, AVM 신뢰구간 라이브, 종부세 정밀화.

### Phase 3 — 규제·설계 차별화 엔진 (8~10주)
> 목표: 빌더블 인벨로프·일조엔진·룰엔진. 기존 P3(expert-panel ROSTERS) + 설계 고도화.

| 모듈 | 작업 | 산출물 | 검증기준 | 공수 |
|------|------|--------|---------|------|
| 설계(베팅2) | shapely 형상코어 통일(sqrt 제거), 한국 일조엔진(정북/도로/인동/채광사선+ray-cast) | buildable_envelope_service.py, environment_analysis.py | VWorld 실측 PNU 부정형 회귀 통과 | 5 |
| 설계 | VWorld PARCEL 직결 site_shape, 기하 SSOT(BuildingMass 도메인), IFC 물량 기하직산 | AutoDesignEngine 폴리곤화 | 2D/3D/IFC 동일기하, 물량 ≤2% | 4 |
| 법규 | 허용용도 RASE 룰엔진(국토계획법 별표→JSON), use_permission_engine 신설 | use_permission_engine.py | 판정 결정론·근거조문 인용 100% | 3.5 |
| 법규 | ZONE_LIMITS→regulation DB 이관(조례 오버레이·effective_date), provenance 전파 | zoning_registry, 3중 서비스 통합 | 클릭-투-소스 지원 | 3 |
| 인허가 | 판정-해석 분리(결정론 룰+LLM 해석), IFC 컴플라이언스 어댑터(일조/인동/주차/피난) | compliance_check(ifc), audit_trail 스키마 | 동일입력 동일출력, 위반 3D 하이라이트 | 4 |
| 설계 최적화 | NSGA-II 다목적 솔버(수익·일조·주차·용적), unit_mix 연동 | optimizer.py(pymoo) | 파레토 N안+수지연동 | 3.5 |
| expert-panel | ROSTERS 정비, 적대적 Red/Blue debate 공용코어 추출 | 디베이트 코어 | 정밀모드 재사용 | 2 |

**Phase 3 게이트:** 빌더블 인벨로프→매스→수지 원클릭, 허용용도 결정론 판정.

### Phase 4 — 학습·멀티모달·지식그래프 (8~10주)
> 목표: ML 보정·멀티모달·KG-RAG. 기존 P4 심화.

| 모듈 | 작업 | 산출물 | 검증기준 | 공수 |
|------|------|--------|---------|------|
| 부지(베팅 인접) | PropAI SiteScore(XGBoost/엔트로피-MCDA+SHAP), isochrone 엔진(OSRM/r5), SiteFacts 통합스키마 | site_scoring.py, isochrone_service | 0~100점+SHAP 설명, 15분도시 점수 | 5 |
| 부지 | 위험레이어 대시보드(침수·산사태·단층·토지이음 행위제한 신호등) | risk_layer_service | 4종 레이어 신호등 렌더 | 4 |
| AVM | 멀티모달(로드뷰 CNN+텍스트 임베딩), 데이터밀도 적응형 블렌딩, 가격지수(반복매매+공간헤도닉) | 멀티모달 파이프라인 | 멀티모달 정확도 개선 측정 | 5 |
| G2B(베팅3) | 스키마 확장(기초금액·복수예비가15·예정가격·하한율·사정율), 사정율 MC 시뮬, 비대칭손실 ML | PriceModel, WinProbability | 사정율 분포·당첨확률·P-win 곡선 | 5 |
| 인허가 | 규제 KG-RAG(triplet 그래프, multi-hop scope/exception), 처리기간 ML 예측 | KG-RAG 인덱스 | 출처추적 multi-hop 응답 | 3.5 |
| ESG | IFC→EPD 자동매칭 whole-life(EN15978 A-C-D), 한국 그리드 탈탄소 시간가중 B6, XGBoost surrogate | carbon whole-life 엔진 | EN15978 전모듈 산출 | 5 |

### Phase 5 — 신규 모듈·상품화·자기학습 루프 (지속)
> 기존 P5 신규모듈 + 폐쇄루프.

| 영역 | 작업 | 산출물 | 공수 |
|------|------|--------|------|
| 조세 | 세후 IRR 통합(수지 결합), 엔티티 옵티마이저(개인/법인/조합/리츠 6구조 병렬) | After-Tax Decision Engine | 4 |
| 등기 | 말소기준권리 룰엔진, 신탁탐지 게이트, 인용강제, 권리 타임라인/난이도 히트맵 | deterministic_rights_engine.py | 4 |
| 수지 | 지분 워터폴(ROC→pref→promote), 설계↔수지 양방향 최적화 | waterfall 모듈 | 3.5 |
| 시장 | LLM tool-calling 대화형(정규식 제거, function-calling) | conversational 재작성 | 3 |
| ESG | 탄소→K-택소노미/녹색채권 브리지, GRESB 2025 quintile 재구현 | 금융 브리지 | 3 |
| G2B 루프 | 적산→적정투찰가→낙찰가율 실적→단가 재보정 자기학습 | 폐쇄루프 | 3 |
| 대화형 | 입지 에이전트(플래닛AI 대응) | site agent | 3 |

---

## 4. 아키텍처 리팩토링

### 4.1 모듈 독립성
- **3중·2중 중복 서비스 통합:** 컴플라이언스 3종(regulation/building_compliance/compliance_service)→단일 `ComplianceEngine` 파사드. ESG `esg/`·`esg/lca/`·`esg/epd/` 재export 제거, router 진입점 일원화(`routers/esg.py` 이중화 해소). tax 엔진 이원화→SSOT. 용적률 계산 산재(_blended_far·far_incentive·far_optimization)→단일 FAR 엔진.
- **판정-해석 계층 분리(전 모듈 원칙):** 결정론 판정(룰엔진/계산)과 LLM 해석을 명확히 분리. 인허가·법규·등기·검증에 일괄 적용 — "LLM 단독 추론 금지, 계산 가능한 것은 결정론".

### 4.2 단일 데이터원(SSOT)
- **SiteFacts 공통 부지 데이터모델:** VWorld/NED/SEMAS/실거래/위험을 한 스키마로 정규화 → Cherre식 지식그래프 기반. 인터프리터·AVM·매싱·수지가 동일 출처 참조.
- **BuildingMass 기하 SSOT:** AutoDesignEngine→IfcGenerator→glTF→2D CAD가 좌표 재산출하는 구조 제거, 단일 도메인모델에서 2D/3D/IFC/물량 파생.
- **UnitPriceRepository / regulation DB / rates.yaml:** 모든 하드코딩 상수(단가·용적률·세율)를 effective-dated 외부 데이터로 이관, 시점 버전 관리.

### 4.3 검증 레이어 (횡단 관심사)
- **결정론 수치-원장 파이프라인:** extract_claims→ground(span)→recompute(deterministic)→judge(LLM/debate)→calibrate. 모든 분석 출력에 Trust Score(faithfulness+groundedness+calc-pass-rate) 노출.
- **provenance/audit_trail 필수화:** 전 판정에 `source(law_article, ordinance_ref, retrieved_at, formula, inputs)` 메타 강제. 프론트 클릭-투-소스.
- **불확실성 정량화 표준:** AVM·수지·낙찰가에 conformal prediction 신뢰구간/FSD 의무 부착.

### 4.4 관측가능성
- **검증 관측성:** 모든 verify 호출 입력/verdict/issues/latency 로깅 + 골든셋 오프라인 eval + faithfulness 임계 알림 + CI 회귀 게이트(RAGAS/TruLens 패턴).
- **ML 거버넌스:** AVM/G2B/ESG-surrogate 모델카드·드리프트 모니터링·PE10/MAPE/FSD 표준지표(IAAO).
- **계산 메타데이터 확장:** 기존 calculation_metadata.py에 Class라벨·단가시점·지수base·법령시행일 필드 추가.

---

## 5. 모듈별 상세표

| 모듈 | 현 위치 | SOTA 격차 | 도입할 혁신 | 리팩토링 | 우선순위 |
|------|---------|-----------|-------------|----------|---------|
| 부지·입지 | 규칙기반 점수·직선거리·위험레이어0 | 학습 SiteScore·isochrone·위험·신뢰구간 AVM | PropAI SiteScore(XGBoost+SHAP), isochrone, 위험 신호등 | site_scoring 분리, SiteFacts, ZONE_LIMITS→DB | **P1** |
| 법규 컴플라이언스 | BCR/FAR 수치만·키워드 영향도 | 빌더블 인벨로프·허용용도 룰엔진·NLP조례추출 | RASE 룰엔진, 빌더블 인벨로프, 조례 코퍼스, CBR-RAG | 3중 서비스 통합, regulation DB, provenance | **P1** |
| 설계·CAD·BIM | sqrt 단일박스·환경분석0·최적화0 | 폴리곤·일조·NSGA-II·diffusion평면·ACCC | 한국 일조엔진, VWorld직결, 다목적솔버, web-ifc | shapely 코어, 기하 SSOT, IFC 물량 기하직산 | **P1** |
| 공사비·QTO | 단가 하드코딩·ML0·8공종 | 라이브단가·ML보정·5D BIM·AACE밴드 | LiveUnitPrice, ML+SHAP, IFC BaseQuantity, G2B역연동 | UnitPriceRepository, QTO 표준스키마, 계수 외부화 | **P1** |
| 수지·ROI | 단일기간 NPV·IRR미산출·결정론MC | 월단위 DCF·XIRR·상관MC·워터폴·PF스코어 | cashflow_engine, 상관MC, PF심사카드, 워터폴 | aggregation 2계층, MC 벡터화, v1/v2 통합 | **P1** |
| 조세 | 엔진이원화·매트릭스오류·종부세flat | 세후IRR·엔티티옵티마이저·effective-dated룰 | After-Tax Engine, 엔티티 옵티마이저, 종부세 엔진 | SSOT 일원화(P1), rates.yaml, 세후 결합레이어 | **P1** |
| ESG·탄소 | A1-A3+B6만·EPD정적·EF분열 | whole-life·동적EPD·surrogate·GRESB quintile | IFC→EPD whole-life, 그리드 시간가중, 탄소-금융 | EF SSOT, EN15978 모듈화, 디렉터리 정리 | P2 |
| 시장·AVM | R²0.94하드코딩·미학습·신뢰구간0 | 멀티모달·conformal·comp자동·가격지수 | SWCP 신뢰구간, 멀티모달, comp_selector, 가격지수 | R²제거, 학습DAG실가동, conversational LLM화 | **P1** |
| 인허가 | LLM자유판정·매트릭스하드코딩 | 결정론룰엔진·IFC도면검증·KG-RAG·세움터 | RASE 룰엔진, IFC컴플라이언스, FAR솔버, KG-RAG | 판정-해석분리, 매트릭스 데이터화, audit_trail | **P1** |
| 등기·권리 | LLM단일추론·말소기준0·신탁0 | 룰엔진·타임라인·인용강제·OCR교차 | 말소기준 룰엔진, 신탁탐지, 인용강제, 난이도히트맵 | 3계층 분리(extract→normalize→adjudicate) | **P1** |
| 공공입찰 G2B | avg±std통계·적격심사메커니즘0 | 사정율시뮬·비대칭ML·P-win·SHAP | 사정율MC, 비대칭손실ML, 수직통합강화, 자가진단 | 스키마확장, BidAnalyzer분리, 결정론MC제거 | **P1** |
| 검증·할루시네이션 | 1-pass·수치재계산0·신뢰구간0 | claim분해·결정론재계산·CoVe·debate·RAGAS | Calc Ledger, Evidence Pinning, conformal, Red/Blue | 파이프라인화, prescan데이터화, Trust Score | **P1(최우선)** |

---

## 6. 위험·의존성

### 6.1 데이터 가용성
- **조달청 낙찰정보서비스(복수예비가/개찰순위):** G2B 사정율 학습의 정답 라벨. 현재 미수집 — Phase 4 선행 수집 필수. 미확보시 사정율 시뮬은 메커니즘 시뮬레이션만 가능(학습 보정 불가).
- **위험레이어(침수·산사태·단층·토지이음):** 행안부/산림청/지질자원연/eum.go.kr 개별 API 안정성·갱신주기 상이. 합성검증 필요.
- **EPD(KEITI)·EC3:** 제품수준 EPD 커버리지 한계. 폴백 원단위 유지 필수.
- **MOLIT 실거래:** AptTradeDev만 승인(나머지 403). 비아파트 AVM 학습데이터 제약 — 활용신청 선행.

### 6.2 API 한계
- **공공데이터 국외IP 차단:** Oracle Cloud 백엔드 경유 우회 유지(기존 운영구조). isochrone(OSRM/r5)·로드뷰 CNN은 국외 호출 가능성 — 별도 경로 설계.
- **CODEF 등기 지연 ~50s/유료:** 병렬화+캐시 유지, OCR 폴백으로 비용 분산.
- **세움터(EAIS) B2G 연동:** 제출 자동화는 기관 협의 필요 — 단기는 사전검토 패키징까지만.

### 6.3 LLM 비용
- **결정론 우선 전략이 비용도 절감:** 계산·판정을 룰엔진으로 이관하면 LLM 호출은 해석·설명·엣지로 한정 → 토큰 절감 + 환각 0 동시 달성. 검증 debate(Red/Blue)는 정밀모드 옵션으로 비용 격리.
- **멀티모달 CNN·surrogate 학습:** 1회성 학습비 + MLflow 운영. 추론은 경량.

### 6.4 규제·정확성
- **세법 잦은 개정(2026.5.9 양도세 중과배제 종료 등):** effective-dated 룰엔진 없이는 정확성 유지 불가 — Phase 1 rates.yaml이 구조적 전제.
- **G2B 하한율 개정(2026.1.30 +2%p):** 법정 테이블 모듈화로 단일출처 참조.
- **AVM 책임 고지:** 부동산플래닛식 명시적 면책 + conformal 신뢰구간으로 법적 안전성 확보.
- **할루시네이션 법적 리스크(PF/은행제출):** 베팅1(Calc Ledger)+인용강제가 1차 방어선. 이것이 전체 계획의 신뢰 기반.

### 6.5 의존성 임계경로
```
rates.yaml/UnitPriceRepository/regulation DB (P1 외부화)
   └→ 종부세·라이브단가·허용용도 룰엔진 (P2~P3)
SiteFacts SSOT (P4) ──→ SiteScore·AVM·매싱·수지 동일출처
BuildingMass 기하 SSOT (P3) ──→ IFC컴플라이언스·whole-life탄소·물량
Calc Ledger (P1) ──→ 전 모듈 횡단 검증 (지속)
조달청 낙찰정보 수집 (P4 선행) ──→ G2B 사정율 학습
```

---

## 권고 실행 순서 요약
**즉시(P1):** 조세 매트릭스 교정 + AVM R²제거 + Calc Ledger — "숫자 신뢰" 3대 응급. → **단기:** 수지 다기간 DCF + AVM 학습실가동 + 라이브단가. → **중기:** 한국 일조엔진 + 허용용도 룰엔진 + IFC컴플라이언스(설계·법규·인허가 차별화 삼각편대). → **장기:** SiteScore·멀티모달AVM·G2B사정율·whole-life탄소(학습/멀티모달 베팅).

핵심 철학: **"데이터 연동은 이미 선도, 이제 추론·계산·검증을 결정론+학습+불확실성 정량화로 SOTA화한다."** 한국 특화(일조·적격심사·PF제도·세법·신탁) × 결정론 검증이 글로벌 툴이 못 넘는 해자다.