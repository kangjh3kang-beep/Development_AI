# 사통팔땅 플랫폼 — v4.0 마스터 실행계획 대비 갭 분석·고도화 로드맵 (v2)

> 작성 2026-07-22 · **v2 보완**: 자체 적대검토로 v1의 결함 4종을 수정 — ①부합도 집계 오류 정정 ②미감사 7개 도메인 보충 실측(GAP-F) 반영 ③확인된 전 공백의 로드맵 완전 매핑(v1은 9개 공백 미배정) ④v4.0 계약 매트릭스 행 12종 추가(Work Package·실무역할·승인등급·검토계획·5D/EVM·감리기성·준공 등).
> 대상: `propai-platform` 실코드 **6축 무날조 정찰**(GAP-A 데이터 · B 법규/승인 · C 설계/BIM/적산 · D 수지/금융/보고서 · E 횡단거버넌스 · F 미감사 도메인 보충). 각 판정은 file:line 근거 EXISTS/PARTIAL/MISSING. 폴더명 유사성 과대평가 배제.
> 측정 기준: `사통팔땅_IDE_플랫폼구축_마스터실행프롬프트 v4.0`(P0~P14 + 횡단 엄밀성 계약 + 분야별 작업패키지 A~J).

---

## 0. 한 줄 결론

**기능 커버리지(무엇을 계산하는가)는 v4.0 요구의 대부분을 이미 실장했다. 부족한 것은 "엄밀성 계약층"(어떻게 신뢰·추적·차단·승인하는가) — Zero-Trust 승격, 단계간 immutable bundle, 필드수준 계보, Rule dual-control, 전문가 승인 상태머신, 결함예산·릴리스 계약이다.** 현 플랫폼은 **강한 분석 엔진 + 국소적 정직성 가드**이고, v4.0의 **전주기 거버넌스 골격**은 미배관. ★부수 발견: repo에 v4.0 계획 문서 자체가 없음 — 현 코드는 v4.0 이전 세대(자가성장 엔진 설계 기반)로, 이 갭은 "잘못 만든 것"이 아니라 **"다음 세대 스펙에 아직 안 맞춘 것"**.

---

## 1. P0~P14 부합도 매트릭스

범례: 🟢 충실 · 🟡 PARTIAL(핵심 실재+공백) · 🟠 부분(개념/근사 수준) · 🔴 MISSING

