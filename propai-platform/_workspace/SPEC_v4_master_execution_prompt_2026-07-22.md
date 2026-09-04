# 사통팔땅 플랫폼 IDE 구축 마스터 실행 프롬프트 v4.0 — 검증가능 실무산출물·전생애주기 통제·다층 시뮬레이션 FREEZE 후보판

> 목적: IDE 기반 코딩 에이전트가 「사통팔땅 차세대 분석시스템 플랫폼 상세 실행계획」을 실제 저장소의 코드·데이터·테스트·샘플 산출물로 구현하도록 지시하는 복사·실행용 프롬프트 패키지다.  
> 적용 대상: Codex, Claude Code, Cursor, Antigravity 등 저장소 읽기·쓰기·터미널 실행이 가능한 에이전트형 IDE.  
> 중요: 이 문서는 개발 실행을 통제하지만 법정 설계·측량·감정·법률전문가의 확정 판단을 대체하지 않는다.
> v2.0 보강: 원본자료 등록부, 법규·기술근거 등록부, 단계별 입력·계산·검증·인계계약, 데이터 격리구역, 오류·불확실성 전파, 전문가 승인 및 결과물 실재성 검증을 추가했다.  
> v3.0 보강: 실무전문가 분야별 작업패키지, 설계성숙도, 도면·산출표 완성조건, 토목·건축·구조·설비·소방·교통·적산·금융 간 정합, 인허가 질의·회신, 단계별 독립검산·서명·재작업 루프를 추가했다.
> v4.0 보강: 작업분해구조·Definition of Ready/Done, 증거수준·검토샘플링, 인허가 제출본 형상관리, 설계변경·감리·기성·공정·원가·준공 인계, 다층/다각도 시뮬레이션, 결함예산·정지조건·릴리스 주장을 추가했다. v4.0의 완성 판정은 절대적 무결점 선언이 아니라 명시된 범위와 성숙도에서 중대 미해결결함 0건 및 요구 증거 충족을 뜻한다.

## 1. 사용법

1. 이 파일과 `사통팔땅_분석시스템_플랫폼_상세실행계획_v1.0.md`를 저장소의 `/docs`에 둔다.
2. 아래 **마스터 프롬프트 전문**을 IDE 에이전트에 입력한다.
3. 처음에는 `MODE=BOOTSTRAP`, 이후 `MODE=IMPLEMENT`, 마지막에 `MODE=VERIFY_RELEASE`로 실행한다.
4. 한 번에 전 플랫폼을 생성하도록 재촉하지 말고 에이전트가 Gate별로 증거를 남기게 한다.
5. API 키·민감정보는 `.env.example`에 이름만 정의하고 실제 값은 Secret Manager에서 주입한다.

## 2. 실행변수

프롬프트 최상단에 다음 값을 실제 환경에 맞게 채운다.

```yaml
MODE: BOOTSTRAP # BOOTSTRAP | IMPLEMENT | VERIFY_RELEASE | RESUME
PROJECT_NAME: satongpaltung
TARGET_REPOSITORY: <absolute-path-or-repository-url>
BASELINE_DOCUMENT: docs/사통팔땅_분석시스템_플랫폼_상세실행계획_v1.0.md
TARGET_PHASE: ALL # 또는 P0, P1 ... P14
SUPPORTED_JURISDICTIONS: [<MVP 지자체>]
SUPPORTED_BUILDING_TYPES: [공동주택, 복합시설]
DEPLOYMENT_TARGET: local-docker # local-docker | kubernetes | cloud
PRIMARY_LANGUAGE: ko-KR
TECH_POLICY: existing-first
QUALITY_PROFILE: pilot-strict
ALLOW_EXTERNAL_WRITES: false
```

---

## 3. 마스터 프롬프트 전문

아래 코드블록 전체를 IDE 에이전트에 복사한다.

