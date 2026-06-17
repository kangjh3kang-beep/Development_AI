# 심의분석 엔진 — 실구동·로드맵 실행 로그 (2026-06-16)

모든 단위를 **계약 → 구현 → 검증(실측)** 으로 완결한 기록. 각 단위 커밋·테스트·HTTP 실호출 증거 포함.

## 0. 누적 상태 (최종)
- **테스트: 146 passed**(skipped 0), **ruff: All checks passed**.
- **alembic head: `0012_analysis_run`**(실DB `propai_db` review 스키마).
- 엔진은 **실행→영속화→조회→인증** + **BIM/VLLM 이중경로 + 규제 지식그래프 + 평가 하네스**를 갖춘 self-contained 풀스택(백엔드 `/api/v1/*` + 콘솔 프런트 `/`).
- 실행: `cd apps/api && HOME=… ../../.venv/bin/python -m uvicorn app.main:app --port 8801` → `http://localhost:8801/`.

## 1. 배선/실구동 기반 (선행)
| 단위 | 산출 | 검증 | 커밋 |
|------|------|------|------|
| 11계층 오케스트레이터 + `/analyze` | run_analysis(Preflight~정성→게이팅→리포트) | uvicorn POST /analyze 200, 124 passed | `08a9a17` |
| 콘솔 프런트 `GET /` | 같은 FastAPI가 백+프 서빙 | GET / 200(9114B) | `dcfd2e8` |
| CORS | 크로스오리진 허용 | preflight 200 + ACAO 헤더 | `23b1918` |
| 콘솔 fetch 절대 URL | 상대경로 파싱오류 수정 | GET / 200, /analyze 200 | `987f258` |
| 플랫폼 라이브 콘솔 | /deliberation-review ↔ /analyze | tsc/eslint 통과 (platform `d8249938`) | — |
| 연구·로드맵 | 실 웹조사 → P0~P4 계획 | 출처 인용 | `f44ee1d` |

## 2. 로드맵 실행 단위 (P0→P2→P1→P3→P4)

### P0 — 실 VLLM 시트분류 어댑터 — 커밋 `8fdd7fe`
- **계약**: 기존 `SheetClassifierAdapter`(classify(sheet)->str|None) 준수.
- **구현**: `adapters/vision/vllm_sheet_classifier`(vision_client 주입 시 실 호출, AnthropicVisionClient 참조구현 lazy httpx+키검사, 미가용 시 graceful degrade=입력신호; SHEET_CLASSIFIER=vllm 팩토리). INV-8/9는 SheetRoleResolver가 보존.
- **검증**: 7 테스트(계약/degrade/한국어 정규화/미상 None/팩토리/resolver 합의 보존), 전체 131 passed.

### P2 — 분석결과 DB 영속화 + 조회 + 인증 — 커밋 `1fd7453`
- **계약**: AnalysisResult.run_id, settings.API_TOKEN.
- **구현**: analysis_run 테이블(JSONB)+0012 마이그레이션, analysis_store(save/get), deps(get_session/require_token), routes(POST 영속화+GET /{run_id}+인증).
- **검증**: 136 passed(+5: store 라운드트립 2, 인증 401 3). HTTP: POST→GET ROUND-TRIP MATCH True, 미지 id 404, review.analysis_run 행수=1.

### P1 — BIM/IFC 이중경로 인제스트 — 커밋 `8ab7edd`
- **계약**: BimElement/BimModel/ExtractionResult(source BIM|VLLM|none).
- **구현**: 경량 IFC(STEP) 정규식 파서(타입→SemanticType 보수 매핑+이름 키워드 정제, 미매핑 UNKNOWN), dual_path(ifc 우선/elements 폴백/none 표면화), AnalysisInput(ifc/elements)+Result(extraction_source/bim_elements) 파이프라인 배선.
- **검증**: 5 테스트, 전체 141 passed. HTTP: extraction_source=BIM, bim_elements(IFCWALL→EXT_WALL·IFCSTAIR→CORE_STAIR·IFCSPACE→PARKING).

### P3 — 규제 지식그래프 — 커밋 `bc3cdb3`
- **계약**: NodeKind/RegNode/RegEdge/RegGraph(+질의 rules_for_article/articles_for_rule/relaxations_for_rule).
- **구현**: build_reg_graph(R3 룰+완화 + R2 미러 → 조문 GROUNDS 룰, 룰 TARGETS 변수, 룰 RELAXES 완화, 완화 REQUIRES 전제), AnalysisResult.reg_graph 배선.
- **검증**: 3 테스트, 전체 144 passed. HTTP: reg_graph 6 nodes/4 edges(ARTICLE·RELAXATION·RULE·VARIABLE / GROUNDS·RELAXES·REQUIRES·TARGETS).

### P4 — 추출 평가 하네스 (AECV-Bench 스타일) — 커밋 `05aafdd`
- **계약**: GoldenItem/EvalReport(accuracy·per_type·mismatches).
- **구현**: data/eval/golden_set.json(시트역할 4+요소 3), extraction_eval(evaluate+run_eval).
- **검증**: 2 테스트(산식 정확성 0.5·불일치 식별·유형별, 골든셋 회귀 바 정확도 **1.0**), 전체 146 passed.

