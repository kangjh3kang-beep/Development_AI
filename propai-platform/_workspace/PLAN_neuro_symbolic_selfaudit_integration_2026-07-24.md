---
title: 신경-기호 자가검증·권원분석 통합 마스터 실행계획 (첨부 제미나이 마스터플랜 × 현 플랫폼 대조)
created: 2026-07-24
status: 계획 확정(실행 승인 대기)
supersedes-integrates: _workspace/PLAN_analysis_self_audit_pipeline_2026-07-24.md (자가검증 정본을 흡수·확장)
source-docs: 사용자 첨부 제미나이 4부작(대지사용권원 ZKP·3D트윈 마스터 / 정비사업 권원확보 / 실시간 API Graph DB / 신경-기호 멀티에이전트)
ground-truth: 3-agent 코드 실측(verif-map·rights-domain·infra-feas) 2026-07-24
---

# 신경-기호 자가검증·권원분석 통합 마스터 실행계획

## 0. 이 문서의 위상 — 무엇을, 왜

사용자 요청: 첨부 제미나이 마스터플랜을 정밀분석하고 **현 플랫폼 실구현과 대조**, 옵시디언(기존 자가검증 계획)을 참조해, **"분석 파이프라인이 라이브검증/IDE에서 잡히는 correctness 오류를 못 잡는"** 근본 문제를 해소하는 100% 완성도 통합 실행계획 수립.

**결정적 발견:** 첨부 문서의 **가장 견고한 핵심(자가검증 `field_audit` Tier A/B/C·`cross_field`·골든시드 G1~G6)은 우리가 이미 확정해 둔 `PLAN_analysis_self_audit_pipeline`의 D1~D6과 정확히 동일**하다. 제미나이는 이 골격을 재확인하면서 ①권원분석 도메인(G7~G24) ②능동 자가증식(Proactive Fuzzer) ③금융 PF ④3D 트윈 ⑤Neo4j ⑥ZKP를 얹었다. 따라서 본 계획은 **held 자가검증 계획을 정본으로 흡수하고, 제미나이 확장분을 현실 대조로 취사선택**한다.

---

## 1. 첨부 문서 정직성 판정 (무목업·라이브검증 원칙)

문서는 존재하지 않는 코드를 존재하는 것처럼 서술한다. 실측으로 확인한 진위:

| 문서 주장 | 실존 여부 | 정직 판정 |
|---|---|---|
| `services/verification/field_audit/` Tier A/B/C·cross_field·rules_registry·runner | **부재** (실제는 range_rules·calc_ledger·verifier_service·hotpath_guard) | 우리 held 계획의 목표 구조 = 미구현 |
| `zkp_verifier.py` (zk-SNARKs) | **부재** | 문서 코드는 **SHA256 해시커밋 — 진짜 영지식증명 아님**. 원본 은닉만 하고 증명 불건전(circuit_result를 평문 필드로 반환). 실 zk는 별도 proving system(Circom/snarkjs) 필요 |
| `pf_stress_testing.py` (MonteCarloPFEngine) | **부재** — 단 대체 자산 `feasibility/monte_carlo_engine.py` 실존(10K sim) | 파일은 없지만 **동등 엔진이 이미 있다** → 재작성 아닌 배선 |
| `rhino_headless_pipeline.py` (Rhino Compute) | **부재** — Rhino Compute 서버 없음 | ★Rhino Compute는 그린필드·유료 인프라. 기존 terrain/geometry 엔진으로 대체 가능. 문서 코드도 `FALLBACK_MOCK` 반환 |
| `proactive_anomaly_proliferator.py` | **부재** | 우리 held 계획 Wave4(자가치유)의 능동형 확장 — 값어치 있음 |
| Neo4j Graph DB 토폴로지 | **흔적 0** | 관계형(SQLAlchemy)+다필지 통합으로 이미 해결. 그래프 도입 ROI 불충분 |
| "SVR 100% 달성·Latency 3.8초·파산확률 12.4%" | — | **날조된 시뮬레이션 수치**. 실행결과 아님 → 목표치로만 취급, 근거로 인용 금지 |
| 대지사용권원 확보 % 법령 테이블(주택법 80/15·95, 도정법 3/4 등) | 부분 실존(scenario_simulator MAGDO_RULES) | 법령 수치 자체는 대체로 정확 — 단 값을 하드코딩 말고 파라미터 DB로 |

**원칙:** 문서의 화려한 레이어(ZKP·Rhino·Neo4j·LoRA)는 사용자의 진짜 통증("파이프라인이 correctness를 못 잡는다")과 **직결되지 않는다.** 정답은 자가검증 correctness 레이어이며 그건 이미 우리 계획이다.

---

## 2. 현 플랫폼 대조 (실측 근거 기반 gap analysis)

### 2.1 자가검증 아키텍처 — 하한선만 있고 상한선이 없다

**현행이 커버하는 것(하한선·grounding·정직성):**
- `range_rules.py:84-190` — 숫자 범위(건폐율>100%·용적률 0~2000%·면적<0)·법정한도 대조(자연녹지 200% 할루시네이션 적발)·시세배수 극단값. `_strip_scenarios()`로 종상향 시나리오 제외.
- `calc_ledger.py:103-165` — 결정론 산식 7개(용적률·건폐율·순이익·수익률·평당공사비·취득세) Python 직접 재계산, 상대오차 2%.
- `verifier_service.py:143-222` — 3단 캐스케이드(prescan→calc+range→LLM grounding).
- `public_data_registry.py` FreshnessChecker(TTL: transaction 30일·official_price 365일), `validator.py:118-226` Pydantic+AnomalyDetector(IQR).

**현행이 커버 못 하는 것(도메인 correctness 상한선) = 이번 캠페인의 표적:**
- 규제→리스크 하한 매핑 검증 0(risk_keywords 하드코딩만).
- POI dedup 정합(학교 과카운트).
- 인허가 매트릭스 커버리지(침묵 폴백 후 분양가 산출).
- 시세 방법론(지역 배수 하드코딩, 실거래 comparable 미사용).
- 실거래 분포 품질(샘플<5 무검증·지역/시기 층화 없음).
- 면적 SSOT·특이부지 정합.

**★가장 중요한 구조 결함:** **도메인 correctness 게이트가 `analyze()` 주경로에 미배선**. `comprehensive_analysis_service.analyze()`(:478)는 8섹션 조립·결정론 specialist 교차검증(:1077, `allow_llm=False`)까지는 주경로에서 하지만, **도메인 correctness field-audit**(규제→리스크 하한·POI dedup·매트릭스 커버리지·시세 방법론)는 호출하지 않고 special_parcel/warnings만 부착 후 `return result`(:1102). correctness 검증은 오직 외부 `POST /verify/analysis`(routers/verification.py:20)로만 존재. **즉 화면·보고서에 나가는 분석은 도메인 correctness 게이트를 안 거친 산출이다.**(specialist 교차검증은 있으나 위 6대 결함류를 못 잡음 — 그게 D1~D6이 라이브에 살아남은 이유.) 이것이 "IDE/사람은 잡는데 파이프라인은 못 잡는" 구조적 원인.

### 2.2 6대 결함 실제 현황 (07-24 계획 이후 일부 변동 — 실증)

| 결함 | 상태 | 근거(파일:라인) | 조치 |
|---|---|---|---|
| **G1** 군사 통제/제한보호·방공기지 위해성 "낮음" | ❌ **미수정 잔존** | `comprehensive:1646-1668` risk_keywords가 "비행안전구역:보통" 등 일부는 있으나 **severity 과소평가 + "통제보호/제한보호/방공기지" 키워드 누락** (비행안전은 존재하나 "보통"으로 저평가) | **P0 최우선** |
| **G2** 학교 POI dedup "5개교" 과카운트 | ❌ **미수정 잔존** | `kakao_local:26-40`·`land_info:1190` 이름병합(모학교) 없음, raw append | **P1** |
| **G3** 관리지역 인허가 판정불가 | ✅ 정직 판정불가(수정됨) | `permit_validator:61-85` permitted_types_known+판정불가 사유 | coverage.py로 **갭 표면화**(조용한 판정불가→명시) |
| **G4** 시세 공시지가×1.2 | ⚠️ 부분 | `comprehensive:1303-1323` MARKET_MULTIPLIER_MAP 1.1~1.8+폴백 1.2, comparable 부재 | 실거래 원/㎡ 경로 완성 |
| **G5** 실거래 최저 2만원·apt혼입 | ✅ 수정됨 | `price_stats:21-50` robust_price_stats log-IQR trim | **회귀 골든으로 잠금** |
| **G6** 경사도 고아 | ⚠️ 부분 | `comprehensive:264-294,794` terrain→detect_special_parcel 주입됨, **UI 렌더 미확인** | 소비처 렌더 추적·검증 |

시사점: 계획을 held 하는 사이 G3/G5는 이미 봉합됐다(정적 계획 수치 재확증 의무의 실례). **G1·G2가 여전히 라이브 오도** — 가장 심각한 둘이 열려 있다.

### 2.3 권원분석 도메인 — ~70-80% 그린필드, 단 원천데이터·부분블록 견고

| 도메인 | 분류 | 근거 | 갭 |
|---|---|---|---|
| 소유권/사용권원 확보율 | **b 부분** | `registry_analysis_service:146-164` _derive_ownership(owners/share/단독·공동) | 확보율% 집계·주택법 80/15·95·도정법 3/4 연산 없음 |
| 매도청구/토지수용 | **b 부분** | `scenario_simulator:24-84` MAGDO_RULES 9사업방식·매도청구 잔여율·법령근거 | 10년 제척·토지수용 타임라인·제척기간 없음 |
| 신탁·우선수익권 | **b 부분** | SalesTrustAccounts(분양신탁만) | 토지신탁 채권최고액·신탁해지 예비비 없음 |
| 대지권 미등기 | **b 부분** | `land_share_service:1-80` analyze_by_pnu 표제부↔전유부 교차·미등기 의심경고 | 세대별 자동태깅(등기부 대지권등록부=유료→정직선언) |
| 상속미등기/공유지분 | **c 전무** | — | 전체 |
| 지분쪼개기·권리산정기준일 | **c 전무** | — | 필드·비교 로직 전무 |
| 무허가 입주권(조례 기준일) | **c 전무** | — | 전무(unauthorized=조회실패 상태값뿐) |
| 국공유지 무상양도(도정법 98조) | **c 전무** | registry owner_type 표기만 | 전무 |
| 금융 PF·DSCR·이자손실 | **c 전무**(엔진 부재는 정직 선언) | checklist:28-30 | Monte Carlo 엔진은 있으나 권원지연↔이자 배선 없음 |