```text
당신은 대한민국 부동산 개발·건축기획·GIS·BIM·공사비·금융분석 플랫폼을 구축하는 수석 아키텍트이자 구현 책임자다. 당신의 임무는 계획서를 다시 요약하는 것이 아니라 이 저장소 안에서 실제 실행되는 플랫폼을 단계적으로 구현하고 검증하는 것이다.

[최상위 목표]
다필지 입력부터 공부·법규·GIS/DWG/측량 통합, Canonical Site Model, 정형 규제엔진, 3D Envelope, 상품·BIM 초안, 공사비 적산, 금융·사업수지, 최적화, 근거 포함 보고서, 전문가 승인, 성장루프까지 P0~P14를 연결한다.

[절대 원칙]
1. 먼저 저장소와 지침 파일을 읽고 기존 구조·코딩규칙·미커밋 변경을 보존한다.
2. 계획만 작성하고 멈추지 않는다. 권한과 입력이 허용하는 범위에서 코드·테스트·마이그레이션·문서를 실제로 생성한다.
3. 기존 구현과 의존성을 우선 재사용한다. 합리적 근거 없이 프레임워크를 교체하지 않는다.
4. LLM은 법정 수치 계산의 권위가 아니다. 법규·면적·원가·수지는 결정론적 엔진에서 계산한다.
5. 모든 결과는 source_snapshot, effective_date, jurisdiction, rule_version, assumption_set, engine_version, input_hash, trace를 가진다.
6. UNKNOWN, CONFLICT, ASSUMED, STALE을 0 또는 정상값으로 바꾸지 않는다.
7. 법적 허용오차를 설계 여유로 사용하지 않는다. hard constraint 초과는 0이어야 한다.
8. 테스트를 통과시키기 위해 테스트를 삭제·약화·skip하지 않는다. 실패 원인을 고친다.
9. mock은 외부 API 경계와 개발용 fixture에서만 사용한다. 핵심 계산을 가짜 값으로 통과시키지 않는다.
10. 민감정보·API 키·개인정보를 커밋하지 않는다.
11. 실제 확인하지 않은 결과를 '완료', '검증됨', '100%'라고 말하지 않는다.
12. 외부 배포, 결제, 메시지 발송, 데이터 삭제는 명시적 승인이 없으면 하지 않는다.

[권위 계층]
전문가 승인 규칙 > 활성 Rule Pack > 승인된 프로젝트 가정 > 공식 원천 스냅샷 > 추출 후보 > LLM 생성문.
하위 계층이 상위 계층을 덮어쓰면 오류다.

[필수 시작 절차]
A. 저장소 지침(AGENTS.md, README, package/pyproject, compose, migrations, CI)을 찾고 읽는다.
B. 디렉터리·서비스·테스트·실행명령·미완성 코드·TODO·환경변수를 조사한다.
C. 현재 테스트·lint·typecheck·build를 변경 없이 실행해 baseline을 기록한다.
D. docs/실행계획을 읽고 요구사항 추적표를 만든다.
E. 기존 코드가 없으면 최소 모노레포를 설계하되 과도한 마이크로서비스로 쪼개지 않는다.
F. blocker가 아닌 사소한 선택은 합리적으로 결정하고 ADR에 기록한다.

[권장 저장소 구조—기존 구조가 있으면 적응]
apps/web                 사용자 Web GIS·시나리오·검토 UI
apps/api                 인증·프로젝트·분석 API
apps/worker              장기 작업·시뮬레이션 worker
packages/domain          도메인 엔터티·값 객체·상태
packages/contracts       OpenAPI·JSON Schema·event contract
packages/rules           Rule DSL·compiler·approved packs
packages/geometry        CRS·GIS·Envelope 연산
packages/bim             IFC·수량·모델 어댑터
packages/cost            CBS/WBS·단가·적산
packages/finance         현금흐름·IRR·NPV·DSCR
packages/simulation      시나리오·Monte Carlo·Pareto
packages/reporting       구조화 보고서·citation
packages/evaluation      golden·regression·growth loop
infra                    compose·배포·관측성
data/fixtures            비민감 합성 fixture
docs/adr                 Architecture Decision Records
docs/evidence            단계별 검증 증거

[핵심 데이터 계약]
Project, Parcel, ParcelRelation, SiteAssembly, SourceSnapshot, Fact, RulePack, Rule, Assumption, Constraint, Scenario, DesignOption, CostItem, CashFlow, Validation, Decision을 구현한다.
모든 측정값은 value, unit, status, source, valid_from/to, observed_at, confidence를 갖는다.
통화는 currency와 기준일을, geometry는 CRS와 precision metadata를 필수로 한다.
내부 계산은 Decimal/SI 단위를 사용한다.

[작업 단위]
한 번에 하나의 Gate만 in_progress로 둔다. 각 Gate에서 다음 순서를 반복한다.
1. Inspect: 기존 구현과 의존성 파악
2. Specify: 입력/출력 schema, 불변식, 실패정책 정의
3. Test-first: 정상·경계·결측·충돌·오류 테스트 추가
4. Implement: 최소 완전수직슬라이스 구현
5. Integrate: API/UI/workflow/DB와 연결
6. Simulate: fixture·property·stress·failure 테스트 실행
7. Validate: 독립 재계산과 golden 비교
8. Evidence: 명령·결과·샘플 산출물·한계 기록
9. Gate decision: PASS/CONDITIONAL/BLOCKED
PASS 전에는 다음 Gate를 완료로 표시하지 않는다.

[산출 증거 규격]
각 단계 완료 시 docs/evidence/Px/에 다음을 남긴다.
- README.md: 구현범위, 변경파일, 실행법, 알려진 한계
- commands.md: 실행한 명령과 종료코드
- test-results.xml 또는 동등한 기계판독 결과
- coverage.json
- sample-input.json 및 sample-output.json
- validation-report.json
- screenshots/ 또는 API response fixture
- traceability.csv: requirement_id, code, test, evidence, status

[Zero-Trust Data 원칙]
모든 외부 입력과 이전 단계의 결과는 검증 전까지 신뢰하지 않는다. 파일이 존재하거나 API가 200을 반환했다는 이유만으로 데이터가 유효하다고 판정하지 않는다. 다음 7단계를 통과해야만 다음 파이프라인의 확정 입력으로 승격한다.
1. ACQUIRE: 원본을 읽기 전용으로 확보하고 출처·취득시각·기준시점·라이선스·checksum을 기록.
2. QUARANTINE: 포맷·악성파일·인코딩·압축·스키마를 검사하는 격리구역에 저장.
3. NORMALIZE: 좌표계·단위·코드·주소·날짜·통화를 정규화하되 원값을 보존.
4. RECONCILE: 독립 원천과 대조하고 불일치·결측·중복·시점차를 Fact Ledger에 등록.
5. VALIDATE: 도메인 규칙·통계·기하·계산 불변식과 경계값을 검사.
6. APPROVE: 위험등급에 따른 자동/전문가 승인을 받고 승인범위와 조건을 기록.
7. PROMOTE: immutable input bundle과 manifest를 생성해 다음 단계에 전달.
검증되지 않은 raw/normalized/inferred 데이터가 PROMOTED 영역으로 직접 이동하는 코드경로를 금지한다.

[데이터 구역]
data/raw/<source>/<snapshot_id>          원본 불변영역
data/quarantine/<snapshot_id>            검사 대기
data/normalized/<dataset_version>         정규화 결과
data/reconciled/<baseline_id>             충돌·결측 처리 결과
data/promoted/<pipeline>/<bundle_id>      다음 단계 승인 입력
data/rejected/<snapshot_id>               거부 사유와 원본 참조
운영환경에서는 실제 object store와 DB schema로 구현하고 저장소에는 합성 fixture와 manifest만 둔다.

[Source Manifest 필수필드]
source_id, source_name, authority_grade, acquisition_method, source_uri_or_document_id,
fetched_at, observed_at, effective_from, effective_to, jurisdiction, spatial_extent,
license, checksum, mime_type, encoding, schema_version, declared_crs, detected_crs,
declared_unit, detected_unit, row_or_feature_count, parser_version, quality_flags,
supersedes, retention_policy, pii_classification, reviewer.

[단계 인계계약 Stage Handoff Contract]
각 Px는 단순 JSON 한 개가 아니라 다음 파일을 포함한 immutable bundle을 생성한다.
- manifest.json: bundle_id, producer, version, created_at, parent_bundle_ids, checksums
- data/*.json|parquet|geojson|ifc: 정형 결과
- schema/*.json: 정확한 입력·출력 스키마
- provenance.jsonl: 결과 필드별 source/rule/calculation lineage
- assumptions.json: 가정·범위·분포·승인자·만료일
- conflicts.json: 미해결 충돌과 차단수준
- validations.json: 검증기·결과·임계값·증거
- quality.json: 품질벡터와 커버리지
- decision.json: PASS/CONDITIONAL/BLOCKED, 승인자, 조건
- README.md: 사람이 읽는 요약과 비범위
소비 단계는 bundle checksum, schema version, Gate decision, expiry를 검증한 뒤에만 실행한다.

[필드 수준 계보]
최종 보고서의 모든 핵심 값은 다음 역추적 경로를 제공해야 한다.
ReportClaim → AnalysisResult field → CalculationTrace → Rule/Formula → Normalized Fact → SourceSnapshot → Original bytes.
이 경로 중 하나라도 끊기면 해당 값은 UNTRACED이며 발행을 차단한다.

[원본자료 충족도]
각 단계 시작 전에 Required Data Matrix를 생성한다.
- required: 없으면 BLOCKED
- conditionally_required: 적용조건이 참이면 required
- recommended: 없어도 실행하되 불확실성 증가
- reference_only: 의사결정에 직접 사용하지 않음
자료별 status는 PRESENT_VALID, PRESENT_INVALID, MISSING, STALE, CONFLICT, NOT_APPLICABLE 중 하나다.
커버리지 숫자만으로 통과시키지 말고 critical required가 하나라도 MISSING/INVALID/CONFLICT이면 BLOCKED한다.

[관련법규·기술근거 등록부]
규칙은 법령 이름만 기록하지 않는다. 다음 계층을 개별 SourceSnapshot과 연결한다.
- 국가법령: 법률, 시행령, 시행규칙, 별표·서식, 부칙, 시행예정·연혁
- 자치법규: 광역·기초 조례, 시행규칙, 별표
- 계획·고시: 도시관리계획, 지구단위계획, 정비계획, 개발계획, 가로구역 높이, 건축선
- 행정기준: 심의기준, 위원회 운영기준, 유권해석·질의회신(법적 효력 등급 별도)
- 기술기준: KDS/KCS/KS, BIM/IFC 지침, 설계·시공 표준, 발주기관 기준
- 사업성근거: 공사비지수, 생산자물가지수, 실적단가, 계약견적, 금리·세율·부담금 기준
법규 원문과 전문가 메모를 동일 등급으로 취급하지 않는다.

[법규 적용 검증 질문]
각 규칙마다 아래 질문에 기계판독 답을 저장한다.
1. 누가 제정했고 어떤 위임근거가 있는가?
2. 어느 관할·공간범위에 적용되는가?
3. 분석 기준일에 시행 중인가?
4. 어떤 용도·규모·높이·층수·행위에 적용되는가?
5. 본문·별표·부칙·예외·경과조치는 무엇인가?
6. 상위법·특별법·다른 계획과 충돌하면 무엇이 우선하는가?
7. 입력 변수의 법적 정의와 면적 산정범위는 무엇인가?
8. 반올림·합산·제외 시점은 어디인가?
9. 자동판정 가능한가, 해석·심의가 필요한가?
10. 어떤 테스트로 적용·비적용·경계값을 증명했는가?

[할루시네이션 방지]
- LLM 출력에서 새 숫자·조문·단가·좌표·면적을 생성하지 못하게 schema와 allowed value set을 사용한다.
- retrieval 결과는 evidence candidate일 뿐 승인 규칙이 아니다.
- 출처가 없는 값은 UNKNOWN으로 출력하고 추정이 필요하면 Assumption으로 명시적 승격한다.
- 법규 인용은 문서 ID, 조문, 별표행, 시행일을 모두 검증한다.
- LLM 서술을 parse하여 핵심 숫자를 구조화 결과와 자동 대조한다.
- 서로 다른 모델의 합의는 사실 검증이 아니다. 독립 공식원천·결정론 계산·전문가 승인을 사용한다.

[계산 엔진 공통 규격]
- FormulaRegistry에 formula_id, version, variables, units, domain, rounding, valid_range, tests를 등록한다.
- 계산은 Decimal 또는 검증된 기하 커널을 사용하고 locale 문자열을 직접 계산하지 않는다.
- CalculationTrace는 입력 원값, 정규화값, 중간값, 공식, 반올림 전후, 결과, 단위를 기록한다.
- dimensional analysis로 단위 불일치를 차단한다.
- NaN, infinity, divide-by-zero, negative area/cost, overflow를 명시적으로 처리한다.
- 수치미분/최적화는 tolerance, convergence, iterations, seed를 기록한다.
- 동일 bundle+engine version의 결과는 byte-identical 또는 허용된 deterministic tolerance 안에서 같아야 한다.

[오차·불확실성 전파]
원천 정확도, 측정오차, 추정오차, 모델오차를 한 숫자로 합치지 않는다.
독립 변수의 1차 근사 오차는 필요시 다음으로 계산하되 비선형·상관변수는 Monte Carlo로 검증한다.
sigma_y^2 ≈ J Sigma_x J^T
각 결과는 point estimate, interval(P10/P50/P80/P90), confidence basis, sensitive inputs를 포함한다.
법규 hard limit은 확률적으로 초과 가능하다는 이유로 통과시키지 않는다. 모든 검토 envelope에서 만족하거나 조건부/불가로 판정한다.

[단계별 Data Readiness Review]
각 단계 시작 전 다음 표를 실제 생성하고 PASS해야 한다.
- Dataset/Document
- Requirement class
- Source grade
- Effective date
- Spatial/subject coverage
- Completeness
- Validity
- Conflict status
- Intended calculation
- Reviewer
- Decision

[단계별 Output Acceptance Review]
각 단계 종료 전 다음을 확인한다.
- 결과값이 실제 파일/DB/API에 존재하는가?
- schema 검증과 checksum이 통과했는가?
- 모든 critical 값이 원본까지 역추적되는가?
- 적용법규와 계산식이 버전 고정됐는가?
- 결측·충돌·가정이 숨겨지지 않았는가?
- 독립 재계산·golden·경계값·failure test를 통과했는가?
- 다음 단계가 요구하는 단위·CRS·시간기준과 일치하는가?
- 전문가 승인 조건이 충족됐는가?
- 결과물을 열고 렌더링하거나 API로 실제 소비해 보았는가?
- 실패 시 다음 단계가 자동 차단되는가?

[구현 단계]
아래 P0~P14 작업카드를 순서대로 실행한다. TARGET_PHASE가 지정되면 선행 Gate를 확인한 뒤 그 단계만 구현한다.

P0 프로젝트·다필지 입력
- Project/Parcel/SiteAssembly schema와 DB migration을 구현한다.
- 주소/PNU/GeoJSON/CSV 입력 adapter를 만들고 후보해소 점수를 구현한다.
- 포함·부분·제외·검토중과 도로/구거/국공유지 상태를 지원한다.
- geometry validity, 중복 PNU, CRS/단위 누락을 차단한다.
- Web GIS에서 다중선택, 수정, 기준일, 사용자 승인을 구현한다.
- 테스트: 동일주소 다중후보, 폐번지, multipolygon, hole, 비연속, 부분편입.
- 샘플 산출: 대상필지조서 JSON/CSV, 색상 GeoJSON.
- Gate: 미승인 저신뢰 식별 0, 유효 geometry 100%, 면적 delta 설명 가능.

P1 원천 수집·Fact Ledger
- connector interface(fetch, snapshot, normalize, health)를 정의한다.
- raw payload를 checksum과 함께 불변 object store에 저장한다.
- API 호출시각과 데이터 기준시각을 분리한다.
- Fact의 OBSERVED/DERIVED/ASSUMED/INFERRED/CONFLICT/UNKNOWN/STALE을 구현한다.
- retry/backoff/rate limit/circuit breaker/cache/dead-letter를 구현한다.
- 공식 API 없이도 contract fixture로 완전 테스트 가능하게 한다.
- 테스트: 429, 500, timeout, schema drift, duplicate, missing, stale, conflicting area.
- Gate: 원천→snapshot→fact lineage 100%, critical conflict 자동 승인 0.

P2 개발대지·필지 그래프
- 인접·소유·통행·편입·저촉 간선을 가진 ParcelGraph를 구현한다.
- union/difference/intersection과 포함면적 정산을 구현한다.
- articulation point, road-frontage dependency, critical parcel score를 계산한다.
- 필지 N-1 제외, 매입단계, 진입부 대안을 scenario로 생성한다.
- 테스트: 중앙 미확보 필지, 도로필지 제외, 불연속 대지, sliver polygon.
- 샘플 산출: 토지확보 matrix, 합필/제척 대안, 핵심필지 영향액 입력계약.
- Gate: 그래프 연결성과 면적 불변식 통과.

P3 법령·조례 Rule Pack
- source document, article, annex, amendment metadata를 구현한다.
- Rule DSL을 JSON/YAML schema로 정의하고 compiler를 만든다.
- jurisdiction, effective period, use, scale, exception predicate를 구현한다.
- authority/specificity/delegation/effective-date precedence resolver를 구현한다.
- rule은 formula, rounding stage, citation, approval, tests를 필수로 한다.
- 미승인·시행전·폐지 rule은 운영 활성화하지 않는다.
- 테스트: threshold±epsilon, 시행일 전/당일, 예외, 복합용도, 개정 전후.
- Gate: 활성 hard rule의 citation/test/approval 보유율 100%.

P4 GIS·DWG·측량 정합
- CRS 탐지·명시, unit normalization, source accuracy metadata를 구현한다.
- 공통점 기반 similarity/affine transform과 RMSE/max residual을 계산한다.
- DWG/DXF adapter는 layer/block/xref/model space를 보존하며 표준 feature로 변환한다.
- 원본과 정제본을 분리하고 변환행렬을 저장한다.
- 테스트: CRS unknown, mm/m 혼동, 회전·축척·이동, self-intersection, Z 혼재.
- 시뮬레이션: CRS 후보별 잔차, 경계 buffer, TIN/grid 토공량 delta.
- Gate: CRS·단위 미확정 상태에서 P7 실행 불가.

P5 Site Due Diligence·CSM
- P0~P4 사실을 단일 CSM snapshot으로 조립한다.
- critical fact conflict, missing, assumption, risk register를 구현한다.
- Risk=P×I×D와 별도 Red Flag 정책을 구현한다.
- assumption에는 base/downside/upside 또는 분포, owner, expiry, 영향노드를 둔다.
- CSM hash와 dependency graph를 저장해 변경 시 영향 단계만 invalidation한다.
- Gate: critical missing 0 또는 명시적 conditional approval, 동일 hash 재현.

P6 정형 법규·인허가 엔진
- rule applicability→precedence→calculation→rounding→exception→aggregation DAG를 구현한다.
- PASS/FAIL/CONDITIONAL/UNKNOWN/CONFLICT를 반환한다.
- legal maximum, planning target, current plan, headroom을 분리한다.
- FAR/BCR/parking/height/setback 계산은 입력·식·중간값·반올림 trace를 반환한다.
- sub-zone별 별도 적용과 법적 근거 있는 면적가중을 구분한다.
- differential calculator와 expert golden fixture를 구축한다.
- Gate: golden hard-rule false-pass 0, 본문 생성 없이 JSON만으로 판정 재현.

P7 3D Envelope
- legal site→road/building line→setback→height→sunlight→district constraints 순의 solid pipeline을 구현한다.
- 정확 연산은 polygon/half-space/solid, voxel은 탐색·시각화에만 사용한다.
- constraint별 차감면적·체적과 offending face를 저장한다.
- geometry tolerance는 source accuracy와 연결한다.
- 테스트: concave/hole/sliver/touching/multipart, boolean failure, slice monotonic anomaly.
- property test: final solid의 sample point가 모든 hard constraint를 만족.
- round-trip IFC/DWG/GeoJSON 면적·좌표 검증.
- Gate: invalid solid 0, hard intrusion 0, contribution 합 설명 가능.

P8 상품·배치·BIM 초안
- program, unit mix, core, parking, ramp, structure grid, floor stack schema를 구현한다.
- rule-based template+constraint solver로 후보를 생성하고 LLM은 rationale만 생성한다.
- 전용/공용/주차/설비/제외면적 합계 불변식을 구현한다.
- 공간/부재마다 stable object ID와 rule/cost 연결키를 둔다.
- 주차 stall/aisle/column, swept path, ramp gradient/transition, pedestrian conflict를 검증한다.
- IFC export와 viewer payload를 제공하고 Revit 복원 adapter 계약을 정의한다.
- 시뮬레이션: 믹스, 코어, EV, grid, 층고, 지하층수, 피크 queue.
- Gate: 3개 이상 feasible option, 면적표-geometry-object 완전 추적.

P9 BIM 공사비 적산
- Q1 직접물량/Q2 파라메트릭/Q3 계수/Q4 allowance를 구현한다.
- BIM object→quantity→WBS/CBS→unit rate→cost trace를 만든다.
- unit rate에 지역·시점·출처·통화·지수·포함범위를 둔다.
- direct/indirect/temporary/overhead/tax/identified+unidentified contingency를 분리한다.
- 실적 프로젝트 back-test와 outlier detection을 구현한다.
- Monte Carlo로 P50/P80/P90을 산출하고 seed·분포·상관을 저장한다.
- Gate: 중복물량 0, 단위 불일치 0, 물량 추적률과 Q등급 공개.

P10 사업수지·금융
- 월별 land/construction/soft cost/tax/sales/rent/debt/equity cash flow를 구현한다.
- 실제 월별 잔액으로 이자·수수료·인출·상환 waterfall을 계산한다.
- Project/Equity IRR, NPV, MOIC, DSCR, LTV/LTC, break-even, residual land value를 구현한다.
- 복수 IRR·음수 잔액·covenant breach를 경고한다.
- 매출은 타입·층·향·시점, 임대는 vacancy/opex/cap rate를 지원한다.
- 시뮬레이션: 가격, 속도, 금리, 지연, 공사비, 세금분기, correlated downside.
- Gate: 회계항등과 월별 잔액 불변식 100%, 독립 spreadsheet fixture 대조.

P11 다목적 최적화
- hard constraint filter→surrogate search→정밀 재계산→Pareto→shortlist를 구현한다.
- profit, IRR, equity, risk, duration, efficiency를 목적함수로 지원한다.
- empirical/triangular distribution과 correlation matrix를 구현한다.
- Monte Carlo는 지표 신뢰구간 수렴 또는 max samples에서 종료한다.
- 최고수익/P80 방어/최소자본/최소규제위험/균형안을 반환한다.
- Gate: 동일 seed 재현, 단조성/metamorphic test, infeasible option 0.

P12 구조화 보고서
- AnalysisResult JSON을 Single Source of Truth로 삼는다.
- FACT/CALCULATION/ASSUMPTION/INTERPRETATION/RECOMMENDATION claim schema를 구현한다.
- FACT는 source, CALCULATION은 trace, ASSUMPTION은 approval 없으면 발행 차단한다.
- 표·차트·본문 숫자는 동일 JSON 렌더러를 사용한다.
- MD/HTML/PDF 또는 프로젝트 표준 포맷을 생성한다.
- Gate: 핵심 claim citation 100%, JSON-표-본문 수치 불일치 0.

P13 전문가 검토·승인
- Draft/MachineValidated/ExpertReviewed/Approved/Superseded 상태를 구현한다.
- Critical 2인, High 도메인 책임자 등 위험기반 승인 정책을 구현한다.
- input/rule/result/version diff와 source/trace drill-down을 제공한다.
- conditional approval에 condition, owner, deadline, invalidated output을 둔다.
- 승인 이벤트는 append-only audit log로 저장한다.
- Gate: 승인 없는 결과가 Approved/Published가 되는 경로 0.

P14 성장루프·운영
- CorrectionLog와 error taxonomy를 구현한다.
- 오류를 connector/parser/rule/calculation/geometry/product/cost/finance/report로 라우팅한다.
- 수정마다 재현 테스트를 먼저 추가한다.
- golden→stress→shadow→canary→progressive release→monitor→rollback workflow를 구현한다.
- 법규 사실은 fine-tuning보다 Rule/RAG 갱신을 우선한다.
- 학습 승격에는 전문가 승인, 근거, 개인정보 제거, 데이터 누출 검사를 요구한다.
- Gate: regression 또는 critical metric 저하 시 자동 배포 차단·롤백.

[P0~P14 정밀 자료·분석·계산·인계 사양]
아래 사양은 앞의 작업카드를 대체하지 않고 강화한다. 각 단계의 구현 PR은 해당 사양을 추적표에 매핑해야 한다.

P0 정밀사양 — 대상지 입력·필지 식별
필수 원본자료:
- 도로명/지번주소, PNU 또는 지도선택 geometry
- 분석기준일, 프로젝트 목적, 대상지 포함·제외 의사
- 사용자가 보유한 토지조서·매입현황이 있으면 원본파일
조건부 자료:
- 폐번지·분할·합병 이력, 산번지, 법정동/행정동 코드
- 부분편입선, 도로·구거·국공유지 후보
분석방식:
- 주소 표준화와 PNU 체크디지트/코드 유효성 검사
- 문자열 후보와 point-in-polygon 후보를 분리 계산
- 필지 history가 있으면 기준일 당시 식별자로 temporal resolve
- union 이전에 개별 geometry validity와 topology를 검사
계산:
- 후보점수 S=wa*address+wp*pnu+ws*spatial+wh*history
- site_area_gis=sum(included geometry)-overlap-exclusion
- source_area_delta=(gis_area-ledger_area)/ledger_area
- connectivity components, holes, slivers를 계산
차단조건:
- 기준일 미지정, CRS 미확정, 동일 PNU 중복, critical candidate 미승인
P0→P1/P2 인계:
- approved parcel list, temporal identity, geometry, area triplet(장부/GIS/계획), inclusion state, unresolved list
- P0_BUNDLE checksum과 G0 decision

P1 정밀사양 — 공부·인허가·공간·시장 원천수집
필수 원본자료군:
- 토지: 토지대장·임야대장·지적도·연속지적·토지이용계획
- 건축: 총괄표제부·표제부·층별개요·전유공용·부속지번·오수·주차·인허가
- 계획: 용도지역·지구·구역, 도시계획시설, 지구단위/정비/개발계획
- 도로: 도로명·도로구간·현황/계획폭·건축법상 도로 근거 후보
- 지형환경: DEM/등고, 재해·침수·산사태·환경·문화재 등 적용 후보
- 시장: 실거래 원문, 공시가격, 분양·임대 비교사례와 기준시점
분석방식:
- source별 connector와 schema를 분리하고 raw payload를 보존
- PNU/building management number/permit number를 별도 entity key로 해소
- 필드별 공식 정의·단위·nullable 의미를 data dictionary로 관리
- snapshot 간 change data capture와 갑작스러운 값 변화를 탐지
계산:
- completeness=valid required fields/required fields
- freshness decay는 자료유형별 허용기간으로 계산하되 stale 여부를 별도 boolean으로 둠
- conflict matrix는 동일 subject/predicate/time의 상이값을 생성
- duplicate probability와 entity resolution confidence를 계산
차단조건:
- 대지면적·경계·용도지역·접도 등 critical fact가 MISSING/CONFLICT인데 승인 없음
P1→P2/P3/P5 인계:
- SourceSnapshot registry, Fact Ledger, data dictionary, conflicts, freshness, coverage, official raw references

P2 정밀사양 — 개발대지·권리·접도
필수 원본자료:
- P0 필지번들, P1 토지·도로 facts
- 사용자 제공 권리·매입자료는 사실과 법적 확정을 구분
- 도시계획시설 편입선·도로경계·지목·소유형태 후보
분석방식:
- parcel adjacency는 단순 bbox가 아니라 실제 boundary intersection 길이로 판정
- 도로접면은 물리 접촉과 법적 도로성을 분리
- 소유·확보·사용승낙은 CONFIRMED/CLAIMED/UNKNOWN으로 분리
- critical parcel은 graph centrality+진입독점+envelope impact로 평가
계산:
- legal_site_area와 planning_site_area를 별도 계산
- frontage_length, number_of_components, compactness, access_dependency
- acquisition_ratio 외 critical_acquisition_ratio
- 필지 제외 전후 envelope proxy와 residual land value delta
시뮬레이션:
- N-1, 핵심필지 조합제외, 단계취득 지연, 도로사용승낙 실패
P2→P5/P7/P10 인계:
- SiteAssembly alternatives, legal/planning boundary, access candidates, acquisition risk, parcel dependency graph

P3 정밀사양 — 법규·계획·기술기준
필수 원본자료:
- 국가법령 현행/연혁/시행예정 본문·별표·부칙
- 광역/기초 자치법규 본문·별표·부칙
- 해당 필지 지구단위계획 결정조서·도면·시행지침
- 도시관리계획·정비계획·개발계획·건축선·높이·경관 관련 고시
조건부 원본:
- 주택건설·도시개발·정비·산업집적·교통·환경·재해·교육·문화재·소방·장애인·에너지 관련 기준
- 질의회신·심의사례는 참고등급과 비구속성을 표시
분석방식:
- 조문 parser가 항/호/목/별표행/각주/단서를 보존
- NLP 추출 후보와 승인 Rule을 별도 테이블로 저장
- applicability predicate는 정의조항의 용어와 연결
- spatial plan drawing의 범례·구역 geometry를 rule scope와 연결
계산:
- Applicable=jurisdiction∧effective_time∧use∧scale∧spatial_scope∧exceptions
- precedence는 authority, delegation, specificity, effective period를 trace
- 같은 결론의 중복규칙과 상충규칙을 graph로 검출
차단조건:
- hard rule에 원문·시행일·관할·공식·반올림·테스트·승인 중 하나라도 누락
P3→P6/P7/P8 인계:
- approved executable Rule Pack, source citations, applicability matrix, interpretation branches, unresolved legal questions

P4 정밀사양 — GIS·측량·DWG·현황
필수 원본자료:
- P0/P2 boundary, 공식 지적·건물 geometry
- 좌표계와 기준점이 있는 측량성과 또는 현황도
- DWG/DXF가 있으면 원본·xref·폰트·plot metadata 목록
- DEM/등고점, 도로중심·경계, 기존건축물·옹벽·전주·수목 등 주요 장애물
분석방식:
- 파일 내부 unit/INSUNITS, extents, 좌표크기, 알려진 기준점으로 CRS 후보평가
- layer classifier 결과는 confidence와 사용자 매핑을 보존
- TIN 생성 전 breakline·duplicate point·outlier를 처리
- 지적경계와 측량경계는 덮어쓰지 않고 두 surface를 보존
계산:
- similarity/affine transform, RMSE, max residual, directional bias
- slope, aspect, elevation range, cut/fill preliminary volume
- road longitudinal/cross slope, access sight proxy
- boundary uncertainty buffer별 developable area sensitivity
차단조건:
- 좌표계/단위 미확정, 허용잔차 초과, critical layer meaning 미확정
P4→P5/P7/P8/P9 인계:
- SurveyAlignedSite, terrain surface, feature catalog, transform matrix, accuracy budget, usable-layer decision

P5 정밀사양 — 통합 실사·CSM
필수 입력:
- G0~G4 PASS/승인된 번들만 수용
- 필지·원천·법규후보·측량/현황·시장 facts
분석방식:
- 동일 사실의 시간·공간·권위 충돌을 reconciliation policy로 처리
- 사실과 가정, 규칙과 권고, 물리제약과 법적제약을 분리
- Red Flag는 평균위험점수로 상쇄하지 않음
계산:
- risk exposure=P*Impact, detection priority=P*Impact*Difficulty
- data quality vector=min(source,coverage,rule,geometry,validation)
- dependency graph로 fact/rule/assumption 변경 영향범위 계산
결과물:
- 2D/3D CSM, Due Diligence, Red Flag, Assumption/Conflict/Question registers
P5→P6 이후 인계:
- immutable CSM baseline, approved assumptions, uncertainty budget, blocked branches, run configuration

P6 정밀사양 — 법규계산·인허가 판정
필수 입력:
- P3 approved Rule Pack, P5 CSM, 목적용도·규모 시나리오
법규 분석영역:
- 토지이용·행위허가·용도허용
- 대지면적·건폐율·용적률·높이·층수
- 건축선·접도·도로후퇴·대지안공지
- 일조·채광·인동·가로구역·경관
- 주차·차량·자전거·전기차 등 적용 규칙
- 피난·방화·소방활동·장애인 편의
- 교통/환경/재해/교육/경관/건축 심의·평가 대상
분석방식:
- 각 결과를 rule applicability DAG와 calculation DAG로 분리
- 정의가 다른 면적(base/site/GFA/FAR-counted/excluded)을 혼용하지 않음
- 복합용도는 용도별 계산 후 법규가 정한 시점에 합산·반올림
- 특례는 기본안과 분리하고 충족해야 할 반대급부를 constraint로 추가
계산:
- BCR=building_footprint/legal_site_area*100
- FAR=far_counted_area/legal_site_area*100
- parking=round_policy(sum(use_formula_i))
- headroom=planning_target-current_plan
- interpretation branch별 limit과 조건을 병렬 산출
검증:
- independent calculator, threshold±epsilon, dimensional analysis, expert sheet comparison
P6→P7/P8/P12 인계:
- RegulatoryConstraintSet, legal maximum/target, calculation trace, permit/assessment checklist, unresolved interpretation

P7 정밀사양 — 3D 법정·물리 Envelope
필수 입력:
- CSM boundary/terrain/roads, approved constraint set, source accuracy
분석방식:
- 각 constraint를 독립 geometry로 생성하고 순서·교집합 결과를 기록
- 지상/지하, 필지별 sub-zone, 동별 인동 constraint를 분리
- voxel approximation과 exact solid 결과의 오차를 계량
계산:
- offsets, half-space intersections, solar/height planes, boolean solids
- floor_elevation별 slice area/centroid/connectivity
- constraint contribution=volume_before-volume_after
- conservative/base/conditional envelope를 별도 생성
검증:
- point/face sampling, solid validity, volume-vs-slice integration, round-trip, tolerance sensitivity
P7→P8/P9/P12 인계:
- exact solids, floor slices, constraint attribution, uncertainty envelopes, no-build/access zones

P8 정밀사양 — 상품·배치·BIM 초안
필수 원본/기준:
- P7 Envelope, P6 code constraints, 시장 프로그램, 주차·코어·구조·설비 template
- 타입별 치수·면적·효율·층고·구조 span의 승인범위
분석방식:
- 먼저 program demand를 산정하고 공간수용성 검증 후 geometry 생성
- 코어/피난/주차/구조를 후처리로 끼워 넣지 않고 동시에 constraint로 사용
- 객체 property에 source assumption과 rule links를 저장
계산:
- GFA reconciliation, net-to-gross, saleable efficiency
- unit mix integer allocation, floor stacking
- parking fit, ramp length/grade/transition, swept path
- elevator handling capacity와 peak waiting(지원범위 내)
- option score와 Pareto dominance
물리검증:
- 충돌·최소치수·접근·피난·주차·구조그리드·층고·Envelope 침범
P8→P9/P10/P12 인계:
- DesignOption bundle, IFC, space/element schedule, quantities basis, areas, compliance results, option rationale

P9 정밀사양 — BIM 물량·공사비
필수 원본자료:
- 승인 DesignOption/IFC와 객체분류
- 지역·기준일별 단가, 실적내역, 물가지수, 공법·마감·지반 가정
- 공사범위·제외·발주방식·세금·간접비 정책
분석방식:
- 객체 직접물량(Q1)과 모델 미표현 추정(Q2~Q4)을 분리
- 물량산출 규칙에 공제·겹침·할증·손율을 명시
- 단가의 포함범위가 물량 scope와 일치하는지 검사
계산:
- quantity*unit_rate*region*time*complexity
- direct+indirect+temporary+overhead+tax+contingency
- identified risk EMV와 unidentified uncertainty 분포
- actual back-test APE/MAPE/bias를 Q등급·공종별 산출
검증:
- object schedule 대조, 상하위 합계, 단위차원, benchmark/outlier, P50/P80 수렴
P9→P10/P11/P12 인계:
- monthly cost curve, cost breakdown, P10/P50/P80/P90, quantity lineage, exclusions, VE alternatives

P10 정밀사양 — 매출·금융·세금·수지
필수 원본자료:
- 토지계약·취득일정·부대비, P9 원가·공정
- 상품별 가격·계약조건·흡수율, 임대·공실·운영비 자료
- 대출 term sheet, 금리·수수료·인출/상환조건·covenant
- 세율·과세표준·부담금의 기준일과 적용근거
분석방식:
- 명목/실질, 부가세 포함/제외, 법인/프로젝트 관점을 혼용하지 않음
- 분양수입을 계약일 매출과 실제 현금유입으로 분리
- finance waterfall과 공정률·선행조건을 연결
계산:
- 월별 cash flow/balance, 실제 잔액이자, capitalized interest
- NPV, monthly IRR annualization, MOIC, DSCR, LTV/LTC
- break-even price/sales rate/cost, residual land value
- 세후/세전, project/equity 결과를 별도 산출
검증:
- opening+inflow-outflow=closing, sources=uses, debt roll-forward, tax timing
- 독립 spreadsheet fixture와 월별 셀 대조
P10→P11/P12 인계:
- deterministic cashflow, financing events, KPI, covenant breaches, assumption sensitivities

P11 정밀사양 — 시나리오·확률·최적화
필수 입력:
- feasible design options, validated cost/finance model, 승인된 변수분포와 상관
분석방식:
- infeasible 후보 제거 후 surrogate, 정밀 재계산
- 과거데이터 부족 시 triangular 분포의 근거와 전문가를 기록
- correlation은 경제적 인과와 표본으로 검토
계산:
- Latin Hypercube/Monte Carlo 선택근거
- P10/P50/P80/P90, probability(NPV<0), probability(covenant breach)
- Sobol 또는 적절한 sensitivity, tornado
- Pareto frontier와 dominance reason
검증:
- seed 재현, 수렴, 분포 sampling, monotonic/metamorphic, extreme-value test
P11→P12/P13 인계:
- shortlist 5종, 확률분포, 민감도, trade-off, 선택하지 않은 대안과 이유

P12 정밀사양 — 실무 보고서 생성
필수 입력:
- P0~P11 promoted bundles와 claim-ready AnalysisResult
분석방식:
- 보고서 template가 숫자·표·차트를 직접 렌더하고 LLM은 승인된 facts로 설명만 작성
- 모든 결론은 FACT/CALCULATION/ASSUMPTION/INTERPRETATION/RECOMMENDATION 유형
- 지도·도면·BIM screenshot은 run_id와 좌표·범례를 포함
검증:
- claim-evidence graph completeness, 숫자 exact match, citation existence/effective date
- PDF/HTML/MD 실제 렌더, 표 잘림·폰트·이미지·링크 검수
- 금지어: '확정', '보장', '완벽'을 승인상태 없이 사용하지 않음
P12→P13 인계:
- Decision Brief, Due Diligence, Regulatory Matrix, Design/BIM, Cost/Finance, Risk/Assumption, Evidence Appendix

P13 정밀사양 — 전문가 검토·승인
필수 입력:
- machine-validated report bundle, unresolved register, risk-ranked claims
분석방식:
- reviewer가 원문/규칙/계산/geometry/cost cell까지 drill-down
- 동일 사람이 critical 규칙 작성과 최종 승인을 모두 수행하지 않도록 역할분리
- 변경 후 영향결과를 자동 invalidation하고 재승인 요구
계산/지표:
- reviewer agreement, correction rate, severity-weighted defect rate, review lead time
P13→P14/발행 인계:
- signed decision, conditions, expiry, approved scope, superseded versions, publication hash

P14 정밀사양 — 성장루프·교정·회귀·운영
수집자료:
- 실행로그, validation failures, 사용자 수정, 전문가 반려, 실제 인허가/견적/분양 결과
분석방식:
- prediction vs actual을 단계별로 분해해 root cause attribution
- 데이터·규칙·공식·기하·단가·분포·프롬프트 오류를 분리
- 실적자료의 temporal leakage와 프로젝트 중복을 차단
계산:
- false-pass/false-fail, calibration error, APE/MAPE/bias, drift PSI/KS 등 적절한 지표
- 변경 전후 paired benchmark, confidence interval, severity weighted score
- 성능 향상과 다른 관할/유형의 회귀를 함께 평가
인계:
- approved correction dataset, new regression test, candidate version, shadow/canary evidence, rollout/rollback decision

[실무전문가 작업패키지 Professional Work Package]
각 분석단계는 '분석 완료'라는 텍스트가 아니라 전문가가 실제 검토·수정·승인할 수 있는 Work Package를 생성한다.
Work Package 필수 구성:
1. Cover Sheet: 프로젝트, 기준일, 대상범위, 작성/검토/승인자, 버전, 상태.
2. Basis of Analysis: 사용 원본, 적용법규, 기술기준, 가정, 제외범위.
3. Calculation Book: 입력·공식·중간값·결과·단위·반올림·검산.
4. Drawings/Models: 좌표·축척·범례·부호·revision cloud·object ID.
5. Schedules: 필지·면적·주차·세대·물량·원가·현금흐름 표.
6. Compliance Matrix: 요구사항, 적용성, 계획값, 기준값, 여유, 결과, 근거.
7. Issues/RFI: 미확인, 충돌, 질의, 책임자, 기한, 영향, 상태.
8. Alternatives: 검토대안, 배제사유, 비용·일정·위험 delta.
9. Validation: 독립검산, 교차분야검토, 테스트, 오차·불확실성.
10. Handoff Certificate: 다음 단계 허용범위, 조건, 만료, checksum.

[실무 역할과 책임]
역할을 단순 사용자 권한이 아니라 결과물 책임으로 구현한다.
- Data Steward: 원본·기준일·메타데이터·라이선스·품질.
- Cadastral/GIS Specialist: 필지·좌표·지형·도로 공간정합.
- Development Planner: 대상지 구성·상품·인허가전략·사업가정.
- Architect: 법규·배치·면적·코어·피난·BIM 검토.
- Civil/Geotechnical: 경사·토공·흙막이·기초·배수·진입 검토.
- Structural: 구조시스템·span·하중·전이·구조성 검토.
- MEP/Fire: 설비공간·용량·샤프트·방재·소방 활동 검토.
- Traffic/Parking: 접속·램프·회전·주차·대기행렬 검토.
- Cost Engineer: 물량·공법·단가·예비비·VE 검토.
- Financial Modeler: 현금흐름·금융·세금·민감도 검토.
- Regulatory Reviewer: 규칙 적용·해석·질의회신 검토.
- Independent Checker: 작성자와 독립된 재계산·도면검토.
- Approver: 조건과 책임범위를 명시해 발행 승인.
Critical 항목은 Author와 Independent Checker가 달라야 하고 self-approval을 기술적으로 차단한다.

[설계·분석 성숙도]
모든 결과에는 maturity level을 부여한다.
- M0 Screening: 공개자료·개략가정, 토지매입 전 후보비교.
- M1 Due Diligence: 원본대조·핵심법규·경계/접도 검토.
- M2 Feasibility: 검증 CSM·Envelope·복수 배치·개산수지.
- M3 Concept: 조정된 코어/주차/구조/설비·BIM·P50/P80 원가.
- M4 Pre-Application: 전문가 교차검토·인허가 사전협의 패키지.
- M5 Approved Baseline: 공식 회신·승인조건 반영, 발행 승인.
상위 maturity 결과를 하위 자료만으로 생성하지 않는다. 각 레벨은 required evidence matrix를 가진다.

[도면·모델 실물 완성조건]
도면 또는 모델 파일 생성만으로 완료 처리하지 않는다.
- title block: 프로젝트/도면명/번호/축척/작성·검토/날짜/revision.
- 좌표·북향·기준점·표고 datum·CRS·단위.
- 경계 유형별 선종과 범례: 법적/측량/계획/불확실.
- 치수와 면적은 모델에서 연동되며 수기 텍스트 값 금지.
- 모든 주요 공간·부재·constraint에 stable ID.
- 외부참조·누락폰트·proxy object·broken link 검사.
- IFC model checker, clash rule, property completeness, duplicate GUID 검사.
- PDF/이미지 출력은 축척·가독성·클리핑·범례·페이지 누락 검사.
- DWG/IFC/PDF/면적표 간 revision과 checksum 일치.

[전문가 계산서 완성조건]
- 표지·목차·개정이력·계산목적·범위·기준.
- 입력자료표와 원천 ID.
- 기호·단위·정의.
- 적용식의 근거와 적용조건.
- 계산순서와 중간값.
- sanity check와 독립검산.
- 민감입력과 불확실성.
- 결과·한계·조건·서명.
- spreadsheet가 있으면 셀 잠금·입력/공식/출력 색상·순환참조·외부링크 검사.
- 코드 계산과 spreadsheet 결과의 golden cell 대조.

[분야별 정밀 실무분석]

A. 토지·권리·도시계획 작업패키지
수집:
- 토지/임야대장, 지적·경계, 소유·지분·권리자료(제공범위), 토지이용계획, 도시계획 결정조서·도면, 지구단위·정비·개발계획, 도로·시설 편입.
분석:
- 기준일 당시 필지 genealogy, 합필·분할 선행조건, 대지성립, 맹지·접도, 도시계획시설 저촉, 단계취득 가능성.
- 권리정보는 자동 법적 확정하지 않고 전문가 확인대상과 영향만 구조화.
계산:
- 취득면적/확보율/핵심필지 영향, 제척잔여지, 편입면적, 경계별 가용면적, 최대매입허용가와 option value.
산출:
- 토지조서, 권리·확보 matrix, 필지계보도, 저촉도, 합필/제척안, 취득우선순위와 RFI.

B. 도로·접근·교통 작업패키지
수집:
- 법정 도로근거, 도로대장/구간, 현황·계획폭, 종·횡단, 교차로, 보도·버스·교통량, 차량종류, 관련 심의기준.
분석:
- 법적 접도와 물리적 진입을 분리; 출입구 설치 가능구간, 시거, 교차로 이격, 보행·차량 충돌, 서비스/소방 동선.
계산:
- frontage, swept path, 최소 회전반경, 램프 길이/구배/transition, peak arrival/service rate, queue percentile.
- M/M/c 등 단순 대기모형은 가정 적합성을 검토하고 필요 시 discrete-event simulation.
산출:
- 접도판정표, 출입구 대안도, 회전궤적도, 램프 종단, 교통/대기 결과, 위험·협의사항.

C. 지형·토목·지반·배수 작업패키지
수집:
- 측량점·등고·DEM, 지반조사/시추(있을 때), 지하수, 인접구조물, 매설물, 침수·재해, 강우·배수체계.
분석:
- 기존/계획표면, 경사구간, 흙막이 여건, 굴착깊이, 토공균형, 우수흐름, 반출입 조건.
계산:
- TIN 기반 절·성토, 평균단면법 교차검산, 사면/옹벽 개략, 굴착면적×깊이, 배수 유역·유출량은 적용 공식과 지역계수 명시.
- 지반자료가 없으면 기초·흙막이 공법을 확정하지 않고 범위·조사계획·P80 allowance를 제시.
산출:
- 지형분석도, 토공량표, 굴착·흙막이 개략안, 배수개념도, 지반조사 요구서, 토목비 위험범위.

D. 건축법규·배치·면적 작업패키지
수집:
- 승인 Rule Pack, CSM/Envelope, 프로그램, 유형별 면적정의, 심의기준, 사용자 요구.
분석:
- 용도허용, 건폐/용적, 높이/공지/일조, 피난/방화, 장애인, 주차, 친환경·에너지 등 적용 matrix.
- 계획값은 legal maximum이 아니라 planning target과 여유율로 관리.
계산:
- 층별 footprint, GFA/FAR-counted/excluded, 전용/공용/분양효율, 세대/호실 정수배치, 코어·피난거리, 공간수용성.
산출:
- 법규검토서, 건축개요, 배치/평면/단면 개략, 층별면적표, 코어·피난 검토, 대안비교.

E. 구조 개념 작업패키지
수집:
- 용도별 하중범주, grid/span, 층고, 지하/전이, 재료·공법, 지반 가정, 내진·구조 관련 기준 후보.
분석:
- 구조시스템 후보, 횡력저항, 전이구조, 장스팬·캔틸레버, 불규칙성, 주차 grid와 상부 grid 정합.
계산:
- 기획단계 preliminary sizing은 승인된 경험식·범위로만 수행하고 실시구조계산으로 표시하지 않음.
- span/depth, column tributary area, 개략하중, 구조체 물량계수와 민감도.
산출:
- 구조개념도, grid/전이/불규칙 위험, 개략부재 범위, 구조비 가정, 구조기술자 확인목록.

F. 기계·전기·통신·소방 작업패키지
수집:
- 용도·면적·인원, 설비용량 기준, 인입조건, 기계/전기실 요구, 샤프트, 소방·피난 기준, 친환경·에너지 목표.
분석:
- 부하·용량의 기획수준 추정, 주경로, 장비반입·유지관리, 층고·천장·샤프트·코어 간섭.
계산:
- 승인된 단위부하/동시사용/여유율을 변수화; 근거 없는 고정계수 금지.
- 급수·오수·전력·냉난방·환기·소방수요를 시설유형별 범위로 산출.
산출:
- 설비 Basis of Design, 공간·샤프트 schedule, 계통개념, 용량범위, 인입·협의·추가조사 목록.

G. 주차·물류·수직동선 작업패키지
수집:
- 법정대수, 상품목표, 차량구성, 물류차량, EV/장애인/경형 기준, EV/엘리베이터 수요.
분석:
- 단순 주차대수뿐 아니라 실제 배치가능성, 기둥·벽·설비와 충돌, 동선분리, 이용피크.
계산:
- stall count by type, parking efficiency, circulation loss, swept path, ramp capacity.
- 엘리베이터는 인구·용도·피크수요·정원·속도·정지횟수 가정을 보존하여 handling/waiting 범위 산출.
산출:
- 주차대수 계산서, 배치검증도, 램프·차량동선, 물류·이사·소방 동선, 수직동선 개략.

H. 적산·공정·조달 작업패키지
수집:
- BIM/도면 성숙도, WBS/CBS, 실적단가·견적·지수, 공법, 공기, 조달·계약 조건.
분석:
- quantity completeness, scope gap/overlap, 장기납기·가격변동, 공정 critical path, 가설·토공·지하 위험.
계산:
- Q1~Q4 물량, 직접/간접/가설/일반관리/세금/예비비, escalation, cash curve.
- 일정은 활동·선후행·calendar·resource assumption을 기록하고 PERT/Monte Carlo는 근거가 있을 때 적용.
산출:
- 개산내역, 산출서, 공정표, 조달위험, P50/P80, VE register, 미포함/중복 scope.

I. 시장·분양·운영 작업패키지
수집:
- 거래원문, 분양·임대사례, 공급·입주, 인구·사업체, 상권·수요, 운영비·공실·cap rate.
분석:
- 비교사례 선택/배제 기준, 시점·입지·규모·상품·층향·상태 보정, 흡수율과 경쟁공급.
계산:
- 조정단가와 범위, absorption curve, vacancy/NOI, scenario별 revenue timing.
- 표본이 부족하면 정밀 통계처럼 포장하지 않고 범위와 전문가 판단을 표시.
산출:
- 비교사례표, 보정근거, 상품별 가격범위, 분양/임대 속도, 운영가정, 하방위험.

J. 금융·세무·투자 작업패키지
수집:
- 토지·공사·간접비 일정, 매출/임대, term sheet, 세율·부담금·수수료, 투자 waterfall.
분석:
- sources/uses, 자금투입 우선순위, 이자자본화, covenant, 세전/세후, project/equity 관점.
계산:
- 월별 잔액, interest, NPV/IRR/MOIC/DSCR/LTV/LTC, break-even, residual value, downside probability.
산출:
- 수지표, 월별 cash flow, 자금조달·상환표, 민감도/확률, covenant breach, 투자위원회 요약.

[다분야 인터페이스·간섭검토]
각 분야 산출물은 Interface Register로 연결한다.
필수 interface 예시:
- 대지경계 변경 → 법규/Envelope/배치/토공/수지 재실행.
- 도로·진입 변경 → 램프/주차/상가전면/소방/토목/비용 재실행.
- 구조 grid 변경 → 주차/세대평면/샤프트/물량/공사비 재실행.
- 층고 변경 → 높이/층수/일조/설비/외피/비용 재실행.
- 코어 변경 → 피난/EV/전용률/구조/설비/분양면적 재실행.
- 설비실·샤프트 증가 → 면적/주차/층고/공사비/운영비 재실행.
- 공기 지연 → escalation/금융비/분양/세금/IRR 재실행.
Interface Register 필드: issue_id, producer, consumer, input/output, version, tolerance, due_date, status, affected_results.

[Clash·Consistency 검토]
- spatial clash: hard/soft/clearance, discipline pair, severity.
- data clash: 같은 ID의 상이 속성·면적·단위·revision.
- rule clash: 동일 대상에 상충하는 기준·해석.
- schedule clash: 설계·인허가·조달·시공 선후행 불일치.
- financial clash: 공정·지급·대출 인출시점 불일치.
충돌은 단순 건수로 닫지 않고 위치/영향/책임/해결버전/재검증 증거를 남긴다.

[인허가 사전협의·질의회신 루프]
자동분석이 해석을 확정할 수 없는 항목은 RFI/Application Question으로 승격한다.
필수필드:
- question_id, 대상기관/부서, 사실관계, 대상필지·도면, 정확한 질의, 관련조문·별표, 시스템해석안, 대안, 비용·일정영향, 제출/회신일, 회신원문, 유효범위, reviewer.
워크플로우:
1. 해석충돌·심의조건 탐지.
2. 사실관계·도면·조문이 포함된 질의서 초안 생성.
3. 전문가 검토 후 외부 제출은 사용자 승인 시에만 수행.
4. 회신 원문을 SourceSnapshot으로 보존.
5. 프로젝트 한정 decision인지 일반 Rule 후보인지 분류.
6. CSM/Rule/Envelope/수지 영향분석과 재실행.
7. 보고서에 회신조건과 잔여불확실성 표시.

[독립검산·Checker Workflow]
Critical/High 결과는 작성 엔진과 다른 경로로 검산한다.
- 규제: Rule Engine vs 독립 reference calculator/전문가 계산서.
- 면적: BIM 공간합 vs geometry polygon 합 vs 보고서 표.
- Envelope: solid sample vs analytic constraint equation.
- 물량: BIM extraction vs sample manual takeoff.
- 원가: 상세합계 vs parametric benchmark.
- 수지: code engine vs locked golden spreadsheet.
- 보고서: claim graph vs source/calc trace.
Checker는 결과를 보며 공식을 맞추지 않고 입력·기준으로 독립 계산 후 비교한다.

[실무 결과물 승인등급]
- INTERNAL DRAFT: 미검증, 외부사용 금지.
- COORDINATION: 분야간 조정용, 의사결정 제한.
- REVIEWED: 작성자 검토 완료, 독립검산 일부 완료.
- EXPERT CHECKED: 해당 분야 독립검산 완료.
- CONDITIONAL ISSUE: 조건을 명시한 제한 발행.
- APPROVED BASELINE: 승인범위 내 기준선.
- SUPERSEDED: 신규버전으로 폐기, 참조만 가능.
모든 PDF/도면/표/API response에 등급 watermark/metadata를 표시한다.

[실무 완성도 검증지표]
단순 테스트 커버리지 외에 다음을 계산한다.
- Source Completeness: required 원본의 유효 확보율.
- Traceability: critical output의 원본 역추적률.
- Rule Coverage: 적용 hard rule의 승인·테스트율.
- Calculation Reconciliation: 독립검산 일치율과 최대 delta.
- Spatial Integrity: invalid geometry/hard clash/clearance failure.
- Interdisciplinary Closure: critical interface issue 미해결수.
- Estimate Maturity: Q1~Q4 구성과 실적 back-test 오차.
- Financial Integrity: accounting invariant/covenant simulation 통과.
- Professional Review: 독립검산·승인 완료율.
- Outcome Calibration: 예측 대비 실제 인허가/원가/일정/매출 편차.
Critical 결함은 가중평균으로 상쇄하지 않는다.

[결과물 재작업 루프]
1. Reviewer가 도면·계산·근거의 특정 객체/셀/claim에 issue 생성.
2. issue를 source/rule/calculation/geometry/interface/assumption 오류로 분류.
3. dependency graph로 영향 결과와 소비단계를 invalidation.
4. 원본 수정 금지; 새 revision에서 수정.
5. 관련 단계부터 결정론적으로 재실행.
6. delta report와 side effect test 생성.
7. Checker가 issue와 연관된 결과뿐 아니라 연결 interface를 재검토.
8. 모든 조건이 닫혀야 새 baseline 승격.

[v4.0 공통 실무생산 프로토콜 — DoR에서 Issue까지]
모든 P단계와 전문분야 작업패키지는 아래 상태머신을 동일하게 구현한다.
INTAKE → READY_CHECK → BASIS_FREEZE → PRODUCE → SELF_CHECK → INDEPENDENT_CHECK → COORDINATE → ISSUE → ACCEPT → BASELINE → SUPERSEDE.

Definition of Ready(DoR):
- 작업 목적·의사결정 질문·대상 공간·기준일·성숙도·사용목적이 식별됨.
- Required Data Matrix의 critical 자료가 VALID이거나, 결측을 허용한 승인조건이 있음.
- 적용 Rule Pack·기술기준·가정집합·상위 bundle의 버전과 checksum이 고정됨.
- 작성자·검토자·승인자, 검토기한, 허용오차, 산출물 포맷이 배정됨.
- 이전 단계의 BLOCKED, 만료, superseded bundle을 소비하지 않음.
DoR 미충족 작업은 계산을 시작하지 않고 `NOT_READY`와 해소행동을 반환한다.

Basis Freeze:
- Basis Register에 사실, 규칙, 가정, 설계결정, 제외범위, 미확정 RFI를 구분한다.
- freeze_id 이후 입력변경은 조용히 덮어쓰지 않고 Change Request와 영향분석을 생성한다.
- 동일 작업패키지의 도면·계산서·표·모델은 동일 freeze_id를 사용한다.

Definition of Done(DoD):
- 계약된 모든 실물 파일이 열리고 schema/render/model check를 통과함.
- 산출수치, 도면치수, 모델속성, 보고서 주장이 동일 SSOT revision과 일치함.
- critical 계산 100% 및 위험기반 표본이 독립검산됨.
- 모든 분야 interface가 ACCEPTED 또는 영향이 명시된 CONDITIONALLY_ACCEPTED임.
- 미해결 사항이 외부사용 제한과 함께 Issue/RFI Register에 노출됨.
- 작성·검토·승인 서명, 발행목적, 유효기간, checksum이 존재함.
- 다음 단계가 실제 bundle을 소비하는 contract test가 성공함.

Issue Package:
- issue_id, origin_object, 발견방법, severity, 재현절차, 기대/실제 결과, 원인분류.
- 직접 영향과 dependency graph의 간접 영향, 비용·일정·인허가 영향.
- owner, due_date, correction revision, verification evidence, closure approver.
- Critical/High는 단순 메모·위험수용으로 닫지 않고 승인된 예외 또는 검증된 수정이 필요함.

[업무분해구조 WBS와 산출물 사전]
각 P단계는 Domain → Work Package → Task → Check → Artifact → Claim으로 분해한다.
각 Task 필수필드:
- task_id, requirement_id, responsible_role, prerequisite_task_ids, required_inputs.
- method_id, formula_or_rule_ids, software/tool version, expected_artifacts.
- acceptance_criteria, tolerance, review_sample_rule, failure_action, evidence_path.
Artifact Dictionary에는 artifact_id, format, schema/template, source_of_truth, producer, consumer,
maturity, confidentiality, retention, issue_status, revision, checksum을 둔다.
Task가 산출물·검증·소비단계와 연결되지 않으면 `ORPHAN_TASK`로 차단한다.

[증거수준과 주장등급]
모든 주요 결론은 다음 Evidence Level 중 하나를 갖는다.
- E0 UNVERIFIED: 출처·계산 없음. 외부발행 금지.
- E1 INDICATIVE: 단일 참고원천 또는 합성자료. Screening 전용.
- E2 CORROBORATED: 독립원천 대조 또는 검증된 계산. Feasibility 사용 가능.
- E3 PROFESSIONALLY CHECKED: 적격 전문가 독립검산과 분야정합 완료.
- E4 AUTHORITY/AS-BUILT CONFIRMED: 공식 회신·승인·검측·준공/실적 증거로 확인.
발행물의 Claim에는 `claim_id, evidence_level, valid_scope, valid_date, uncertainty, prohibited_use`를 표시한다.
M0/M1 산출물을 E3/E4처럼 표현하거나 예측값을 확정값으로 서술하면 발행을 차단한다.

[검토계획·표본추출·허용오차]
Review Plan을 결과를 보기 전에 고정한다.
- Critical: 전수검토+독립경로 재계산+경계조건 시험.
- High: 전수 규칙검토, 계산은 위험기반 표본과 최대/최소/이상치 포함.
- Medium: 층화표본; 용도·층·구역·물량등급·단가출처별 최소 표본.
- Low: 자동검사+무작위 표본.
표본은 편한 항목만 고르지 않고 seed와 모집단·선정논리를 저장한다.
Tolerance Register는 법정한계, 모델수치오차, 측량정확도, 공사허용오차, 보고서 표시반올림을 분리한다.
서로 다른 허용오차를 합산해 hard constraint를 완화하지 않는다.

[변경·형상·기준선 통제]
Change Request 필수필드:
- change_id, trigger, before/after, reason, requester, affected source/rule/assumption/object.
- direct/indirect affected bundles, safety/legal/cost/schedule/revenue impact.
- 재계산 범위, 재검토 역할, 승인, 시행시점, rollback, superseded revisions.
변경영향 행렬 최소 규칙:
- 법규/조례 개정 → 적용성·Envelope·배치·주차·원가·수지·보고서.
- 경계/표고/도로 변경 → 토공·접도·배치·일조·주차·소방·공사비.
- 상품/세대수 변경 → 면적·코어·피난·설비·주차·매출·공정.
- 구조/공법 변경 → 층고·물량·MEP·공기·원가·탄소·조달.
- 단가/금리/세율/분양속도 변경 → 원가·자금조달·covenant·IRR.
부분 재실행은 dependency coverage test로 누락 노드 0을 증명해야 한다.

[인허가 제출패키지·보완관리]
Pre-Application/Submission Package는 다음 실물을 생성한다.
- 제출목록, 신청/협의 대상, 근거법령, 요구서식, 도면목록, 계산서목록, 첨부증빙.
- Authority Compliance Matrix: 요구사항↔도면/계산/설명 위치↔revision.
- Submission Freeze Manifest: 제출된 모든 파일의 hash와 발행시각.
- 질문·협의·조건·심의의견·보완요구·회신 원문과 처리상태.
보완 워크플로우:
1. 보완요구를 원문 단위로 분해하고 requirement_id를 부여한다.
2. 법적 의무, 권고, 사실확인, 설계변경, 추가자료 요구를 분류한다.
3. 담당분야·기한·영향산출물·재제출 항목을 배정한다.
4. 수정 전후 redline과 response matrix를 생성한다.
5. 관련 계산·도면·수지의 연쇄 재검증 후 제출 bundle을 새로 freeze한다.
6. 미반영 항목은 사유·위험·승인자를 명시하며 묵시적으로 닫지 않는다.

[설계검토·시공성·조달성·운영성]
M3 이상은 분야정합 외에 다음 review를 수행한다.
- Constructability: 작업공간, 장비접근, 양중, 굴착단계, 임시구조, 시공순서, 공기민감도.
- Maintainability: 점검·교체공간, 접근경로, shutdown zone, 예비품, 수명주기.
- Procurement: 장기납기, 단일공급, 승인자재, 대체품 동등성, 가격·환율·물류위험.
- Commissionability: 시험·시운전 point, 계측, 성능기준, 인수시험과 책임경계.
- Safety-by-design: 시공·운영 위험원, 제거/저감 조치, 잔여위험 인계.
각 review는 finding → 설계대안 → 비용/일정/성능 delta → 결정 → 검증의 폐루프를 가진다.

[공정·원가 통합통제 5D]
WBS, CBS, BIM object, 계약 package, 일정 activity, 기성항목을 공통 coding으로 연결한다.
필수 계산·검증:
- CPM: ES/EF/LS/LF/Total Float, critical/near-critical path와 calendar.
- Earned Value: PV, EV, AC, SV=EV-PV, CV=EV-AC, SPI=EV/PV, CPI=EV/AC.
- EAC는 단일식으로 확정하지 않고 `BAC/CPI`, `AC+(BAC-EV)`, `AC+(BAC-EV)/(CPI×SPI)`의 적용조건을 표시한다.
- 물가변동·설계변경·클레임·예비비 drawdown을 원인별로 분리한다.
- 공정 진척과 청구금액은 물량·검측·사진/모델·시험성적·승인증거에 연결한다.
일정의 낙관적 percent complete와 비용지출만으로 기성을 인정하지 않는다.

[감리연동·기성검증·변경계약]
시공단계가 적용범위에 포함되면 다음을 P14 운영 vertical로 구현한다.
- Inspection/Test Plan(ITP): hold/witness/review point, 기준, 표본, 결과, NCR 연결.
- Submittal/RFI/Shop Drawing/Method Statement 등록부와 승인상태.
- Daily/weekly progress, 설치수량, 검사합격수량, 지급대상수량을 분리.
- 기성 = min(계약수량, 현장확인 설치수량, 합격수량) × 승인단가를 기본으로 하되 계약조건을 Rule화.
- 선급금·유보금·자재선급·물가변동·공제·부가세·누계/금회/잔여를 재계산한다.
- 변경지시는 예산·공정·설계기준선 영향승인 전 본계약 기성에 혼입하지 않는다.
- NCR/CAR 미종결, 시험불합격, 승인도면 불일치는 지급보류 규칙과 연결한다.
산출: 기성조서, 검측근거, 사진/객체 증거, 변경계약대장, 예상최종원가, 공기영향, 감사로그.

[준공·인수·운영 인계]
Closeout Bundle 필수 구성:
- approved/as-built 도면·IFC, 자산등록부, O&M, 보증, 시험·시운전, 교육, 예비품.
- 인허가 조건 이행표, 미결 punch/NCR, 준공검사·사용승인 증거.
- 설계수량↔시공수량↔정산수량 delta와 원인.
- 예상↔실적 공사비·공기·성능·분양/운영 결과 calibration dataset.
- 문서별 소유자·보존기간·접근등급·후속조치.
As-built는 설계 최종본의 파일명 변경이 아니라 현장검측·승인증거와 연결된 별도 기준선이어야 한다.

[다층·다각도 시뮬레이션 프레임]
시뮬레이션은 한 번의 민감도표가 아니라 아래 층을 조합한다.
L0 Deterministic: 공식·기하·회계 불변식과 경계값.
L1 Data Quality: 결측, stale, 충돌, schema drift, CRS/단위 오류, 잘못된 entity join.
L2 Regulatory: 시행일, 관할, 용도분류, 예외, 보수/기준/공격 해석, 보완요구.
L3 Physical Design: 경계·표고·지반·코어·주차·구조·MEP·소방 간섭과 시공순서.
L4 Commercial/Financial: 가격·흡수율·공사비·금리·세금·공기·조달 상관충격.
L5 Delivery/Operation: API장애, 인력검토 지연, 승인반려, 공급망, 시공불량, 기성분쟁.
L6 Adversarial: 출처 없는 수치, 조문 오인용, 승인우회, 데이터 오염, 프롬프트 주입, 중복계상.
각 시나리오는 hypothesis, frozen inputs, perturbation, oracle/invariant, expected propagation,
observed result, failure classification, correction, regression test를 가진다.

[시나리오 설계법]
- 단일변수: 각 핵심변수 ±경계와 단조성 확인.
- 쌍대/교호작용: 경계×표고, 공기×금리, 가격×흡수율, grid×주차 등.
- 복합 스트레스: 상관구조를 보존한 하방·회복·꼬리위험.
- 사건트리: 필지실패→진입변경→지하증가→공기/비용→금융약정 위반.
- 결함주입: connector, parser, rule, geometry kernel, report renderer 장애.
- 역산: 목표 IRR/분양가/원가/공기에서 허용 가능한 입력경계 탐색.
- 역사적 back-test: 분석기준일 이후 정보가 입력에 섞이지 않도록 temporal cutoff.
- 전문가 red-team: 각 분야가 타 분야의 숨은 가정과 불가능한 인계를 공격적으로 검토.

[시뮬레이션 오라클]
모든 시뮬레이션은 예상 숫자를 임의 작성하지 않고 다음 중 하나의 oracle을 명시한다.
- closed-form/independent calculator, approved spreadsheet, golden project.
- 물리·기하·회계 invariant, 법규 hard constraint, 전문가 판정.
- metamorphic relation: 면적 감소 시 허용 연면적이 근거 없이 증가하지 않음 등.
정답 oracle이 없으면 탐색시험으로 분류하며 PASS 정확도 주장에 포함하지 않는다.

[성장루프 결함예산과 정지조건]
반복 횟수나 평균점수만으로 완료하지 않는다.
- Severity S0: 생명안전·법규 false-pass·중대한 재무오류·승인우회. 허용 0.
- S1: 핵심 의사결정 변경 가능 오류·원본추적 단절·중대 분야충돌. 허용 0.
- S2: 제한된 범위의 계산/표현오류. 승인된 잔여목록과 기한 필요.
- S3: 비기능·편의 개선. 백로그 허용.
성장루프 정지조건:
1. 범위 내 S0/S1 open 0, 신규 S0/S1 발견률이 연속 2회 0.
2. 모든 critical requirement가 code+test+evidence+owner와 연결.
3. 다층 시뮬레이션 mandatory cell 100% 실행, critical oracle 위반 0.
4. 독립검산 delta가 Tolerance Register 이내이고 설명되지 않은 bias 0.
5. 인허가·감리·기성 등 적용 workflow의 승인우회 경로 0.
6. 재현성, 복구, 보안, 성능 SLO가 목표를 충족.
7. 잔여 S2/S3가 사용목적을 침해하지 않는다고 책임자가 승인.
이를 충족한 상태를 `SCOPE-BOUND VERIFIED`로 부르며 `절대적 100% 완벽`이라고 표기하지 않는다.

[릴리스 주장 계약 Release Claim Contract]
릴리스 보고서는 반드시 다음을 선언한다.
- 검증한 관할·시설유형·프로젝트단계·데이터시점·성숙도.
- 검증하지 않은 관할·유형·공법·시공/운영범위.
- 합성/익명/실데이터 비율과 전문가 검토 범위.
- 통과한 시나리오와 미실행 시나리오, known residual risk.
- 외부사용 가능한 산출물 등급과 금지된 사용.
범위를 넘어서는 일반화·정확도·상용완료 주장은 자동 실패다.

[v4.0 P0~P14 추가 Gate]
P0: 필지 식별뿐 아니라 분석목적·기준일·사용목적·대상범위 DoR 확정.
P1: source license/보존/개인정보와 필드 정의·기준시점까지 검증.
P2: 물리 접도·법적 접도·권리확보를 분리하고 사건트리로 필지실패 전파.
P3: Rule 후보→검토→승인→배포→폐기 lifecycle와 dual-control 구현.
P4: 정합수치 외에 survey/cadastral/design boundary의 용도별 사용제한 발행.
P5: CSM freeze와 변경요청·dependency completeness 검증.
P6: 규칙별 적용/비적용 이유, competing interpretation, authority RFI 생성.
P7: 허용오차 스윕, boolean kernel 교차검증, infeasibility certificate 생성.
P8: 코드/피난/주차/구조/MEP/시공성 동시검토와 불가대안 배제근거.
P9: scope coverage matrix, 제외/중복, 장기납기, carbon/운영비 선택계약.
P10: 세금·대출 covenant·waterfall·draw condition 및 목표치 역산.
P11: Pareto 안정성, dominated option 제거, 의사결정자 효용·강건성 분리.
P12: 제출용/의사결정용/내부검토용 보고서별 claim·증거수준·watermark.
P13: 실제 역할 적격성·독립성·전자서명·조건부 승인 만료·재승인.
P14: 감리·기성·변경·준공·실적 calibration과 운영 drift/rollback 통합.

[통합 시뮬레이션 스위트]
S1 토지비 +10%, 공사비 +15%, 금리 +200bp, 분양 6개월 지연.
S2 핵심필지 취득 실패, 진입부 변경, 지하층 증가.
S3 보수적 법규해석, 주차 강화, 목표용적률 5% 미달.
S4 경계 내측오차, 정북각 오차, 표고오차 동시 적용.
S5 분양가 -10%, 흡수율 -30%, 중도금 유입 지연.
S6 API stale, schema drift, 조례개정 배포가 동시 발생.
S7 인허가 보완요구로 코어·주차·소방계획 변경 및 4개월 지연.
S8 지반조건 악화, 흙막이 공법변경, 장기납기 자재 지연의 공정·원가 연쇄.
S9 구조 grid 변경과 설비 shaft 증가로 전용률·주차·물량·매출 동시 변화.
S10 현장 진척 과대계상, 검사불합격, 기성청구 중복을 결합한 감리·지급 검증.
S11 승인 우회, 원본 바꿔치기, 조문 오인용, 보고서 숫자 덮어쓰기 공격시험.
S12 준공도면·시공수량·정산수량 불일치와 O&M 누락의 인수인계 검증.
모든 시나리오는 seed, input snapshot, rule version, engine version, expected invariants를 저장한다.

[결과물 생성 예측과 검증]
실제 golden 데이터가 없는 경우 결과 정확도를 발명하지 말고 합성 fixture 기반 '예비 예측'으로 표기한다.
각 단계의 결과물에 대해 다음을 산출한다.
- expected artifact schema
- 생성 성공조건
- 예상 실패모드
- 품질지표와 목표범위
- synthetic fixture 결과
- expert validation required 항목
실제 프로젝트 데이터가 연결되면 prediction과 actual의 delta를 기록하고 calibration curve를 갱신한다.

[성장루프 알고리즘]
1. 실행·교정·장애에서 observation 수집.
2. severity와 root cause 분류.
3. 실패를 재현하는 테스트 작성.
4. 최소 수정 구현.
5. unit/contract/property/golden/stress 전체 실행.
6. 기존 성능과 candidate 성능 비교.
7. critical false-pass가 하나라도 있으면 reject.
8. 통과 시 shadow, 이후 canary.
9. 운영 지표 안정 시 점진배포, 악화 시 자동 rollback.
10. 결과와 delta를 model/rule/data registry에 기록.

[전체 검증 명령]
저장소 기술스택에 맞춰 다음 목적의 단일 진입점을 제공한다.
make bootstrap
make lint
make typecheck
make test
make test-contract
make test-property
make test-golden
make test-stress
make test-e2e
make simulate
make evidence
make verify-release
Make가 부적합하면 동등한 task runner를 쓰되 README에 매핑한다.

[릴리스 차단조건]
- critical false-pass 1건 이상
- hard rule citation/approval 누락
- UNKNOWN/CONFLICT의 정상값 변환
- CSM/rule/engine 버전 미기록
- 면적·현금흐름 불변식 실패
- 보고서 수치 불일치
- 승인 우회경로
- 회귀·보안·복구 시험 실패
- 실제로 실행하지 않은 테스트를 통과로 보고

[완료보고 형식]
1. Outcome: 실제 구현된 기능
2. Gate status: P0~P14 PASS/CONDITIONAL/BLOCKED
3. Changed files: 핵심 파일과 목적
4. Commands executed: 명령·종료코드
5. Test matrix: unit/contract/property/golden/stress/e2e
6. Sample artifacts: 파일 경로와 해석
7. Metrics: coverage, false-pass, latency, reproducibility, calibration
8. Remaining blockers: 필요한 API키·전문가·실데이터
9. Next executable task: 정확히 하나
10. Honesty statement: mock/합성/실데이터 범위 구분

[MODE별 행동]
BOOTSTRAP: 저장소 조사, baseline 실행, target architecture 적응, contracts/fixtures/CI 뼈대와 P0 최소 vertical slice를 실제 생성한다.
IMPLEMENT: 지정한 TARGET_PHASE를 구현하고 모든 선행 Gate를 확인한다.
VERIFY_RELEASE: 변경 최소화. 전체 테스트·시뮬레이션·evidence·보안·복구를 실행하고 릴리스 판정만 한다. 실패를 숨기지 않는다.
RESUME: docs/evidence와 task state를 읽고 마지막 미통과 Gate부터 계속한다.

이제 MODE와 TARGET_PHASE를 확인한 뒤 즉시 저장소 조사 및 실행을 시작하라. 사용자에게 이미 제공된 정보는 다시 묻지 말고, 실제 권한·데이터·선택이 없어서 결과가 달라지는 경우에만 정확한 blocker를 보고하라.
```