## 3. 엔드투엔드 실측 증거 (HTTP)
- `POST /api/v1/analyze`(BIM ifc + rules + citations) → extraction_source=BIM, bim_elements 3, reg_graph 6/4, far_limit COMPLIANT(완화 MET), run_id 영속화.
- `GET /api/v1/analyze/{run_id}` → ROUND-TRIP MATCH True(extraction_source·reg_graph 포함).
- 미지 id → 404. API_TOKEN 설정 시 무토큰 → 401.

## 4. 실연동 (키 발급·주입·검증)
- **키 발급/주입 가이드**: `docs/KEY_SETUP.md` + `.env.example`(키는 로컬 .env에만, 채팅/커밋 금지).
- **VLLM(Anthropic) 실 어댑터**: `AnthropicVisionClient`(P0) — `SHEET_CLASSIFIER=vllm`+`ANTHROPIC_API_KEY` 시 활성.
- **관할(VWORLD) 실 어댑터**: `adapters/jurisdiction/vworld`(용도지역 조회→zones, 키 없으면 fallback) + 팩토리(`JURISDICTION_ADAPTER=vworld`). resolver 기본값=팩토리(mock 기본 유지).
- **통합 상태 doctor**: `GET /api/v1/doctor` — 어댑터별 live/mock + 키 보유 여부(bool, 값 비노출). 키 없으면 정직하게 `live:false`.
- **검증(키 없이)**: `test_live_integration`(8) — httpx 모킹으로 VLLM/VWORLD **요청 구성·응답 파싱·정규화·키없음 degrade·팩토리** 증명. doctor 실호출로 현재 mock 상태 확인. 전체 154 passed, ruff clean.
- **라이브 검증(키 주입 후 사용자 실행)**: `docs/KEY_SETUP.md §4` — doctor의 `live:true` 확인 + 실 도면/PNU로 /analyze.

## 4.1 관리자 키 연결 — 방식 C(플랫폼이 스코프 키만 내보내기) ✅
- **배경**: 엔진(별도 서비스)이 플랫폼 마스터키로 금고 전체를 복호화하는 것은 신뢰 경계를 넘음
  (자동 분류기가 ① api_keys 직접조회 ② 마스터키 argv 복사 ③ 부팅 복호화 — 같은 경계 3회 차단).
- **설계**: 플랫폼(금고 소유자)이 `apps/api/scripts/export_scoped_secrets.py`로 **허용목록 키만**
  엔진의 `.env.secrets`로 내보냄. 엔진은 자기 `.env(.secrets)`만 읽음(마스터키·금고 접근 0).
  - 출처: 플랫폼 `.env` 베이스라인 + `--with-db` 시 `platform_secrets` 동일 로직 복호화 오버레이.
  - 하드 디나이: DATABASE_URL/JWT/SECRET/PRIVATE_KEY 등 절대 미포함. 파일 `0600`. 요약은 마스킹만.
- **엔진 측**: `settings`가 `.env` 위에 `.env.secrets` 오버레이(`.gitignore`됨). `LOAD_PLATFORM_SECRETS=false`.
- **검증**:
  - export 스크립트 합성 테스트 — 허용목록만 기록·디나이 키 차단·0600·마스킹 요약 **ALL PASS**.
  - 엔진 부팅(합성 `.env.secrets`)→`GET /api/v1/doctor`: `sheet_classifier.live:true`,
    `jurisdiction.live:true`, `platform_secrets.master_key_present:false`(경계 안 넘음). 분류기 차단 없음.
  - 커넥터(대안) 단위검증 포함 전체 **160 passed, ruff clean**. 가이드: `docs/KEY_SETUP.md §0`.
- **운영 실행(사용자)**: 플랫폼에서 위 스크립트 `--with-db` 1회 실행 → 엔진 재시작 → doctor `live:true`.

## 6. 반복 완성 루프 — 라운드 진단 + 단선 해소

### 라운드1-2 진단(실측, tools/diag_round1.py)
7 시나리오 + 결정론 + 성능 다각도 실측. **로직·게이팅·결정론은 목표 부합·정상**:
- 11계층 배선 작동, 결정론 full_equal=true, 무음 skip 금지(결손 시 7계층 표면화).
- 무음 오판 0 게이팅: 저신뢰(0.3)→NEEDS_REVIEW/LOW, 충돌→NEEDS_REVIEW(conflicts 보존),
  미검증 인용→NEEDS_REVIEW(보수), 위반→NON_COMPLIANT, 시뮬 플래그→NEEDS_REVIEW. 전부 정확 분리.
- 설계도서 경로 BIM(IFC 5요소)·2D 폴백(VLLM) 작동. 성능 순수계산 50ms.
- **단선=외부 실데이터 자동연동**: ①멀티모달 도면 자동해석 end-to-end ②실키(VLLM/VWORLD) ③Qdrant ④Celery ⑤규제 supply.

### ✅ P-A — 멀티모달 도면 자동해석 end-to-end
- 갭: 기존 `resolve_elements`는 elements(구조화 요소)를 사람이 채워야 했고, VLLM은 시트역할만 분류.
- 구현: `contracts/drawing_extraction.py`(DrawingSheet/ExtractedElement/DrawingExtraction) +
  `adapters/vision/drawing_extractor.py`(DrawingExtractor: 비전 주입 시 live, 아니면 힌트 폴백, 둘 다 없으면
  추출불가 표면화-날조금지; AnthropicDrawingVisionClient live + build_drawing_extractor 팩토리) +
  AnalysisInput.drawings/AnalysisResult.drawing_source·drawing_elements_n + 파이프라인 0a 배선.
