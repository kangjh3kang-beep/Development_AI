# Flagship B — 이미지융합 AVM (PoC) QA 검증 보고

대상: 백엔드 `eafc4e3` / 프론트 `644beaf`
검증자: PropAI QA Verifier · 2026-06-05 · 읽기 검증(코드 수정·배포·push 없음)

## 종합 판정: **배포가능 (GO)**

블로커 0건. 계약 정합·할루시네이션 방지·이미지 안전·경로 마운트·재사용 시그니처·회귀 모두 PASS. WARN 2건은 비차단 코스메틱/운영 의존성.

---

## 검증 증거 (직접 실행)

| 검증 | 결과 | 명령/근거 | 출력 |
|------|------|-----------|------|
| 백엔드 컴파일 | PASS | `python3 -m py_compile` (4파일) | PY_COMPILE_OK |
| main.py AST | PASS | `ast.parse(main.py)` | main.py AST OK |
| 백엔드 린트(신규) | PASS | `.venv/bin/ruff check` avm_vision 2파일 | All checks passed! |
| 프론트 타입체크 | PASS | `npx tsc --noEmit` (web 전체) | EXIT 0 |
| 재사용 시그니처 | PASS | grep 교차확인 | 전부 일치 |

---

## 항목별 판정표

### 1. 계약 정합 — **PASS**
백엔드 응답 ↔ 프론트 `types.ts` ↔ 계약 11 1:1 매핑 확인.

| 필드 | 백엔드(avm_vision_service.py) | 프론트(types.ts) | 계약 | 판정 |
|------|------|------|------|------|
| `image.available/source/bbox/thumbnail_url` | :394-401 | :14-24 | OK | PASS |
| `image.center/zoom`(추가필드) | :398-399 | :17-20 `center:[number,number]\|null`, `zoom:number\|null` | 계약 허용(확장) | PASS |
| `features.source` "image"\|"proxy" | :412,433,169 | :30 | OK | PASS |
| `features.green/built/edge/road_frontage/terrain/poi_density/detail` | :413-419, 117-124 | :31-37 | OK | PASS |
| `adjustment_pct` float | :452 | :51 number | OK | PASS |
| `adjusted_value_won` number\|null | :453,437-439 | :52 | OK | PASS |
| `confidence` 0~1 | :454 | :54 | OK | PASS |
| `experimental: true` 고정 | :456 | :57 boolean | OK | PASS |
| `note` | :458-459 | :60 | OK | PASS |
| `ok/address/pnu/coordinates/base_value_won/base_value_per_sqm_won/rationale/sources` | :442-457 | :41-58 | OK | PASS |

- `image.source` 백엔드 실제값 `f"VWorld-{basemap}"` = `"VWorld-PHOTO"` (vworld_service.py:483 + get_aerial_image 호출 zoom=18 PHOTO default) ↔ 프론트 리터럴 `"VWorld-PHOTO"\|null` 일치.
- 타입/중첩 불일치로 깨지는 화면값 **없음**. `bbox`는 계약상 `[...]|null` 허용이며 백엔드 항상 null(:397) → 프론트 `bbox:number[]|null`(types.ts:21) 안전. 프론트는 bbox 미사용(썸네일은 center/zoom 기반, AvmVisionPanel.tsx:123) → 렌더 영향 0.