**원천 데이터 파이프라인은 강함:** Hyphen/Tilko 등기·건축HUB·VWorld·MOLIT·MOLEG 전부 구성됨. 그러나 `owners`/지분은 registry 응답에만 있고 **DB 미영속**, 다필지 통합분석은 면적가중만 있고 **소유권 통합 없음** → 권원 correctness의 병목은 데이터가 아니라 **hydration 배선**.

### 2.4 중량 인프라 — 대부분 기존자산으로 충분, 그린필드는 불요

| 레이어 | 판정 | 근거 |
|---|---|---|
| Monte Carlo PF | ✅ **READY** | `feasibility/monte_carlo_engine.py:22-100`(10K sim·fallback 1K), finance_service NPV 배선 |
| 3D 디지털 트윈 | ⚠️ **부분(Rhino 불요)** | terrain_service SRTM 경사/토공, Three.js/ifcopenshell/glTF 분리 존재, ray-cast·polygon clip 완비 |
| Neo4j Graph DB | ❌ **불요** | 관계형+다필지 통합으로 해결, ROI 불충분 |
| LLM self-correction | ⚠️ 단일재시도 | `base_interpreter:421-699` set_retry_feedback 1회 — L1 스팟수정엔 충분, SagaLLM급 불요 |
| ZKP zk-SNARK | ❌ **불요** | Fernet platform_secrets+해시체인 append-only 원장으로 컴플라이언스 충족. 문서 해시커밋은 zk 아님 |

---

## 3. 통합 아키텍처 판정 (ADOPT / ADAPT / EXTEND / DEFER-REJECT)

| 제미나이 제안 | 판정 | 실행 방식 |
|---|---|---|
| 자가검증 Tier A/B/C(field_audit) | **ADOPT** | held 정본 그대로 + ★analyze() 주경로 배선 |
| 골든 G1~G6 회귀 | **ADOPT(현실 재정렬)** | G1·G2 flip, G3·G5 잠금, G4·G6 완성 |
| Proactive Anomaly Fuzzer | **ADOPT** | Wave4 능동형 확장(HITL+특이성 감지) |
| 권원 correctness(G7~G24) | **EXTEND(데이터 배선 조건부)** | registry_analysis/scenario_simulator/land_share 위 확장. 유료·전무 항목은 정직선언 |
| Monte Carlo PF | **ADAPT** | 기존 monte_carlo_engine 재사용, 권원지연 ΔT↔이자/DSCR 배선 |
| 3D envelope | **ADAPT(스코프)** | 기존 geometry로 부분, Rhino 그린필드 REJECT |
| self-correction retry loop | **ADAPT** | 기존 단일재시도 활용, field_audit finding을 retry feedback으로 |
| Neo4j / ZKP zk-SNARK / LoRA / SagaLLM | **DEFER-REJECT** | 관계형·Fernet·단일재시도로 충분. 근거 없는 인프라 부담 회피 |

**핵심 원리(held 계획 유지):** 박제하는 것은 *값*이 아니라 *규칙·관계·출처·방법론*. 값은 런타임에 권위 소스에서 신선하게 당기고, 검증기는 "그 값이 규칙에 맞는가"만 본다 → 수시변동 데이터에도 검증기가 안 낡는다. correctness 게이트는 현행 정직성·grounding과 **병렬**로, 그리고 반드시 **analyze() 주경로 위에** 놓는다.

---

## 3.5 근본 뼈대 재구성 — 삼각 척추 × 비대칭 계약 (사용자 재검증 + architect 적대검증 반영)

**재검증 계기:** 초안(§4 이하)은 사용자가 신고한 통증("파이프라인이 correctness를 못 잡음")은 정확히 해결하나, **검증 척추 하나만** 세웠다. architect 적대검증 정렬점수: 커버리지 척추 ~35%·생성 오케스트레이션 척추 ~15%·실무결과물 ~40%. 사용자가 지목한 **근본 뼈대는 삼각 척추**이며, 초안은 ①을 후방배치·②를 최소화했다. 이를 재구성한다.

### 제1원리 — 비대칭 계약: **neuro proposes, symbolic disposes** (출처·재현가능성 경계, 3계층)

"시니어 LLM이 전체 통할"을 **문자 그대로 하면 오히려 후퇴**한다(과잉교정): 6대 결함은 전부 **결정론 버그**라 LLM 통할이 예방 못 하고, 값을 LLM이 생산하면 `calc_ledger` 재계산-대조 검증모델이 붕괴(자유서술 수치는 재도출 불가) → **correctness 검증 불가능**.

★사용자 정정으로 경계가 정밀화됨: LLM 통할의 대상은 "원천데이터 생성"이 아니라 "**사실검증된 수집 원천데이터를 기반으로 한 분석·종합**"이다. LLM이 원천데이터를 생성하면 곧 할루시네이션+재현불가(=calc_ledger 붕괴와 동일 문제의식). 따라서 경계는 "수치 vs 서술"이 아니라 **출처·재현가능성(provenance/reproducibility)**이며 3계층으로 분업한다:

| 계층 | 내용 | 권한 |
|---|---|---|
| **① 원천데이터** (VWorld·MOLIT·등기·건축HUB…) | 권위 소스 수집·사실검증 | **LLM 생성 금지**(출처 추적). LLM은 "무엇을·어디까지 수집"만 **판단(propose)** |
| **② 파생 결정값** (FAR·확보율·건폐율…) | ①에서 결정론 산식 계산 | **LLM 생성 금지**. calc_ledger 재도출 가능(reproducible) |
| **③ 분석·종합·서술·시나리오·전문가판단** | ①②를 근거로 통할 | **LLM 오케스트레이션(propose)**, 심볼릭 게이트가 구속(dispose) |

즉 **neuro(시니어 오케스트레이터)** = ③ 통할 + ①의 수집 넓이 판단. **symbolic(불변식·골든·게이트)** = ①② 출처·수치의 권위(dispose). 선례: `verifier_service.py:143`이 이미 이 패턴(on-path 결정론 재계산 + off-path LLM 그라운딩) → **원리로 승격·명문화**.

### 제1원리 계 — 자가교정은 계층마다 메커니즘이 다르다 (현 플랫폼 실측)

architect가 이 계획의 오류 2건을 잡고 교정한 것 = "독립 적대감사 → 교정 → 재검증". **플랫폼이 자기 분석에 대해 이걸 하도록** 만드는 게 자가검증의 본질. 현 실측:
- **실존(③ 서술 자가교정)**: `pipeline.py:350 _verify_and_maybe_retry` — 검증(v1)→fail시 이슈주입 1회 재생성→**재검증(v2)**→통과 채택/실패 시 원본+경고배지. 상한 1(무한루프·비용통제). `blindspot_interpreter`(design_audit)도 동일. **단 (a)LLM 서술 sections만 (b)`/pipeline`·design_audit에만·핵심 `analyze()`엔 부재 (c)결정론 버그 못 고침**(틀린 값을 충실히 서술할 뿐).
- **미구축(①② 결정론/도메인 자가교정)**: 문서의 `SelfCorrectionController.compile_with_validation`·`llm_auditor` 부재. **결정론 결함은 LLM 재생성으로 불가** → **불변식(field_audit)이 잡아 P1 제자리 재계산 / P0 차단**해야 함. = Phase0.

★계약: **③ 오류→LLM 재생성 자가교정**(기존 루프 일반화·`analyze()`로 확장), **①② 오류→불변식 기반 자가교정**(field_audit 신설). 두 메커니즘을 혼동하면(결정론 버그를 LLM 재생성으로 고치려 하면) 실패한다.

### 제1원리 계2 — 결정론 오류 자가교정 taxonomy (오라클 문제·정직한 완결 경계)

"LLM이 자기가 안 만든 결정론 결함을 재생성으로 못 고침"의 해결은 **탐지와 교정을 분리**하고 **오라클 문제**를 정면으로 다뤄야 완전하다.

**탐지(detection) — 오라클 유무별:**
- **불변식(권위 오라클 대조)**: 기대값이 **버그난 계산경로와 독립된 권위 소스**에서 와야 실효(같은 소스면 버그 재구현 = "검증기를 누가 검증하나"). D1의 severity·D3의 매트릭스는 **독립 권위표(법제처/국토계획법 별표 또는 손큐레이션 SSOT)**를 기준으로.
- **변성관계(metamorphic, 오라클 불요)**: 정답 몰라도 관계 위반 탐지 — "필지 추가→총면적 감소 불가"·"더 엄격한 zone→더 높은 FAR 불가"·"실효FAR ≤ 법정FAR".
- **차등/교차경로(differential, 오라클 불요)**: 독립 계산경로 발산 탐지 — 단일필지 vs 다필지 경로 동일입력(면적 SSOT류·D6 인접).
- **속성기반/퍼저**: 조합공간 위반 케이스 자동발굴(척추 A).

**교정(correction) — 3분기, 자율성 경계:**
1. **KNOWN 버그(D1~D6)** → 결정론 root 수정(SSOT keyword·dedup fn·matrix) + 불변식 **회귀잠금**. 완전 자율. (Phase0 W1)
2. **UNKNOWN + 기계 권위 오라클 존재**(법제처 MOLEG·국토계획법 별표 API) → 불변식이 오라클 불일치 탐지 → **오라클값으로 P1 자동교정**. 자율.
3. **UNKNOWN + 기계 오라클 없음** → 탐지 → **P0 격리/플래그 → growth-loop/HITL 에스컬레이션 → 실무자(감정평가사·건축사)가 정답 authoring → 불변식 잠금**. HITL-in-loop(오라클 문제의 근본 한계 — 완전 자율 아님). HITL 정답은 **오라클로 축적**되어 다음부터 경우 2로 승격.