- 검증: AT 7(힌트추출·비전추출·UNKNOWN 정규화·날조금지·결정론·정규화·파이프라인 배선) +
  diag S8(도면→2요소 자동추출→extraction VLLM). **전체 167 passed, ruff clean.**

### ✅ P-A.2 — 도면 면적표 → 법정 산정 자동구성
- 갭: 도면 추출 area가 산정으로 안 흘러 calc_targets를 사람이 작성해야 했음.
- 구현: DrawingSheet.area_table/DrawingExtraction.area_tables + `services/extraction/calc_target_builder.py`
  (면적표 outer_area + area보유·타입확정 요소 → building_area calc_target; 면적표 없으면 빈+note, 날조금지) +
  파이프라인 P-A.2 배선(명시 calc_targets 우선, 없으면 도면 자동) + AnalysisResult.calc_targets_source.
- 검증: AT 3(면적표→자동산정 600-100=500·명시입력우선 800-50=750·면적표없음 skip표면화). **전체 170 passed, ruff clean.**
- 효과: 도면 업로드 → 요소+면적 자동추출 → 법정 산정까지 end-to-end(설계도서 자동분석 정량 본체).

### ✅ P-C — 유사사례 Qdrant 벡터검색 배선
- 갭: corpus_ingest/matcher/embedder/qdrant가 다 있었으나 파이프라인 L4가 `StatAggregator.aggregate(issue,
  corpus)`로 corpus를 무차별 집계 — **벡터검색을 완전 우회**.
- 구현: `services/precedent/precedent_search.py`(PrecedentSearch: 분석마다 격리 client로 즉석 적재→검색,
  임계 0.99로 동일임베딩 선별, INV-24 후보표기 보존; 실 의미 임베더 주입 시 의미유사 검색으로 격상) +
  파이프라인 L4 교체(issue+corpus → 벡터검색→유사사례만 집계) + AnalysisResult.precedent_source.
- 검증: AT 5(유사선별·무관제외·결정론·파이프라인 배선·무관필터, 성숙도 임계 5건 반영). **전체 175 passed, ruff clean.**

### ✅ P-D — 비동기(Celery) 분석 태스크
- 갭: run_analysis 동기 → 대량 도면/실 LLM 호출 시 요청 블로킹.
- 구현: `tasks/analysis_tasks.analyze_task`(순수, 결정론 보존) + celery eager 옵션(dev 폴백) +
  API `POST /analyze/async`(eager면 결과 즉시 포함)·`GET /analyze/task/{id}`(운영 worker+backend) +
  settings.CELERY_TASK_ALWAYS_EAGER. **운영=eager=false + worker+redis로 진짜 비동기**.
- 검증: AT 3(eager 태스크 실행·비동기 API·동기=비동기 결정론). **전체 178 passed, ruff clean.**

### ✅ P-E — 규제 수집(supply) 자동 연결
- 갭: 파이프라인 L5가 mirror_rules를 직접 입력받아, 공급측이 수집·적재한 규제(mirror_store)를 자동 조회 안 함.
- 구현: 파이프라인 L5 배선 — mirror_rules 없으면 `mirror_store.get(jurisdiction)` 자동 조회(ACTIVE만,
  소비측 읽기전용 INV-13), 미적재 시 보수 게이팅 표면화(날조 금지). AnalysisResult.mirror_source.
- 검증: AT 4(supply 적재→자동조회·DRAFT 차단 INV-14·명시입력 우선·미적재 보수). **전체 182 passed, ruff clean.**

### ✅ P-C 격상 — 실 의미 임베더(OpenAI) 주입
- 갭: P-C 해시 임베더는 양수벡터라 '정확 쟁점일치'만 가능(표기 다른 유사 쟁점 못 잡음).
- 구현: `adapters/embedding/embedding_client.py`(OpenAIEmbeddingClient, lazy httpx·키검사·실패 None) +
  `embedder.py` Embedder(client 주입, is_semantic, 실패 시 해시 폴백) + build_embedder 팩토리 +
  PrecedentSearch 임계 자동(의미 0.75 / 해시 0.99) + doctor embedder 상태 + settings EMBEDDER/EMBEDDING_MODEL.
- 검증: AT 6(의미주입·해시폴백·실패폴백·결정론·의미임계분리·기본경로 회귀무). **전체 188 passed, ruff clean.**
- ✅ **실 검증 완료**: OPENAI 진짜 키(관리자 DB, len164 HTTP200 dim1536) → 실 의미 임베딩으로
  **용적률(한)↔FAR(영) cos 0.406 > 무관(주차) 0.143** 의미분리 PASS. 표기·언어 달라도 유사쟁점 포착.
- ※ 앞서 OPENAI 401(placeholder)은 export DB오버레이 **pgbouncer 충돌**(DuplicatePreparedStatementError)로
  `.env` placeholder가 나왔던 것 — `statement_cache_size=0`+NullPool로 해소(trust_infra 9546be5d, DB 33키 안정).
  전 키 진짜 확인: ANTHROPIC·OPENAI=DB(관리자), VWORLD=env, 모두 HTTP 200.

