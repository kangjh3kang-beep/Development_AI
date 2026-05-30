# 사통팔땅(PropAI) 플랫폼 통합 구현계획서 (2026-05-29)

## 1) 목적
- 전 기능 모듈을 성능목표 중심으로 재정렬하고, 외부 표준/논문/유사 플랫폼 근거를 연결해 실행 가능한 통합 구현계획을 수립한다.
- 최종 목표는 "주소 입력 1회 -> 전주기 자동분석" 파이프라인의 정확도/속도/신뢰성 동시 달성이다.

## 2) 기준 성능목표 (내부 문서 기준)
- API 평균 응답시간: 200ms 이하 (LLM 제외)
- LLM 응답시간: 5초 이하
- Monte Carlo 10,000회: 30초 이하
- 가용성 목표: 99.9% SLA
- BIM IFC 파싱 정확도: MAE < 2%

근거:
- `PropAI_v58_마스터인덱스.md:881`
- `PropAI_v58_마스터인덱스.md:882`
- `PropAI_v58_마스터인덱스.md:883`
- `PropAI_v58_마스터인덱스.md:899`
- `PropAI_v58_마스터인덱스.md:116`

## 3) 현재 코드 기준 핵심 갭

### CRITICAL
1. KPI 벤치마크 테스트 비활성화
- `tests/benchmarks/bench_ifc.py:26`
- `tests/benchmarks/bench_graphql.py:15`
- 영향: 성능목표/정확도 목표를 CI에서 증명하지 못함.

2. 실시간 스트림이 랜덤 모의값 기반
- `apps/api/routers/kdx.py:83`
- 영향: 실시간 운영 의사결정 신뢰도 저하.

### HIGH
3. 인허가 로직의 정적 룰/정적 기간 모델
- `apps/api/services/seumter_permit_service.py:14`
- `apps/api/services/seumter_permit_service.py:42`

4. 수요예측 Redis 연결의 환경독립성 부족
- `apps/api/services/demand_forecast_service.py:26`

5. ESG/GRESB 및 탄소계수의 정적 모델 의존
- `apps/api/app/services/esg/gresb_scoring_service.py:10`
- `apps/api/services/carbon_calculation_service.py:96`

### MEDIUM
6. 대시보드 KPI 일부 하드코딩
- `apps/api/routers/dashboard.py:57`

7. 시장 AI 지역코드/룰 기반 파싱의 일반화 한계
- `apps/api/app/services/market/conversational_market_ai.py:73`

## 4) 기능 모듈별 외부 근거 + 구현전략

### A. 입지/AVM/시장분석
외부 근거:
- XGBoost 논문: https://arxiv.org/abs/1603.02754
- 국토부 실거래가 공개시스템: https://rt.molit.go.kr/pt/info/info.do?mobileAt=v
- VWorld OpenAPI: https://www.vworld.kr/dev/v4dv_2ddataguide2_s001.do
- Zillow Zestimate(유사 가치추정 서비스): https://www.zillow.com/zestimate/

구현전략:
- 실거래가 + 공간정보 + 규제정보를 통합한 Feature Store 구축
- CTGAN 폴백 휴리스틱(`avm_service.py`)을 학습데이터 품질 게이트로 대체
- 지역코드 룰기반 파싱을 NER/지오코더 결합형으로 개선

목표 KPI:
- AVM: MAPE, 지역별 편향도, p95 추론시간
- 시장분석: 질의 정답률, 근거링크 포함률

### B. 법규/RAG/인허가
외부 근거:
- BEIR (IR 벤치마크): https://arxiv.org/abs/2104.08663
- RAGAS (RAG 평가): https://arxiv.org/abs/2309.15217
- NIST Zero Trust: https://csrc.nist.gov/pubs/sp/800/207/final

구현전략:
- 법규 원문 버전관리 + 개정이력 반영 파이프라인
- Dense+Sparse 하이브리드 검색 + 근거조항 강제 출력
- 인허가 체크리스트/소요일을 정적 상수에서 지역/시점/케이스 기반 확률모델로 전환

목표 KPI:
- 법규 판단 정밀도/재현율
- Hallucination rate
- 인허가 리드타임 예측오차