| 단계 | 영역 | 부합도 | 실재(강점) | 핵심 공백 |
|---|---|---|---|---|
| **P0** | 필지입력 | 🟡 | 면적 triplet(공부/좌표/입력) 교차검증·자동보정 금지, 배치입력 3종 | PNU 체크디지트·후보해소 점수식·편입/제외/구거 상태기계 |
| **P1** | 원천수집·Fact Ledger | 🟠 | CircuitBreaker+백오프+캐시 base client | **Fact Ledger(OBSERVED/ASSUMED/CONFLICT)·SourceSnapshot 필수필드·raw+checksum 불변저장·dead-letter 전무**; 핵심 커넥터(VWorld/G2B)에 회복탄력성 미적용 |
| **P2** | 필지그래프 | 🔴 | (union 면적집계 일부) | ParcelGraph·articulation point·road-frontage·critical parcel·N-1 시나리오 전무 |
| **P3** | Rule Pack | 🟡 | 타입계약(관할·시행일·인용·CalcRule), 시행일 precedence, DRAFT→ACTIVE 승격게이트 | **DSL 스키마+컴파일러 없음**, formula/rounding/approval/tests 강제요소 없음, **dual-control 전무**(승인자 신원 필드조차 없음) |
| **P4** | GIS·측량정합 | 🟢 | CRS·control point·RMSE·왕복오차·공차초과 시 FIELD_VERIFICATION 강등(계획서에 가장 충실) | 원본/정제본 이원저장·layer block/xref 보존 명시 |
| **P5** | CSM·실사 | 🟡 | SiteBasis 상태기계·모순탐지·해시재현 | 단일 CSM 스냅샷 조립체·Risk=P×I×D 레지스터·자동 부분 invalidation(권고까지만) |
| **P6** | 법규계산·판정 | 🟡 | **CalcTrace 강제 emit·Rationale/LegalRef·legal-max/target/headroom 분리(근거층 가장 견고)**, 3값 판정+거짓불합격 방지+신뢰도 게이팅 | **golden false-pass=0 테스트 없음**(현재 false-FAIL 방지만), 법령 위계(상위법/특별법/위임) 상충 해소기 없음 |
| **P7** | 3D Envelope | 🟠 | setback→height→sunlight 해석식 순차 적용 | **exact solid 차감 없음**(bbox 감산+정북사선 스트립적분 2D), 차감체적/offending face·conservative/base/conditional 분리·property test·round-trip 없음 |
| **P8** | 배치·BIM 초안 | 🟡 | **IFC export 실재**(ifcopenshell IFC4), A/B/C 3옵션, 면적 불변식 일부, 주차 치수 KB(주차장법 모듈) | constraint solver 아님(rule 템플릿 변형), **주차 stall배치/aisle/swept path/ramp 검증 없음**(대수 산정만), 편집안정 ID 유예 |
| **P9** | BIM 적산 | 🟡 | cost breakdown·WBS/CBS 12공종·단가 provenance(tier/지역/시점/출처/KOSIS지수), 구조 물량계수, Monte Carlo P50/80/90(seed) | **Q1~Q4 tier 미분리**, back-test(APE/MAPE/bias)·outlier 없음, MC 상관 없음(독립표본), 가설/예비비 별도비목 없음 |
| **P10** | 수지·금융 | 🟡 | **월별 부채 waterfall(브릿지/PF 잔액·월이자·중도상환) 실재**, 무차입 IRR/NPV·S커브·세금 시점주입 | **은행 KPI 결손: MOIC·Equity IRR·LTV/LTC·break-even·RLV·복수IRR/음수잔액/covenant 경고 전무**(LTV 70% 하드코딩), golden spreadsheet 대조·sources=uses·월별 잔액 불변식 테스트 없음 |
| **P11** | 다목적 최적화 | 🟠 | SLSQP+가중합 Pareto, MC(seed 고정), 토네이도/OAT 민감도 | hard filter→surrogate→재계산→shortlist 파이프라인·LHS·correlation·Sobol·6목적함수·P80·covenant확률·seed재현/단조성/metamorphic 테스트 없음 |
| **P12** | 구조화 보고서 | 🟡 | **단일 정본모델→PDF/PPTX/DOCX 통일 렌더·fmt_value 표기 일원화**, verified URL만 통과·실데이터 없으면 섹션 생략 | **claim schema(FACT/CALC/ASSUMPTION…) 없음**, 미승인 가정 발행차단·citation 100%·수치일치0 강제·금지어 게이트 없음 |
| **P13** | 전문가 승인 | 🔴 | append-only 해시체인 감사원장(실재) | **Draft/MachineValidated/ExpertReviewed/Approved/Superseded 상태머신 전무**, 위험기반 정족수·조건부 승인 없음, **승인우회 차단 대상 자체가 없음**(전문가패널=LLM 페르소나 시뮬) |
| **P14** | 성장루프·운영 | 🟡 | 자가성장(propose-only PR+사람승인 게이트)·자가치유(rollback)·shadow 관측·few-shot 학습 | **CorrectionLog·9-way 에러 택소노미 없음**(severity도 high/med/low), canary/progressive 배포 게이트·재현테스트-선작성 강제 없음 |

**부합도 집계(정정)**: 🟢 1(P4) · 🟡 9(P0·P3·P5·P6·P8·P9·P10·P12·P14) · 🟠 3(P1·P7·P11) · 🔴 2(P2·P13).

---

## 2. 횡단 엄밀성 계약 매트릭스 (v4.0 공통 계약 — v2에서 12행 확장)

