# 고가치 갭(high) 영역별

## drawing_extraction (도면 추출·면적표·자동 calc_target 구성)
- 제외 측정치(length/depth/underground/accessory)가 도면 자동경로에서 소실 — DRAWING_AUTO로는 EAVE/BALCONY/PARKING 제외가 정확히 산정 불가
  → ExtractedElement에 length/depth/underground/accessory(또는 measurements dict) 필드 추가하고 _from_vision/_from_hints에서 VLLM·힌트의 측정치를 매핑, build_calc_targets_from_drawing이 이를 CalcElement 입력으로 승계. 미상 측정치는 None 유지(HELD 표면화 보존). EAVE/BALCONY/PARKING 자동경로 회귀테스트 추가.
- 기하(geometry)에서 면적/길이를 산출하는 능력 전무 — area/outer_area는 항상 외부 스칼라 입력(VLLM 텍스트 또는 사람 힌트)에 의존
  → (1) IFC는 ifcopenshell 또는 IFCQUANTITYAREA/IFCEXTRUDEDAREASOLID 파싱으로 실 면적 추출. (2) 2D는 벡터(폴리라인/해치) 경계좌표×축척으로 결정론적 면적 적분기 추가(슈레이스 공식). VLLM이 답한 면적은 cross_validate 대상으로 강등(1차출처 금지 원칙). 결정론 산정 게이트 보존.

## multimodal_vision
- 도면 파일 업로드 엔드포인트 부재 — image_ref(경로/URL)만 JSON으로 받음, 멀티파트 업로드·PDF/DWG 변환 파이프라인 없음
  → POST 멀티파트 업로드 라우트 + PDF 페이지→시트 이미지 분할(PyMuPDF) + ALLOWED_IMAGE_DIR 저장 → drawings[].image_ref 자동 채움. 사용자가 도면 PDF 한 장만 올리면 시트 자동분리·분류·추출까지 무손 연결(현재는 사용자가 시트별 이미지를 직접 준비해야 함 = 편의성 갭).
- VLLM 비전 출력의 스키마/좌표 검증 부재 — JSON 텍스트 substring 파싱, bbox·좌표 grounding·근거 인용 없음
  → 비전 출력에 bbox·신뢰도·근거좌표를 요구하고 pydantic 스키마 강검증 + 축척(scale_unit)으로 픽셀→실면적 결정론 환산을 추가. 그래야 INV-4(설명가능성: 정량근거)와 INV-1(산정 결정론)이 비전 area에도 적용됨. 현재는 LLM이 부른 area를 검증 없이 calc_target_builder가 산정입력으로 승계.

## extraction_dualpath_preflight
- 축척 분모(scale_denominator)가 도면 픽셀 측정→실척 환산에 실제 소비되지 않음 — preflight 전제로만 잠기고 면적 산정과 단절
  → DrawingExtractor.extract에 PreflightContext.scale을 주입해, 비전이 픽셀/도면길이로 area를 줄 때 scale_denominator로 실척 환산하는 결정론 변환 단계 추가. 축척 미확정(assumed)이면 환산 결과를 HELD로 강등 표면화.
- IfcParser가 BimElement.area/length/storey를 채우지 않음 — IFC에서 정량(면적/층) 미추출, calc 입력 승계 불가
  → IFCQUANTITYAREA/IFCELEMENTQUANTITY 연관 파싱으로 BimElement.area·storey 채우기(ifcopenshell 선택적 어댑터). 정량 결손은 UNKNOWN-area로 표면화해 무음 0 방지.

## data_collection (데이터 수집·취합·가공: adapters[vworld/molit/moleg] · supply/mirror · corpus_ingest · cross_validate)
- 외부 1차출처 응답 캐싱/영속화 부재 — 분석마다 매번 재호출(쿼터/지연/비용 폭주)
  → (PNU/주소/law_query 키, snapshot 축일자 결속) 응답 캐시 테이블 신설 + TTL/축일자 무효화. 동일 PNU 재분석·다출처 교차검증 시 중복 호출 제거. ETag/If-Modified-Since 또는 content_hash 비교로 변경분만 갱신.
- 수집 데이터(미러·후보·하베스트 문서)의 DB 영속화 미배선 — 프로세스 재시작 시 휘발
  → MirrorWriter/Harvester/CorpusIngest에 AsyncSession 주입해 mirror_snapshot/source_document/harvest_job upsert. 소비측 default_store().get을 DB 조회로 교체(읽기전용 INV-13 유지). 재시작·다중워커 간 수집결과 공유 확보.

## pipeline_ux
- 도면 파일 업로드(multipart) 진입점 부재 — 사용자가 도면을 직접 올릴 수 없고 image_ref(서버측 허용경로/공인URL/data-uri) 문자열을 JSON으로 줘야 함
  → POST /api/v1/analyze/upload 멀티파트 엔드포인트 추가: 업로드된 도면을 ALLOWED_IMAGE_DIR(또는 임시 격리 스토리지)에 저장 후 image_ref로 자동 치환해 run_analysis에 전달. 콘솔 UI에 드래그앤드롭 파일 input과 시트역할 선택 추가. 보안 불변식(경로탈출·SSRF 차단)은 기존 image_source 검증 재사용.


# 설계 제안(관점별 high-value)

## agent_orchestration — 도면/데이터 추출·분류·교차검증을 역할분담된 LLM 에이전트(추출가/검증가/취합가)로 배치하되, 모든 산정/판정 게이트는 결정론으로 유지. 핵심 통찰: 이 엔진에는 '에이전트' 추상이 전무하나(agent|orchestrat|consensus grep 0건), 이미 두 개의 '합의' 원형이 존재한다 — (1) 시트역할 3원 합의(sheet_role_resolver.py:46), (2) 범용 N-출처 합의엔진 CrossSourceValidator(validator.py:25, UNANIMOUS/MAJORITY/CONFLICT/SINGLE/ABSENT). 이 두 합의 패턴을 '비전 추출' 영역으로 일반화하는 것이 멀티에이전트 고도화의 결정론-보존 척추다. LLM은 '추출가/검증가' 역할로 다중화하되, '취합가'는 결정론 합의(CrossSourceValidator 재사용)로 두고, 산정 입력 승계는 calc_target_builder→CalcEngine의 기존 결정론 게이트를 통과시킨다. 비전 비결정성(temperature 미고정·무캐시, drawing_extractor.py:94-124)이 INV-1을 비전 경로에서 깨는 현 상태가 가장 시급한 단일 결함.
- [high/M] 비전 추출 합의 에이전트(N-패스 추출가 + 결정론 취합가) — CrossSourceValidator를 비전 영역으로 일반화: 신규 app/services/extraction/vision_consensus.py + 계약 확장. DrawingExtractor.extract(drawing_extractor.py:60)를 단일호출에서 'K-패스 추출가' 패턴으로 확장: 동일 image_ref에 대해 (a) 비전 추출가 N회(또는 N개 프롬프트 변형/N개 모델), (b) 결정론 힌트 경로, (c) 향후 OCR/IFC 경로의 산출을 요소키(semantic_hint+sheet+근사 bbox)별로 묶어 기존 CrossSourceValidator.validate(validator.py:25)에 SourceValue 리스트로 투입. 합의결과(UNANIMOUS/MAJORITY/CONFLICT/SINGLE)를 ExtractedElement.consensus_status로 승계. 취합가(aggregator)는 LLM이 아니라 _norm 기반 결정론 다수결(validator.py:39-49)을 그대로 재사용 — 즉 '추출가만 LLM, 취합가는 결정론'.
- [high/S] 비전 추출가 결정론화 — temperature=0 + (image_ref+prompt 해시) 응답 캐시로 INV-1을 비전 경로에 복원: AnthropicDrawingVisionClient.extract_elements(drawing_extractor.py:94-124) 및 AnthropicVisionClient.classify_sheet(vllm_sheet_classifier.py:57-83)의 httpx.post json에 temperature=0 추가, 그리고 신규 app/adapters/vision/vision_cache.py(키=sha256(image_bytes+prompt+model), 값=원응답 JSON, TTL/스냅샷 결속)를 호출 앞단에 삽입. snapshot에 추출결과를 고정 저장(재심의 시 동일 입력 재사용).
- [high/M] 비전 area sanity 검증가 에이전트 — outer_area 대비 모순검출 + DualPathCheck 교차검증으로 환각 면적 강등: 신규 app/services/extraction/area_sanity.py: ExtractedElement.area를 (1) area_table outer_area 대비 비율 상한 초과 검출, (2) 제외 area 합 ≤ outer_area 모순검출, (3) 면적표/IFC/2D 적분과 기존 DualPathCheck(dual_path_check.py:23) 교차 — 밴드 초과 시 area를 산정승계에서 제외하고 HELD note. calc_target_builder.build_calc_targets_from_drawing(calc_target_builder.py:11)이 sanity 통과 요소만 excl 후보로 승계하도록 가드 삽입(현재 line 18-22는 area!=None·UNKNOWN제외만 검사, 모순 무검출).
- [high/L] 독립 기하 적분 추출가 추가 — IFC IFCQUANTITYAREA / 2D 폴리라인 슈레이스로 결정론 area 산출, VLLM area는 합의의 1표로만 강등: 신규 app/adapters/bim/ifc_quantity.py(ifcopenshell 선택적 어댑터, ifc_parser.py 계약 유지)로 IFCQUANTITYAREA/storey에서 면적·층 추출, + app/services/extraction/polygon_area.py(폴리라인 경계좌표×scale_denominator 슈레이스 적분). 이 결정론 area를 제안1 합의의 독립 SourceValue로 투입 → VLLM 텍스트 area는 '여러 출처 중 1표'로 강등(1차출처 금지 원칙). preflight scale(scale_unit.py)을 픽셀→실척 환산에 실제 소비(현재 축척은 전제로만 잠기고 면적과 단절).