### ✅ P-A 격상 — VLLM 멀티모달 비전 완성(실 이미지 전송)
- 갭: AnthropicDrawing/VisionClient가 image_ref를 **텍스트 프롬프트로만** 넣음 — 실제 이미지 미전송(진짜 멀티모달 아님).
- 구현: `adapters/vision/image_source.py`(build_image_block/build_content: 로컬파일→base64, http→url source,
  data-uri 파싱, 비이미지→텍스트 폴백) + Drawing/Sheet 클라이언트가 멀티모달 content([image, text]) 전송.
- 검증: AT 6(URL·data-uri·파일base64·비이미지·content구성·클라이언트 멀티모달) + **실 Anthropic 비전 실검증**:
  합성 도면 이미지 → **5요소(EXT_WALL/CORE_STAIR/PILOTIS/PARKING/BALCONY) 정확 추출**. **전체 194 passed, ruff clean.**

### ✅ 인프라 어댑터 — 진짜 비동기(redis worker) + 실 Qdrant
- **P-D 진짜 비동기 실검증**: celery_app include로 worker 태스크 등록 → `analyze_task.delay` → redis 큐 →
  **celery worker 처리**(eager=False) → 결과 NON_COMPLIANT. redis(PONG) 가동 실검증.
- **실 Qdrant 어댑터**: `RealQdrantClient`(qdrant-client, `:memory:` 임베디드 / http 서버, collection 차원별
  분리) + `build_qdrant` 팩토리(QDRANT_URL 시 실, 아니면 in-memory mock 폴백) + PrecedentSearch 차원 자동
  (의미 1536 / 해시 16). 검증: AT 3(`:memory:` 실 qdrant-client upsert/search·폴백·파이프라인). 서버는 URL만 교체.
- **누적 197 passed, ruff clean.** 남은 인프라=실 Qdrant 서버·worker 상시기동·실 법령 API(전부 가동/키만).

### ✅ 다중출처 교차검증 + 국가법령정보(law.go.kr)
- 동기: 다양한 1차출처를 합의 판정해 데이터 신뢰도·정확도 향상(사용자 제안, 엔진 철학 정합).
- 구현: `contracts/cross_validation`(SourceValue/CrossValidation: UNANIMOUS/MAJORITY/CONFLICT/SINGLE/ABSENT) +
  `services/cross_validate/validator`(만장일치 1.0 / 과반+이견표면화 / 불일치→NEEDS_REVIEW / 단일 보수 /
  결손; 수치허용오차·문자열정규화, 결정론, 무음 오판 0) + `adapters/legal/law_go_kr`(국가법령정보센터 DRF,
  OC=MOLEG_API_KEY, 검색/존재여부, 키없음·실패 graceful) + 파이프라인 cross_facts→합의(law.go.kr 키 있으면
  자동 합류)→AnalysisResult.cross_validations + settings MOLEG_API_KEY/BASE_URL.
- 검증: AT 16(교차검증 8·law 4·파이프라인 4: 만장/과반/불일치/단일/결손/허용오차/정규화/결정론/자동합류). **213 passed, ruff clean.**
- **★실연동 검증**: MOLEG OC(10자, propai-platform/.env 실값)로 **law.go.kr DRF HTTP 200**(건축법 success
  totalCnt6), 엔진 교차검증 law.go.kr 자동합류 UNANIMOUS(mirror+law conf1.0). data.go.kr(MOLIT) 국가법령정보는 403.

### ✅ 교차검증 출처 확장 — 국토부 건축물대장(MOLIT)
- 동기: MOLIT(data.go.kr 공용키, 실값 64자)을 교차검증 출처로 추가(사용자 제안) → 3중 출처(미러·법령·건축물대장).
- 구현: `adapters/regulation/molit_building`(건축물대장 BldRgstHubService, serviceKey=MOLIT, PNU분해
  →용적률 vlRat/건폐율 bcRat/연면적, resultCode≠00·미승인·무건축물 None graceful) + 파이프라인 교차검증
  MOLIT 자동합류(building_pnu+building_metric) + settings MOLIT_API_KEY/MOLIT_BLD_URL.
- 검증: AT 6(PNU분해·파싱·미승인·합류 UNANIMOUS·불일치 CONFLICT) + **실 MOLIT 호출 200**(건축물대장
  resultCode00, 종로구 청운동) → 교차검증 molit_building 실 합류 확인. **전체 219 passed, ruff clean.**

### ✅ 교차검증 출처 확장 — 개별공시지가(VWORLD NED)
- 동기: 공시지가(VWORLD vs 국토부) 교차검증(사용자 제안). **워크플로우 3각 조사로 500 원인 규명**:
  내 엔드포인트 `LandPriceService/att/getLandPriceAttr`가 오타(존재X) → 정답=`IndvdLandPriceService/attr/
  getIndvdLandPriceAttr`, stdrYear 필수. NSDI(data.go.kr 1611000)는 2024 VWORLD 이관으로 폐지(500).
  **정답 경로=VWORLD NED** `api.vworld.kr/ned/data/getIndvdLandPriceAttr`(key=VWORLD).