| 계약 | 부합도 | 실측 상태 |
|---|---|---|
| Zero-Trust 7구역(ACQUIRE→PROMOTE) | 🔴 | 데이터구역·승격 상태기계 전무, 서비스가 dict 직접 전달. 승격게이트는 SiteBasis 한 표면에만 국소 존재 |
| Stage Handoff immutable bundle | 🟠 | 제출용 zip(submission_bundle: manifest·sha256·provenance·양방향 검증)만 존재. bundle_id/parent/provenance.jsonl/decision/expiry·소비단계 사전검증 없음 |
| 필드수준 계보(7-hop)·UNTRACED 차단 | 🟠 | 분석-해시 DAG(lineage)만. SourceSnapshot→OriginalBytes 미도달, UNTRACED 발행차단 없음 |
| 계산엔진 규격(FormulaRegistry·Decimal·차원해석·오차전파) | 🟠 | 결정론 재계산 원장(calc_ledger 6산식·2%·NaN/inf/div0 가드) 실재. FormulaRegistry·Decimal 강제·dimensional analysis·해석적 오차전파(JΣJᵀ) 없음 |
| 권위계층 enforcement(6단계) | 🔴 | 2-티어 신뢰경계(caller vs server 보수채택)만. 6단계 위계·하위>상위 덮어쓰기 차단 없음 |
| DoR/DoD 11-상태·Basis Freeze | 🟠 | SiteBasis 5-상태(불법전이 예외·인간승인 필수·P0게이트) 실재 — 정신은 구현. 11-상태 전주기·freeze_id·Change Request 연동 아님 |
| Required Data Matrix(4등급·5상태) | 🔴 | 매트릭스 산출물 없음. critical 미상→보수차단 정신만 국소 구현 |
| Maturity(M0~M5)·Evidence(E0~E4)·Claim 등급 필드 | 🔴 | 산출물 등급 필드 전무(존재하는 maturity는 에이전트 2단계 성숙도로 무관) |
| **실무 결과물 승인등급 watermark**(INTERNAL DRAFT~SUPERSEDED) | 🔴 | PDF/도면/API에 등급 표시 체계 없음 *(v2 추가행)* |
| **Work Package 10구성**(Cover/Basis/CalcBook/Compliance Matrix/RFI/Handoff Certificate…) | 🟠 | 조각은 존재(법규검토서·산출근거·제출번들·체크리스트)하나 통합 Work Package 규격·Handoff Certificate 없음 *(v2 추가행)* |
| **실무 역할 13종·책임 분리**(Author≠Independent Checker) | 🔴 | 역할=인증 권한(role/tier)뿐. 결과물 책임 역할·독립검산자 분리 강제 없음(LLM 페르소나는 시뮬) *(v2 추가행)* |
| **독립검산 Checker Workflow** | 🟠 | calc_ledger(규제·수지 일부 독립 재계산)·cross_validation(다출처 UNANIMOUS/CONFLICT) 실재. 면적 BIM↔geometry↔표 3원, 물량 sample takeoff, 수지 golden spreadsheet 대조는 없음 *(v2 추가행)* |
| **검토계획·표본추출·Tolerance Register** | 🔴 | Critical 전수/위험기반 표본 계획·허용오차 분리 레지스터 없음(공차는 좌표정합에 국소) *(v2 추가행)* |
| **결과물 재작업 루프**(issue→invalidation→재실행→delta) | 🟠 | staleness "재분석 권장"·모순탐지 실재. issue 분류→dependency invalidation→결정론 재실행→delta report 폐루프 아님 *(v2 추가행)* |
| **WBS·산출물 사전·ORPHAN_TASK 차단** | 🔴 | task↔artifact↔검증↔소비 연결 사전 없음 *(v2 추가행)* |
| Interface Register·Change Request·변경영향 행렬 | 🔴 | 분야간 interface_id 등록·변경영향·dependency coverage 없음(변경 리스크 '예측'만 존재) |
| **시공성/조달성/유지관리/시운전/안전 5-review** | 🔴 | constructability 등 M3+ review 체계 미감사 범위서도 히트 없음 *(v2 추가행)* |
| **공정·원가 5D — EVM** | 🟡 | **EVM 실구현**: PV/EV/AC/SPI/CPI/EAC/ETC 완전형(billing_service `compute_evm`+이상탐지+해시체인, supervision_service PMBOK식) *(v2 추가행 — GAP-F 발견 강점)* |
| **공정·원가 5D — CPM** | 🔴 | CPM 네트워크(ES/EF/Float/주공정선)·공정표 전무(히트0). WBS↔activity↔기성 공통코딩 없음 *(v2 추가행)* |
| **감리·기성 검증** | 🟠 | 기성 EVM·과다청구 이상탐지·감리 진도추정(OpenCV)·계약 milestone 실재. **기성=min(계약,설치,합격)×단가 게이트식·ITP/검측·지급보류 규칙 없음** *(v2 추가행)* |
| **준공·인수 Closeout** | 🔴 | as-built·punch·O&M·준공 인계번들·실적 calibration 전무(히트0) *(v2 추가행)* |
| 다층 시뮬레이션 L0~L6·S1~S12·오라클 명시 | 🔴 | 단발 MC/shadow만. 계층 스택·통합스위트·오라클 규격 없음 |
| 결함예산 S0~S3·정지조건·릴리스 계약 | 🔴 | RELEASE/PILOT_ONLY/REJECT·verified_scope·critical_false_pass·정지조건 전무 |
| Evidence 아티팩트(docs/evidence/Px)·traceability.csv | 🔴 | 물리적 전무(런타임 evidence_contract는 별개 목적) |
| 검증 진입점(make test-golden/stress/simulate/verify-release) | 🟠 | CI(pytest+cov·vitest·tsc·eslint·playwright·locust) 실재. golden/property/stress/simulate/verify-release 전용 진입점 없음 |
| RFI·인허가 사전협의·보완관리 루프 | 🔴 | 해석충돌→질의 승격·회신원문 보존·보완요구 분해/redline/response matrix 전무 |