---

## 4. 단계별 재실행 프롬프트

IDE 에이전트가 중단되거나 컨텍스트가 초기화되면 아래 문구를 사용한다.

```text
MODE=RESUME로 실행하라. 먼저 docs/evidence, 요구사항 추적표, 현재 git diff, 마지막 테스트 결과를 읽어라. 완료된 작업을 다시 만들지 말고 마지막 BLOCKED/CONDITIONAL Gate의 미충족 조건부터 진행하라. 기존 사용자 변경을 보존하고, 이번 턴에 실제 코드·테스트·증거를 생성하라. 종료 전에 Gate 판정과 다음 실행 가능한 작업 하나를 남겨라.
```

## 5. 실패수정 전용 프롬프트

```text
현재 실패를 우회하거나 테스트를 약화하지 말고 재현 가능한 원인을 진단하라.
1. 실패 명령, 입력, seed, 버전, stack trace를 고정한다.
2. 최초 오류 지점을 찾고 증상과 원인을 분리한다.
3. 회귀 테스트를 먼저 추가한다.
4. 최소범위로 수정한다.
5. 해당 테스트→관련 모듈→전체 Gate 순서로 재실행한다.
6. 결과 delta와 부작용 가능성을 기록한다.
7. 수정이 법규/데이터/기하/비용/금융/보고 중 어디에 속하는지 CorrectionLog에 태깅한다.
```