### 2. 할루시네이션 방지 (핵심) — **PASS**
- **±8% 상한 강제**: `MAX_ADJUST_PCT=8.0` (avm_vision_service.py:23), `_clamp_pct` (:32-33) `max(-8, min(8, ...))`. 영상융합 `_fuse_image` 마지막 `pct=_clamp_pct(pct)` (:211), 프록시융합 `_fuse_proxy` (:253) **두 경로 모두 클램프**. PASS.
- **근거 없으면 0**: 영상 reasons 없으면 pct 0.0 유지(:181 초기 0.0, :218 "보정 없음(0%)"); 프록시 동일(:226, :260). 특징 None이면 가중 미적용 → 0.0. PASS.
- **base 없으면 adjusted_value_won=None (날조 안함)**: :437-439 `adjusted_value_won: int|None = None; if base_won is not None:` 만 계산. PASS.
- **experimental 항상 true**: :456 하드코딩 `True`. PASS.
- **cv2 미설치 → features.source="proxy" 정직 표기**: `_extract_image_features` try/except 지연 import (:47-52) → None 반환 → 메인에서 `img_feats is None` 분기로 `_build_proxy_features` (:422-434), source="proxy" (:169,433). note에 "cv2 미가용/디코딩 실패 — 프록시 특징으로 폴백" (:424) 또는 "항공 정사영상 미취득…프록시" (:428) 명시. PASS.
- **과장(CNN/MAPE) 문구 부재**: 코드/응답 전수 확인. note 고정값 "실험적(EXPERIMENTAL) 영상융합 보정. 검증된 감정평가가 아닙니다." (:459). 프론트 헤더/면책 "검증된 가치 단정이 아닙니다"(Panel:141), "법적·평가적 효력이 없으며 참고 지표"(Panel:333). "검증된 CNN/MAPE" 류 **전무**. PASS.

### 3. 이미지 취득 안전 — **PASS**
- `get_aerial_image` (vworld_service.py:455-512): `center=f"{lon},{lat}"` 정확(:472, lon,lat 순서 — VWorld 라이브 확정), `basemap="PHOTO"` default(:461), zoom `max(7,min(18,zoom))` 클램프(:469). PASS.
- 실패 graceful: 키 없음/좌표 없음 → None(:467); 비-PNG/비-200 → 경고 후 None(:498-503); 예외 → None(:508). 메인은 `acq and acq.get("bytes")`만 available=True (:392), 아니면 image_block default available=false (:374-379). PASS.
- `asyncio.wait_for` 가드: 이미지 취득 호출 `timeout=_IMG_TIMEOUT(12s)` (:386-391). 좌표(12s)/desk(30s)/프록시(12s) 전부 가드(:296,316,331,353,131,155). PASS.
- **프론트 VWorld 키/Referer 안전**: getmap은 Referer 필수 → 브라우저 `<img>` 직접호출 403 위험. 프론트는 Next 프록시 `/api/vworld/data?service=image` 경유(AvmVisionPanel.tsx:32-48 thumbUrl). route.ts:23-28 `service==="image"` 분기로 `/req/image` 라우팅 + `headers:{Referer:"https://www.4t8t.net"}` 부여(:32) + PNG arrayBuffer 패스스루(:36-46). 키는 도메인제한 공개키(`NEXT_PUBLIC_VWORLD_API_KEY`, 기존 lib/vworld-client 정책과 일관) + 프록시 경유로 노출표면 = 기존 data/address 프록시와 동일. 403/키직노출 **회피 적정**. PASS.

### 4. 경로/마운트 — **PASS · 404 위험 0**
- 프론트 `apiClient.post("/avm-vision/analyze")` (Panel:97) → api-client.ts:88 `getRequestUrl` 자동 `/api/v1` + path = `/api/v1/avm-vision/analyze`.
- 백엔드 라우터 `@router.post("/analyze")` (avm_vision.py:23) + main.py 마운트 `include_router(avm_vision.router, prefix="/api/v1/avm-vision")` (main.py:338).
- 결합 = `/api/v1/avm-vision/analyze` **정확 일치**. import도 routers `__init__` 묶음에 추가(main.py:42), AST/py_compile OK. 404 위험 0. PASS.

### 5. 재사용/엣지 — **PASS**
| 재사용 | 호출(avm_vision) | 실제 시그니처/키 | 판정 |
|------|------|------|------|
| `AutoZoningService.analyze_by_address(address)` | :296 | auto_zoning:38, 반환 `coordinates={lat,lon}`(:57-60)·`pnu`(:56) | PASS |
| `vw.geocode_address(address)` 폴백 | :316 | lat/lon/pnu 사용(:318-320) | PASS |
| `get_parcel_by_pnu(pnu)` 기하중심 | :330 | geometry 좌표 평탄화(:333-339) | PASS |
| `desk_appraisal(pnu=, address=)` | :353-354 | desk_service:122 `*,pnu,address` kw-only OK. 반환 `ok/appraised_total_won/appraised_price_per_sqm/pnu`(:333-338) 사용(:357-360) | PASS |
| `get_land_characteristics(pnu)` | :131 | vworld:361, 반환 `road_side/terrain_height/terrain_form`(:402-404) 사용(:137-143) | PASS |
| `CommercialAreaService.get_stores_in_radius(lat,lon,radius_m=500)` | :155-156 | commercial:44 시그니처 일치, `None` 반환 가드(:158) | PASS |