## multimodal_accuracy — 도면→요소/치수/면적 추출의 정밀도, 이중경로(BIM vs 비전) 대조, 신뢰도 전파, 결손/모호 HELD, dual_path(명기 vs 산정) 실측 연계. 모든 제안은 BASE 경로 하위 실제 file:line 검증 기반. 정정: 현황 매핑의 일부 '갭'은 실제로는 부분 EXISTS임을 확인 — CalcElement는 이미 length/depth/underground/accessory 필드 보유(contracts/legal_quantity.py:56-91), BimElement는 area/length/storey 필드 보유(contracts/bim.py:12-19), cross_sheet_identity/cross_validate/extraction_eval 모두 EXISTS. 진짜 MISSING은 '필드는 있으나 추출·승계 배선이 끊긴' 지점들이다.
- [high/S] ExtractedElement 측정치 확장 + calc_target_builder 제외 측정치 승계 배선: (1) contracts/drawing_extraction.py:40-48 ExtractedElement에 measurements dict(또는 length/depth/underground/accessory 4필드, 모두 Optional, 기본 None) 추가. (2) adapters/vision/drawing_extractor.py:40-51 _from_vision와 :26-37 _from_hints가 VLLM raw / element_hints에서 동일 키를 매핑(미상은 None 유지). (3) AnthropicDrawingVisionClient.extract_elements 프롬프트(drawing_extractor.py:101-107)에 length/depth/underground/accessory 출력 키 추가. (4) services/extraction/calc_target_builder.py:18-22 excl 빌더가 area뿐 아니라 length/depth/underground/accessory를 CalcElement 입력 dict로 함께 전달. CalcElement는 이미 해당 필드 전부 보유(contracts/legal_quantity.py:63-70)하므로 계약 변경 불필요. (5) EAVE/BALCONY/PARKING DRAWING_AUTO 자동경로 회귀테스트 추가.
- [high/L] 결정론 기하 면적 적분기(슈레이스) + IfcParser 정량 추출 — 비전 area를 cross_validate 대상으로 강등: (1) services/extraction/geometry_area.py 신설: 2D 폴리라인/해치 경계좌표 list + scale_denominator → 슈레이스 공식 결정론 면적 적분 함수. (2) adapters/bim/ifc_parser.py:49-65 IfcParser가 IFCQUANTITYAREA/IFCELEMENTQUANTITY 연관을 파싱해 BimElement.area/length/storey 채움(현재 :54에서 IFCQUANTITYAREA를 skip만 함). 무거운 dep 없이 STEP 정규식 확장, ifcopenshell은 선택적 어댑터로 동일 BimModel 계약 주입. (3) services/extraction/dual_path.py:17-26 BIM 경로가 area를 SemanticElement→CalcElement로 승계. (4) VLLM이 답한 area(drawing_extractor.py:48)는 1차출처가 아니라 cross_validate 대상으로 표시(source 메타 'vision_estimate'). 면적표/IFC/2D적분과 교차검증해 밴드 초과 시 강등.
- [high/M] DrawingExtractor에 PreflightContext.scale 주입 — 픽셀/도면길이 → 실척 결정론 환산: services/preflight/scale_unit.py가 산출하는 ScaleResult(scale_denominator, assumed)를 DrawingExtractor.extract(adapters/vision/drawing_extractor.py:60)에 인자로 주입. 비전이 픽셀/도면길이 단위 area/length를 줄 때 scale_denominator로 실척 환산하는 결정론 변환 단계 추가. analysis_pipeline.py에서 현재 도면 추출(0a, line 68-82)이 preflight(R0, line 101-109)보다 먼저 실행되므로, 순서를 조정하거나 scale을 2-pass로 후적용. scale source가 USER/CADASTRAL_CROSSCHECK(assumed=True, scale_unit.py:31-45)이면 환산 결과를 HELD로 강등 표면화.
- [high/M] VLLM 추출 area sanity 게이트 + 면적표/IFC/적분 교차검증 강등: (1) services/extraction/area_sanity.py 신설: ExtractedElement.area에 결정론 sanity 게이트 — outer_area 대비 단일 요소 비율 상한(param 주입), 제외 area 합 ≤ outer_area 모순 검출. (2) 위반 시 해당 요소를 HELD/note로 표면화(임의 드롭 금지). (3) drawing_extractor.py 또는 calc_target_builder.py:18-22 승계 직전에 게이트 삽입. (4) VLLM area를 면적표(area_tables)·IFC area·2D 적분과 CrossSourceValidator(cross_validate/validator.py:24)로 교차검증해 밴드 초과 시 confidence 강등. 임계 param은 data/resolution_parameters.json 주입(area_ratio_max 등 신설).
- [high/M] 도면 멀티파트 업로드 라우트 + PDF→시트 분할 어댑터: (1) api/routes에 POST /api/v1/analyze/upload 멀티파트 엔드포인트 신설(검증: api 디렉터리 grep 결과 upload/UploadFile/multipart 매치 0건 = MISSING). 업로드 파일을 ALLOWED_IMAGE_DIR(image_source.py:19-22가 이미 fail-closed 허용루트 검증)에 격리 저장 후 image_ref로 자동 치환해 run_analysis 전달. (2) adapters/vision/pdf_split.py 신설: PyMuPDF로 멀티페이지 PDF→페이지 이미지 분할 + 페이지별 DrawingSheet 자동 생성(현재 DrawingSheet는 단일 image_ref 1장만, drawing_extraction.py:31). (3) ui/index.html에 드래그앤드롭 파일 input + 시트역할 선택 추가.