---

## 3. 분야별 작업패키지 A~J 커버리지 (v2 신설 — GAP-F 보충 실측 반영)

| 패키지 | 부합도 | 실측 요지 |
|---|---|---|
| A 토지·권리·도시계획 | 🟡 | 필지·용도지역·법규 기반은 강함(P0·P4·P6). 필지계보·확보 matrix·N-1은 P2 공백과 동일 |
| B 도로·접근·**교통** | 🟠 | 접도·도로 facts는 존재. **교통해석 전무**: queue/M/M/c/시거/교차로/LOS/swept path 히트0(주차 치수 KB만) |
| C 지형·토목·지반·배수 | 🟡 | **지형 실계산**: SRTM DEM 경사(중앙차분)·aspect·절/성토(cut/fill 체적)·단면 — 견고. **지반·배수 전무**: 흙막이 구조계산·유출량/유역·지지력 히트0(원가항목뿐) |
| D 건축법규·배치·면적 | 🟡 | P6·P8과 동일(법규검토·면적표·배치 실재, solver/주차배치 공백) |
| E 구조 개념 | 🟢 | **실재**: STRUCTURE_SPANS KB(KDS 근거 슬래브/보 두께비·무량판 공식·라멘 경간·벽식), 구조형식별 물량계수(RC/SRC/SC/PC) — 개념설계 수준 충족 |
| F 기계·전기·통신·소방 | 🔴 | **엔지니어링 전무**: 설비부하·용량·샤프트·기계실·제연 히트0. 법령 체크리스트·원가항목·분야 라벨만 |
| G 주차·물류·수직동선 | 🟠 | 법정대수+주차모듈 치수 KB만. stall 배치검증·램프·swept path·EV 대기 전무 |
| H 적산·공정·조달 | 🟡 | 적산(P9)+**EVM 실구현** 강점. CPM 공정망·조달위험·장기납기 없음 |
| I 시장·분양·운영 | 🟠 | **AVM 비교사례는 실계산**(IDW 입지보정·표본신뢰도·범위)·KOSIS 시점보정 실재. **흡수율·vacancy 정밀·NOI/cap 단순식·하방위험 부재, 분양 비교보정은 LLM 서술** |
| J 금융·세무·투자 | 🟡 | P10과 동일(waterfall 실재, 은행 KPI·covenant·세무 관점분리 공백) |