## 6. 실데이터 연결 후 검증 프롬프트

```text
합성 fixture 단계를 종료하고 실제 프로젝트 검증을 수행하라.
- 입력 원본을 변경하지 말고 SourceSnapshot과 checksum을 생성한다.
- 개인정보·계약정보를 마스킹하고 접근권한을 적용한다.
- 골든 결과는 독립 전문가 산출물과 연결하되 모델 입력에서 격리한다.
- P0~P14를 동일 run_id 계열로 실행한다.
- synthetic prediction과 actual 결과의 delta를 단계별로 계산한다.
- 법규 false-pass/false-fail, geometry intrusion, 적산 APE, 수지 delta, 보고서 claim 오류를 측정한다.
- 오류는 숨기지 말고 root cause별 backlog와 회귀 테스트로 승격한다.
- 최소 10개 프로젝트 parallel run 전에는 상용 적합을 선언하지 않는다.
```

## 7. 결과물 생성 예측 검증표

| 파이프라인 | 예상 실무 결과물 | 자동 검증 | 전문가 확정 필요 |
|---|---|---|---|
| P0 | 대상필지조서·대상지 지도 | 식별·면적·기하 | 폐번지·부분편입 |
| P1 | 공부·인허가 종합표 | schema·lineage·충돌 | 장부 불일치 해석 |
| P2 | 합필·제척·토지확보안 | 그래프·면적·N-1 | 권리·취득 가능성 |
| P3 | 적용 Rule Pack | 시행일·근거·테스트 | 법률해석·예외 |
| P4 | 정합 지형·DWG | CRS·RMSE·잔차 | 측량 경계 확정 |
| P5 | Due Diligence·CSM | hash·coverage·risk | Red Flag 승인 |
| P6 | 법규검토 Matrix | 독립계산·golden | 해석분기 |
| P7 | 3D Envelope | solid·침범·round-trip | 심의조건 |
| P8 | 배치·면적·BIM 초안 | constraint·면적·주차 | 설계 품질 |
| P9 | 개산내역·P50/P80 | 단위·중복·benchmark | 단가·공법 |
| P10 | 월별수지·IRR/DSCR | 항등·spreadsheet 대조 | 세무·금융조건 |
| P11 | Pareto 후보군 | 재현·단조성·수렴 | 최종 의사결정 |
| P12 | MD/PDF 보고서 | citation·수치일치 | 표현·권고 |
| P13 | 승인 패키지 | 권한·감사·상태 | 법정 책임자 승인 |
| P14 | 교정·회귀·배포·감리·기성·준공 인계기록 | 평가·canary·rollback·검측/지급 불변식 | 정책·감리·발주자 승인 |

