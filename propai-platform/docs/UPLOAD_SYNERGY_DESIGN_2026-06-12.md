# CAD 도면 업로드 상호연동 설계 (2026-06-12)

> 목적: **DXF/IFC 1회 업로드 → 편집(CAD2.0)·설계심사·건축문법검증·템플릿DB 4곳이 같은 도면 데이터를 공유**하는 연동 허브.
> 원칙: additive·하위호환, shapes[]가 단일 표준 표현(추가 정규화 없음), 결정론(LLM 0), 정직 표기(실명 날조·가짜값 금지), arch_grammar.py는 읽기전용(import만).

## 0. 현재 배선 진단 (코드 근거 확정)

- 업로드 진입점: `design_v61.py:765` import_dxf → `dxf_import_service.parse_dxf_to_shapes` 가 `{shapes:[{kind,layer,source_layer,points,closed,text}], unit, scale_px_per_m, main_outline_index, ignored}` 반환. 영속은 `design_v61.py:470` save_drawing(design_versions.design_data_json.shapes).
- **확정 버그 ①(키 불일치)**: 프론트 `cad-shapes.ts:316` dxfImportToShapes는 `result.polylines`를 읽는데 백엔드는 `result.shapes`를 반환 → **DXF 가져오기가 항상 빈 결과**.
- **확정 버그 ②(run() 부재)**: 라우터 `design_audit.py:297`은 `orchestrator.run(db,site,params,geometry,ifc_file_url)`을 호출하나 실 `DesignAuditOrchestrator`엔 `audit()`(194행)만 존재 — `test_design_audit_api.py`의 _FakeOrchestrator.run으로만 테스트 통과, **라이브 503**.
- 템플릿: `{ref}/geometry`(design_references.py:210)는 업로드 shapes가 아니라 원본 DXF를 dxf_to_geometry로 재파싱(우회). from-design만 normalize_geometry 사용.
- 문법검증: `extract_boundaries(rooms,...)`(unit_plan_generator.py:337)는 축정렬 사각 rooms(name,x,y,w,h)+한글 실명 전제 — 임의 폴리곤 미수용.
- 결론: 편집·템플릿은 부분연동, **심사·문법은 미연동**.

## 1. 설계 핵심

A) **연동 허브** `cad_upload_hub.py`(신규): `distribute(parse_result)` → 4소비형 결정론 분배
   - editing_shapes(sanitize) / geometry_payload(normalize_geometry 재사용) / design_raw(닫힌 polygon→surface, 정점→points, 변→lines, id 자동) / rooms(역추출기) / params_hint(main_outline bbox→building_width/depth_m, 면적합→building_area_sqm, source='도면추정', brief 하위우선) / diagnostics. 멱등·외부호출 0.

B) **shapes→rooms 역추출기** `shapes_to_rooms.py`(신규):
   - 실 후보 = 닫힌 polygon(정점≥3, shoelace>1.0㎡). 라벨 point-in-polygon 귀속 → room_type_of(text). 미라벨은 면적·위치 휴리스틱(최대면적→거실, <4㎡ 습식위치→욕실) + name '실(추정)'·inferred=True·confidence — **한글 실명 날조 금지**.
   - 비사각 처리: polygon→bbox 사각 근사하되 원본 polygon·실면적(area_sqm) 보존(면적은 폴리곤 실값, 경계추출만 bbox).
   - bbox 타일링은 extract_boundaries 전제와 안 맞으므로 `boundaries_from_bbox_rooms(rooms,tol)`로 공유변 자체 판정 → BOUNDARY_SCHEMA dict 생성(외곽=room_b None) → classify_boundaries·place_openings·validate_connectivity 재사용. 갭은 warnings 정직 보고.

C) **설계심사 DXF 입력**: run-upload에 dxf_file 추가 → parse→hub.distribute → design_raw를 geometry, rooms를 grammar, params_hint를 brief 미입력 보완(기존값 우선). + **orchestrator.run() 어댑터 신설**(버그② 해소): site에서 zone_type·sigungu·address·pnu, ifc_file_url→params_from_ifc 병합 후 audit() 위임, verdict 영문 별칭(부적합 fail/조건부적합 conditional/적합 pass).

D) **문법검증 연동**: audit()에 rooms 파라미터(기본 None) → 9번째 grammar 섹션(additive). LDK 오픈·연결성·채광창 결과를 AuditFinding(engine='grammar')로 findings 결합, 리포트 S5 핑거·S6 경고. rooms 없으면 skipped. 기존 8엔진·overall 결정론 불변.

## 2. 작업 항목 (WI-1~10)

| ID | 제목 | 파일 | 리스크 | 의존 |
|---|---|---|---|---|
| WI-1 | shapes→rooms 역추출기 | services/cad/shapes_to_rooms.py + tests/test_shapes_to_rooms.py | M | — |
| WI-2 | bbox 경계 어댑터(boundaries_from_bbox_rooms) | shapes_to_rooms.py | H | WI-1 |
| WI-3 | 연동 허브 distribute() | services/cad/cad_upload_hub.py + tests/test_cad_upload_hub.py | M | WI-1,2 |
| WI-4 | orchestrator.run() 어댑터(라이브 503 수정) | design_audit_orchestrator.py + test_design_audit_core.py | H | — |
| WI-5 | 심사 grammar 9번째 섹션 | design_audit_orchestrator.py | M | WI-2 |
| WI-6 | run-upload dxf_file 수용+허브 배선 | routers/design_audit.py + test_design_audit_api.py | M | WI-3,4,5 |
| WI-7 | _build_report_sections grammar 핑거+RunRequest rooms | routers/design_audit.py | L | WI-6 |
| WI-8 | DesignAuditWorkspace DXF 슬롯 활성화 | DesignAuditWorkspace.tsx | L | WI-6 |
| WI-9 | 템플릿 등록 shapes 경유 정합(우회 제거, dxf_to_geometry 폴백 보존) | routers/design_references.py + test_template_assembly.py | L | WI-3 |
| WI-10 | import-dxf 키 불일치 수정(shapes 1차·polylines 폴백) | cad-shapes.ts + CADEditor.tsx + cad-shapes.test.ts | M | — |

> WI-9는 1차 구현 웨이브(6병렬)에 미포함 — 후속 보강 후보.