- 엣지: 422(address·pnu 모두 없음) 라우터에서 차단(avm_vision.py:30-31) + 서비스 방어(:282-284). ok:false(base·좌표 전무) (:366-371, 빈결과 금지). 이미지 미취득 → available=false + proxy 폴백 + note(:425-428). cv2 try/except(:47-52, :84-86). PASS.

### 6. 회귀/품질 — **PASS** (WARN 2 비차단)
- main.py 타라우터 무영향: +2줄(import+include_router)만, AST OK, 기존 라우터 정의/순서 불변. PASS.
- `DeskAppraisalReportClient` 무파괴: +11줄(import 1 + `res?.ok` 가드 패널 렌더 1블록, :471-481). 시드 필드 `appraised_total_won`(client type:51 number\|null)·`appraised_price_per_sqm`·`pnu`(:52 string\|null)·`ranAddr` 모두 기존 존재 확인. 패널 prop `baseValueWon?:number\|null`(Panel:75)에 null 허용 → 타입 호환. 기존 보고서/PDF/검증배지 로직 불변. PASS.
- **tsc EXIT 0** (web 전체) — 변경/신규 4파일 포함 타입 무오류. PASS.
- 신규 백엔드 2파일 ruff All checks passed. PASS.
- 토큰색: 레이아웃/표면 `var(--surface-*)`,`var(--line)`,`var(--text-*)`,`var(--accent-strong/soft)` 사용. 하드코딩 hex는 의미색(상향#10b981/하향#ef4444/실험#a78bfa/도로등급)에 한정 — 메모리 토큰 정책 준수. PASS.
- `apiClient` import 보존: AvmVisionPanel.tsx:13 `import { apiClient }` 존재(린터 삭제 함정 회피). PASS.

---

## WARN (비차단)

- **WARN-1 (코스메틱)**: 신규 `get_aerial_image`가 파일 기존 스타일 따라 `Optional[Dict]`·`List` 사용 → ruff UP006/UP007 힌트 3건(vworld_service.py:455~512). **파일 전반 30건 중 일부(기존 코드와 동일 패턴)이며 신규 avm_vision 2파일은 0건**. 빌드/런타임 무영향. 배포 후 파일 일괄 modernize 시 함께 처리 권장. 비차단.
- **WARN-2 (운영 의존성)**: 보고대로 현 로컬/일부 배포에 cv2 미설치 → `features.source="proxy"`로 정직 폴백(설계 의도, 정상 동작). 영상분석(image) 승격은 배포에 `opencv-python-headless`+numpy 설치 시. 정직 표기되므로 할루시네이션 위험 0이나, "이미지융합" 본 가치(cv2 특징) 발현을 위해 배포 이미지에 cv2 설치 권장. 비차단(프록시 폴백이 안전).

## 깨지는 화면값
- 없음. 모든 응답 필드가 프론트 옵셔널 체이닝(`res?.`, `f?.`, `img?.`)·null 가드로 graceful. 이미지 미취득 시 "항공영상 미취득" 안내(Panel:202), proxy 시 배지 "공간컨텍스트 추론"(Panel:222) 자동 분기.

## 결론
**APPROVE / GO.** 계약 100% 정합, 할루시네이션 방지 장치(±8% 클램프·근거0·base없으면None·experimental고정·정직 폴백 note·과장문구 전무) 전부 구현·검증. 경로 404 위험 0, tsc/py_compile/ruff(신규) 클린, 회귀 무파괴. 배포 전 권장(비차단): 배포 이미지에 cv2 설치하여 image 모드 활성화.