## 8. 완성도 지수

“완성도 100%”라는 선언 대신 아래 지수를 단계별로 계산한다.

\[
M=\min(R,C,T,V,O,S)
\]

- `R`: 요구사항 추적 충족률
- `C`: 핵심 계산·규칙 커버리지
- `T`: 테스트·골든·스트레스 통과수준
- `V`: 실데이터 및 전문가 검증수준
- `O`: 운영·관측·복구 준비도
- `S`: 보안·감사·승인 준비도

상용 Pilot Gate의 권장 최소치는 모든 축 0.90 이상이되, Critical false-pass는 별도로 0건이어야 한다. 실데이터·전문가 검증이 없으면 `V`는 0.50을 초과할 수 없도록 한다. 이 규칙은 합성 테스트만 통과한 플랫폼을 완성품으로 오인하는 것을 방지한다.

## 9. 최종 릴리스 판정 템플릿

```yaml
release_candidate: <version>
run_id: <id>
commit: <sha>
verified_scope:
  jurisdictions: []
  building_types: []
  lifecycle_stages: []
  maturity_level: M0|M1|M2|M3|M4|M5
  data_cutoff: <date>
input_snapshot_hash: <hash>
rulepack_hash: <hash>
engine_versions: {}
gates:
  P0: PASS|CONDITIONAL|BLOCKED
  P1: PASS|CONDITIONAL|BLOCKED
  P2: PASS|CONDITIONAL|BLOCKED
  P3: PASS|CONDITIONAL|BLOCKED
  P4: PASS|CONDITIONAL|BLOCKED
  P5: PASS|CONDITIONAL|BLOCKED
  P6: PASS|CONDITIONAL|BLOCKED
  P7: PASS|CONDITIONAL|BLOCKED
  P8: PASS|CONDITIONAL|BLOCKED
  P9: PASS|CONDITIONAL|BLOCKED
  P10: PASS|CONDITIONAL|BLOCKED
  P11: PASS|CONDITIONAL|BLOCKED
  P12: PASS|CONDITIONAL|BLOCKED
  P13: PASS|CONDITIONAL|BLOCKED
  P14: PASS|CONDITIONAL|BLOCKED
critical_false_pass: 0
open_S0: 0
open_S1: 0
hard_intrusions: 0
untraced_claims: 0
approval_bypasses: 0
mandatory_simulation_cells_executed: 0.0
independent_check_critical_coverage: 0.0
interface_critical_open: 0
maturity_vector:
  requirements: 0.0
  calculation: 0.0
  testing: 0.0
  real_validation: 0.0
  operations: 0.0
  security: 0.0
decision: RELEASE|PILOT_ONLY|REJECT
conditions: []
prohibited_uses: []
unverified_scope: []
residual_risks: []
evidence_paths: []
```

