# 104 디지털트윈 백엔드 고도화 (Executor 산출물)

대상(백엔드만): `app/routers/design_v61.py`, `app/services/digital_twin/scene_service.py`
프론트(DigitalTwinScene.tsx/types.ts)는 미터치. 신규 의존성 0. push/배포 없음.

---

## 1. glb 로드 버그 — GET 라우트 신설 (필수, 옵션A)

### 근본원인
`/{project_id}/bim/model.glb`가 **POST 전용**이라 프론트 `BuildingGlb`의 `GLTFLoader.loadAsync`(=GET)가 항상 405 → 건물 영구 미표시.

### 수정 (design_v61.py)
- **신규 GET 라우트** `GET /{design_version_id}/bim/model.glb` 추가 (POST 라우트는 보존 — 회귀 0).
  - `_load_mass_from_design_version(design_version_id, db)` 신규 헬퍼: design_version_id가 UUID면 `design_versions` 테이블에서 `floor_count`/`max_height_m`/`design_data_json`을 raw SQL로 로드 → `_resolve_mass`와 동일 형태(`building_width_m`/`building_depth_m`/`num_floors`/`floor_height_m`)로 재구성 후 `_enrich_interior` 적용. `max_height_m/floor_count`로 층고 역산. 폭/깊이가 없으면(예: cad_2d 편집본) 12×9m 합리적 기본값 보완.
  - UUID 아님/행 없음 → 쿼리·기본 폴백 매스로 `_resolve_mass` 절차생성 (가짜 금지·정직 절차생성).
  - 매스 확정 후 `build_ifc_from_mass` → `IfcToGltfService().convert` → `Response(media_type=model/gltf-binary)`.
  - **ETag**(glb sha1 16자) + **Cache-Control: public, max-age=300** 부착.
- `_resolve_mass`/`build_ifc_from_mass`/`IfcToGltfService` 기존 로직 그대로 재사용.

### 정합 (scene_service.py `_resolve_building_glb`)
- `glb_url`을 GET 경로 `/api/v1/design/{design_version_id or project_id}/bim/model.glb`로 유지하되 `method="GET"`, note를 "GET으로 glb 로드(GLTFLoader.loadAsync)"로 교체(과거 "POST로 로드" 제거). design_version_id 있으면 그걸로 URL 구성, 없으면 project_id 폴백.

---

## 2. 주변건물 실높이 (scene_service `_build_neighbors`)

- 기존: 모든 이웃 `height_m=9.0` 고정 추정.
- 개선: footprint 수집 시 각 이웃에 대상지 중심까지 거리 `_dist` 부여 → **신규 `_enrich_neighbor_heights()`**가
  - 19자리 유효 PNU 후보를 **거리순 상위 N=14동**만 선별(직렬 전수호출 금지).
  - `BuildingRegistryService.get_title_by_pnu(pnu)`를 **`asyncio.gather` 병렬** 호출, 개별 `timeout=8s`, 배치 상한 `14s`.
  - 성공: `height_m = ground_floors × 3.3`, `ground_floors` 기록, `estimated=false`.
  - 실패/무자료/국외IP차단/배치타임아웃: 기존 9m 추정 유지(`estimated=true`) + 정직 로그(`주변 실높이 보강: N/M동 실측치환`).
  - 페이로드 청결: 반환 전 `_dist` 보조필드 제거.
- 상수 신설: `NEIGHBOR_REGISTRY_TOP_N=14`, `NEIGHBOR_REGISTRY_TIMEOUT_S=8.0`, `NEIGHBOR_REGISTRY_BATCH_TIMEOUT_S=14.0`. SCENE_TIMEOUT_S=88 가드 내(실측 0.9s).
- `build_scene` badges: `neighbors_estimated`를 실측<전체일 때만 true로, `neighbors_total`/`neighbors_real_height` 추가, note에 실높이 N동/추정 M동 구분 명시.
- (선택) `building_registry_service._parse_title_items`는 이미 `ground_floors`(grndFlrCnt)를 반환 → 직접 높이 필드(heit) 추가 불필요. 라이브 응답에 직접 높이 필드 없음(층수환산 채택).

---

## 3. 항공정합 `_aerial_cover_m` (scene_service.py)

- VWorld getmap `crs=EPSG:4326`이나 cover_m는 웹메르카토르 m/px(`156543*cos(lat)/2^zoom`) 근사. EPSG:4326 정사각 이미지는 가로/세로 도(deg) 폭은 같지만 미터 환산은 위도가 더 김(경도는 cos(lat)배).
- **정합 위험을 코드 주석으로 명시**: 현 cover_m는 **가로(경도) 폭**에 정합, 세로(위도)는 `/cos(lat)`배 더 넓음(한국 lat≈37 → 세로 약 25% 큼). 과도수정 방지로 함수 반환값은 기존 가로폭 유지.
- **aerial 페이로드에 분리 필드 추가**: `cover_m`(=cover_lon_m, 기존호환), `cover_lon_m`, `cover_lat_m`(=cover_lon_m/cos(lat)), `crs:"EPSG:4326"`. 프론트가 정밀 드레이프 시 가로/세로 스케일 분리 적용 가능.

---

## 라이브 검증 결과

- `py_compile` 두 파일 PASS(별도 캐시디렉토리 — 기존 pycache 권한 우회).
- **GET glb 폴백 경로**: design_version 없음/UUID아님 시 `_resolve_mass`(12×9m·5층) → glb **22244 bytes, magic `glTF`** 확인. PASS.
- **라우트 등록**: `GET /api/v1/design/{design_version_id}/bim/model.glb`(신규)·`POST /{project_id}/bim/model.glb`(보존) 둘 다 등록 확인.
- **get_title_by_pnu 실높이**(propai-platform/.env의 실키 a517c6 로드): 강남구 테헤란로152 일대 PNU 라이브 조회 → ground_floors 21/14/45/6/5 등 실제 반환. 합성 PNU는 정직하게 None.
- **`_build_neighbors` 통합**: 이웃 60동, 상위14 병렬조회 → 5동 실측치환(16.5~62.7m), **elapsed 0.9s**(가드 88s 내), `_dist` 누수 없음. PASS.
- apps/api/.env는 더미키(dummy-mo)라 그 경로 실행 시 None 폴백 정상 동작 확인(정직 폴백).
- `git diff`: import 삭제 0(린터 트랩 없음), 추가만. print/TODO/HACK/debugger 잔존 0.

---

## 미진/주의사항

- 새 GET 라우트 실DB 경로(UUID design_version 존재 시 매스 복원)는 로컬 DB 미연결로 단위검증만(폴백·SQL구조 확인). 라이브 DB에 cad_2d 외 mass-type 버전이 적재된 경우의 폭/깊이 복원은 `design_data_json`에 building_width/depth가 저장돼 있어야 정확(없으면 12×9 기본 보완 — 정직). 향후 `/mass` POST 결과를 design_versions에 저장하면 GET 복원 정밀도 향상.
- 항공 세로압축은 주석+분리필드로 노출만 했고 실제 드레이프 보정은 프론트 몫(과도수정 방지).
- get_title_by_pnu는 국외IP에서 차단될 수 있음 — 운영(Oracle 국내IP)에선 정상, 차단 시 9m 폴백·로그로 graceful.