- **★INCORRECT_KEY 진짜 원인 = Referer 헤더 누락**(VWORLD 키는 Referer 도메인 검증, 등록=www.4t8t.net).
  플랫폼 vworld_service.HEADERS에서 규명. 활용신청·키는 정상이었음(또 내 호출 방법 문제).
- 구현: `adapters/regulation/vworld_landprice`(getIndvdLandPriceAttr, key=VWORLD + **Referer 헤더**,
  pnu+stdrYear→pblntfPclnd, 결손 None graceful) + 파이프라인 land_pnu 자동합류 + settings VWORLD_NED_URL/REFERER.
- 검증: AT 4 + **실 VWORLD NED HTTP 200 → 청운동 개별공시지가 5,244,000원/㎡(2025)** → 교차검증 UNANIMOUS 실합류.
  **전체 223 passed, ruff clean.** ✅ 공시지가 실연동 완료.

### ✅ VWORLD 활용 확장 — 토지이용계획(용도지역·고도제한)
- 동기: VWORLD NED 추가 활용(사용자 제안). 토지이용계획=용도지역/지구/고도제한 = 심의 핵심 규제 1차출처.
- 구현: `adapters/regulation/vworld_landuse`(getLandUseAttr+Referer, land_use_zones/has_zone) +
  파이프라인 land_use_pnu+land_use_contains 자동합류(vworld_landuse 출처).
- 검증: AT 4 + **실 VWORLD 호출 200 → 청운동 17개 규제 자동조회**(자연녹지·제1종일반주거·대공방어협조구역
  (위탁고도)·자연경관지구·역사문화환경보존·토지거래허가구역 등), has_zone('고도')=True. **전체 227 passed, ruff clean.**
- 효과: PNU만으로 전 규제(용도지역/고도/경관/보존/허가구역) 자동 조회 → 법령/조례 한도 적용·교차검증 기초.

### ✅ VWORLD 종합 활용 — 대지 규제 카드(토지특성+토지이용계획 자동수집)
- 활용방안 워크플로우(3각: NED규제·3D시뮬·혁신시나리오, 3 agents) → 최적안=시나리오1 '대지 규제 카드'
  (PNU 1건으로 토지 전 정보 자동수집, 심의 입력 전제 1차출처 고정). 승인 API 전체 분석.
- 핵심 3종 실호출 200 검증: 지오코더(주소→좌표)·토지특성(getLandCharacteristics)·필지(GetFeature).
- 구현: `adapters/regulation/vworld_landchar`(getLandCharacteristics → 지목/경사/도로접면/용도지역/이용상황/
  공시지가) + `contracts/land_card`·`services/land/land_card`(토지특성+토지이용계획 통합) +
  AnalysisInput.collect_land_card/land_year + AnalysisResult.land_card + 파이프라인 6.4 자동수집.
- 검증: AT 5(파싱·통합·부분결손·파이프라인·기본off) + **실 VWORLD 대지카드**(청운동: 지목 대·제1종일반주거·
  연립·완경사·소로한면·공시지가 515만원/㎡·중첩규제 17). **전체 232 passed, ruff clean.** 서비스설명과 정합.
- **+기존 건물(getBuildingUse)**: `adapters/regulation/vworld_building`(연면적/건폐율/용적률/층수/용도/동수,
  다동 합산, 나대지 None) → land_card.existing_building. **실검증 청운동 9개동·연면적 50,551㎡·공동주택**.
  AT 2 추가. **전체 234 passed, ruff clean.** 잔여 개발용량(법정한도−기존)·증축 심의·MOLIT 교차검증 기초.
### ✅ ① 지오코더(주소→PNU 진입점)
- adapters/regulation/vworld_geocoder(getcoord 주소→좌표 + GetFeature 좌표→PNU, 지번 우선·도로명 폴백) +
  AnalysisInput.address → 파이프라인 6.35 지오코딩 → AnalysisResult.geocoded + 대지카드 effective_pnu 자동연결.
- 검증: AT 4 + **실 주소 '서울 종로구 청운동 1'(PNU 미상) → PNU 1111010100100010000 → 대지카드(제1종일반주거·
  공시지가 515만원)** end-to-end. **전체 238 passed, ruff clean.** 도면 대지위치만으로 전 토지정보 자동.
### ✅ ② 잔여 개발용량(법정한도 − 기존 용적률)
- `services/land/zone_limits`(국토계획법 시행령 제84/85조 용적률·건폐율 상한 21용도지역, 1차출처) +
  `remaining_capacity`(법정−기존 용적률, 초과 판정, 조례강화 note) → land_card.area/remaining_capacity.
  vworld_landchar에 area(lndpclAr)/shape 추가.
- 검증: AT 5 + **실 청운동: 제1종일반주거 법정 200%, 대지 15,622㎡, 기존연면적 50,551㎡ → 기존 FAR 323.6%,
  잔여 -123.6%, 초과=True(기존불적합 → 증축불가·재건축 규모축소)**. **전체 243 passed, ruff clean.**
### ✅ ③ 주변 건물 스카이라인(일조/경관 시뮬 입력)
- `adapters/regulation/vworld_nearby`(lt_c_bldginfo BBOX → footprint+지상층수+높이, skyline_context
  평균/최고 층수) + AnalysisInput.collect_surrounding/surrounding_radius_m + AnalysisResult.surrounding_context
  + 파이프라인 6.36(geocoded 좌표 기반).