---

## 4. 진단 — 왜 이런 패턴인가

6개 축이 완전히 일관된 그림을 그린다:

1. **"정직성 DNA"는 코드 전반에 실재.** 자동보정 금지, NaN/inf/div0 가드, 미확정→보수적 강등(NEEDS_REVIEW/FIELD_VERIFICATION_REQUIRED), "검증된 MAPE 과장 금지", verified URL만 통과, now()/가짜해시 금지. → v4.0의 철학(무날조·UNKNOWN 보존)은 이미 문화로 정착.
2. **엔진의 계산은 실동작.** IFC(ifcopenshell)·월별 waterfall·EVM 완전형·DEM 절성토·구조 예비치수·Monte Carlo(seed)·calc_ledger 결정론 재계산·CalcTrace 강제 emit·단일정본 다포맷 렌더·해시체인 감사원장. → 스텁이 아니라 진짜 계산.
3. **그러나 "계약층"이 비어 있다.** 서비스들이 dict를 직접 주고받으며 국소 검증·강등을 붙이는 구조. v4.0이 요구하는 횡단 골격(구역 승격·bundle 계약·원본 역추적·이중통제·승인 상태머신·결함예산 릴리스 판정)이 미배관.
4. **정밀 도메인의 층위가 갈린다.** 실계산(지형·구조·EVM·AVM) / 2D·계수 근사(Envelope·적산 Q등급) / 전무(MEP·교통·CPM·ITP·Closeout). 전무 영역 중 MEP·교통은 **전문 외부지식 의존도가 높아** 자동화 우선순위 판단이 필요.

**결론**: 재작성이 아니라 **횡단 계약층을 얇게 관통시키고, 정밀 도메인을 선택적으로 심화**하는 문제다.

---

## 5. 고도화·보강 로드맵 (v2 — 전 공백 완전 매핑)

원칙: ①안전·법적 신뢰성(S0/S1급) 먼저 ②기존 자산 위 계약층 관통(재작성 금지) ③각 웨이브 성장루프 9.5 게이트 ④전무 전문영역(MEP·교통)은 명시적 후순위/스코프 결정.

### 🔴 Wave 1 — 거버넌스 골격 (승인우회·false-pass 직결, 최우선)

| ID | 항목 | 내용 | 재사용 자산 | 규모 |
|---|---|---|---|---|
| W1-1 | Rule dual-control(SoD) | HITLTask에 author/reviewer/approver 신원 + approve() 승인자 인자 + 동일인 작성·승인 기술적 차단 | hitl_queue·rule_candidate | 중 |
| W1-2 | P13 전문가 승인 상태머신 | Draft/MachineValidated/ExpertReviewed/Approved/Superseded + 위험기반 정족수(Critical 2인) + 조건부승인(condition/owner/deadline/만료) + "승인없이 Published 경로 0" 게이트 | SiteBasis 상태기계 패턴·감사원장 | 대 |
| W1-3 | golden false-pass=0 회귀 | 인허가 판정 expert golden fixture + hard-rule false-pass=0 스위트(현 false-FAIL 방지에 대칭 추가) | evaluator·finding_gate·기존 golden(추출용) | 중 |
| W1-4 | claim schema + 발행차단 | FACT/CALCULATION/ASSUMPTION/INTERPRETATION/RECOMMENDATION 분류 + ASSUMPTION 미승인 발행차단 + '확정/보장/완벽' 결정론 금지어 게이트 + **승인등급 watermark**(INTERNAL DRAFT~APPROVED BASELINE, PDF/API 표시) | ReportModel·evidence_bridge | 중 |
| W1-5 | 법령 위계 precedence resolver *(v2 추가)* | authority/specificity/delegation(상위법·특별법·위임) 상충 해소 + 상충 rule graph 검출(현 시행일·값출처만) | reg_graph·calc_rule effective_on | 중 |

### 🟠 Wave 2 — 추적성·데이터 계약 (감사·재현 기반)