## data_pipeline (수집·취합·가공 극대화: 다출처 자동수집·교차검증·1차출처·증분/캐시·신선도·미러 자동적재·코퍼스 벡터화)
- [high/M] 외부 1차출처 응답 캐시 계층(external_source_cache 테이블 + AdapterCache 게이트웨이): 신규 테이블 external_source_cache(컬럼: cache_key[adapter+endpoint+정규화params 해시], adapter, payload JSONB, content_hash, etag, fetched_at, snapshot_id, status)을 r2_models.py에 추가(alembic 0012). app/adapters/cache/source_cache.py에 AdapterCache(get/put, TTL·snapshot 결속) 신설. molit_building.py:39, vworld_geocoder.py:29/53, vworld_landchar/landuse/landprice/building/nearby.py의 직접 httpx.get을 캐시 경유 호출로 교체 — 키 존재+TTL 유효+동일 snapshot이면 DB payload 반환, 아니면 ETag/If-Modified-Since로 변경분만 재호출 후 upsert.
- [high/M] 수집 데이터 DB 영속화 배선(MirrorWriter·Harvester·CorpusIngest에 AsyncSession 주입): mirror_store.py:30의 in-memory _DEFAULT_STORE를 DB-backed store로 교체: MirrorWriter.write(mirror_writer.py:31 self.store.put)와 Harvester.run(harvester.py:25)·CorpusIngest.ingest(corpus_ingest.py:17)에 AsyncSession(db/session.py)을 주입해 mirror_snapshot/source_document/harvest_job 테이블(r2_models.py 이미 존재)에 upsert. 소비측 default_store().get(mirror_store.py:17)을 DB read-only 조회로 교체.
- [high/S] 수집 신선도(as_of/collected_at/max_age) 추적 + 노후 시 NEEDS_REVIEW 표면화: SourceValue(cross_validation.py:15)에 collected_at·data_vintage·max_age_days 필드 추가, LandCard(land_card.py:11)에 collected_at·max_age_days 추가(stdr_year만 있고 수집일자 없음). validator.py:25 합의 산정 직전에 staleness 게이트 삽입 — vintage가 snapshot 기준일(as_of) 대비 max_age 초과 시 해당 SourceValue를 STALE 표시하고 CrossValidation.status를 NEEDS_REVIEW 쪽으로 보수화. 공시지가 기준연도(land_card.py:88 stdr_year) 노후를 note로 표면화.
- [high/L] reconcile_mirror 완결: 라이브 diff→mirror 갱신→영향 finding 재분석 트리거: reconcile_tasks.py:11 reconcile_mirror는 현재 LiveNetwork().get 후 live_ok bool만 반환하는 스텁. (1) LiveNetwork.get(network.py:14)에 공급측 한정 실 httpx 구현 주입, (2) 라이브 1차출처 본문 vs mirror_snapshot 룰 content_hash diff, (3) 불일치 시 mirror_snapshot upsert(새 snapshot_id), (4) 영향받는 finding/citation_check 재분석 트리거(analysis_tasks.analyze_task.delay). celery_app.py는 redis broker·eager 폴백이 이미 구성됨 — 운영은 CELERY_TASK_ALWAYS_EAGER=false+worker로 진짜 비동기.

