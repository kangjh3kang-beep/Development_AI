# PropAI × C2R v1.3 하이브리드 구현계획 (2026-06-27)

## 종합판정
YES — C2R v1.3는 우리 결함의 '체계적 버전'이며 고도화·재발방지에 유효하다. 이번 세션에서 우리가 국소패치로 푼 4건(층수 3중불일치·draw3D 미표시·단일박스·부지소실)은 전부 동일 근본원인(SSOT 단선 + 산출물에 기하 불변식/계약 게이트 부재 + provenance 미부착)에서 나왔고, 문서의 중심사상('Buildable>Render, 검증가능 데이터파이프라인 우선, hash/trace/invariant/계약, AI이미지는 결과설명일 뿐')이 바로 그 재발을 구조적으로 막는 일반화다. 단, 문서를 통째로 ADOPT할 필요는 없다. 우리는 이미 결정론 매스·엔벨로프 엔진(compute_optimal_mass·compute_buildable_envelope)·기하 SSOT(DesignGeometry)·룰엔진(BuildingCodeRuleEngine)·공용 일조산식(sunlight_setback)·c2r think_before 게이트·evidence/provenance 문화·parcel-batch 상태머신(JobState+sha256 멱등)·shapely를 보유하므로, 문서의 '계약층'(INV-GEO 하드게이트·envelope_result 단일계약·§4 hash/run_id·render guard·서버측 design-run)을 기존 자산 위에 ADAPT로 흡수하는 것이 ROI·리스크에서 압도적으로 우월하다. Revit Add-in(.NET8)·Oracle23ai 마이그레이션·OCI Terraform·NIM·APS/Forma는 우리 스택(FastAPI·Postgres/PostGIS·Next.js·Qdrant·Oracle Cloud VM·Supabase)과 불일치/과대이므로 REJECT 또는 packet 개념만 IFC/glTF로 ADAPT한다. 종합: 문서는 우리 결함을 해결하는 올바른 방향이며, '하드 기하 불변식 + 단일 envelope_result 계약 + hash/run_id 규율'을 1차 증분으로 즉시 채택한다.

## 구현가능성
우리 스택에서 핵심 강점(INV-GEO 하드게이트·envelope_result·hash/run_id·render guard·서버측 design-run)은 전부 최적구현 가능하다. (1) shapely가 이미 cad/site_layout·solar_envelope·design_geometry 3모듈에 import되어 있어 INV-GEO 검증기는 신규 의존성 0, 순수 추가 모듈로 to_design_payload·DesignGeometry 조립·compute_optimal_mass 출구에 하드게이트 배선 가능. (2) envelope_result는 Pydantic(이미 전역 표준)으로 정의하고 DesignResult/flat dict/DesignGeometry 3경로를 어댑터로 흡수 → 무회귀 이행. (3) hash/run_id는 hashlib(이미 ledger content_hash·design_spec hash에서 사용)로 additive 부착, provenance 계약 문화 보유. (4) 서버측 design-run 상태머신·멱등은 parcel-batch(JobState enum·sha256 멱등키·Celery enqueue+BackgroundTasks 폴백·submit/poll/cancel)를 일반화하면 신규 프레임워크 불필요 — 단 prod Celery 워커 상시가동 미보장이라 parcel-batch식 env플래그 게이팅+BackgroundTasks 폴백 적응 필수(brief boot ~20s 블록 회피). 영속은 Postgres에 design_runs 테이블 신설로 충분. 불가/불일치: Oracle23ai SDO_GEOMETRY·Revit DirectShape·OCI Terraform·NIM은 스택 충돌 또는 라이선스($11K ODA 등)로 현 단계 비현실적. 결론: 문서 강점의 90%가 기존 자산 재사용으로 저침습·고가용 구현 가능.