### C. 설계/CAD 자동화
외부 근거:
- Autodesk Forma: https://www.autodesk.com/products/forma/overview
- TestFit: https://testfit.io/

구현전략:
- 용적률/건폐율/일조/이격거리 제약 최적화 엔진화
- 다목적 최적화(Pareto)로 대안 생성
- 사용자 선택 피드백 기반 랭킹 재학습

목표 KPI:
- 대안 생성시간
- 규정위반률
- 최종 대안 채택률

### D. BIM/IFC/공사비/리스크
외부 근거:
- buildingSMART IFC 4.3: https://ifc43-docs.standards.buildingsmart.org/
- IfcOpenShell 문서: https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html
- AACE RP 57R-09(확률적 원가리스크): https://web.aacei.org/docs/default-source/toc/toc_57r-09.pdf

구현전략:
- 골든 IFC 세트 + 자동 비교검증으로 MAE<2% 강제
- Monte Carlo 병렬화/벡터화 + 시드관리로 재현성 확보
- 공사비/리스크 결과를 금융모듈로 자동 전달

목표 KPI:
- IFC 수량산출 오차
- Monte Carlo 처리시간(10,000회)
- 리스크 P90 오차

### E. ESG/LCA/LCC/Taxonomy
외부 근거:
- ISO 14040: https://www.iso.org/standard/37456.html
- ISO 21930: https://www.iso.org/standard/61694.html
- EU Taxonomy Regulation 2020/852: https://eur-lex.europa.eu/eli/reg/2020/852/oj/eng
- GRESB 2025 Reference Guide: https://documents.gresb.com/generated_files/real_estate/2025/real_estate/reference_guide/complete.html
- EnergyPlus 문서: https://energyplus.readthedocs.io/en/stable/

구현전략:
- 정적 탄소계수를 EPD 공급망 DB/버전 기반으로 치환
- GRESB 단순화 모델을 실제 프레임워크 항목맵으로 업그레이드
- LCA/LCC/Taxonomy 결과를 은행 제출용 보고서로 자동 연결

목표 KPI:
- 탄소 산출 재현성
- 외부평가 정합률
- 개선권고 이행률

### F. 디지털트윈/운영/SRE
외부 근거:
- Procore: https://www.procore.com/what-is-procore
- Autodesk Construction Cloud: https://construction.autodesk.com/
- SLO/에러버짓: https://sre.google/sre-book/service-level-objectives/

구현전략:
- KDX/Webhook/WebSocket 이벤트 버스를 실데이터 스트림으로 전환
- 관측성 표준화(Trace/Metric/Log) + SLO 기반 알람
- 운영상태 점수와 유지보수 태스크 자동 연계

목표 KPI:
- 이벤트 지연시간
- MTTR
- 에러버짓 소진율

### G. 인프라/성능/보안
외부 근거:
- FastAPI worker 배포: https://fastapi.tiangolo.com/deployment/server-workers/
- Celery Tasks: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- RabbitMQ Reliability: https://www.rabbitmq.com/docs/reliability
- PostGIS Spatial Index: https://postgis.net/documentation/faq/spatial-indexes/
- PostgreSQL EXPLAIN: https://www.postgresql.org/docs/current/sql-explain.html
- Kubernetes Autoscaling: https://kubernetes.io/docs/concepts/workloads/autoscaling/
- OWASP Top 10: https://owasp.org/www-project-top-ten/

구현전략:
- API 경로별 성능 SLI 계측(p50/p95/p99)
- GiST/쿼리플랜 튜닝 자동 리포트
- 비동기 큐 안정성(재시도, DLQ, idempotency key) 표준화
- 인증/인가/토큰 저장/회전 정책 단일화

목표 KPI:
- API p95 latency
- 5xx 비율
- 보안취약점 밀도
- SLA 99.9%

## 5) 우리 플랫폼의 독보적 통합 구조
- 핵심 컨셉: "혈관 네트워크" 자동 파이프라인
- 기준 문서: `propai-platform/_workspace/SYSTEM_ARCHITECTURE_PLAN.md:75`