## user_convenience
- [high/M] 도면 멀티파트 업로드 + PDF 자동 시트분리 진입점 (POST /api/v1/analyze/upload): 신규 라우트 apps/api/app/api/routes/analysis_routes.py에 POST /api/v1/analyze/upload(UploadFile) 추가. 신규 어댑터 apps/api/app/adapters/vision/upload_intake.py: (1) 업로드 파일을 ALLOWED_IMAGE_DIR(image_source._allowed_dir, image_source.py:19) 하위 격리경로에 저장, (2) PDF면 PyMuPDF로 페이지→PNG 렌더링하여 페이지별 DrawingSheet(drawing_extraction.py:27) 자동 생성, (3) 저장경로를 image_ref로 채워 AnalysisInput.drawings(analysis.py:35)에 주입 후 run_analysis 호출. UI index.html:48의 JSON textarea 옆에 drag-and-drop file input + 시트역할 셀렉트 추가. 현재는 UploadFile/File( 사용처가 코드 전역에 전무(grep 0건)이고 image_source.build_image_block(image_source.py:51)은 이미 존재하는 경로/URL/data-uri만 처리해 PDF·파일쓰기 불가 = 사용자가 시트별 이미지를 직접 준비해 JSON으로 image_ref를 손으로 적어야 하는 진입장벽.
- [high/S] ExtractedElement→CalcElement 제외 측정치(length/depth/underground/accessory) 승계 배선: apps/api/app/contracts/drawing_extraction.py:40 ExtractedElement에 length/depth/underground/accessory(또는 measurements dict) 필드 추가(미상=None 유지). drawing_extractor.py:40 _from_vision / drawing_extractor.py:26 _from_hints가 VLLM/힌트의 해당 측정치를 매핑. calc_target_builder.py:18-22 build_calc_targets_from_drawing의 excl dict가 현재 semantic_type/area/confidence만 담는 것을 length/depth/underground/accessory까지 확장해 CalcElement(legal_quantity.py:65-70, 이미 해당 필드 보유)로 승계. EAVE/BALCONY/PARKING 제외가 DRAWING_AUTO 경로에서 정확 산정되도록 회귀테스트 추가.
- [high/M] VLLM 비전 추출 area의 sanity 게이트 + 교차검증 강등(1차출처 보존): apps/api/app/services/extraction/area_sanity.py 신규: ExtractedElement.area에 대해 (1)제외 area 합 ≤ outer_area 모순검출, (2)단일 제외 area/outer_area 비율 상한(param JSON 주입) 초과 시 HELD/note. drawing_extractor.AnthropicDrawingVisionClient.extract_elements(drawing_extractor.py:94)가 부른 area는 1차출처가 아니므로 calc_target_builder 승계 전 cross_validate(services/cross_validate/validator.py)로 면적표/IFC/2D적분과 대조해 밴드 초과 시 강등. analysis_pipeline.py:87 도면 자동 calc_target 구성 직전에 게이트 삽입.
- [high/L] 2D 벡터/IFC 결정론 면적 적분기(shoelace + IFCQUANTITYAREA): apps/api/app/services/extraction/area_integrator.py 신규: (1)2D 폴리라인/해치 경계좌표×scale_unit.py 축척으로 슈레이스 공식 결정론 면적 적분, (2)IFC는 ifcparser.py:54가 현재 skip하는 IFCQUANTITYAREA/IFCELEMENTQUANTITY를 파싱해 BimElement.area·storey(ifc_parser.py:59-64에서 현재 미설정)를 채움. scale_unit.ScaleResult.scale_denominator(scale_unit.py:20, 현재 preflight 전제로만 잠기고 면적산정과 단절)를 DrawingExtractor.extract에 주입해 픽셀/도면길이→실척 환산. VLLM이 부른 area는 cross_validate 대상으로 강등.


# ===== ROADMAP =====

All proposals are now verified against real code. Here is the integrated roadmap.

---

# 심의분석 + 설계도면 자동분석 — 멀티모달 자동분석 고도화 로드맵

> 검증 기준: BASE 하위 실제 file:line 인용. 베이스라인 **337 tests collected**(`pytest --co` 실측). 모든 증분은 결정론 보존·무음0·INV-3(param 주입)·설명가능성을 게이트로 한다.

## 0. 검증 요약 — 무엇이 EXISTS이고 무엇이 진짜 MISSING인가

증분 설계의 전제가 되는 핵심 사실관계를 먼저 고정한다(허위 MISSING 배제).

| 항목 | 상태 | 근거(file:line) |
|---|---|---|
| `CalcElement.length/depth/underground/accessory` | **EXISTS**(필드) | legal_quantity.py:65-70 |
| `BimElement.storey/area/length` | **EXISTS**(필드) | bim.py:17-19 |
| 제외 측정치 → CalcElement 승계 배선 | **MISSING**(excl dict가 area만 전달) | calc_target_builder.py:18-22 |
| `ExtractedElement` 측정치 필드 | **MISSING**(area/quantity만) | drawing_extraction.py:40-48 |
| IfcParser 정량 추출 | **MISSING**(IFCQUANTITYAREA skip) | ifc_parser.py:54 |
| 비전 temperature=0 / 응답 캐시 | **MISSING**(httpx json에 temperature 없음) | drawing_extractor.py:114-116 |
| `scale_denominator` → 면적 환산 소비 | **MISSING**(preflight 전제로만 잠김) | scale_unit.py:20 vs drawing_extractor.py:60 |
| `SimEngine.run_view` 본체 | **EXISTS** | sim_engine.py:25-26 |
| run_view 파이프라인 배선 | **MISSING**(grep 0건) | analysis_pipeline.py:163-170 |
| `CrossSourceValidator`(N-출처 합의) | **EXISTS**(재사용 척추) | validator.py:24-54 |
| `CrossSheetIdentity` / `DualPathCheck` | **EXISTS** | cross_sheet_identity.py:13 / dual_path_check.py:19 |
| Agent/orchestrator/consensus 추상 | **MISSING**(0 파일) | grep 0건 |
| `area_sanity` / `geometry_area` / `vision_consensus` | **MISSING** | services/extraction/ 디렉터리 |
| 멀티파트 업로드 라우트 | **MISSING**(UploadFile 0건) | analysis_routes.py(없음) |
| OCR 추출기 본체(Method.OCR) | **MISSING**(enum·priority만) | enums.py:29, evidence_ledger.py:18 |
| 외부 1차출처 캐시 / static_scan | **MISSING**(디렉터리 없음) | ls 0건 |
| MirrorStore DB 영속화 | **MISSING**(in-memory `_DEFAULT_STORE`) | mirror_store.py |
| `reconcile_mirror` 완결 | **MISSING**(live_ok bool 스텁) | reconcile_tasks.py:11-22 |
| `image_source` 보안가드(SSRF/경로탈출) | **EXISTS**(재사용) | image_source.py:19-48 |
| `param("area_tol"/"length_tol")` | **EXISTS**(INV-3 주입처) | resolution_parameters.json |
| `GoldenItem` area/quantity 기대값 | **MISSING**(item_id/input/expected만) | eval.py:9-13 |
| `AnalysisResult.run_id`(영속 키) | **EXISTS** | analysis.py:69 |

**단일 최시급 결함**: 비전 경로의 비결정성(temperature 미고정·무캐시, drawing_extractor.py:114-116)이 INV-1을 비전 영역에서 깬다. 동시에 비전 area가 1차출처로 무검증 승계된다(calc_target_builder.py:18-22가 sanity 없음). 이 둘이 스토리라인의 출발점이다.

---

## 1. 스토리라인 — 의존성 그래프와 순서 원칙

원칙: **(빠른가치·저난이도) → (정확도 기반공사) → (협업·관측) → (운영·UX)**. 의존선:

```
P-가시성(독립, 즉시)  ─┐
                       ├─► P-멀티모달정확도 ─► P-에이전트(합의) ─► P-데이터/운영
P-멀티모달정확도 기반    │        (측정치·축척·sanity가      (합의는 정확도 출처들이
공사(필드·축척)  ───────┘         합의의 '표'가 됨)            ≥2개일 때 의미)
```

핵심 의존 사실:
- **에이전트 합의(P-에이전트)는 정확도 출처가 ≥2개일 때만 의미** → P-멀티모달정확도(측정치 승계·기하 적분·축척 환산)가 선행이어야 N-패스 비전 + 결정론 기하 + 면적표가 합의의 독립 '표'가 된다.
- **area_sanity는 area_table만으로도 가동**(P-멀티모달정확도 내 조기 가능)이나, IFC/2D 적분 출처가 있으면 교차검증 풀이 채워져 강건해진다.
- **static_scan은 캐시 도입 후에만 의미**(허용 패턴 '캐시 경유'가 존재해야 함).

---

## 2. Phase 그룹과 증분

각 증분: **대상/계약 · 변경 · 불변식 보존 · 결정론/테스트 리스크 · 효과**. `[가치/난이도]` 표기.

---

### Phase P-가시성 (무음 데드패스 제거·즉시 가치, 독립)

선행 의존 없음. 가장 빠른 가치. 베이스라인 비파괴가 거의 확실.

**INC-1 [high/S] view 시뮬 배선 + 미처리 sim_inputs 키 skipped 가드**
- 대상: analysis_pipeline.py:163-170 / 계약 변경 없음(`run_view` EXISTS, sim_engine.py:25-26).
- 변경: `if inp.sim_inputs.get("view"): sim_metrics.append(sim.run_view(inp.sim_inputs["view"]))` 추가. 처리키 집합 `{sunlight,egress,parking,view}` 대비 `inp.sim_inputs.keys()` 차집합을 `skipped.append("sim: 미배선 키 …")`로 표면화.
- 불변식: run_view는 결정론(sim_engine.py:3 주석). 미배선 키 표면화는 무음0 직접 강화.
- 리스크: 거의 없음. view 미입력 시 동작 동일 → 337 비파괴.
- 효과: 무음 데드패스 제거(view 엔진이 호출조차 안 되던 결함). 향후 키 누락 무음화 차단.
- 테스트: `sim_inputs={"view":…}` 시 SimMetric 1건 추가, 미지원 키 입력 시 skipped 포함.

**INC-2 [medium/S] 리포트 사람친화 title/recommendation 매핑(룰→라벨, LLM 없음)**
- 대상: 신규 `services/report/labels.py` + 신규 param `data/rule_labels.json` / 소비처 analysis_pipeline.py:349-373(`items.append`), report_builder.py(title/recommendation 필드 이미 수용).
- 변경: `rule_id/metric_id → {title, recommendation}` 결정론 매핑 테이블. items.append가 `item_id`만 채우던 것을 title/recommendation까지. 매핑 부재 시 `title=None` → UI item_id 폴백 + note.
- 불변식: LLM 아닌 룰→라벨 결정론(INV-1). 라벨은 JSON 주입(INV-3). 부재 표면화(무음 금지).
- 리스크: 낮음. 신규 필드만 채움, 기존 판정 불변.
- 효과: 비전문가 가독성. 설명가능성(사람이 읽는 도출이유).

> **P-가시성 완료 게이트**: 코드리뷰 8차원 ≥4.5 유지(무음 데드패스 0 증명, 신규 라벨 결정론·param 준수). 337 + 신규 테스트 통과.

---

### Phase P-멀티모달정확도 (정확도 기반공사 — 후속 합의/평가의 토대)

이 Phase가 P-에이전트의 선행. "필드는 있으나 배선이 끊긴" 지점부터 메운다.

**INC-3 [high/S] ExtractedElement 측정치 확장 + calc_target_builder 제외 측정치 승계**
- 대상: drawing_extraction.py:40-48(`ExtractedElement`에 length/depth/underground/accessory Optional 추가) · drawing_extractor.py:26-37 `_from_hints`/40-51 `_from_vision`(동일 키 매핑, 미상 None) · drawing_extractor.py:101-107 프롬프트에 출력 키 추가 · calc_target_builder.py:18-22(excl dict에 측정치 4종 추가). CalcElement는 필드 보유(legal_quantity.py:65-70)라 계약 변경 불필요.
- 불변식: 미상=None → CalcElement underground/accessory=None이 HELD 표면화(legal_quantity.py:59-61 기존 규약, 무음 전량제외 금지). 산정은 결정론 CalcEngine, VLLM은 '측정치 수집' 보조. provenance src=vision|hint 보존.
- 리스크: 낮음. None 기본값이라 기존 입력 동작 불변 → 337 비파괴.
- 효과: **EAVE/BALCONY/PARKING 제외가 DRAWING_AUTO 경로에서 정확 산정 가능**(현재는 측정치 소실로 불가). 무음 미흡 제거.
- 테스트: PARKING(underground/accessory)·EAVE(depth)·BALCONY(length) 측정치를 가진 도면 자동경로 → CalcElement에 승계되어 제외 산정 회귀.

**INC-4 [high/M] DrawingExtractor에 PreflightContext.scale 주입(픽셀→실척 결정론 환산)**
- 대상: drawing_extractor.py:60 `extract` 시그니처에 `scale: ScaleResult|None` 추가 · 파이프라인 실행순서(현재 0a 도면추출이 R0 preflight보다 먼저, analysis_pipeline.py:68-82 vs 101-109) → 2-pass(추출 후 scale 후적용) 또는 순서 조정.
- 변경: 비전이 픽셀/도면길이 단위 area/length를 줄 때 `scale_denominator`로 실척 환산하는 결정론 단계. `source=USER/CADASTRAL_CROSSCHECK`(assumed=True, scale_unit.py:31-45)면 환산결과 HELD 강등.
- 불변식: 곱셈 결정론(픽셀×scale²). assumed scale이면 HELD 표면화(무음0). scale_denominator는 입력 산출(하드코딩 금지). 원시 픽셀값·scale·source provenance 동반.
- 리스크: **중**. 파이프라인 순서 변경이 입력해시·skipped 순서에 영향 가능 → 출력 동일성 회귀를 골든 입력으로 고정 검증.
- 효과: 축척이 면적과 결합(현재 단절). INC-5(2D 적분기)의 픽셀 입력 환산 전제.
- 테스트: 동일 픽셀+scale 2회 동일 면적; assumed scale → HELD.

**INC-5a [high/M] IfcParser 정량 추출(IFCQUANTITYAREA → BimElement.area/storey) + dual_path 승계**
- 대상: ifc_parser.py:54(현재 IFCQUANTITYAREA를 skip) → IFCQUANTITYAREA/IFCELEMENTQUANTITY 연관 파싱으로 BimElement.area·length·storey 채움(STEP 정규식 확장, 무거운 dep 없이) · dual_path.py:17-26(BIM 경로가 area를 SemanticElement→CalcElement로 승계).
- 불변식: STEP 파싱은 결정론. IFC 정량 결손은 area=None(UNKNOWN-area) 표면화(무음0). 좌표/IFC 엔티티 ref provenance.
- 리스크: 중(정규식 연관 파싱 정확도). 독립 적용 가능(축척 무관).
- 효과: BIM 있으면 2D 환각·면적표 의존 우회(1차출처 정량). INC-6 합의의 독립 표.

**INC-5b [high/L] 결정론 2D 기하 면적 적분기(슈레이스) — 비전 area를 cross_validate 표로 강등**
- 대상: 신규 `services/extraction/geometry_area.py`(폴리라인/해치 경계좌표 + `scale_denominator` → 슈레이스 적분) · drawing_extractor.py:48의 VLLM area에 `source="vision_estimate"` 메타 부착.
- 불변식: 슈레이스는 순수 결정론(동일 좌표→동일 면적). VLLM area는 1차출처 금지(INV-3)에 따라 cross_validate 입력으로만 강등. 좌표·scale·공식명 provenance(INV-4).
- 리스크: **L**. 좌표 입력 형식 정의·축척 결합 필요 → INC-4 선행 권장. 가장 무겁지만 "VLLM area를 1차출처로 안 쓴다"는 불변식의 핵심.
- 효과: 1차출처 불변식의 정량 척추. INC-6 합의·INC-7 sanity의 독립 출처.

> INC-5는 a(IFC, 독립)와 b(2D, 축척 의존)로 분리 — a를 먼저 머지해 가치 조기 확보.

**INC-6 [high/M] VLLM area sanity 게이트 + 면적표/IFC/2D 교차검증 강등**
- 대상: 신규 `services/extraction/area_sanity.py` · 신규 param `area_ratio_max`(resolution_parameters.json) · 소비처 calc_target_builder.py:18-22 승계 직전.
- 변경: 결정론 부등식 — (1) 제외 area 합 ≤ outer_area, (2) 단일 제외 area/outer_area ≤ `area_ratio_max`. 위반 시 HELD/note(드롭 금지). VLLM area를 면적표·IFC(INC-5a)·2D적분(INC-5b)과 `CrossSourceValidator`(validator.py:24)로 교차검증 → 밴드 초과 시 confidence 강등.
- 불변식: 부등식 결정론(INV-1). 임계 param 주입(INV-3). 위반은 HELD 표면화(무음0). 강등 사유(밴드·대조출처) note(INV-4).
- 리스크: 낮음(area_table 단독으로도 가동). 교차검증부는 INC-5 출처가 있을 때 강건.
- 효과: 환각 면적 무검증 승계 제거(현재 calc_target_builder.py:21은 area!=None·UNKNOWN제외만 검사, 모순 무검출).
- 테스트: 제외합>outer_area → HELD; 비율 초과 → 강등; IFC와 밴드 내 → AGREED.

**INC-7 [medium/M] 다행(multi-row) 면적표 + 층별 calc_target 자동구성**
- 대상: drawing_extraction.py:37 `DrawingSheet.area_table`·:56 `DrawingExtraction.area_tables`를 `rows:[{floor,target,area}]`로 확장(단일 outer_area 1행 호환) · calc_target_builder.py:24-33(층별 → gross_floor_area/far_floor_area target).
- 불변식: 행→target 매핑 결정론. 매핑 테이블 param(INV-3). 미검출 행 빈+note(calc_target_builder.py:14-15 규약, 무음0). 시트·행 provenance.
- 리스크: 중(area_tables 소비처 동반 수정 — INC-6 area_sanity도 area_tables 소비).
- 효과: 연면적/용적률 다행 면적표 자동해석(현재 단일 outer_area→building_area만).

> **P-멀티모달정확도 완료 게이트**: 코드리뷰 ≥4.5(슈레이스/IFC/환산 전부 결정론 증명, VLLM area 강등이 INV-3 충족, 측정치 None→HELD 무음0). 337 + 신규 회귀 통과. 결정론 골든 입력 2회 실행 동일 출력 확인.

---

### Phase P-에이전트 (LLM 역할분담 + 결정론 합의 게이트)

**선행 = P-멀티모달정확도**(합의에 투입할 독립 출처가 ≥2개여야 의미). LLM은 '추출가/검증가', 취합가는 **결정론**(`CrossSourceValidator` 재사용).

**단계별 에이전트 배치 — 어디에 어떤 역할, 산출을 어떻게 결정론 게이트로 합류하나**

| 단계(파이프라인 위치) | 에이전트 역할 | LLM 여부 | 결정론 게이트로의 합류 |
|---|---|---|---|
| 0a 도면추출(analysis_pipeline.py:68) | **추출가**(N-패스 비전) | LLM | 산출을 SourceValue로 변환 |
| 0a 도면추출 | **결정론 추출가**(IFC INC-5a / 2D 슈레이스 INC-5b / 힌트) | 비-LLM | 동일 요소키로 같은 SourceValue 풀에 합류 |
| 0a→P-A.2 사이 | **검증가**(area_sanity INC-6 + cross_sheet_identity.py:13) | 비-LLM | sanity 위반·UNMATCHED → 강등/HELD |
| P-A.2 승계 직전 | **취합가**(aggregator) | **비-LLM**(validator.py:39-49 다수결) | 합의결과 → ExtractedElement.consensus_status |
| 이후 산정/판정 | (에이전트 없음) | 결정론 | 기존 CalcEngine/Evaluator 게이트 그대로 |

**INC-8 [high/S] 비전 추출가 결정론화 — temperature=0 + 응답 캐시(INC-6 합의의 전제)**
- 대상: drawing_extractor.py:114-116 httpx json에 `"temperature": 0` 추가 · vllm_sheet_classifier.py:57-83 동일 · 신규 `adapters/vision/vision_cache.py`(키=`sha256(image_bytes+prompt+model)`, 값=원응답 JSON, TTL/snapshot 결속)를 호출 앞단 삽입.
- 불변식: temperature=0+캐시로 INV-1을 비전 경로에 복원. 캐시 미스/실패는 기존 graceful None 폴백(drawing_extractor.py:124, 무음0). 캐시키에 model·prompt 포함(설명가능성). 산정 게이트 불변.
- 리스크: 낮음·독립 적용 가능. 라이브 키 없으면 동작 동일(키 가드 drawing_extractor.py:95) → 337 비파괴.
- 효과: **INV-1을 비전 경로에 복원**(현재 단일 결함). INC-9/INC-12의 재현성 전제.

**INC-9 [high/M] 비전 추출 합의 에이전트(N-패스 추출가 + 결정론 취합가)**
- 대상: 신규 `services/extraction/vision_consensus.py` · drawing_extraction.py `ExtractedElement.consensus_status` 필드 추가 · drawing_extractor.py:60 extract를 'K-패스' 패턴으로.
- 변경: 동일 image_ref에 (a) 비전 추출가 N회(또는 N 프롬프트/모델), (b) 결정론 힌트, (c) IFC/2D 출력을 요소키(semantic_hint+sheet+근사 bbox)별로 묶어 `CrossSourceValidator.validate`(validator.py:25)에 SourceValue 리스트로 투입. UNANIMOUS/MAJORITY/CONFLICT/SINGLE을 consensus_status로 승계.
- 불변식: 취합가는 결정론 다수결(validator.py:39-49) → 동일 캐시입력(INC-8) 동일 출력(INV-1). CONFLICT/SINGLE은 needs_review 표면화(무음0). by_source/dissent 보존(설명가능성). 합의 임계 param(INV-3).
- 리스크: 중(요소키 정의·N-패스 비용). INC-8(캐시) 없으면 N-패스가 재현 불가 → INC-8 선행 필수.
- 효과: 시트역할 3원 합의(sheet_role_resolver.py)·N-출처 합의(validator.py)를 '비전 추출' 영역으로 일반화. 멀티에이전트 고도화의 결정론-보존 척추.

**INC-10 [medium/M] ✅ 완료 — 추출 오케스트레이터(인라인 비전블록을 명시적 에이전트 파이프라인으로)**
- 대상: 신규 `services/extraction/extraction_orchestrator.py` · analysis_pipeline.py:68-99(0a/P-A.2/0b 인라인)를 `orchestrate_extraction(drawings,ifc,hints)->ExtractionBundle`로 추출.
- 단계: ① 시트역할 합의(SheetRoleResolver 재사용) ② 추출가(INC-9 N-패스) ③ 검증가(INC-6 sanity + cross_sheet_identity.py) ④ 결정론 취합가 ⑤ calc_target 승계. 각 단계 타이밍·강등사유를 `ExtractionBundle.trace`로 노출.
- 불변식: 순서·입력 불변 리팩터 → 출력 동일성(INV-1). 단계 skipped/강등 trace 표면화(무음0). step provenance 누적.
- 리스크: 중(대형 함수 리팩터). 골든 입력 출력 동일성으로 회귀 고정.
- 효과: 에이전트 협업 실체화 + 관측성. INC-9·INC-6을 단계로 흡수.
- **구현 노트**: 6단계(role_resolve/extract/aggregate/calc_target/dual_path/verify). 취합가④=`merge_with_consensus`(CrossSourceValidator, LLM 미관여). 단일 패스는 SINGLE(원순서·값 보존, consensus_status 메타만 — to_pipeline_elements/calc_target 비소비). N-패스는 `vision_consensus_passes`(기본 1) param + 비전 경로만. `extraction_trace`는 timing 제외 결정론 투영(완전동치 보존). cross_sheet③은 관측만(값 미변형, 단일시트 n/a). skipped 문자열·순서 인라인과 byte 동일.

> **P-에이전트 완료 게이트 ✅ 충족**: 적대적 다관점 리뷰(behavior 4.7·gate 4.7·quality 4.5, min 4.5 ≥4.5) — 취합가 LLM 미관여 코드증명·캐시키(sha256 model‖image_ref‖prompt) 설명가능성·CONFLICT→needs_review(trace status + skipped) 무음0·합의 결정론 동일입력 2회 동일 확인. **370 passed**(362→+특성화2+오케스트레이터6), ruff clean, static_scan 0. 10개 엣지 입력 byte 동일(0 mismatch).

---

### Phase P-데이터 (수집·취합·신선도·캐시·운영 영속화)

P-가시성과 병렬 착수 가능하나, static_scan(INC-15)은 캐시(INC-11) 선행.

**INC-11 [high/M] ✅ 완료 — 외부 1차출처 응답 캐시 계층(source cache 테이블 + AdapterCache)**
- 대상: 신규 `external_source_cache` 테이블(alembic 신규: cache_key=adapter+endpoint+정규화params 해시, payload, content_hash, etag, fetched_at, snapshot_id, status) · 신규 `adapters/cache/source_cache.py`(get/put, TTL·snapshot 결속) · molit_building.py / vworld_*.py / law_go_kr.py의 직접 httpx.get을 캐시 경유로.
- 불변식: 캐시는 데이터 확보 단계만 — 적중 후 동일 입력→동일 출력(결정론 영향 0). 미스/만료는 재호출→실패 시 기존 graceful None(무음0). payload에 ref/etag/fetched_at 보존(1차출처·설명가능성). snapshot_id 결속(재현성).
- 리스크: 중(7개 어댑터 호출부 교체·DB 세션). 라이브 키 없는 테스트는 캐시 미스→기존 경로라 337 비파괴.
- 효과: 분석마다 재호출(쿼터/지연/비용) 제거. INC-12 신선도·INC-15 static_scan의 토대.
- **구현 노트**: sync 어댑터 ↔ async DB 경계 분리 — **L1 프로세스 인메모리**(어댑터 sync 경로, 결정론) + **L2 DB 영속**(`warm_from_db`/`flush_to_db`를 async `analyze` 라우트 경계에서 호출, snapshot 결속). 공유 `cached_get(adapter,url,params,secret_param_keys,...)` 헬퍼로 8개 어댑터 일괄 경유(원 httpx 시그니처/예외 보존 — headers 조건부, etag 방어적). **secret(OC/key/serviceKey)는 cache_key·DB에서 제외**(비유출). jurisdiction/vworld.py는 계약 상이(AdapterTimeout)로 제외. 적대적 리뷰 통과(gate 4.8/determinism 8.7/quality 8.5) — LOW 3건(flush dirty-clear는 commit 후로·만료 eviction·warm rollback) 반영. **379 passed**(370→+INC-11 9), ruff clean, static_scan 0, alembic 0013 up/down 가역.

**INC-12 [high/S] ✅ 완료 — 수집 신선도(collected_at/data_vintage/max_age) + 노후 NEEDS_REVIEW**
- 대상: cross_validation.py `SourceValue`에 collected_at·data_vintage·max_age_days · land_card.py `LandCard`에 collected_at·max_age_days · validator.py:25 합의 직전 staleness 게이트.
- 변경: vintage가 snapshot 기준일(as_of) 대비 max_age 초과 시 SourceValue STALE 표시 + CrossValidation.status를 NEEDS_REVIEW 보수화. 공시지가 stdr_year 노후 note.
- 불변식: 메타 비교 결정론. 노후→무음 사용 아닌 NEEDS_REVIEW 표면화(무음0 연장). vintage/collected_at provenance(설명가능성).
- 리스크: 낮음. INC-11 fetched_at을 collected_at으로 승계 시 시너지(독립 가능).
- 효과: 오래된 공시지가/대장 무표면화 제거.
- **구현 노트**: `SourceValue.is_stale(as_of)`(data_vintage→collected_at 우선, max_age_days 초과; wall-clock 미사용 결정론) + `CrossValidation.stale_sources`·`needs_review`에 stale 포함. `validate(...,as_of=None)` — **as_of None이면 미평가(후방호환, vision_consensus 무영향)**, status는 합의 결과 정직 보존(노후를 CONFLICT로 위장 안 함). 파이프라인 cross_facts가 `as_of=application_date` 전달, landprice SourceValue에 data_vintage(land_year)/max_age 730. `LandCard.is_stale(as_of)`(stdr_year 기준) + collect_land_card 노후 note(max_age 365 동일 임계). 적대적 리뷰 4.7(gate_pass) — LOW(LandCard dead 필드) 해소(collected_at 제거·is_stale로 max_age 소비). **385 passed**(379→+6), ruff clean, static_scan 0.

**INC-13 [high/M] ✅ 완료 — 수집 데이터 DB 영속화(MirrorWriter/Harvester/CorpusIngest에 AsyncSession)**
- 대상: mirror_store.py `_DEFAULT_STORE`(in-memory)를 DB-backed로 · MirrorWriter.write·Harvester.run·CorpusIngest.ingest에 AsyncSession 주입(mirror_snapshot/source_document/harvest_job 테이블, mirror_store.py 주석상 0005 존재) · 소비측 `default_store().get`(analysis_pipeline.py:195)을 DB read-only 조회로.
- 불변식: 소비측 read-only get(INV-13 라이브 미호출 유지). ACTIVE-only 적재(미승인 룰 비노출). snapshot_id/content_hash 재현성.
- 리스크: 중(세션 인프라). 테스트는 in-memory 폴백 유지로 337 비파괴.
- 효과: 프로세스 재시작 휘발 제거·다중워커 공유.
- **구현 노트**: INC-11 warm 패턴 재사용 — **L1 in-memory(MirrorStore, 폴백/테스트) + L2 DB(mirror_snapshot)**. mirror_store에 async write/load/`warm_mirror_from_db`, analyze 라우트가 warm(DB→in-memory) → **소비측 run_analysis 불변**(default_store().get 그대로, INV-13 read-only). MirrorWriter.persist_to_db·CorpusIngest.persist_to_db(async). 공급측 `supply/db_persist.py`(source_document/precedent_case upsert, emit INV-23). 적대적 리뷰(inv13 8.5·persist 8.2·quality 7.5, gate_pass) — 확인 3건 해소: **(HIGH)** run_harvest_job asyncio.run 글로벌 엔진 교차루프 무음실패 → 일회용 NullPool 엔진+실패 로깅; **(MED)** mirror_snapshot 동시writer 중복 → **alembic 0014 (jurisdiction,snapshot_id) 유니크 + on_conflict_do_nothing**(원자 멱등); **(LOW)** MirrorStore 상한+harvest 회귀 테스트. **391 passed**(385→+6), ruff clean, static_scan 0, alembic 0014 up/down 가역.

**INC-14 [high/L] ✅ 완료 — reconcile_mirror 완결(라이브 diff→미러 갱신→영향 finding 재분석)**
- 대상: reconcile_tasks.py:11-22(현재 live_ok bool 스텁) · network.py LiveNetwork.get에 공급측 한정 실 httpx 주입 · 라이브 본문 vs mirror_snapshot content_hash diff · 불일치 시 새 snapshot_id upsert · 영향 finding `analyze_task.delay` 트리거.
- 불변식: 라이브는 reconcile(공급측)에서만(INV-13). 미러 갱신은 새 snapshot append(기존 불변, 재현성). 재분석=동일입력 재실행(결정론). content_hash 전후 보존(설명가능성).
- 리스크: L(broker·LiveNetwork 실구현·INC-13 의존). 운영 배선 비중 큼.
- 효과: 주기 수집·정합 실가동.
- **구현 노트**: alembic **0015**(mirror_snapshot.content_hash + analysis_run.input_payload, nullable·가역) · MirrorSnapshot 계약/write·load store에 content_hash 배선 · **LiveNetwork.get** env 게이트(`LIVE_NETWORK`, 기본 mock; True 시 실 httpx, follow_redirects=False) · **reconcile_mirror_db**(미러 로드→content_hash diff→불일치 시 결정론 snapshot_id(`rcl-<hash[:16]>`)로 append 멱등→영향 run(input_payload.pnu) 조회→reconcile_log) · **reconcile_mirror**(라이브 게이트·default_store put·중복제거+상한(`RECONCILE_MAX_REANALYZE`) 후 reanalyze_task 디스패치, citation_ref urlencode) · **reanalyze_task**(새 미러 warm(H1)→동일입력 run_analysis→결과 영속(H2), NullPool 교차루프 안전) · **reconcile_all**+celery **beat_schedule**(distinct 관할 fan-out, `RECONCILE_INTERVAL_SECONDS`). 적대적 리뷰(결정론·INV13 6.5·영속/멱등 5.5→해소후·무음실패/품질 6.0, gate_pass) — 확인 5건 해소: **(HIGH)** 다중워커 재분석 stale 미러 → reanalyze_task가 DB warm; **(HIGH)** 재분석 결과 미영속(fire-and-forget) → save_analysis append; **(MED)** snapshot_id 주입 input_hash 변경/rules verbatim=라벨회전 → docstring 정직 정정(rule 재파싱은 재하베스트 후속 명시); **(MED)** citation_ref 미인코딩 URL 인젝션 → urlencode+follow_redirects=False; **(MED)** 재분석 fan-out 무상한 → dedup+상한 절단 로깅. **한계(정직)**: content_hash diff는 본문 변화만 탐지(rules 재파싱=하베스트 몫), reanalysis lineage(old→new run) 후속. **검증**: 신규 AT 18(reconcile 14+live_network 3+input_payload 1) + 전체 **414 passed**(396→414, skipped 0), ruff clean, static_scan 0, live_call_scan 그린, alembic 0015 down→up 가역. **운영 잔여**: 실 worker+redis(beat)·LIVE_NETWORK=on+실 law.go.kr 연동(키/배선).

**INC-15 [medium/S] ✅ 완료 — INV-13 정적검사(regulation/land/cross_validate 소비경로 + 캐시 경유 강제)**
- 대상: 신규 `services/static_scan/live_call_scan.py`(현재 부재) · 스캔 대상에 adapters/regulation·services/land·services/cross_validate 포함, '키 가드+graceful None+AdapterCache 경유'를 허용 패턴, 캐시 우회 직접 httpx.get을 위반으로.
- 불변식: 정적검사가 INV-13 무음 라이브 차단을 코드화(결정론·무음0 강화).
- 리스크: 낮음. **INC-11 선행 필수**(허용 패턴 '캐시 경유'가 존재해야).
- 효과: 소비경로 무라이브 보증 범위 확대.
- **구현 노트**: AST 스캐너 `tools/live_call_scan.py`(기존 tools/static_scan.py 선례 위치) — 소비경로의 직접 `httpx.*`/`requests.*` 네트워크 호출 탐지(별칭 import 미탐 한계 명시). 강제 테스트 `tests/acceptance/test_live_call_scan.py`가 **adapters/regulation·adapters/legal·services/land·services/cross_validate** 스캔→위반 0 + 스캐너 자기검증 4(탐지·cached_get 허용·allowlist). 프로덕션 코드 변경 0(dev/CI 가드). 현 소비경로는 INC-11로 전부 cached_get 경유라 위반 0. **396 passed**(391→+5), ruff clean.

**INC-16 [medium/M] 아웃바운드 공통 래퍼(retry+백오프+토큰버킷 RPS+서킷브레이커)** *(선택, 운영 강건)*
- 대상: 신규 `adapters/http_client.py robust_get` · 7개 어댑터 개별 httpx.get(각 15s)을 단일 경유로. 불변식: 전송 계층만(결정론 영향 0), 재시도 소진 후 기존 graceful None(무음0). 효과: 쿼터 보호·회복력. INC-11과 결합 시 최적.

> **P-데이터 완료 게이트**: 코드리뷰 ≥4.5(캐시가 결정론 무영향 증명, 신선도 NEEDS_REVIEW 무음0, INV-13 정적검사 그린). 337 + 신규 통과.

---

### Phase P-UX (업로드·OCR·평가·스트리밍)

업로드(INC-17)는 즉시 가치이나 PyMuPDF 의존 추가가 있어 별도 Phase. OCR/평가는 정확도 Phase 산출에 의존.

**INC-17 [high/M] 도면 멀티파트 업로드 + PDF→시트 분할**
- 대상: 신규 POST `/api/v1/analyze/upload`(analysis_routes.py, UploadFile 0건=MISSING) · 신규 `adapters/vision/upload_intake.py`(PyMuPDF로 PDF 페이지→PNG, 페이지별 DrawingSheet 자동생성) · 업로드를 ALLOWED_IMAGE_DIR 격리저장 후 image_ref 치환 · ui/index.html 드래그앤드롭+시트역할 셀렉트.
- 불변식: 경로탈출·SSRF는 image_source.py:25-48 재사용(fail-closed). PDF 분할 결정론(페이지 순서 고정). 암호화/실패 PDF note(무음0). 산정 게이트 무관(수집 보조). 원본 파일명·페이지 인덱스 provenance.
- 리스크: 중(PyMuPDF 의존). 미설치 환경 graceful degrade 필요.
- 효과: 사용자가 시트별 이미지를 손으로 JSON에 적던 진입장벽 제거. **편의성 최대 갭 해소.**

**INC-18 [medium/L] 결정론 OCR 어댑터(Method.OCR 본체)**
- 대상: 신규 `adapters/vision/ocr_reader.py`(tesseract/paddleocr로 표제란·면적표 셀·치수 숫자) → Method.OCR(enums.py:29) 실제 소비(현재 priority만, evidence_ledger.py:18) · titleblock_reader.py가 OCR 텍스트 입력 · pdfplumber/ezdxf 텍스트 레이어 1차, OCR 폴백.
- 불변식: 텍스트 레이어 1차(INV-3), VLLM은 분류·의미부여 보조. 숫자→정량 결정론 규칙(INV-1). 저신뢰 HELD/UNKNOWN(element_classifier 패턴, 무음0). 셀 좌표·원시텍스트 provenance.
- 리스크: L(OCR 의존·정확도). INC-17 전처리 공유.
- 효과: 숫자 정량 결정론화로 INV-1 강화. INC-7 다행 면적표 셀 인식 결합 시 극대화.

**INC-19 [medium/M] 라이브 비전 면적/수량 골든셋 + extraction_eval 정량 회귀바 CI 승격**
- 대상: data/eval/golden_set.json에 area/quantity 기대값+허용오차(area_tol/length_tol 재사용, eval.py:9-13 GoldenItem 확장 필요) · extraction_eval.py:18-48에 area MAE/허용밴드 통과율·합의상태 분포(UNANIMOUS율) → EvalReport · CI 게이트.
- 불변식: 평가는 결정론 골든셋 대비(extraction_eval.py:18-38 패턴). 허용오차 param(INV-3). 라이브 측정은 산정 게이트와 분리(관측 전용). MAE·밴드 통과율 명시(설명가능성). 무음 오판을 precision/recall로 수치화(무음0 정량 보증).
- 리스크: 중(GoldenItem 확장·실 도면 라벨링). INC-5(면적 산출)·INC-6(sanity)·INC-9(합의)가 측정 대상 생성 → 후행.
- 효과: 라이브 경로 품질을 수치로 보증(현재 운영 전 미지수).

**INC-20 [medium/M] 계층별 진행 SSE + analysis_run status/progress** *(선택, 장기 실행 UX)*
- 대상: run_analysis(analysis_pipeline.py:54, ~388줄)를 `step(name,fn)`로 분해 · analysis_store status/progress 컬럼 · GET `/api/v1/analyze/{run_id}/events`(SSE) · async 경로(analysis_routes.py:39)에 진행·취소.
- 불변식: 스텝 분해는 순서·입력 불변(출력 동일성·결정론 유지). per-step skipped 일원화(무음0 강화). step_durations 진단 필드(산정 무관).
- 리스크: 중(대형 리팩터). 골든 출력 동일성 회귀 필수. INC-13 영속 status 의존.
- 효과: 진행 추적·관측성. INC-10 오케스트레이터와 결합 시 step 일원화.

> **P-UX 완료 게이트**: 코드리뷰 ≥4.5(업로드 보안가드 재사용 증명, OCR 텍스트 1차·결정론, 평가가 산정과 분리). 337 + 신규 통과. PyMuPDF/OCR 미설치 환경 graceful degrade 확인.

---

## 3. 권장 머지 순서(요약 스토리라인)

```
1. INC-1, INC-2            (P-가시성 — 즉시, 독립, 저리스크)
2. INC-3                   (측정치 승계 — 저난이도 high value)
3. INC-8                   (비전 결정론화 — 단일 최시급 결함, 독립)
4. INC-4 → INC-5a → INC-5b (축척 환산 → IFC 정량 → 2D 적분)
5. INC-6, INC-7            (area sanity·교차검증 → 다행 면적표)
6. INC-9 → INC-10          (비전 합의 에이전트 → 오케스트레이터)
7. INC-11 → INC-12, INC-13 (캐시 → 신선도·영속화)   [P-가시성과 병렬 가능]
8. INC-15, INC-16, INC-14  (static_scan → 래퍼 → reconcile 완결)
9. INC-17                  (업로드 — 편의성 최대 갭)
10. INC-18, INC-19, INC-20 (OCR → 정량 평가바 → SSE)
```

## 4. 횡단 불변식 게이트(모든 증분 공통)

- **결정론**: 산정/판정 게이트는 LLM 미관여. LLM(추출가/검증가)은 '추출·분류·수집'만, 취합가는 `CrossSourceValidator`(validator.py 결정론 다수결). 비결정 소스(비전)는 INC-8(temperature=0+캐시)로 재현성 복원 후에만 합의/평가에 투입.
- **무음0**: 미상→None→HELD/UNKNOWN/NEEDS_REVIEW/skipped 표면화. 드롭 금지. 미처리 키 차집합 가드(INC-1).
- **INV-3**: 모든 임계(area_ratio_max·max_age·합의임계)는 resolution_parameters.json/param() 주입. 코드 리터럴 0건(parameters.py:1-5 규약).
- **설명가능성**: 모든 산출에 provenance(좌표·scale·공식·출처ref·캐시키·합의 by_source/dissent) 동반.
- **베이스라인**: 매 증분 `pytest --co`=337 비파괴 + 신규 테스트. 결정론 증분은 골든 입력 2회 실행 동일 출력으로 회귀 고정.

---

### 검증 메모(파일 미확인 제안 배제 결과)
모든 (A)/(B) 제안을 BASE 하위 실코드로 대조했다. (B) multimodal_accuracy의 "정정"(CalcElement·BimElement 필드 EXISTS, 배선만 MISSING)은 **정확**하다(legal_quantity.py:65-70, bim.py:17-19, calc_target_builder.py:18-22, ifc_parser.py:54). agent/cache/static_scan/upload/OCR-body/vision_consensus/area_sanity/geometry_area는 **진짜 MISSING**(grep/ls 0건). `run_view`는 EXISTS(sim_engine.py:25)이나 파이프라인 배선 MISSING(grep 0건) — (A)의 "무음 데드패스" 진단이 옳다. 베이스라인 테스트 수는 실측 337로 프롬프트와 일치. 사실근거 없는 제안은 발견되지 않아 추가 배제 항목은 없다.

핵심 인용 파일(절대경로): `\\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI_deliberation\propai-platform\services\deliberation-review\apps\api\app\` 하위 — `services\pipeline\analysis_pipeline.py`, `services\extraction\calc_target_builder.py`, `adapters\vision\drawing_extractor.py`, `contracts\legal_quantity.py`, `contracts\drawing_extraction.py`, `adapters\bim\ifc_parser.py`, `services\preflight\scale_unit.py`, `services\cross_validate\validator.py`, `services\sim\sim_engine.py`, `adapters\vision\image_source.py`, `core\parameters.py`, `services\eval\extraction_eval.py`, `supply\mirror\mirror_store.py`, `tasks\reconcile_tasks.py`.