## 비교 매트릭스
- **기하 불변식(INV-GEO-001~008): polygon valid·non-manifold·면적보존·0세대/0면적 차단·상태 enum** [ADAPT] — 우리: 전무. is_valid/make_valid/is_simple/PASS_WITH_WARNINGS grep 0건. to_design_payload가 검증없는 raw 4코너 사각형 방출, 매스단계 footprint=sum / 문서: INV-GEO-001~008을 하드게이트로 강제(polygon valid·self-intersection·면적일치·PASS/PASS_WITH_WARNINGS/FAIL enum)
- **단일 산출물 계약(envelope_result)** [ADAPT] — 우리: 3~4경로 ad-hoc dict: DesignResult(자유형 design_payload/summary/compliance)·compute_buildable_envelope flat ~30키 dict·DesignG / 문서: 모든 매스/엔벨로프 산출물을 단일 envelope_result Pydantic 계약(상태 enum 포함)으로 통일
- **provenance hash/run_id(input/rule_set/geometry/prompt/render hash + run_id + source_version)** [ADAPT] — 우리: 기하계약에 미부착(grep 0건). 존재 hash는 ledger content_hash(few-shot 큐레이션)·design_spec hash·object_store SigV4뿐 = C2R 체인과 무관 / 문서: §4 공통계약: run_id+artifact URI+5종 hash+상태 enum을 모든 결과에 부착해 재현·출처추적·변조탐지
- **rule kernel 분리(area_119·solar_61_86·apartment_spacing·education_env·local_ordinance)** [ADAPT] — 우리: 분산: solar_61_86는 3모듈 중복(일부만 sunlight_setback helper 통일), apartment_spacing은 solar_envelope advisory note에만, education_en / 문서: derive_envelope MVP에서 rule kernel을 명시 분리·합성·trace
- **render routing guard(geometry_hash 필수, 검증된 브리프만 렌더)** [ADAPT] — 우리: 부재. /render는 brief 받아 바로 provider 호출 → 인벨로프와 무관한 임의 브리프로도 렌더 가능(문서 원칙 정면위반, P0급 갭) / 문서: P3b: geometry_hash를 필수로 요구하는 render routing guard로 검증 안 된 렌더 차단
- **AI이미지=결과설명 원칙(법규/면적의 원천 아님)** [ADOPT] — 우리: 이미 코드로 준수: build_foundation은 인벨로프 먼저 산출·렌더 기본 미호출(pending_provider), image_provider는 가짜 바이트 없이 정직강등(provider_unconfigure / 문서: 동일 중심사상
- **서버측 설계런 상태머신(S0~S9)+멱등 Celery+WS** [ADAPT] — 우리: 설계는 stateless 동기 호출(generate_design_proposals·build_foundation 무상태·무hash·무persist). 상태머신·멱등은 parcel-batch에만(JobState·sha / 문서: S0~S9 명시 상태머신+멱등 Celery task(input_hash 캐시)+WebSocket 이벤트+§4 영속
- **Engine A(self-host)/Engine B(외부 API, human approval 없이 호출불가) 분리** [DEFER] — 우리: openai/gemini 동일선상 호출, 키만 있으면 즉시 외부호출. cost는 enforce_llm_quota(402)로 부분충족 / 문서: P3b: Engine A/B 분리 + human approval gate + 렌더단위 cost guard
- **Revit packet/DirectShape import(문서 핵심계약)** [ADAPT] — 우리: 부재. C2R는 이미지 렌더만(image_provider/render_brief). Buildable 파이프라인 종착점 없음. Revit 미보유 / 문서: Revit DirectShape import를 Buildable 핵심계약·종착점으로 명시
- **Oracle DB 23ai(SDO_GEOMETRY·vector) 마이그레이션** [REJECT] — 우리: Postgres/PostGIS+Supabase+Qdrant 보유. Oracle23ai 없음 / 문서: Oracle 23ai로 기하·벡터 통합 저장
- **OCI Terraform·Object Storage·NIM·APS/Forma 인프라** [REJECT] — 우리: Oracle Cloud VM(수동 SSH 블루그린)·Supabase Storage 보유. Terraform/NIM/APS 미사용 / 문서: P0/P2 인프라로 OCI Terraform·Object Storage·NIM·APS/Forma
- **family dictionary / family_asset(설계 부재 자산 사전)** [ADAPT] — 우리: design_ingest(부지맞춤 자동생성: 검색+조합)·design reference geometry·massing_strategy 목적함수 SSOT 보유 / 문서: family_asset 사전으로 표준 부재 카탈로그

## ADOPT
- AI이미지=결과설명 원칙의 '명시적 헌법화': 우리는 이미 코드로 지키나(렌더 기본 미호출·정직강등), 문서처럼 karpathy_render_ruleset.md 옆에 'Buildable>Render, 이미지는 법규/면적/복원의 원천이 될 수 없다'를 정본 원칙으로 명문화해 전 설계경로의 불변계약으로 승격
- 상태 enum(PASS / PASS_WITH_WARNINGS / FAIL) 3상태 모델 — 현재 think_before/verify_adjusted_plan는 통과/차단 이진이라 '경고는 있으나 진행가능'을 표현 못함. 문서의 PASS_WITH_WARNINGS를 그대로 채택해 0세대 등 하드FAIL과 advisory 경고를 분리
- '검증가능 데이터 파이프라인이 거버넌스의 1순위'라는 우선순위 원칙 — Buildable(기하·법규 검증)을 Render·LLM보다 항상 먼저·우선으로 두는 의사결정 규율

## ADAPT
- INV-GEO-001~008 → shapely 기반 신규 공용 모듈 geometry_invariants.py(폴리곤 valid·self-intersection(is_simple)·non-manifold·footprint 면적 = sum(units+core+corridor) 보존단언·0세대/0면적 차단·PASS/PASS_WITH_WARNINGS/FAIL enum). shapely 이미 import됨 → 신규 의존성 0. to_design_payload·build_design_geometry·compute_optimal_mass 출구에 하드게이트 배선
- envelope_result 단일 Pydantic 계약 → DesignResult·compute_buildable_envelope flat dict·DesignGeometry·build_foundation 4경로를 어댑터로 수렴(상태 enum·핵심메트릭·근거 포함). 기존 소비처는 어댑터로 무회귀 흡수
- §4 hash/run_id → hashlib로 input_hash/rule_set_hash/geometry_hash/prompt_hash/render_hash + run_id(uuid) + source_version을 envelope_result·brief·render 응답에 additive 부착(기존 ledger content_hash 패턴 재사용)
- render routing guard → /render가 brief의 geometry_hash와 envelope를 대조, 미검증 브리프 렌더 차단. enforce_llm_quota(402) cost게이트는 그대로 재사용
- S0~S9 서버측 design-run → parcel-batch JobStore/JobState 패턴을 'design_run'으로 일반화(Postgres design_runs 테이블), input_hash 멱등캐시, Celery enqueue + BackgroundTasks 인프로세스 폴백(prod 워커 미보장 대응), 1차는 GET 폴링(WS는 후속). 프론트 DAG(topoSort/topoLevels)는 백엔드 런의 구독자로 강등(SSOT는 백엔드)
- rule kernel 분리 → solar_61_86는 기존 sunlight_setback helper로 완전 통일, apartment_spacing·education_env(special_parcel 재사용)·area_119(building_code_rules 재사용)·local_ordinance를 derive_envelope에서 합성·trace. 각 규칙 적용을 rule_set_hash로 추적
- Revit packet → IFC/glTF packet으로 ADAPT: 이미 ProceduralBuilding/IFC4→glb·DesignInterpreter 보유. Buildable 종착점을 'IFC/glTF export packet(geometry_hash 부착)'으로 정의해 Revit 미보유를 우회하면서 문서의 '핵심계약 종착점' 정신 충족
- family dictionary → 기존 design_ingest 검색+조합·design reference geometry·massing_strategy를 family_asset 사전 개념으로 정규화(표준 코어/세대 카탈로그 + geometry_hash)

## REJECT
- Oracle DB 23ai 마이그레이션(SDO_GEOMETRY·vector) — 현 Postgres/PostGIS+Supabase+Qdrant 스택과 정면충돌, 기하는 shapely+PostGIS·벡터는 Qdrant로 이미 충분
- Revit Add-in(.NET8) DirectShape import — Revit 실사용자 미확인·라이선스·.NET 스택 부재. IFC/glTF packet으로 대체
- OCI Terraform IaC — 현 Oracle Cloud VM 수동 SSH 블루그린 운영체계로 충분, Terraform 전환은 현 단계 과대
- NIM(NVIDIA Inference Microservice) — self-host GPU 추론 인프라 미보유·불필요, 외부 API(openai/gemini) 게이트로 충분
- APS(Autodesk Platform Services)/Forma — 문서도 '선택'으로 분류. Autodesk 종속·비용. 우리 절차생성 IFC 파이프라인과 중복
- family_asset을 Oracle 23ai 저장 전제로 신설 — 저장은 Postgres/Qdrant 재사용. 사전 개념만 ADAPT

## 우리결함 해결도
- [STRONG] 단일박스·0세대 결과가 게이트 없이 통과(이번 세션 국소패치로 임시해결, 재발방지 구조 없음) → INV-GEO 하드게이트(footprint=sum(units+core+corridor) 면적보존 단언 + 0세대/0면적 FAIL)를 to_design_payload·compute_optimal_mass·DesignGeometry 조립 출구에 공용 배선하면, 단일박스/0세대가 산출 즉시 FAIL로 차단됨. CLAUDE.md 공용화·전역스윕 정책에 정합(한 곳 고치면 전역 따라옴)
- [STRONG] 층수 3중불일치(canonicalFloors)·SSOT 단선이 근본원인이었으나 패치만 적용 → envelope_result 단일 Pydantic 계약이 canonicalFloors·massGeom·메트릭을 단일 정본으로 강제하고, 3~4경로 ad-hoc dict를 어댑터로 수렴 → 산출물 다중표현으로 인한 불일치 재발을 타입계약으로 차단
- [MODERATE] 근거(evidence·legalRefs) 파편화(siteAnalysis·trustMeta·complianceData) → envelope_result에 rule kernel trace + rule_set_hash + 근거계약{value,basis,source,legal_link,confidence}을 표준 부착해 근거를 단일 계약면에 통합. 이번 세션 추가한 근거 인스펙터의 단일 소스가 됨
- [MODERATE] 동일부지 재요청마다 전체 재계산(멱등 부재)·런 추적 불가(감사/재현 불가) → input_hash 멱등캐시 + run_id 영속(design_runs)으로 동일입력 캐시히트·재현·변조탐지 확보. parcel-batch 검증패턴 재사용이라 저위험
- [STRONG] 검증 안 된 임의 브리프로도 렌더 가능(인벨로프와 무관) — 문서 중심사상 정면위반 → render routing guard가 geometry_hash·envelope 대조로 미검증 렌더 차단 → 'AI이미지가 법규/면적의 원천이 되는' 오염 경로를 원천봉쇄
- [WEAK] 설계 타당성 ~75~80% 정체(빈 참고도면 compose(site,[],...)·참고검색 미배선·PixelRAG 미실행) → 문서가 직접 해결하진 않으나(이건 reference RAG 배선 문제), rule kernel 분리·envelope_result 계약이 참고도면 주입의 검증 프레임을 제공. 단 PixelRAG 하이브리드는 별도 트랙

## 하이브리드 증분(실행순서)
1. **geometry_invariants.py 공용 하드게이트(INV-GEO) + PASS/PASS_WITH_WARNINGS/FAIL enum** — shapely 기반 신규 공용 모듈: polygon valid(make_valid)·self-intersection(is_simple)·non-manifold·footprint 면적=sum(units+core+corridor) 보존단언·0세대/0면적 차단. to_design_payload·compute_optimal_mass·build_design_geometry 출구에 하드게이트 배선. 독립배포·무회귀(차단만 추가)
   - 재사용:shapely(이미 3모듈 import)·DesignGeometry·compute_optimal_mass·_compute_podium_tower·sunlight_setback helper / 문서접목:INV-GEO-001~008 하드 기하 불변식 + 상태 enum / 리스크:낮음. 순수 추가 게이트라 정상경로 무영향, 단 기존에 몰래 통과하던 잘못된 산출이 FAIL로 노출될 수 있어 1차는 PASS_WITH_WARNINGS로 그림자운영 후 FAIL 승격
2. **envelope_result 단일 Pydantic 계약 + 4경로 어댑터 수렴** — DesignResult·compute_buildable_envelope flat dict·DesignGeometry·build_foundation을 단일 envelope_result(geometry·metrics·status enum·evidence·canonicalFloors)로 수렴. 기존 소비처(compose·feasibility·pdf)는 어댑터로 흡수, 무회귀 가드
   - 재사용:Pydantic(전역표준)·DesignGeometry(통합계약에 가장 근접)·evidence 근거계약 / 문서접목:envelope_result 단일 타입계약 + 상태 enum / 리스크:중간. 다수 소비처 회귀 가능 → 어댑터 + 소비처별 무회귀 테스트로 단계 이행. order1 게이트가 어댑터 출력을 검증해 안전망
3. **hash/run_id provenance 규율(§4) additive 부착** — input_hash/rule_set_hash/geometry_hash/prompt_hash/render_hash + run_id(uuid) + source_version을 envelope_result·brief·render 응답에 부착. 비침습 메타데이터
   - 재사용:hashlib(ledger content_hash·design_spec hash 패턴)·provenance 문화 / 문서접목:§4 run_id + 5종 hash + artifact URI 공통계약 / 리스크:낮음. 응답 필드 추가뿐. geometry_hash는 order4의 render guard 전제라 선행 필요
4. **render routing guard — geometry_hash 필수 검증** — /render가 brief의 geometry_hash·envelope를 대조해 미검증 브리프 렌더 차단(blocked_by_unverified_geometry). enforce_llm_quota(402)는 그대로
   - 재사용:c2r think_before 게이트·image_provider 정직강등·enforce_llm_quota / 문서접목:P3b render routing guard / 리스크:낮음. 차단 추가뿐. order3 geometry_hash 의존
5. **rule kernel 분리 + derive_envelope trace** — solar_61_86는 sunlight_setback로 완전통일, apartment_spacing·education_env(special_parcel)·area_119(building_code_rules)·local_ordinance를 derive_envelope에서 합성·trace, rule_set_hash로 추적. education_env를 설계엔진에 미배선 상태→배선
   - 재사용:sunlight_setback·special_parcel.detect_special_parcel·BuildingCodeRuleEngine.check_all·massing_strategy / 문서접목:rule kernel 분리(area_119·solar_61_86·apartment_spacing·education_env·local_ordinance) / 리스크:중간. 규칙 중복제거 시 미세 수치변동 가능 → 골든테스트로 기존 결과 고정 후 리팩토링
6. **서버측 design_run 상태머신 + input_hash 멱등 + BackgroundTasks 폴백** — parcel-batch JobStore/JobState를 design_run으로 일반화(Postgres design_runs), input_hash 멱등캐시, Celery enqueue + BackgroundTasks 인프로세스 폴백(env 플래그 게이팅), GET 폴링. 프론트 DAG는 구독자로 강등
   - 재사용:parcel-batch(JobState·sha256 멱등·Celery+BackgroundTasks 폴백)·dependency-graph topoSort·ws_manager(후속) / 문서접목:P3 S0~S9 상태머신 + 멱등 Celery task + (WS 후속) / 리스크:중간. 프론트/백엔드 런 권위 이중화 → 백엔드 단일권위 경계 명시. prod Celery 미보장 → BackgroundTasks 폴백 필수(boot 블록 회피)
7. **IFC/glTF Buildable packet(종착점) + family_asset 정규화** — Buildable 종착점을 IFC/glTF export packet(geometry_hash 부착)으로 정의(Revit packet ADAPT). design_ingest 검색+조합·massing_strategy를 family_asset 사전으로 정규화
   - 재사용:ProceduralBuilding·IFC4→glb·DesignInterpreter·design_ingest·design reference geometry / 문서접목:Revit packet(→IFC/glTF)·family dictionary / 리스크:중간. 절차생성 정합성. order1 INV-GEO가 packet 출력도 검증해 안전망

## 리스크
- envelope_result 수렴 시 다수 소비처(compose·feasibility·pdf·프론트 메트릭바) 회귀 — 어댑터 + 소비처별 무회귀 골든테스트로 단계 이행 필수
- INV-GEO 하드게이트를 즉시 FAIL로 켜면 기존에 몰래 통과하던 잘못된 산출이 대량 차단될 수 있음 — 1차 PASS_WITH_WARNINGS 그림자운영으로 노출빈도 측정 후 FAIL 승격
- prod Celery 워커 상시가동 미보장(beat는 rates/auction/growth만) — design_run을 Celery 전제로 짜면 브로커 미가동 시 ~20s 블록(parcel_batch.py 교훈). BackgroundTasks 폴백 + env 게이팅 필수
- 프론트 DAG(useNodeRunner)와 백엔드 design_run 권위 이중화 시 SSOT 충돌 — 백엔드를 단일권위로, 프론트는 구독자로 강등하는 경계가 order6의 전제
- rule kernel 중복제거(solar_61_86 3모듈 통일·종상향 분리) 시 미세 수치변동으로 기존 분석결과 변경 가능 — 골든테스트로 고정 후 리팩토링
- Revit→IFC ADAPT가 실제 Revit 실사용자 워크플로우를 대체 못할 수 있음(BIM 협업 단절) — Revit 실사용자 존재 여부 확인 전까지 IFC/glTF로 진행
- 문서가 설계 타당성 75~80% 정체의 핵심(빈 참고도면·PixelRAG 미배선)을 직접 해결하지는 않음 — reference RAG 배선·PixelRAG 하이브리드는 본 하이브리드와 별개 트랙으로 병행 필요

## 결정(사용자)
- 진행: INC1부터 바로 구현
- Revit: 실수요 있음 → IFC/glTF 진행 + IFC→Revit 브리지 후속 DEFER