| ID | 항목 | 내용 | 재사용 자산 | 규모 |
|---|---|---|---|---|
| W2-1 | Fact Ledger + SourceSnapshot | Fact 7상태(OBSERVED~STALE) + SourceSnapshot 필수필드(authority_grade/observed_at/effective_from/detected_crs/pii_classification) + raw+checksum 불변저장 + dead-letter; 핵심 커넥터(VWorld/G2B)에 base client 회복탄력성 적용 | base_client·public_data_registry | 대 |
| W2-2 | 필드수준 계보 + UNTRACED 차단 | lineage DAG를 SourceSnapshot→OriginalBytes까지 확장 + 미추적 claim 발행차단 | ledger/lineage·analysis_ledger | 중 |
| W2-3 | Stage Handoff bundle 계약 | submission_bundle 일반화 — bundle_id/parent/provenance.jsonl/assumptions/conflicts/validations/decision/expiry + 소비단계 사전검증 | report/submission_bundle | 중 |
| W2-4 | Required Data Matrix + Zero-Trust 승격 | 4등급 매트릭스+critical MISSING→BLOCKED; SiteBasis 승격게이트를 파이프라인 전역 원칙화(권위계층 2-티어→6단계 확장 포함) | site_basis_state·trust | 대 |
| W2-5 | ParcelGraph(P2) *(v2 추가)* | 인접(경계 intersection)·소유·통행 간선 + articulation/critical parcel + N-1 시나리오 | auto_zoning 인접판정·shapely | 중 |
| W2-6 | CSM 조립체 + Risk Register *(v2 추가)* | P0~P4 사실의 단일 CSM snapshot + Risk=P×I×D·Red Flag(평균상쇄 금지) + dependency 자동 부분 invalidation(현 '권고'→실행) | SiteBasis·staleness·contradiction | 중 |

### 🟡 Wave 3 — 정밀 도메인 심화 (정확도·상용성)

| ID | 항목 | 내용 | 재사용 자산 | 규모 |
|---|---|---|---|---|
| W3-1 | 은행 KPI 완성(P10) | MOIC·Equity IRR·LTV/LTC·break-even·RLV·복수IRR/음수잔액/covenant 경고 + **golden spreadsheet 대조·sources=uses·월별 잔액 불변식 100% 테스트** + 명목/실질·매입세액·자본화이자 | cashflow_generator·dcf_assembly | 대 |
| W3-2 | 3D exact solid Envelope(P7) | polygon offset·half-space·solid boolean 차감 + 차감체적/offending face + conservative/base/conditional 3종 + point/face property test + round-trip 검증 | geometry_invariants·solar_envelope·shapely | 대 |
| W3-3 | 적산 Q1~Q4 + back-test(P9) | tier 명시분리 + 실적 back-test(APE/MAPE/bias)+outlier + MC 상관 + 가설/예비비 비목 | geometry_qto·boq_bim_merge·cost_monte_carlo | 중 |
| W3-4 | 최적화 파이프라인(P11) | hard filter→surrogate→재계산→Pareto→shortlist 5종 + LHS+correlation+Sobol + P80 + covenant확률 + seed재현/단조성/metamorphic 테스트 | ai_optimizer·monte_carlo_engine | 대 |
| W3-5 | 주차 배치·3D clash(P8) | stall/aisle 배치검증·ramp 구배/전이·swept path + 3D 공간 clash 검출(현 triage→검출) | PARKING_MODULE KB·bimir | 중 |
| W3-6 | RFI·사전협의·보완관리 루프 *(v2 추가)* | 해석충돌→RFI 승격(question_id/기관/조문/해석안/대안) + 회신원문 SourceSnapshot 보존 + 프로젝트결정 vs 룰후보 분류 + 보완요구 분해·redline·response matrix | deliberation 엔진·reg_reconcile | 중 |
| W3-7 | Rule DSL + 컴파일러 *(v2 추가)* | JSON/YAML rule schema + compiler + formula/rounding/citation/approval/tests 필수요소 강제(현 Pydantic 계약→선언적 DSL) | calc_rule·calc_params.json | 대 |
| W3-8 | 시장·분양 정밀화(패키지I) *(v2 추가)* | 흡수율(absorption curve)·vacancy/NOI 정밀·하방위험 분포 + 분양 비교사례 보정을 LLM 서술→결정론 계산(AVM 패턴 확장) | avm_service·cost_index_service | 중 |