**★정직한 완결 경계:** "모든 결정론 버그 자율교정"은 오라클 문제로 **원리적 불가**(SVR 100%식 과장 금지). 달성가능한 완결 = **탐지 완전(불변식+변성+차등+퍼저) + 교정 3분기(오라클 있으면 자율, 없으면 HITL) + HITL 정답의 오라클화(성장)**.

**Graceful degradation(실무 필수):** P0는 **전체 분석 실패가 아니라 해당 필드만 격리 + "검토 필요" 배지**, 나머지 결과물은 정상 제공(차단이 실무자 무용지물을 만들면 안 됨). 격리 필드는 growth-loop 큐로.

### 척추 A — 커버리지(조합 완전성) · 現 ~35% → Phase0 코어로 승격

★교정: **골든 예시(G1~G30)는 앵커일 뿐 커버리지가 아니다**(30개 ≠ 조합 커버리지, "30개 통과=안전"은 거짓 안심). 조합폭발(zone~20 × 지목~28 × 규제overlay × 권리상태 × 면적 × 도로…)은 열거 불가.
- **입력 차원 레지스트리(신설)** — 분석에 영향하는 차원×값 목록을 SSOT로 박제.
- **조합 샘플러(pairwise/N-wise)** — 2-way 결함 99% 색출 계통 샘플링(문서 pairwise 개념 채택).
- **보편양화 불변식 스위트** — 규칙을 "예시 성립"이 아니라 "**모든 입력에 성립**"으로(`calc_ledger` 재계산 모델을 도메인 correctness로 확장).
- **속성기반/변성 테스트(property-based/metamorphic)** — 입력 자동생성으로 조합공간 계통 커버.
- **골든은 회귀 핀으로 강등** · **Proactive Fuzzer는 W4→A척추의 tail 발굴기로 재배치**(반응형 미지 발굴).

### 척추 B — 생성 오케스트레이션(풍부한 실무 결과물) · 現 ~15% → 신설

현 생성경로 실측: `analyze()`(comprehensive:478)가 sec1~8을 `_calc_*/_research_*/_analyze_*` 결정론 계산·리터럴 dict 조립(:1102 return), LLM(`SiteAnalysisInterpreter`~970·`MarketInterpreter`~985)은 완성 result에 **산문만 side-key** 부착(수치 비생산), `senior_consultation`(:941)은 사후 additive(`allow_llm=False`:1079), `propai_orchestrator`는 `analyze()`가 **미호출**하는 고정 7스텝 상태머신, `expert_panel`/`personas`는 comprehensive를 **역소비**하는 사일로. → 계획은 이 결정론 파이프라인을 "검증 대상"으로만 봤다.
- **범위한정 시니어 오케스트레이터(신설)** — 비대칭 계약 하: LLM이 (1)수집 넓이 결정 (2)조사 통할(다필지·특이부지·권원 분기) (3)서술 풍성화(실무 서술·시나리오·전문가 판단) 오케스트레이션. **모든 수치는 결정론 메서드 산출·게이트 통과**.
- 기존 자산 통합: `propai_orchestrator`(고정 상태머신)→LLM 플래너 승격 검토, `senior_consultation`·`expert_panel`·`personas` 역소비 사일로를 생성 척추로 수렴.
- **결과물 풍성화 루브릭(게이트화)** — 실무 서술·claim별 근거링크·시나리오 구간·전문가 판단 프레이밍을 **측정·강제**(현 "풍성화"는 주석 수준).

### 척추 C — 수집 완전성(상류) · 現 부재 → 신설

★사용자 Q5 핵심: **필드 미수집이면 검증은 볼 게 없고 생성은 구멍** — 검증·생성보다 상류.
- **분석유형별 required-input manifest(신설)** — 분석×필수필드 SSOT.
- **수집 완전성 게이트** — 미수집 필수필드를 finding으로 표면화(현 `NEEDS_OFFICIAL_SURVEY`는 필드별 임시표기지 계통 게이트 아님).
- 유료·부재 데이터는 정직선언(무목업).

### 측정가능 100% — 커버리지 원장

- **커버리지 원장/대시보드(신설)** — 어느 차원×불변식이 커버됐는지 **정직하게 측정된 %** 서피스. "100%"를 감사가능 지표로 전환(첨부 문서의 날조 "SVR 100%" 차단).
- 정직한 100% = **측정 커버리지% + 능동 tail 발굴 + 데이터부재 정직표기 + 값=결정론·게이트 통과**.

> **재구성 요지:** 검증-게이트 본능(on-path symbolic + off-path neuro)은 아키텍처적으로 건전 — 문제는 *틀림*이 아니라 *결핍*이었다. 세 척추를 비대칭 계약 아래 세우되, 사용자 프레임의 "neuro 전체통할"은 **값 경로에서 거부**(결정론 유지)하고 넓이·서술에서만 채택한다.

---

## 4. Phase별 통합 실행계획

각 서브PR 공통 게이트(세션 표준): 구현 → **R1 어드버서리얼 리뷰(code-reviewer)·변이주입으로 골든 flip 증명** → tsc/eslint/pytest(비마스킹) → **라이브검증**(테스트계정 로그인·실주소 재분석) → 기록(커밋+옵시디언) → 전역 스윕(공용화). 공유파일 편집 전 `coord.sh claim`·전용 워크트리.

### 4.0 삼각 척추 → Phase 매핑 (재구성 반영)

§3.5 세 척추의 6개 구성요소를 Phase에 재배치. **커버리지 척추·수집완전성은 W4가 아니라 Phase0 코어**로, **생성 오케스트레이터는 신설 Phase**로 격상:

| 척추 구성요소 | 배치 | 비고 |
|---|---|---|
| 비대칭 계약 명문화(neuro proposes/symbolic disposes) | **Phase0 W0** | verifier_service 패턴을 원리로 승격·문서화. 이후 전 척추의 계약 |
| 입력 차원 레지스트리 + 불변식 스위트 | **Phase0 W0-W1**(코어) | 골든 하네스와 함께. 규칙=보편양화 불변식으로 프레이밍 |
| 조합 샘플러(pairwise/N-wise) + 속성기반 테스트 | **Phase0 W1**(코어, W4 아님) | 불변식을 조합공간에 계통 적용. 골든=회귀 핀 |
| 수집 완전성 게이트(required-input manifest) | **Phase0 W2-3 상류로**(신설) | 검증·생성보다 상류. 미수집 필수필드 finding |
| Proactive Fuzzer(tail 발굴) | **Phase0 W4** | 반응형 미지 발굴 — 커버리지 척추의 tail |
| 커버리지 원장/대시보드 | **Phase0 W4 + Phase 상시** | 측정 커버리지% 서피스 |
| **범위한정 시니어 오케스트레이터 + 풍성화 루브릭** | **Phase G(신설)** | 생성 척추. 비대칭 계약 하 — 수치=결정론, 넓이·서술=LLM. Phase0 프레임 위에 |

**시퀀싱 갱신:** Phase0(자가검증+커버리지+수집 척추) → **Phase G(생성 오케스트레이터 척추)** → Phase1(권원 correctness) → Phase2(PF) → Phase3(3D). Phase G는 Phase0의 게이트가 있어야 안전(생성물을 symbolic이 구속). 아래 Phase0 상세는 이 매핑으로 재해석하여 읽는다(W1에 조합 샘플러·불변식 승격, W2-3 상류에 수집 게이트, W4에 Fuzzer+원장).

### Phase 0 — 자가검증 correctness 레이어 (held 정본, 최고 ROI·즉시)
**이것이 사용자 통증의 직접 해답.** held `PLAN_analysis_self_audit_pipeline`의 W0~W4를 실행하되, 실측이 드러낸 **2대 교정**을 반영:

- **교정 A(★구조):** field_audit runner를 **`analyze()` 주경로에 배선**(현재 검증은 외부 /verify로만 존재). `comprehensive_analysis_service.analyze()` return 직전에 `result["field_audit"] = runner.run(result, ctx).to_dict()`. off-path LLM 감사기만 async, Tier A/B 불변식은 이미 계산된 result에 pure O(n)이라 지연 무시.
- **교정 B(현실 골든):** 골든시드를 실제 상태로 재정렬 — G1·G2는 현행 오류를 flip(수정), G3·G5는 이미 정답이므로 **회귀 잠금**(재발 시 FAIL), G4·G6는 부분→완성.

**W0** 계약·골격·골든 하네스(behavior 불변, additive): `contracts.py`·`rules_registry.py`·`runner.py`(no-op)·`analyze()` 삽입(빈 리포트)·골든 6 fixture(현행 assert). 재사용: `run_range_checks`(range_rules:84)·`run_calc_checks`(calc_ledger:103,_CHECKS:51)·`_emit_growth_verdict/_issues`(verifier_service:19/37, PII-safe).

**W1 — 계층 A 하드 불변식(최우선·결정적):**
- **W1-1 [P0 G1]** `protection_zone_severity.py` SSOT 신설(통제보호/제한보호/방공기지/비행안전/군사/개발제한/상수원→severity). 3소비처(regulation_analysis·comprehensive:390~·land_info) 수렴. cross_field 불변식: "규제목록에 보호구역 → 종합리스크 ≥ 하한". 골든: 호미곶 리스크 낮음→높음 flip, 변이(키워드 제거)시 FAIL.
- **W1-2 [P1 G2]** `dedup_school_cluster()`(kakao_local): 이름정규화(운동장·체육관·병설·분교 접미 제거)+좌표근접 모학교 병합. cross_field: "school_n=dedup 고유 모학교 수". 골든: 대보초 5→1, 입지점수 재계산.
- **W1-3 [G3 정직→명시]** coverage.py: 등장 zone이 매트릭스/룩업 미등재 시 조용한 판정불가 대신 **"커버리지 갭" finding 표면화**. 관리지역 등재(국토계획법 별표).