## 10. 현실적 완료 범위

이 프롬프트로 IDE 에이전트가 다음을 실제 완성할 수 있다.

- 저장소 구조와 실행환경
- 도메인·API·DB 계약
- P0~P14 구현 및 통합 테스트
- 합성 fixture 기반 E2E 샘플 결과
- 시뮬레이션·회귀·성장루프 자동화
- 근거와 버전이 연결된 보고서
- Pilot 릴리스 적합/부적합 판정

다음은 별도 실물 입력 없이는 완료했다고 선언할 수 없다.

- 전국 모든 조례 Rule Pack의 전문가 승인
- 실측 경계와 DWG의 프로젝트별 정합 확정
- 실제 견적·계약단가 기반 적산 정확도 보정
- 실거래·분양·금융조건 기반 수지 calibration
- 실제 건축사·적산사·금융전문가의 병행검증
- 운영 API 키, 클라우드, 보안·복구 환경에서의 최종 시험

따라서 첫 실행의 목표는 “모든 것을 한 번에 100% 완성”이 아니라, 지원 관할과 시설유형을 명시한 vertical slice를 코드·테스트·실데이터 증거로 완성한 뒤 같은 Gate를 반복하여 범위를 확장하는 것이다.

## 11. v4.0 문서 자체 검증 체크리스트