- 검증: AT 3 + **실 청운동 150m: 주변 59개동·평균 2.5층·최고 4층**(저층 스카이라인 → 신축 돌출도 판정 기준).
  **전체 246 passed, ruff clean.**
### ✅ ③+ 3D 정밀 일조/그림자 시뮬(shapely)
- shapely 2.1.2 도입. `sun_position.sun_altitude_azimuth`(시각별 고도/방위각) + `services/sim/shadow_3d`
  (building_shadow 그림자 폴리곤 투영=footprint+높이+태양반대 convex hull, sunlight_analysis 동지 9~15시
  일영비율/일조시간, 위경도→로컬미터 평면근사, 층고 파라미터화 INV-20 준수) + vworld_nearby footprint
  geometry + geocoder site_geometry + 파이프라인 6.36 일조 배선.
- 검증: AT 6 + **실 청운동(주소→필지 geometry 15,539㎡ → 주변 49매스 → 동지 9~15시 차폐 0.78~0.86,
  일조 0h=고밀 저층단지 실측)**. **전체 261 passed, ruff clean.**
- **순차 ①②③ 완료** — 지오코더·잔여용량·주변 스카이라인.

### ✅ 종상향(용도지역 상향) 가능성 분석 — 정적 잔여용량의 한계 보완
- 동기(사용자 지적): 재건축/재개발 시 도시정비법·지구단위계획 **종상향으로 용적률 상향** 가능 →
  모든 토지를 종상향 가능성 염두에 두고 실데이터로 실제 가능성 판별, 형질변경 시 분석 변동 반영.
- 구현: `services/land/upzoning`(UPZONING_LADDER 주거→상업 위계 + upzoning_scenarios 단계별 용적률/
  추가용량 + upzoning_signals 토지이용계획 촉진(지구단위/정비/역세권/입안중)/제약(고도/경관/보존) →
  가능성 HIGH/MIXED/LOW/UNKNOWN) → land_card.upzoning(현행 remaining_capacity와 별도 시나리오).
- 검증: AT 7 + **실 청운동(제1종일반 → 2종일반 +7,811㎡ → 3종일반 +15,622㎡; 촉진=도시관리계획 입안중,
  제약=대공방어(고도)·역사문화보존·자연경관·중점경관 → 가능성 MIXED)**. **전체 253 passed, ruff clean.**
- **✅ workflow(도시정비법 종상향 3각) 반영**: 신호 확장(재정비촉진/정비예정/개발진흥/입지규제최소 촉진;
  문화재보존영향/비행안전/군사 제약) + **높이봉인 게이팅**(고도/경관지구 → 용적률 상향해도 높이규제로
  실현 제약, "상한↑ ≠ 가용 연면적") + **BLOCKED**(문화재/그린벨트/군사=개발 봉쇄). likelihood
  BLOCKED>LOW>MIXED>HIGH>UNKNOWN. **실 청운동: LOW + height_sealed=True(대공방어 고도·경관)**. AT 9.
  **전체 255 passed, ruff clean.**
### ✅ 종상향 다중경로 + 지자체 조례 (다층/다각 — 사용자 지적 완성)
- workflow(종상향 다중경로 3각: 7경로·서울/경기 조례·다층최적) 반영.
- 구현: `upzoning.ORDINANCE_FAR`(시도×용도지역 조례 용적률 — 서울 일반상업 800% vs 시행령 1300%,
  PNU 앞2자리 시도코드, 미등록 시 시행령 상한 폴백) + `PATHWAYS`(지구단위/정비/역세권활성화/청년안심/
  사전협상/입규최소, 경로별 ladder_jump·공공기여·요건·근거법령) + `multipath_scenarios`(경로별 목표
  용도지역·조례용적률·최대연면적·공공기여) → land_card.upzoning.multipath.
- 검증: AT 4 + **실 청운동: 역세권활성화→근린상업 600% 93,732㎡·지구단위→2종 200% 31,244㎡·사전협상→
  3종 250%, 각 경로 공공기여/근거 + height_sealed 게이팅**. **전체 265 passed, ruff clean.**
### ✅ 형질변경(종변경) 재계산 — 사용자 지적 완성
- multipath 각 경로에 종변경 재계산: target_bcr_pct(건폐율 교체) + far_increase_area(증가 연면적) +
  contribution_rate(경로별 공공기여율 0.1~0.6) + public_contribution_area + **net_floor_area_gain(공공기여
  차감 후 순증)**.
- 검증: AT 3 + **실 청운동 역세권활성화: 근린상업 600% 건폐 70%, 증가 70,299㎡, 공공기여 50%(35,149㎡)
  → 순증 35,149㎡**. **전체 267 passed, ruff clean.**
### ✅ 3D 스카이라인 돌출도 — 경관심의 참고
- skyline_protrusion(skyline, proposed_floors): 신축안 층수 vs 주변 평균(ratio_vs_avg)·최고(exceeds_context_max)
  → 등급(LOW 최고이내 / MEDIUM 최고초과 / HIGH 최고 2배초과). 결손 None, 부분 스카이라인도 가능항목만 산출.
- 배선: AnalysisInput.proposed_floors → pipeline 6.36 surrounding_context["protrusion"]. AT 3, 전체 270 passed, ruff clean.
- 후속: 역세권 거리요건(250~350m, 지하철역 데이터) 정량 게이팅.