**W2 — 계층 B 수시변동 안전망(경고+배지·비차단):**
> ★**재확증 스파이크(2026-07-29) 반영 — W2 재정의**: 계획이 "신규 배선 필요"라 한 인프라 대부분이 **이미 존재·배선됨**(W1-3 패턴 반복). `desk_appraisal_service.py`(420줄)=공시지가기준법+**거래사례비교법(comparable)+5법인 교차검증 CV·신뢰도+methodology 태그** 완비(소비처 land_price 라우터·rough_feasibility_orchestrator·avm_vision). `robust_price_stats`(price_stats.py:21)=log-IQR·실배선 3곳(comprehensive:1430·land_info:983·nearby_map:392)·`test_price_stats.py` 5건 진짜 회귀락. `result["provenance"]`(comprehensive:887-890)=미등록소스 `registered:false` **이미 부착**. → **실제 계층B 작업 = 이미 계산된 result를 판정하는 얇은 P2 배지 불변식 3개 + 발견결함(가짜 G5 골든) 정직화.** 계획의 신규 배선(desk_appraisal→Section3 재배선·distribution.py·freshness populate)은 순수 판정 안전망(계층B) 범위 초과 → **별도 기능 티켓으로 분리**. 착수 우선순위(스파이크): **provenance배지 > G4시세배지 > G5골든정직화**.
- **W2-1 [G4] 시세 methodology 배지**(재정의): desk_appraisal·triangulation·methodology **신설 불필요(이미존재)**. field_audit 계층B 불변식 1개 — Section3 표시시세 vs Section4 실거래(robust_price_stats)/desk_appraisal `method_cmp`를 **comparable 존재 시** N배 격차 대조→P2 배지, **comparable 부재 시** "공시지가추정(폴백)" 정직배지. ★**독립오라클=실거래 comparable 전용**: `land_price_estimator._market_multiplier`가 comprehensive `MARKET_MULTIPLIER_MAP`+동일 1.2폴백 재사용(:11·:23)이라 **desk_appraisal 채택값을 오라클로 쓰면 폴백부재 시 검증대상과 동일계산 수렴=버그재구현(W1-3 함정)**. comparable(Section4 robust avg / method_cmp)만 독립.
- **W2-2 [G5] 가짜골든 정직화**(재정의·결함수정): robust_price_stats 회귀락은 `test_price_stats.py`로 **이미 달성**. ★발견결함=`test_golden_baseline.py::test_g5_regression_lock_robust_stats`가 **실함수 미호출·fixture JSON 필드만 assert**(동어반복)+**실측 반증**(fixture n=6·excluded=[20000]→500000 주장이나 실함수는 n<8(=`_MIN_SAMPLE_FOR_TRIM=8`)이라 트림 스킵→avg=418333·20000 유지)=**거짓안전**. 교정=G5 골든을 **실함수 호출 회귀로 교체**(실반환 락). distribution.py 동적IQR·지역/시기 층화=신규·계층B 초과→후순위. ★계획 "샘플<5"는 코드 `_MIN_SAMPLE_FOR_TRIM=8`로 **정정**.
- **W2-3 [provenance] unknown-source/stale 배지**(재정의·최고ROI): `result["provenance"]`가 **이미 result에 존재**(registered:false=unknown-source). field_audit 계층B 불변식—순회하며 `registered:false`(미등록) 또는 freshness `is_fresh:false`(populate된 경우만) → **P2 배지**. 오라클=데이터-메타(자기선언)라 **구조적 독립·안전**. ★"관문(차단)" 승격은 계층B(비차단) 상충→**P2 배지까지**. stale 실효화(`mark_updated`가 auction_service 1곳만 호출→molit/vworld last_updated 영구None)는 **상류 populate 별도 티켓**(미포함시 stale배지 대부분 무발동—정직하나 공허).

**W3 — 계층 C + LLM 어드버서리얼 + 지형 배선:**
- **W3-1** llm_auditor.py — 결정적 필드+근거+원본을 도메인/법령 대조 challenge(grounding과 별개·off-path·best-effort·캐시·use_llm 게이트). 기존 base_interpreter:421 단일재시도를 finding→retry feedback으로 연결.
- **W3-2 [C]** 점추정(적정분양가·수익성)→신뢰구간/시나리오·불확실 명시(confidence.py).
- **W3-3 [G6 완성]** terrain_service 경사도 소비처 렌더 추적·검증(주입은 됨:794, UI 표면화 확인). 수집가능(경사도)/실측필요(입목축적) 분리, 수집가능이 None이면 finding.

**W4 — 자가치유·능동 자가증식(성장엔진 폐합):**
- HITL: 감사 findings→growth/healing_rules·improvement_agent(반복 finding 자동감지→수정제안/few-shot).
- **Proactive Anomaly Fuzzer**(제미나이 채택): 피드백 없이 입력필지 특이성(용도지역 3중 걸침·복합 권리결함·규제 4중첩) + 모델 불확실성 스코어 임계초과 시 합성변이 시드 자동생성→field_audit 통과분만 골든 승격(PG-series). ★무한증식 방지 게이트(라운드 상한·중복제거·비용 budget)·무목업(합성시드는 실데이터 아님 명시).
- 계층 B 기준선(지역·지목별 정상 원/㎡·IQR 배수)을 platform_insights 누적학습(하드코딩 금지).

### Phase 1 — 권원 correctness 확장 (데이터 배선 조건부, EXTEND)
**Phase 0 자가검증 프레임 위에 권원 도메인 규칙을 추가.** 데이터가 이미 흐르는 3건만 우선(나머지는 정직선언·후속):
- **P1-1 소유권 확보율**: `registry_analysis._derive_ownership`의 owners/share → 확보율% 집계 + 주택법 80/15·95·도정법 3/4 임계 판정. **owners DB 영속**(현재 응답에만 존재) + 다필지 소유권 통합(대표소유자 규칙). Tier A 불변식: "확보율 임계 미달인데 '즉시 사업가능' 산출 → finding".
- **P1-2 매도청구/토지수용**: `scenario_simulator.MAGDO_RULES` 확장 — 10년 장기보유자 제척, 토지수용/매도청구 제척기간 타임라인(최고2M→회답2M→소송2M·손실보상90일). 법령 수치는 **파라미터 DB**(하드코딩 금지).
- **P1-3 대지권 미등기**: `land_share.analyze_by_pnu`의 의심경고를 field_audit finding으로 승격 + 세대별 태깅. 등기부 대지권등록부 유료→**정직선언 유지**(근사·추정 금지).
- **정직 스코프(전무 5건):** 상속미등기·권리산정기준일·무허가입주권·국공유지 무상양도·PF/DSCR은 **데이터/엔진 부재를 명시 선언**하고 후속 Phase로. 억지 근사 금지(무목업).

### Phase 2 — 금융 리스크 정량화 (Monte Carlo, ADAPT)
- 기존 `feasibility/monte_carlo_engine.py` 재사용. **권원확보 지연 ΔT → 브릿지론 이자손실·DSCR·파산확률** 배선(문서 GBM/DSCR 수식은 개념적으로 타당). finance_service NPV 경로에 통합. field_audit 계층 B로 "지연 리스크 미반영 수지 → 경고".

### Phase 3 — 3D envelope 시각화 확장 (ADAPT·스코프, 후순위)
- 기존 terrain/geometry(ray-cast·polygon clip·정북일조·건축선후퇴) + Three.js/glTF로 가용 envelope 3D 렌더. **Rhino Compute REJECT**(그린필드·유료). ★Claude는 이미지 생성 불가 — 렌더는 기존 프론트 자산 배선.

### DEFER-REJECT (명시적 비실행 + 근거)
- Neo4j: 관계형+다필지 충분. ZKP zk-SNARK: Fernet+해시체인 원장 충분·문서 코드는 진짜 zk 아님. LoRA 파인튜닝: 데이터·ROI 미성숙. SagaLLM 분산트랜잭션: 단일재시도로 충분. → 근거 없는 인프라 부담 회피(그린필드 금지 원칙).

---

## 5. 골든 회귀 시드 — 현실 재정렬

| 시드 | 입력(frozen) | 현 상태 | 목표 | 계층 | Phase |
|---|---|---|---|---|---|
| G1 | 호미곶 통제보호 방공500m | ❌ 리스크 낮음 | 리스크 ≥ 높음 | A cross_field | 0/W1-1 |
| G2 | 대보리 POI | ❌ 학교 5 | 학교 1(대보초) | A cross_field | 0/W1-2 |
| G3 | 보전관리 임야 | ✅ 판정불가 | 갭 명시 finding | A coverage | 0/W1-3 |
| G4 | 호미곶 시세 | ⚠️ 지역맵+폴백1.2 | 실거래 원/㎡ | B methodology | 0/W2-1 |
| G5 | land 실거래 | ✅ log-IQR | **회귀 잠금** | B distribution | 0/W2-2 |
| G6 | 임야 경사도 | ⚠️ 주입·렌더미확인 | UI 렌더 확인 | B/A freshness | 0/W3-3 |
| G7+ | 권원(소유율·매도청구·대지권) | c/b | Phase1 확장분 골든 | A/B 권원 | 1 |

각 시드: 변이주입(가드 무력화)시 FAIL 확인 = 가드 실재 증명(세션 표준).

---

## 6. "100% 완성도"의 정직한 정의

문서의 "SVR 100%"는 날조 수치다. "모든 경우의 수 100%"는 조합폭발로 **문자적 불가능**(억지 추구는 가짜 지표를 낳는다). 우리가 약속할 수 있는 정직한 100%는 **삼각 척추별 측정가능 완결**:

**척추 A(커버리지):**
- 규칙을 **예시가 아닌 보편양화 불변식**으로 강제(모든 입력에 성립) — `calc_ledger` 재계산 모델을 도메인 correctness로 확장.
- **조합 샘플러가 pairwise 2-way 결함 99%+ 색출** + 속성기반 테스트로 조합공간 계통 커버.
- **커버리지 원장이 측정된 %를 서피스**(차원×불변식 커버율) — "100%"를 감사가능 지표로. 골든은 회귀 핀(앵커)일 뿐 커버리지 척도 아님.