### ⚪ Wave 4 — 운영·릴리스 성숙도 (파일럿 출하 게이트)

| ID | 항목 | 내용 | 재사용 자산 | 규모 |
|---|---|---|---|---|
| W4-1 | CorrectionLog + 에러 택소노미 | 9-way 라우팅 + severity S0~S3 + 재현테스트-선작성 강제 | growth 루프·verifier issue_types | 중 |
| W4-2 | 다층 시뮬레이션 L0~L6 + S1~S12 | 계층 스택 + 통합 스트레스 스위트 + **오라클 명시 규격**(closed-form/golden/invariant/전문가) | cost_monte_carlo·shadow_simulator | 대 |
| W4-3 | 결함예산·릴리스 계약 + 등급필드 | RELEASE/PILOT_ONLY/REJECT + verified/unverified_scope + critical_false_pass=0 정지조건 + maturity(M0~M5)/evidence(E0~E4)/claim_id 필드 + **Tolerance Register**(법정한계/수치오차/측량정확도/표시반올림 분리) | — (신규) | 중 |
| W4-4 | Evidence 아티팩트 + 진입점 | docs/evidence/Px + traceability.csv(requirement↔code↔test↔evidence) + make test-golden/property/stress/simulate/verify-release | CI 기존 잡 | 중 |
| W4-5 | Interface Register + Change Request | 분야간 interface_id + 변경영향 행렬 + dependency coverage(누락노드 0 증명) + **재작업 루프 폐쇄**(issue→invalidation→재실행→delta report) | design_change_predictor·staleness | 중 |
| W4-6 | 5D 공정 연동(CPM) *(v2 추가)* | CPM 네트워크(ES/EF/Float/주공정)+공정표 + WBS↔activity↔기성 공통코딩 + EVM 연결(EVM은 기실재) | billing_service EVM·work_breakdown | 대 |
| W4-7 | 감리·기성 게이트·준공 Closeout *(v2 추가, 조건부)* | 기성=min(계약수량,설치,합격)×승인단가 Rule화 + ITP/검측·지급보류 + as-built·punch·O&M Closeout bundle. **전제: 시공단계를 플랫폼 적용범위에 포함할지 사업 결정 필요**(v4.0도 조건부) | supervision_service·contract_service | 대 |

### 명시적 후순위·스코프 결정 필요 (로드맵 비배정 사유 기록)

| 항목 | 사유 |
|---|---|
| MEP·소방 엔지니어링(패키지F) | 부하·용량·제연 계산은 설비 전문지식·기준 DB 의존도가 높음. **기획단계는 W3에서 '승인된 단위부하 변수화+공간 schedule'로 최소화**하고 실엔지니어링은 전문가 협업 결정 후 |
| 교통 대기행렬·시거(패키지B) | M/M/c·DES는 교통영향평가 도메인. **swept path·램프(W3-5)까지만 내재화**, 정밀 교통해석은 외부 성과 연계 결정 후 |
| 지반·배수 수리계산(패키지C 잔여) | 흙막이 구조·유출량은 지반조사 실데이터 전제. v4.0 자체가 "지반자료 없으면 공법 확정 금지·P80 allowance 제시" — **현 단계는 조사요구서+allowance 범위 산출(W3-3에 편입)** |
| P0 소보강(체크디지트·후보점수·편입상태) | 위험도 낮음 — W2-5(ParcelGraph) 착수 시 동반 처리 |

---

## 6. 착수 순서·의존관계·검증 게이트

```
W1(거버넌스) ──→ W2(추적성) ──→ W3(정밀도) ──→ W4(출하게이트)
   │                │                │
   └ W1-2 승인SM은 W2-3 bundle의 decision 필드가 소비
     W2-1 Fact Ledger는 W2-2 계보의 하부
     W3-1(은행KPI)·W3-2(solid)는 상호 독립 — 병렬 가능
     W4-3 릴리스 계약은 W1~W3 산출을 집계(최후)
```