### ✅ 설명가능성 표준 + 토지/종상향 영역 적용 + 조례 시점태깅
- 워크플로 2종: ① 서울 한시완화·역세권 거리 1차출처 검증(HIGH) → docs/VERIFIED_FACTS_zoning.md.
  ② 엔진 전 산출물 근거동반 현황 전수매핑(4영역) — 공통결손: 법령ID만 흐름·도출식 부재·INV-20 하드코딩·
  심의민감 산출(shadow/skyline)이 근거게이트 우회·무음 강등.
- 표준 3종: **contracts/rationale.py**(LegalRef·RationaleInput·Rationale[summary·formula·inputs·legal_basis·caveats]),
  **services/explain/legal_refs.py**(조문ID→법령명·조항호·요지·시행일·1차출처 사전 22종, 미등록 placeholder 표면화).
- 적용: remaining_capacity·multipath 각 산출에 rationale 동반. **조례 연결**(잔여용량이 시행령만 쓰던 모순
  해소 — PNU 시도 조례 우선). **조례 시점태깅** ordinance_far(as_of) + 한시완화 '조건부 가능' 표면화(단정 금지).
  pipeline application_date→as_of 배선.
- 검증: 실 청운동 유사(제1종일반 150% vs 기존 323.6% 초과 / 역세권활성화 근린상업 600% 순증 35,149㎡) rationale
  동반 출력 확인. AT 5(test_explainability) + 전체 **275 passed, ruff clean**.
### ✅ 설명가능성 확장 — sim(일조/경관)
- shadow_3d.sunlight_analysis·skyline_protrusion 반환에 rationale 동반(건축법§61·시행령§86 / 경관법§9·건축법§60).
- 무음 오판 수정: sunny_hours_9to15가 '연속'이 아닌 과반일조 시각 총합임을 caveat로 표면화(시행령§86 연속판정과 별개).
- INV-20: sunlight_threshold(과반임계) 함수 파라미터화 + method에 동적 반영. AT 2 + 전체 **277 passed, ruff clean**.
### ✅ 설명가능성 확장 — report/reg_graph basis_article 본문 해소 (★작업경로=모노레포 정본)
- **작업 경로 이전**: 정본=모노레포 `services/deliberation-review`(독립 워크트리 Development_AI_deliberation,
  브랜치 feature/deliberation-review). 원본 propai-review는 보관. 원본 068c3af→정본 rsync 동기화.
- legal_refs에 **법령 수준 키 4종**(국토계획법시행령/국토계획법/건축법시행령/건축법) + **resolve_text()** —
  거친 basis_article("국토계획법 시행령" 등 조문번호 없음)을 best-effort 해소, match=exact/law_level 정직 표기.
- reg_graph RegNode에 law/article/summary/effective_date/source/resolved 속성 → ARTICLE 노드가 법령 본문·출처
  동반(ID만 흐르던 결손 해소). pipeline evidence에 legal_basis 결속, 미해소는 표면화(무음 금지).
- 검증: AT 2(test_basis_resolve) + 전체 **279 passed, ruff clean**(정본 워크트리).
### ✅ 설명가능성 확장 — legal_calc CalcTrace 제외 정량
- CalcTraceEntry에 threshold/threshold_unit/measured/excluded_amount 필드 + calc_params.meta()로
  basis_article·description·value 전파(calc_params.json의 근거가 출력에 소실되던 결손 해소).
- area_calculator(처마/발코니/필로티/지하·주차/건축선)·height_floor_calc(옥탑 비율) 각 제외에 임계·실측·차감량·근거 동반.
  예: "발코니 깊이 1.2m ≤ 기준 1.5m(건축법 시행령 제119조)".
- AT 4(test_calc_trace_explain) + 전체 **283 passed, ruff clean**.
### ✅ 설명가능성 확장 — final_gate 강등사유 + cross_validation 출처 ref (★전 영역 완료)
- final_gate: NEEDS_REVIEW 강등 시 reason 라벨(unverified / below_threshold(값<임계) / conflict /
  dual_path_HELD) — 무음 강등 제거.
- cross_validation: CrossValidation.sources(SourceValue 값+1차출처 ref) 보존 — by_source가 값만 담아
  역추적 불가하던 결손 해소.
- AT 2(test_gate_xval_explain) + 전체 **285 passed, ruff clean**.
- **★설명가능성 전 영역 완료**: land·sim·report/reg_graph·legal_calc·final_gate·cross_validation 모든
  핵심 산출에 도출이유(summary·formula·inputs)·법령(legal_basis 본문·출처)·한계(caveats)·정량근거 동반.

### 통합 최종 스냅샷(diag)
- 전 출처 표면화: drawing_source/calc_targets_source/precedent_source/mirror_source.
- precedent_source=VECTOR_SEARCH(P-C 배선), 도면 자동(S8) drawing_source=HINTS→extraction VLLM.
- **결정론 보존**(hash_equal·full_equal=true), 순수계산 51ms. 모든 신규 배선이 무음 오판 0·결정론 불변식 유지.