**척추 B(생성):** 결과물 풍성화 루브릭(실무 서술·claim별 근거링크·시나리오·전문가판단)을 **측정·강제** — "풍부함"을 검증가능 산출물로.

**척추 C(수집):** required-input manifest로 **수집 완전성 게이트** — 미수집 필수필드는 finding(검증·생성 이전 상류 봉쇄).

**공통(비대칭 계약):** 모든 수치는 결정론·게이트 통과(neuro가 값 생산 금지) · 데이터/엔진 부재(유료 등기·PF)는 근사 없이 정직선언 · 능동 tail 발굴로 미지 축소.

즉 100%는 "환각 0"의 불가능 선언이 아니라 **"아는 규칙은 불변식으로 빠짐없이 강제(측정된 커버리지%로 감사), 필수 입력의 수집을 상류에서 보장, 풍부함을 루브릭으로 측정, 모르는 것은 정직 표기, 새 오류를 스스로 잡아 규칙으로 승격하는 삼각 폐루프"**의 완성이다.

---

## 7. 리스크 & 거버넌스

| 리스크 | 완화 |
|---|---|
| 하드 차단 오차단(false positive) | 1단계 경고+배지, 골든/실사용 안정 후 P0 차단 승격. `FIELD_AUDIT_ENABLED`+per-rule enable map(즉시 롤백) |
| 매트릭스/키워드 확장 회귀 | coverage 어설션은 미등재 표면화하되 기본 비차단. 기존 골든 유지 |
| 계층 B 기준선 과적합 | 하드코딩 금지·platform_insights 누적학습·분포 런타임 산출·교차 삼각검증 |
| LLM 감사기 지연/비용 | off-path·best-effort·캐시·use_llm 게이트. 실패해도 core 반환 불변 |
| 권원 데이터 미영속/유료 | owners 영속 배선 우선, 유료(대지권등록부)는 정직선언·근사 금지 |
| Proactive Fuzzer 무한증식 | 라운드 상한·중복제거·budget 게이트·합성시드 무목업 명시 |
| 멀티세션 공유파일 충돌 | coord.sh claim/release·전용 워크트리·작은 서브PR |

---

## 8. 시퀀싱·규모·착수

```
Phase0(자가검증 W0→W1[P0 G1]→W1-2→W1-3→W2→W3→W4)  ← 최우선·즉시·held정본
   ↓ (프레임 완성)
Phase1(권원 correctness: 소유율·매도청구·대지권 — 데이터배선 조건부)
   ↓
Phase2(Monte Carlo PF 배선)   Phase3(3D envelope·후순위)
   ✗ DEFER-REJECT: Neo4j·ZKP-zk·LoRA·SagaLLM·Rhino
```
- **규모:** Phase0 ~8–9 dev-day(held 계획, 병렬 단축). Phase1 ~5–6d(데이터 영속 포함). Phase2 ~2d. Phase3 후순위.
- **의존:** Phase1은 Phase0 프레임 선행. Phase2는 독립. 6대 결함 중 **G1(P0)이 단일 최우선**(가장 심각한 라이브 오도).
- **착수 첫 커밋(승인 후):** `coord.sh claim verification/field_audit`+전용 워크트리 → W0 골격+골든6(현행 assert)+analyze() 삽입(빈 리포트) → W1-1 protection_zone_severity SSOT+G1 flip → R1 → 라이브검증(호미곶 리스크 높음).

---

## 9. 확정 결정 (2026-07-24 사용자 승인)

전문가·실무자·사용자 관점 재검증 후 사용자가 확정:

| 결정 | 선택 | 반영 |
|---|---|---|
| **착수 범위** | **Phase0 자가검증 프레임**(~2~3주) | 신고오류 즉시봉합(too narrow)도 전 백본(too broad)도 아닌 프레임 우선. Phase G/1/2/3은 **Phase0 완료 후 별도 승인**. "플랫폼이 자기오류 스스로 잡는 폐루프의 첫 벽돌". |
| **불변식 오라클** | **하이브리드** | W1 불변식 설계 반영: ①손큐레이션 권위표로 **즉시 착수**(protection_zone_severity·ZONE_PERMIT_MATRIX를 authoritative SSOT로 취급) ②기계 오라클 있는 영역(법제처 MOLEG·국토계획법 별표 API)만 자동대조 ③**HITL 교정을 오라클로 축적**(경우③→②승격). AST 자동 룰생성(문서 제안③)은 **Phase0 밖·후속 옵션**(초기투자·비정형파싱 난밥). |
| **척추 순서** | **정확성 먼저(Phase0 → Phase G)** | 사용자 첫 지적(빈약함)보다 나중 지적(틀림)을 선행 — 틀린 값을 풍부하게 서술하면 오도 악화. 견고한 correctness 기질 위에 Phase G 풍성화. |

**#1(결정론 자가교정 완결성) 판정 정직화:** "모든 결정론 버그 자율교정"은 **오라클 문제로 원리적 불가**(§3.5 제1원리 계2). 달성가능 완결 = 탐지 완전(불변식+변성+차등+퍼저) + 교정 3분기(오라클 있으면 자율·없으면 HITL) + HITL 정답의 오라클화. **완벽 자율을 주장하지 않는 것이 정직한 완결**이며, 하이브리드 오라클 결정이 경우③(HITL)을 경우②(자율)로 점진 승격시키는 성장 경로다.

**추가 확정(제 판단·질문 밖):** ①HITL 정답 오라클화(성장루프) ②비즈니스 임팩트 우선순위(권원 확보율>시세>리스크>인허가) ③design_audit 경로도 Phase0 커버(DA-7 사용자 첫 지적 경로) ④변성/차등 탐지·graceful degradation은 §3.5 taxonomy에 반영 완료.

> **상태: 계획 확정 + 착수 결정 완료 — 실행(코드) 승인 대기.** 승인 시 Phase0 W0(하네스·골든·analyze 배선) → W1-1(G1 P0·protection_zone_severity 손큐레이션 SSOT) 성장루프 착수.

---

## 10. 통찰-생성 성장루프 (메타 자가검증 — 사용자 제기)

**문제의식(사용자):** 왜 시스템(과 AI)이 통찰·질문·문제의식을 **스스로** 생성·검증 못 하고 매번 외부 challenge(사람)에 의존하나? → **통찰 생성 자체를 성장루프로.**

### 10.1 현 성장엔진 실측 — build-on(그린필드 아님)

- **실존 후반부(반응형 처리)**: `growth/capture_service.record_event/record_fallback`(이벤트 포착) → `platform_insights` 적재 → `analyzer.py:539`(FROM platform_insights) → `improvement_agent`(`_rule_diagnosis`·`_llm_proposal`·`_store_proposal`) → `healing_rules`/`heal_actions`/`learning_loop`. 성숙 파이프라인(성장뇌 감사 3/5).
- **★갭(능동 생성 전반부 부재)**: insight 출처가 전부 **반응형**(fallback·error·telemetry가 **이미 터진 뒤** 포착). `adversar/redteam/hypothesis/devil/challenge` 생성 = **0**. "이미 깨진 것에서 학습"만, "무엇이 깨질 수 있나 능동 적대 생성"은 없음.
- **★삼중 평행선(이 세션의 근본 발견)**: ①field_audit이 반응형 `/verify`에 능동 correctness 게이트를 더함 ②통찰루프가 반응형 growth에 능동 문제의식 생성을 더함 ③AI(나)가 반응형(사용자 challenge)에서 능동 자기도전으로. **셋 다 "반응형이 결함", 처방은 "능동을 주경로에 배선".**

### 10.2 통찰-생성 루프 설계 (6요소)

1. **트리거**(비용/소음 보정): 실질 산출물(계획·아키텍처·고위험 분석) 완료 시 반사적 + **저신뢰 구간 표적**(신뢰도 1급 산출물화) + 신규성 신호 + 주기적 코퍼스 introspection.
2. **다층 렌즈**(통찰공간 커버리지): 도메인전문가·실패모드레드팀·실무자여정·완전성비평·**프레임 도전자**. 각 렌즈=생성(propose) 지시. 렌즈 다양성이 입력공간 pairwise처럼 통찰공간 커버.
3. **신규성 필터**(정지 문제): "알려진 우려 원장"과 dedup → novel만. loop-until-dry(K라운드 novel 0 → 정지).
4. **증거 검증 = 재귀 오라클 종결(dispose)**: 생성 통찰 = 가설(neuro proposes) → **코드/데이터/도메인권위로 검증**(dispose). ★무한후퇴는 메타-통찰이 아니라 **증거에서 종결**(실증: "커버리지 후방배치"=grep 확증 / "비행안전 누락"=코드에서 반증). 통과분→골든/불변식/차원 **승격**, 실패분→폐기+신규성 원장 적재(재생성 방지).
5. **2층 적용**: (a)**개발 프로세스(AI)** — 실질 계획 저술 시 **반사적 적대 통찰 패스 상설화**(하네스 스킬, 사용자가 매번 레드팀일 필요 없게) (b)**플랫폼 런타임** — 분석마다 **"악마의 변호인" 생성층**(field_audit 넘어 "규칙이 안 잡는 무엇이 틀릴 수 있나" 검증 가설 생성 → 기존 `improvement_agent`로 피딩). **Proactive Fuzzer를 통계이상탐지→의미론적 문제의식 생성으로 격상**.
6. **배선점**: 능동 생성+검증 통과 통찰 → 기존 `improvement_agent._llm_proposal`/`_store_proposal`/`platform_insights`로 피딩. 척추 A(Proactive Fuzzer)+Wave4(성장폐합)에 배선.

### 10.3 정직한 한계 (과장 금지)

- 자동생성은 **"알려진 우려 공간"에 수렴** — 알려진 실패패턴 재조합은 잘함(아키텍처 냄새 대부분 포착).
- **프레임 재정의형 novel 통찰**(사용자 "삼각 척추"류)은 루프가 **후보 생성**은 하나 어느 재프레이밍이 옳은지 **사람 판단이 판정**. → 인간 의존을 "모든 통찰 생성"에서 "**최상위 재프레이밍 판정**"으로 감축(제거 아님·제거 주장은 SVR100%식 날조).
- 보정 없으면 **alert fatigue**로 죽음(신규성 필터·저신뢰 표적·트리거 규율 필수).