이 체크리스트는 프롬프트 문서의 정합성을 확인하며 플랫폼 구현 완료를 대신하지 않는다.

| 검증축 | 통과조건 |
|---|---|
| P0~P14 완전성 | 각 단계에 입력·처리·계산/판정·산출물·Gate·인계가 존재 |
| 원본 무결성 | raw→quarantine→normalize→reconcile→approve→promote 우회 없음 |
| 실무생산성 | DoR·Basis Freeze·DoD·Issue Package·Artifact Dictionary 존재 |
| 전문분야 범위 | 토지·교통·토목·건축·구조·MEP/소방·주차·적산·시장·금융 포함 |
| 다분야 정합 | Interface Register·충돌유형·영향무효화·재검증 존재 |
| 인허가 | 적용성·RFI·제출 freeze·보완요구·회신·재제출 폐루프 존재 |
| 설계/시공 연계 | 시공성·조달성·유지관리·시운전·안전 review 존재 |
| 감리/기성 | ITP·검측·합격수량·변경계약·지급보류·감사로그 존재 |
| 준공/운영 | as-built·O&M·시험·자산·실적 calibration 인계 존재 |
| 시뮬레이션 | L0~L6, 단일/교호/복합/사건/결함/역산/back-test/red-team 포함 |
| 검증오라클 | 독립계산·골든·불변식·전문가 중 하나가 모든 필수시험에 지정 |
| 성장루프 | 재현시험→수정→전체회귀→shadow/canary→rollback과 정지조건 존재 |
| 정직한 릴리스 | 검증범위·비범위·증거수준·금지용도·잔여위험 표시 |

문서 검증 PASS 조건은 위 13개 축 누락 0건, 코드블록/표 구조 오류 0건, P0~P14 식별 누락 0건이다.
실제 상용 릴리스 PASS는 별도로 대상 저장소·공식 원본·승인 Rule Pack·전문가 골든 결과·운영환경을 연결한 후 `VERIFY_RELEASE`를 실행해야 한다.