### ✅ 멀티모달 고도화 INC-10 — 추출 오케스트레이터(P-에이전트 완료)
- **계약**: 신규 `contracts/extraction_bundle.py`(ExtractionBundle/ExtractionStage). `AnalysisResult.extraction_trace` 가산.
- **구현**: 신규 `services/extraction/extraction_orchestrator.py` `orchestrate_extraction(...)->ExtractionBundle` —
  인라인 0a(도면추출)/P-A.2(calc_target)/0b(이중경로)를 6단계 명시 파이프라인으로 분리:
  ①role_resolve(SheetRoleResolver 관측·재사용) ②extract(추출가) ③verify(cross_sheet 관측) ④aggregate(취합가)
  ⑤calc_target ⑥dual_path. 단계 타이밍·강등사유를 `trace`로 노출(관측성). `analysis_pipeline.py`는 인라인 39줄 →
  오케스트레이터 호출 13줄로 단순화.
- **불변식 보존**: **취합가는 LLM 미관여**(`merge_with_consensus`=CrossSourceValidator 결정론). 단일 패스는 SINGLE
  (원순서·값 보존, consensus_status 메타만 — `to_pipeline_elements`/`calc_target_builder` 비소비로 산출 비누수).
  N-패스는 `vision_consensus_passes`(기본 1) param + 비전 경로만(동일 캐시입력 INC-8 → 재현). `extraction_trace`는
  비결정 timing 제외 결정론 투영(완전동치 보존). CONFLICT→needs_review를 trace status + skipped로 표면화(무음0).
- **검증**: AT 8(특성화 2 + 오케스트레이터 6) + 전체 **370 passed**(362→370), ruff clean, static_scan 0. 적대적 다관점
  리뷰(behavior 4.7/gate 4.7/quality 4.5, min 4.5 ≥ 게이트) — 10개 엣지 입력 byte 동일(0 mismatch), 결정론 2회 동일 확인.

### ✅ 멀티모달 고도화 INC-11 — 외부 1차출처 응답 캐시 계층(P-데이터 착수)
- **계약/스키마**: 신규 `contracts`-급 `db/models/cache_models.ExternalSourceCacheModel`(external_source_cache:
  cache_key uniq·adapter·endpoint·params_hash·payload JSONB·content_hash·etag·fetched_at·snapshot_id·status)
  + **alembic 0013_external_source_cache**(revises 0012, review schema, up/down 가역).
- **구현**: 신규 `adapters/cache/source_cache.py` — vision_cache(INC-8)의 분산/영속 확장. **L1 프로세스 인메모리**
  (sync `cached_get` — 어댑터 동기 httpx 경로, 적중→동일 출력 결정론, TTL·만료 회수·상한 eviction) +
  **L2 DB 영속**(async `warm_from_db`/`flush_to_db` — `analyze` 라우트 경계에서 best-effort, snapshot 결속).
  8개 어댑터(law_go_kr·molit_building·vworld_landprice/landuse/landchar/building/nearby/geocoder)의 인라인
  httpx.get을 공유 `cached_get` 경유로(원 시그니처/예외 보존). run_analysis가 `set_snapshot`로 snapshot 결속.
- **불변식**: 캐시는 데이터 확보 단계만 — **결정론 영향 0**(적중→동일 입력→동일 출력). 미스/실패→graceful None
  (무음0, None 미캐시→재시도). **secret(OC/key/serviceKey)는 cache_key·DB에서 제외**(비유출, 실 호출엔 포함).
  jurisdiction/vworld.py는 계약 상이(AdapterTimeout)로 의도적 제외. 테스트 간 캐시 격리(conftest autouse clear).
- **검증**: AT 9(적중·시크릿제외·None미캐시·TTL·어댑터경유·키없음·만료회수·flush-commit실패보존·DB라운드트립) + 전체
  **379 passed**(370→379), ruff clean, static_scan 0. 적대적 다관점 리뷰(gate 4.8·determinism 8.7·quality 8.5,
  전부 gate_pass) — 시크릿 비유출·결정론 코드 증명, 7건 기각·LOW 3건 반영(flush dirty-clear→commit 후, 만료 eviction, warm rollback).

## 5. 남은 항목 (운영 연결/결정 필요)
- **단선 해소 완료(코드)**: P-A·P-A.2·P-C·P-D·P-E 모두 계약→구현→AT→검증 완결, mock→live 스위치 +
  결정론 보존. **인프라/키 가동만 남음**: P-B 실키(사용자 1회 export), P-C 실 임베더+Qdrant,
  P-D worker+redis, P-E 실 법령 API+적재.
- **trust_infra**(작업/배포 브랜치, 사용자 확정)의 `apps/api`에서 `export_scoped_secrets.py --with-db` 실 1회(사용자) → 엔진 라이브 검증. 스크립트는 trust_infra 커밋 `160f466c`(키는 형제 worktree `Development_AI/propai-platform/.env` 자동탐지).
- 실 키 주입 후 라이브 호출 검증(사용자) · VWORLD 데이터 레이어ID/속성 문서 확정 · ifcopenshell 정밀 IFC.
- 규제 KG pgvector/SPARQL 질의 · Celery 비동기 배치 · 분석목록 페이지네이션 · 토지이음/ELIS 추가.

근거 연구: `docs/RESEARCH_AND_ROADMAP.md`. 페이즈별 자기수렴 감사: `docs/*_SELF_CONVERGENCE_AUDIT.md`. 키 가이드: `docs/KEY_SETUP.md`.