> 이 §10은 척추 A·Wave4의 일반화이자 **이 세션의 자기적용**이다: 사용자가 매번 통찰을 끌어낸 것을 시스템(과 AI)이 반사적으로 하게 만든다. 위임 렌즈 실패조차 코디네이터가 직접 생성으로 대체해 요점을 증명했다(능동 생성은 위임가능하되 최종 종합·검증 책임은 주경로).

---

## 11. 거버넌스·안전 (통찰루프 실연이 발굴한 확증 결함 — §10 dispose 적용)

§10 통찰루프의 첫 실연(레드팀 렌즈)이 **코디네이터도 사용자도 못 본** 16개 failure mode를 자율 발굴했다. §10 규율대로 **가설(propose)→코드 검증(dispose)**을 거쳐 확증·정밀화한 것을 여기 박제한다.

### 11.1 ★자율 변이 루프 거버넌스 (F4 클러스터 — 구조적, 필수)

**확증된 결함:** 플랫폼에 **인간개입 없는 스케줄 변이 루프가 이미 존재**하고(`celery_app.py:70-138` Beat: analyze-growth-hourly·evaluate-healing */10분 · `feature_flags.evaluate:423`가 `down_pct≥임계`에서 `llm_narrative` 자동 비활성:480-487 · `analyzer._llm_enabled:611` live-read), 계획 W4가 field_audit 판정을 이 루프에 피딩하는데 §7 거버넌스가 이를 다루지 않았다.
- **정밀화(dispose)**: 자동토글은 `llm_narrative`(비critical·AUTO_TOGGLEABLE, CRITICAL_FEATURES 제외:78,126)로만 스코프된 **의도된 안전 degradation**. 결정론 ①② 값은 자동변이 안 됨 → 파국 아님.
- **★그러나 진짜 결함(필수 조치)**:
  1. **카테고리 오류 신호 라우팅**: field_audit의 ①② correctness 플래그가 generic down/fail로 집계돼 ③ 서술기능을 끔. → **field_audit 판정을 verify_result growth 신호에서 제외·네임스페이스**하여 quality_drop/토글을 구동 못 하게. field_audit→growth 배선은 **관측전용(observation-only)**, `recommended_action` 없이, 인간 승격 전까지 L1 미소비.
  2. **F4b 무경계 임계 드리프트**: `clamp_abs_band`가 `THRESHOLD_ABS_BANDS`의 **단 1키**(fallback_warn_pct)만 클램프, 나머지는 원값 통과(:64-69). 계획이 추가할 임계(샘플러·LLM감사 confidence·W2-2 IQR배수)는 abs-band 없이 자동튜닝되면 기하급수 드리프트. → **abs-band 필수(fail-closed: band 없으면 autotune 비적격).**
  3. **F4c 원장 lineage 부재**: 자동토글 config 하 산출물이 append-only 해시체인 원장에 적재되고 `/report/pdf-from-ledger`의 단일 출처가 되는데(`pipeline.py:461-501,685-752`), config 롤백이 **원장 산출물을 되돌리지 못함**. → 원장 엔트리에 `{prompt_version, active_feature_flags, oracle_version, field_audit_verdict}` 스탬프 + 롤백된 action과 교차하는 from-ledger 렌더에 "degraded config 하 생성" 배너.
  4. **F4d 커버리지 분모 자기정의**: "측정 100%"는 **손큐레이션 차원 레지스트리에 누군가 열거한 것의 100%**(외국인소유·종교용지·개발제한 해제예정지·소송계류 등 미등록 차원 표현 불가). 계획이 골든엔 이 false-comfort를 명시했으나 **레지스트리 자체엔 미적용**. → 커버리지 대시보드는 **known-unknowns 목록 + 마지막 외부 완전성감사일** 표시, bare "100%" 금지.

### 11.2 불변식·루프 하드닝 (F1/F2/F3/F5 — Wave에 접목)