통합 흐름:
1. 주소 입력
2. 부지/입지/규제/시세 자동 분석
3. 설계 대안 자동 생성
4. IFC/BIM 물량 및 공사비/리스크 산출
5. ESG/LCA/LCC/Taxonomy 평가
6. 금융/세무/투자지표 산출
7. 보고서/대시보드/협업 승인 자동화

차별화 포인트:
- 각 단계 산출물을 다음 단계 특징값으로 자동 전달하는 "폐루프" 구조
- 모든 결과에 근거(법조항/데이터소스/모델버전) 동시 저장
- 운영데이터(디지털트윈/시장/공정)를 다시 설계/금융 단계로 피드백

## 6) 단계별 실행 로드맵

### P0 (즉시, 1주)
- 벤치마크 테스트 활성화 + CI 게이트 강제
- KDX 랜덤 스트림 제거, 실제 이벤트 소스 연동
- KPI 하드코딩 제거(대시보드)

### P1 (2~3주)
- 인허가/법규 모델 동적화
- AVM/시장AI feature store + 모델 품질 게이트
- ESG 탄소/점수 계산 로직의 표준정합 고도화

### P2 (4~6주)
- IFC 골든셋 + 정확도 회귀테스트 자동화
- Monte Carlo 가속(병렬/벡터화)
- 통합 리포트(은행/투자자/내부) 자동생성

### P3 (지속운영)
- SLO/에러버짓 운영정착
- 분기별 외부 벤치마크 리포트
- 규정 개정/데이터소스 변경의 자동 회귀검증

## 7) 검증 프레임 (필수)
- 성능: API p95/p99, 큐 지연, DB 쿼리플랜 변화
- 정확도: AVM MAPE, IFC MAE, 법규 판정 F1, ESG 정합률
- 안정성: 가용성, 장애복구시간, 실패재시도 성공률
- 보안: OWASP Top 10 시나리오 점검 + 테넌트 경계 침투 테스트

## 8) 즉시 실행 작업 백로그
1. `tests/benchmarks/*` 스킵 제거 및 테스트 데이터셋 확정 (**완료**)
2. `apps/api/routers/kdx.py` 실시간 스트림 실데이터 연동 (**완료**)
3. `apps/api/services/seumter_permit_service.py` 동적 규정/기간 엔진 분리 (**완료**)
4. `apps/api/services/carbon_calculation_service.py` EPD 연동 레이어 추가 (**완료: JSON/ENV 외부화 1차**)
5. `apps/api/services/demand_forecast_service.py` Redis DSN 환경변수화 (**완료**)
6. `scripts/perf/run_stage3_benchmarks.py` 추가 및 Stage 3 리포트 자동생성 (**완료**)
7. CI 주기 실행(스케줄) + 실 IFC fixture 확장 + strict gate 적용 (**샘플 기준 완료: workflow/strict gate/real-ifc-min + parsed_count=3 통과, 실 원본 온보딩 자동화/비식별화(scrub) + 외부경로 호환성 테스트 + incoming 품질게이트(중복/용량 포함) + 온보딩/벤치 오케스트레이션 + mode=move 후 incoming 비움 검증 완료, workflow_dispatch의 refresh 컷오버 리허설 입력(run_refresh_rehearsal/refresh_mode) 추가, 실 프로젝트 원본 fixture 교체 대기**)
8. API p95(<=200ms) 자동측정 Stage4 벤치 + strict gate + 리포트 자동화 (**완료: `run_stage4_api_latency_benchmarks.py` + Stage3-4 workflow 확장 + `/api/v1/system/integration/status` p95 0.0014s, `/api/latest` p95 0.0012s**)

## 9) 결론
- 현재 플랫폼은 기능 폭은 넓지만, 목표를 "측정/증명"하는 계층(벤치마크/운영계측/표준정합)이 약하다.
- 본 계획의 핵심은 기능 추가가 아니라, 전 모듈을 하나의 성능/정확도 계약(SLA+모델KPI)으로 묶는 것이다.
- 이 구조로 전환하면 "독보적 통합 유기 플랫폼"의 차별성이 코드/데이터/운영에서 동시에 증명 가능해진다.