- **순서 근거**: W1은 v4.0이 "허용 0"으로 규정한 S0(승인우회·법규 false-pass) 직결 + 규모 중간 → 신뢰 조기 확보. W2가 승인·차단이 딛는 추적 기반. W3은 계약층 위 정밀도(은행 KPI가 상용 신뢰성 직결로 첫손). W4는 앞 웨이브 집계 게이트.
- **웨이브별 완료 게이트(DoD)**: 각 웨이브는 ①신규·수정 코드 성장루프 4렌즈 9.5 통과 ②무-DB 전체 pytest 무-hang ③해당 v4.0 Gate 조항의 기계검증 테스트 추가(예: W1-2는 "승인없이 Published 경로 0" 시도 테스트) ④배포 인계문서. 
- **병렬 트랙**: 기존 관례대로 웨이브별 전용 워크트리·브랜치(다세션 충돌 방지).

---

## 7. 완성도 지수 추정 (v4.0 §8: M=min(R,C,T,V,O,S), 파일럿 게이트 전축 ≥0.90)

정적 실측 기반 추정(±0.1). **min이 지배하므로 현 M ≈ 0.2**:

| 축 | 추정 | 근거 |
|---|---|---|
| R 요구추적 | ~0.3 | 기능은 광범위하나 requirement↔code↔test 추적표 부재 |
| C 계산·규칙 커버리지 | ~0.65 | 핵심 계산 실동작·CalcTrace, 그러나 FormulaRegistry·Q등급·정밀 3도메인 공백 |
| T 테스트·골든·스트레스 | ~0.5 | 7천+ 유닛·계약 테스트 실재, golden(판정·수지)·property·stress 스위트 부재 |
| V 실데이터·전문가 검증 | **~0.2** | v4.0 규칙상 실데이터·전문가 병행검증 전 V≤0.5; 전문가 승인 체계 자체가 미구현이라 하한권 |
| O 운영·관측·복구 | ~0.6 | 배포·rollback·모니터링·자가치유 실재, canary/progressive·DR 시험 부재 |
| S 보안·감사·승인 | ~0.45 | 감사원장·RBAC·시크릿 관리 실재, 승인 상태머신·SoD·watermark 부재 |

→ **파일럿 게이트까지의 지배 경로는 V·R·S** = 정확히 Wave 1(승인·SoD)·Wave 4(추적표·릴리스계약)·실데이터 검증. 로드맵 우선순위와 일치함을 확인.

---

## 8. 정직성 선언 (v4.0 릴리스 계약 정신 준수)

- 본 분석은 **정적 코드 실측**(file:line grep/read, 6축 병렬 정찰)이며 런타임 실행·실데이터 검증은 하지 않았다. "MISSING"은 "해당 어휘·구조의 코드 부재 확인(검색 히트 0)"이지 존재 불가능의 증명은 아니다.
- **v2에서 정정된 v1 결함**: ①집계 오류(🟡8·🟠4·🔴4 → 🟡9·🟠3·🔴2) ②미감사 7영역(토목/구조/MEP/교통/시장/5D/감리·준공) 보충 실측 후 반영 — 이 과정에서 **EVM 완전 실구현·구조 예비치수·DEM 절성토라는 v1 미기재 강점 발견** ③확인된 전 공백의 로드맵 배정(v1 누락 9건: 법령위계·RFI·Rule DSL·ParcelGraph·CSM/Risk·권위계층·watermark·Tolerance·CPM) ④횡단 계약 12행 추가.
- **잔여 미검증**: 시공성 5-review·인허가 제출 보완 워크플로의 세부는 관련 히트 부재로 MISSING 추정이나 전수 감사는 아님. energy/esg/smart_city 등 v4.0 범위 밖 서비스는 의도적으로 제외.
- 부합도는 **v4.0(차세대 스펙) 기준**이다. 정확한 서술은 "1세대로 잘 만들어졌고, v4.0 거버넌스로의 승격이 남았다"이다. 규모(중/대)는 상대 추정이며 착수 시 웨이브별 성장루프로 재산정한다.