| ID | 확증 결함 | 조치(해당 Wave) |
|---|---|---|
| **F1a** | `_deep_find` 깊이우선 first-key-wins가 payload 성장 시 operand 교차오염(FAR gfa=통합·land=첫필지) → **불일치를 pass로 인증** | scoped 추출(단일 parcel/section 컨텍스트 내 검증), 형제 subtree 횡단 금지. (W0 계약·F5 공통) |
| **F1b** | metamorphic "실효FAR≤법정FAR"은 인센티브FAR(공개공지·역세권)에 **정당 위반** → 프리미엄 딜에 false P0 | 모든 "≤legal" 불변식을 `_has_relaxation_basis`(range_rules:130)·overlay 조건부화. anti-golden(인센티브FAR 프로젝트) 추가. (W1·W2) |
| **F1c** | 손큐레이션 오라클(protection_zone_severity·ZONE_PERMIT_MATRIX)에 TTL·owner·상류 변경감지 없음 → 법 개정 시 **양방향 확신오류** | 오라클 버전화·review-by·owner + MOLEG/별표 API 주기 differential로 이탈 행 플래그(하이브리드 오라클 결정과 정합). (W1·§9) |
| **F1d** | "any high⇒fail" 단일 붕괴·규칙 상호모순(리스크하한 vs 리스크↔수지 일관성 공동만족 불가) | block/advisory 불변식 분리·명시 precedence + 새 불변식 도입 시 co-satisfiability 체크. (W0·W1) |
| **F2a** | retry가 **누락 래칫**: regen이 "더 낫다" 검증 없이 "v2 not-fail"만 → 플래그 claim **삭제가 최저비용 통과** → 서술 빈약화·prompt튜너가 학습 | 채택을 regen⪰original(정보/커버리지 지표)로 게이트, "claim 사라짐"을 별도 실패로. analyze() 확장 시 필수. (§3.5·W3) |
| **F2b** | 사용자 correction 자유텍스트가 prompt튜닝 조종 → 악의적 "군사리스크 과대" 스팸이 **G1 불변식과 모순되는** addendum 유도, 교차검증 없음 | prompt 후보를 **불변식 스위트로 사전검증**·피드백 가중/인증(down-vote≠오라클)·injection strip. (W4·§10) |
| **F3a** | Fuzzer가 model-uncertainty로 seed → **아는 영역 과표집·진짜 unknown-unknown 회피** + 자기 통과분을 커버리지 분모로 승격(**blind spot을 "covered"로 세탁**) | 실 프로덕션 tail(실제 관측된 희귀 zone/지목/권리조합)로 seed, fuzzer 승격 골든은 별도 할인 버킷, novelty-distance 추적. (§10·W4) |
| **F3b** | 배지 인플레(실 필지마다 3~5 "검토필요") → 습관화·G1 P0 매몰 = 최대 usability 실패 | 분석당 finding **하드캡 + severity 정렬 다이제스트** + dismissal율 건강지표. (graceful degradation 보강) |
| **F3c** | on-path 비용 superlinear(O(#불변식×payload-tree)) → "지연 무시" 반증 | payload를 **1회 scoped 필드맵 인덱싱** 후 불변식은 인덱스 대상(O(#불변식)), 샘플러 전 부하테스트. (교정 A 보강) |
| **F5a/b** | 3-way 상호작용(pairwise 미포착): {다필지×혼재zone×특이부지 reshape}→subtree횡단 / {신규 시나리오키×완화키워드×값>법정}→**잠긴 골든 조용히 재개방** | 시나리오 스트립·operand 추출을 **구조적 allowlist-closed**(미지 subtree 격리), 해당 family에 ≥3-way 샘플링·anti-golden. (F1a 공통·W2) |

### 11.3 미해결 질문 (착수 시 규명)

레드팀이 코드로 못 닫은 것(정직 표기): ①L3 prompt addendum 텍스트가 실 시스템프롬프트에 실제 주입되나(F2b 실 폭발반경) ②L3 후보를 실사용자에 서빙하는 canary 경로 존재?(없으면 auto-adopt inert·더 안전) ③analyze() field_audit이 distinct `analysis_type`로 emit하나 같은 라벨 상속하나(F4a 완화 여부) ④regional_benchmark/redis_cache 자동토글이 G4/W2-1의 comparable-price 근거를 무력화할 수 있나(교차시스템).

> §11은 §10 통찰루프의 **첫 자기적용 산출물**이다: 자율 패널이 발굴(propose)→코디네이터가 코드로 검증·정밀화(dispose)→계획에 승격. 이 과정 자체가 "시스템이 스스로 통찰을 생성·검증·반영"의 실증이며, 동시에 **완전자율이 아님도 실증**한다(F4a 심각도 정밀화·미해결 4질문은 인간/코드 검증이 종결).

---

## 12. 도메인 커버리지·감사범위 (도메인 실무전문가 렌즈 — §10 dispose 적용)

### 12.1 ★META-발견(확증): 골든 표본 편향 + 최고위험 엔진이 감사경로 밖 → 커버리지 분모가 틀렸다

**확증(grep dispose):** `comprehensive_analysis_service.analyze():478`은 재초환·비례율·부담금 엔진을 **호출하지 않는다**(:903·:931 "정비사업 입력 보통 없어/있을 때만" 주석뿐, 호출 0). 엔진은 격리 실존: 재초환 `feasibility/modules/m02_reconstruction.py`·부담금 `tax/project_charges.py`(docstring이 "개략수지가 부담금 통째 누락" 버그 기록)·비례율 `senior_agents/evaluators/urban.py`. → **골든 G1~G6이 전부 호미곶 임야에서 표집돼, "측정 100%"가 임야를 덮어도 강남 재건축·수도권 재개발(시장 최대 파이·최대 오도리스크)엔 구조적으로 눈이 먼 상태를 "높은 커버리지"로 착시.** 레드팀 F4d(분모 자기정의)의 가장 깊은 버전. verif-map(analyze()가 zoning/far specialist만)과도 수렴.

**구조 교정(필수 — §9 결정 갱신):**
1. **골든을 사업유형 매트릭스로 층화 재표집**: 도심상업·재건축·재개발·농지·GB(해제예정)·지방소멸·역세권 각 ≥1건(임야 6은 유지·확대). 표본이 곧 커버리지 상한.
2. **커버리지 원장 분모 = "사업유형×결정변수"**(차원×불변식이 아니라).
3. **감사범위를 격리 고위험 엔진으로 확장**: 재초환·비례율·부담금·통합세무를 감사경로에 배선(analyze()가 사업유형 감지 시 호출 or 각 엔진 실행지점에서 감사). **격리 자산 배선이 신규 손큐레이션보다 상위 ROI(그린필드 아님).**
4. **기존 오라클 재사용**: `legal_reference_registry`의 `housing_price_cap`(주택법57조):256·`reconstruction_levy`:274·`development_charge`:385·토지거래허가:596를 커버리지 오라클로(신규 protection_zone_severity 손큐레이션과 SSOT 이중화 회피 — O9 확증).

### 12.2 사업 project-killer 경우의 수 (골든/불변식 부재·감사경로 밖)

| ID | killer | 세그먼트 | 근거 | 검증 |
|---|---|---|---|---|
| **K1** | 재초환(재건축부담금) 미반영→사업성 정반대 | 재건축 | m02 존재·감사0 | 재건축 골든→n_levy 산출 필수 불변식·변이(재초환0)→"양호"면 FAIL |
| **K2** | 분양가상한제 매출상한 부재→규제지역 분양수입 과대 | 규제지역 | 기본형건축비=공사비만(rough_feasibility:507) | "상한제 대상→분양수입≤상한가×세대" 불변식 |
| **K3** | 비례율<100%↔분담금 정합 불변식 부재 | 재개발/재건축 | urban.py:40 verdict 미대조 | "비례율<100→분담금>0 명시"·"분담금>0인데 '부담없음'→finding" |
| **K4** | 부담금 완전성 게이트 부재→총사업비 과소 | 전 개발 | project_charges 파편(tax·scenario_simulator) | "사업유형×규모→적용 부담금 집합" SSOT·완전성 assert |
| **K5** | 흡수율/미분양 부재→지방 100%분양 환상 | 지방소멸 | comprehensive grep0 | 인구·미분양관리 manifest·"감소지역 100%가정→finding" |
| **K6** | 안전진단이 게이트 아닌 주석 | 재건축 | scenario_simulator:1107 문자열 | "재건축인데 D/E 근거없음→판정보류" |
| **K7** | 일조 사선제한 실효연면적 축소 미반영 | 주거 협소필지 | 일조=목업/deliberation 분리 | "주거+남북짧음→일조사선 실효연면적, 미적용시 법정을 실효로 오기→finding" |
| **K8** | 맹지/접도요건→건축 자체 불가 | 임야·자투리 | access.py 불변식화 안됨 | "맹지+진입로 근거없음→'개발가능'→finding" |
| **K9** | 매장문화재·역사문화환경 타임폭탄 | 경주·부여권 | special_parcel 감지만 | "문화재영향 대상→인허가 로드맵에 지표조사 소요" |
| **K10** | 정비구역 지정요건(노후도·호수밀도) 미검증 | 재개발 | 확보율만 있음 | "재개발인데 노후도 입력없음→지정가능성 판정불가" |
| **K11** | 종상향+기부채납 net-out 불변식 부재 | 도심 복합 | _strip_scenarios 제외만 | "종상향 가정시 기부채납률만큼 가용면적/매출 차감" |
| **K12** | 시간축(일몰제·제척·거래규제) 부재 | 정비·GB·허가구역 | legal_reference:596 게이트 아님 | "지정일+일몰기한 vs 진행단계→해제위험 finding" |

### 12.3 correctness 정의가 실무와 어긋나는 지점 (이진 오판 — 내 계획 자기교정 포함)

- **M4 ★내 G1 자기교정**: G1 리스크를 **일괄 "높음" flip은 과잉교정**(비행안전 6구역 외곽 vs 1구역 활주로·제한보호=협의개발 가능 vs 통제보호=거의불가). 평탄화하면 협의가능 정상사업을 죽인다(§3.5가 경고한 과잉교정을 G1에 범함). → severity를 **구역별·행위별 granular**로(키워드 존재≠일괄 높음). **W1-1 재설계 필수.**
- **M1** metamorphic "실효FAR≤법정FAR"은 인센티브조닝(공개공지·역세권·공공기여)에서 정당 초과 → 상한은 "기준"이 아니라 "**상한용적률(인센티브·조례·심의)**"(F1b와 수렴).
- **M2** G4 "실거래=유일정답"은 방법론 편향(보상=감정·상업=수익환원) → "물건유형별 평가방법 태그 필수"로 프레이밍.
- **M3** G3 판정불가→산출 압박이 가짜정밀 → "커버리지 갭(매트릭스 누락)"과 "정직한 판정불가(본질적 조례의존)" **구분**.
- **M5** 다필지 "단일vs다필지 일치" 차등검사는 대표값류에 오탐 → 면적 SSOT 항등식에만.
- **M6** 확보율 단순비는 국공유지·미상속·종중·신탁에서 오판 → 사업방식·소유유형별 산정식 분기(scenario_simulator:29,55 이미 방식별 임계 구분).

### 12.4 미배선 권위 오라클(다수 이미 코드에 존재) · 풍성화 필수항목

- **오라클(재사용 ROI)**: 토지이음/LURIS 교차(O1·test_landuse_cross 격리)·ELIS 조례(O2·경사도/용적 강화분·조례가 국가법보다 엄격·*존재 미검증*)·감정선례·표준지(O3)·판례/해석례로 HITL 반자동시드(O4)·심의사례(O5)·HUG 미분양관리지역(O6·*존재 미검증*)·청약경쟁률(O7)·표준정관(O8)·legal_reference_registry(O9·확증).
- **척추 B 풍성화 루브릭 강제항목(PF 제출 수준)**: R1 항목별 총사업비(부담금 포함)·R2 시기별 자금수지표+peak funding·R3 손익분기 분양률·R4 토네이도 민감도(분양가·공사비·분양률·금리·인허가지연)·R5 인허가 로드맵+소요기간·R6 Exit 시나리오·R7 세무(취득중과~처분)·R8 자금·신탁구조·R9 개발대안 비교·R10 리스크 등록부·R11 claim별 근거·기준일 각주.

> §12는 §10 통찰루프의 **두 번째 자기적용**이자 이 세션 최대 발견: 두 자율 렌즈(레드팀·도메인)가 **독립적으로 수렴** — 감사범위·커버리지 분모가 저위험 세그먼트에 편향. 골든 층화·감사범위 확장·격리 엔진/오라클 배선이 신규 손큐레이션보다 상위 ROI. (ELIS/HUG 존재는 미검증 — 착수 시 규명.)

### 12.5 ★층화축 재정의 — 토지속성 조합이 1차축 (사용자 지적·grep 확증)

**사용자 지적:** 지목은 임야만 있는 게 아니고, 임야도 자연녹지/계획관리/보전관리인지·보전산지/준보전산지인지에 따라 **분석방향·결과값이 뒤바뀐다** — 충분히 반영됐나?

**검증(grep dispose) — 부분적·정직하나 under-deliver:**
- 정직성 작동: `special_parcel.py:215`가 임야 산지구분을 `NEEDS_OFFICIAL_SURVEY`·`보전산지_여부:None`로 정직 선언(과거 산/임야 용적률 과대표시·녹지 과대낙관 버그의 교정). → 조용히 틀리진 않으나 **보전/준보전을 분해 안 해 under-deliver**.
- 부분 자산 격리: `feasibility/land_conversion_charges.py:34` `_FOREST_TYPES=("준보전산지","보전산지","산지전용제한지역")` 단가 구분(**analyze() 밖 격리엔진**)·`legal_reference_registry:411 forest_land_classification`(산지관리법4조)·`dev_act_permit_gate:247` 경사도(조례 우선·별표4 25° 폴백).
- ★**갭: 지목 × 용도지역 × 산지구분 조합이 1급 커버리지 차원이 아님.** §12.1이 제안한 strata 1차축(사업유형)은 거칠고 직교라 이 조합을 못 잡음. 예: 자연녹지 임야 中 보전산지=개발 극히제한 vs 준보전산지=개발행위허가 가능 → 완전 상이. 이것이 "모든 경우의 수"의 실체.

**교정 — 척추 A/C 재배선:**
1. **척추 A 입력 차원 레지스트리 1차 층화축 = 토지속성 조합**: **지목**(임야/전/답/대/도로/구거/…) **× 용도지역**(자연녹지/생산녹지/보전녹지/계획관리/생산관리/보전관리/제1·2종주거/준주거/상업/…) **× 산지구분**(보전[임업용/공익용]/준보전) **× 농지구분**(농업진흥/보호/진흥밖) **× 규제 overlay**. **사업유형은 2차축**. pairwise/N-wise 샘플러가 이 조합을 계통 커버(레드팀 F5 3-way·도메인 META와 수렴).
2. **척추 C 수집 완전성**: 산지구분·경사도·입목축적·농지구분을 임야/농지 required-input manifest에 추가. **단 산림청 공식데이터 유료/미확보면 NEEDS_OFFICIAL_SURVEY 정직 유지(근사 금지)** — 그러나 **KNOWN(용도지역×지목)으로 분해가능한 방향은 지금도 차별화**해야(NEEDS_OFFICIAL_SURVEY로 뭉뚱그리지 말 것).
3. **격리 `land_conversion_charges`(보전/준보전)를 감사경로에 배선**(도메인 META 교정).
4. **불변식 예: "임야 & 보전산지 → 개발가능성 '제한' 상한 + 산지전용 근거 필수"·"자연녹지 임야인데 용적률을 도시지역급으로 산출 → finding"**(과거 과대표시 버그의 회귀 골든화).

**★기반 ② 재정의:** 골든 strata의 **1차축은 사업유형이 아니라 토지속성 조합**(지목×용도지역×산지구분×…). 이것이 착수 전 차원 레지스트리(기반 ①②)를 바로잡아야 하는 결정적 증거 — 사용자 통찰을 일회성이 아니라 **레지스트리의 차원으로 박제**하면 샘플러가 자동 커버(통찰의 제도화).

### 12.6 입력 차원 레지스트리 (차원 도출 — 사용자 요청 "다양한 경우의수 추가차원 통찰 도출")

**★5대 스키마 통찰(단순 나열이 아니라 이 원리가 레지스트리를 정의):**
1. **조건부 트리(naive 곱 아님)**: 다수 차원이 상위차원에 조건부 — 산지구분은 지목=임야일 때만·농지구분은 전/답일 때만·재초환은 재건축일 때만·안전진단은 재건축/리모델링일 때만. → 무의미 조합("대지×보전산지") 미샘플·조합폭발 통제·**유효조합만 커버**(첨부문서 "4,800+ 조합"의 실유효공간은 훨씬 작음).
2. **가지성(knowability) 계층 → 척추 C manifest 정의**: Tier K(항상 known·VWorld/토지이음 무료: 지목·용도지역·면적·형상·공시지가) / Tier C(수집가능·유료가능: 용도지구·구역·산지구분·농지구분·규제overlay·권리등기·규제지역) / Tier S(공식조사 필요·흔히 미확보: 경사도·입목축적·지반). → **KNOWN은 지금 차별화, S는 정직 NEEDS_OFFICIAL_SURVEY**.
3. **overlay 스택 = 최소구속(binding=min)**: 용도지역 FAR 200%라도 고도지구·문화재는 높이, GB는 전면 차단 → **실효 envelope = 모든 적용 overlay의 교집합**. 불변식 "실효 ≤ min(모든 적용 overlay)". 과거 과대표시 버그가 여기 삶.
4. **결정변수 페어링**: 커버리지 분모 = 토지속성조합 → **결정변수**(개발가부·실효FAR/BCR·건축규모·인허가경로/기간·부담금집합·매출상한·세제·리스크·확보율/매도청구·자금수지). 고가치 타깃 = 고위험 결정변수를 flip하는 조합.
5. **위험지대 = KNOWN 과신 + 조건부 하위차원 무시**(사용자 지적 정확): 자연녹지 임야를 보전/준보전 무시하고 도시급 산출 = 과대표시 버그. **우선 커버 타깃 = 조건부 하위차원 상호작용.**

**차원 레지스트리(축그룹 A~H · Tier · 조건부 · 현코드status[grep])** — status=코드존재 여부일 뿐 감사-커버리지 아님(도메인 META: 존재≠배선):

| 축그룹 | 차원(값 예시) | Tier | 조건부 | 코드status |
|---|---|---|---|---|
| **A 토지본원** | 지목(28법정)·용도지역(주거1·2·3종/준주거/상업4/공업3/녹지[보전·생산·자연]/관리[보전·생산·계획]/농림/자연환경)·면적규모(소필지<100·광평수>1만)·형상(정형/부정형/자루)·공시지가대 | K | — | 지목·용도지역·면적 ✅ |
| **B 지구·구역 overlay(스택)** | 용도지구(경관/고도/방화/방재/보호/취락/개발진흥/특정용도제한)·용도구역(GB/시가화조정/수자원보호/도시자연공원)·지구단위계획(완화·강화)·도시계획시설 저촉 | C | — | 지구단위124·용도지구37·시설저촉39·GB35·용도구역1(미미) |
| **C 지목-조건부 세부** | **[임야→]산지구분(보전[임업용/공익용]/준보전/전용제한)**·[전답→]농지구분(진흥/보호/밖)·초지 | C/S | 지목 gating | 산지구분=honest None·농지=partial |
| **D 제약·보호 overlay(binding)** | 군사(통제/제한/비행1~6)·문화재(지정/역사문화환경 반경/매장유존)·상수원·수변·특별대책·재해위험(침수/산사태/급경사지)·접도구역·완충녹지·연안·철도/공항보호 | C | — | 군사=G1 partial·문화재17·상수원28·재해9 |
| **E 접근·기반(gating)** | 접도(건축법도로 접함·너비·**맹지**)·건축선후퇴·상하수도/전기 인입·역세권/교통·도로개설계획 | C/S | — | 건축선94·역세권141·접도 partial |
| **F 권리·소유(등기)** | 소유형태(단독/공유/구분/국공유혼재/종중/재단)·확보율·권리제한(근저당/신탁/지상권/법정지상권/분묘기지권/가등기/가압류/임차권)·대지권(미등기/분리처분)·상속(미등기/다수상속인)·거래규제(허가구역/농취증/외국인) | C | 사업유형 일부 | 권리=registry partial·외국인0 |
| **G 사업·정비 맥락** | 사업유형(신축/재건축/재개발/가로주택/소규모재건축/역세권활성화/도시개발/산단/물류/관광/SOC)·**[재건축→]안전진단·재초환**·**[정비→]지정요건(노후도·호수밀도)·동의율·일몰**·건축물현황(나대지/기존/무허가/위반)·시행방식(조합/신탁/공공/민간) | C | 계층조건부 | 재초환=isolated·안전진단=주석·정비=동의율만 |
| **H 시장·시기·금융** | 규제지역(투기과열/조정)·분양가상한 대상(공공택지/규제지역)·HUG관리(미분양/고분양가)·인구동향(성장/소멸→흡수율)·과밀억제권역(취득중과)·**기준시점(as-of·소급correctness)**·금리/PF환경 | C | 분양사업 일부 | 규제지역3·과밀2(미미)·분양가상한=ref만·흡수율=0 |

**★신규 도출(기존 임야6·사업유형 층화가 놓친 것):** ①조건부 트리 스키마(폭발통제) ②overlay binding=min 불변식(과대표시 회귀골든) ③기준시점 축(소급 correctness·저장분석 재감사) ④가지성 3계층(K 지금차별화/S 정직) ⑤형상·면적규모(광평수 체감·자루형 효율) ⑥거래규제·외국인(취득가능성 gate) ⑦시행방식(조합/신탁 — 확보율 산정식 분기) ⑧건축물현황(무허가/위반 — 입주권·철거).

**자율 확장 축그룹 I~K + 정비 gap-fill (통찰루프 자율 수행·status grep 검증):**

| 축그룹 | 차원(값) | Tier | 조건부 | 코드status |
|---|---|---|---|---|
| **I 환경·물리(binding on 실효규모)** | 지반/토질(연약/암반/매립/성토→기초공법·토목비)·**오염토양(토양환경보전법→정화의무·비용·기간)**·지하수위(지하층·차수)·소음/진동(도로·철도·공항→방음·거실배치)·일조/인동거리(정북→실효건축규모)·조망/경관(조망축→높이·심의) | S/C | — | 일조248·경관23·지반16·소음7·**오염토양0★gap** |
| **J 절차·심의·기여(→기간·재량)** | **기부채납 방식(부지/건물/현금→종상향 net-out·인센티브)**·공공기여율·환경영향평가(규모·용도 gating→절차·기간)·교통/재해/인구영향평가·심의대상(도계위/건축위/경관위/통합심의/사전결정→재량·기간)·정비기반시설 무상양도/유상매입(도정법98) | C | 규모·용도 gating | 기부채납57·환평25·심의15·교평6 |
| **K 금융·구조·Exit(→자금수지·리스크)** | 자금조달구조(자기자본/브릿지/본PF 비율)·신탁방식(관리형/차입형/책임준공/분양관리)·시공사 신용보강·Exit(선분양/후분양/임대/리츠→수지·세제)·PF조달환경·금리 | C | 사업 gating | 신탁방식3(미미) |
| **F/G gap-fill(정비 correctness·0 handling)** | **권리산정기준일·지분쪼개기(현금청산 판정)**·**무허가건물 입주권 기준일(조례별 1989.3.24 등)**·**세입자·영업보상(재개발 vs 재건축→명도·비용)**·명도난이도 | C | 정비 gating | 권리산정1·무허가0·영업보상0 **★전부 gap** |

**★루프 수렴 선언(loop-until-dry):** 축그룹 A~K(~60차원·조건부 트리)로 **축 레벨은 포화**. 이후 후보는 (a)기존 축의 **값(value)**(특정 기초공법·개별 조례 수치·세부 용도지구 종류 — 새 축 아니라 값)이거나 (b)**초희소·초국지(특정 지자체 고유 심의관행)** → 사전등록보다 **HITL/퍼저 트리거가 효율**(§10 신규성 필터·비용 규율). 신규 고임팩트 축 산출이 급감 = **정직한 정지점**. 더 생성하면 alert fatigue·값을 축으로 오격상.

> §12.6은 §10 통찰루프의 **차원 발굴 자율 적용**: 코디네이터가 도메인지식으로 60+축 생성(propose)·grep status 검증(dispose)·조건부트리로 폭발통제·수렴까지 자율 수행. ★경계 정직 재보정: **알려진 도메인 차원의 열거·검증·스키마적용은 자율**(방금 60+ 도출·되물음 불요였음 — 앞서 "축판정은 사람"으로 되물은 건 과장). 진짜 인간 필요는 (1)최상위 프레임 재정의(삼각척추류 패러다임) (2)자원한계 하 **우선순위 판정**(어느 축부터 구현) (3)초국지 tacit 지식뿐. 사용자 산지구분 기여도 도메인 렌즈가 자율 발굴한 인접군(K1~12)과 겹침 = 인간의존은 좁다. 이 레지스트리가 기반 ①(커버리지 분모)·기반 ②(골든 strata 1차축) 구체 스키마 = **동결 대상**.

> 이 계획은 CLAUDE.md 버그수정 정책("정답 기준선과의 격차로 패턴 정의 → 공용화 → 전역 스윕")을 **런타임에 플랫폼이 매 분석마다 스스로 적용**하게 만들고, 제미나이 마스터플랜의 값어치 있는 확장(권원·능동증식·PF)을 **현실 대조로 취사**하되 근거 없는 인프라(Neo4j·zk·Rhino)는 정직하게 거부한다. 상태: **계획 확정 — 실행 승인 대기.**
