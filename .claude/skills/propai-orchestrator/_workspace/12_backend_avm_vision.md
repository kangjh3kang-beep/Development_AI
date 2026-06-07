# Flagship B — 이미지융합 AVM (PoC) 백엔드 구현 보고

커밋: `eafc4e3` feat(avm-vision): 이미지융합 AVM PoC 백엔드(VWorld 항공영상+cv2 특징, 프록시 폴백, 실험적 보정)

## 1. 신규/변경 파일 · 엔드포인트 · 마운트

| 파일 | 내용 |
|------|------|
| `apps/api/routers/avm_vision.py` (신규) | 얇은 라우터. `POST /analyze` (prefix는 main에서 부여) |
| `apps/api/app/services/avm_vision/__init__.py` (신규) | 패키지 |
| `apps/api/app/services/avm_vision/avm_vision_service.py` (신규, 460줄) | 본체: 좌표/PNU 확보 → 기준값 → 영상취득 → cv2 특징/프록시 폴백 → 융합 |
| `apps/api/app/services/external_api/vworld_service.py` (수정 +62줄) | `get_aerial_image(lat, lon, zoom=18, size=512, basemap="PHOTO")` 신규 메서드 (VWorld static image getmap) |
| `apps/api/main.py` (수정 +2줄) | import `avm_vision` + `include_router(prefix="/api/v1/avm-vision")` (avm 등록 직후, line ~338) |

- **엔드포인트**: `POST /api/v1/avm-vision/analyze`
- 요청: `{address?, pnu?, base_value_won?, base_value_per_sqm_won?}` (계약 일치)
- 422: address/pnu 모두 없음 (라우터에서 HTTPException). ok:false: 기준값·좌표 모두 불가.

## 2. VWorld 이미지 취득 — 라이브 결과 (★ 실제 호출 확인)

**성공.** 실제 키(루트 `.env`, 7C8CD147…)로 라이브 호출하여 진짜 항공 정사영상 PNG 취득 확인.

- 엔드포인트: `https://api.vworld.kr/req/image`
- 핵심 파라미터(라이브로 확정): `service=image&request=getmap&format=png&basemap=PHOTO&crs=EPSG:4326&center=<lon>,<lat>&zoom=<7~18>&size=512,512&version=2.0`, 헤더 `Referer: https://www.4t8t.net`
- **함정 1**: `bbox`가 아니라 **`center`(lon,lat) 필수**. bbox 제공 시 `PARAM_REQUIRED: center가 없어서…` 오류.
- **함정 2**: `zoom` 유효범위 **7~18** (19 요청 시 INVALID_RANGE). 코드에서 7~18로 클램프.
- **함정 3**: basemap 유효값 `[NONE, GRAPHIC, GRAPHIC_NIGHT, PHOTO, PHOTO_HYBRID, GRAPHIC_WHITE]`. 항공사진=`PHOTO`. (`Satellite`는 무효)
- 강남 테헤란로(127.0276,37.4979) zoom=18 → `200 image/png 679,944 bytes`, 512×512 RGB. 시각 확인 결과 실제 강남 교차로 항공사진. 저장 검증: `/tmp/vworld_18.png` (PNG image data, 512×512).
- E2E 라이브: address="서울특별시 강남구 테헤란로 152" → ROAD 지오코딩 좌표 확보 → **image.available=true, source=VWorld-PHOTO 취득 성공**.

> 정직 명시: PoC라 취득한 PNG 바이트는 보관(thumbnail_url 미발급)하지 않는다. 프론트는 동일 좌표로 VWorld 이미지 API를 직접 재요청해 썸네일 표시 가능(image.center/zoom 제공).

## 3. 재사용 함수 (file:line) · 프록시 특징 구성

- 좌표/PNU: `app/services/zoning/auto_zoning_service.py:38 analyze_by_address` (coordinates/pnu) → 폴백 `vworld_service.py:70 geocode_address` → 폴백 `get_parcel_by_pnu:21` 기하 중심.
- 기준값: `app/services/land_intelligence/desk_appraisal_service.py:122 desk_appraisal` (base 미제공 시). 반환의 `appraised_total_won`/`appraised_price_per_sqm`를 base로 사용.
- 영상: `vworld_service.py get_aerial_image` (신규).
- 프록시 특징 (`_build_proxy_features`):
  - `terrain`: `vworld_service.py:361 get_land_characteristics` → terrain_height/terrain_form 결합.
  - `road_frontage`: 동 메서드 roadSideCodeNm → good/normal/poor 등급 매핑.
  - `poi_density`: `app/services/external_api/commercial_area_service.py:44 get_stores_in_radius`(반경500m 점포수) → /800 정규화(0~1).

## 4. 융합 보정 로직 · 과장 방지 장치

- **상한 ±8%** (`MAX_ADJUST_PCT=8.0`, `_clamp_pct`로 모든 경로 강제 클램프 — 검증: clamp(20)→8, clamp(-15)→-8).
- 영상(`_fuse_image`): 식생과다(>0.55)→하향, 적정녹지→미세상향, 시가화율↑→상향, 에지밀도↑→상향. confidence **0.5~0.7**(특징 수 기반).
- 프록시(`_fuse_proxy`): 접도 good→상향/poor→하향, POI 고밀→상향, 지세 급경사→하향. confidence **0.30~0.45**.
- **근거 없으면 adjustment_pct=0** (검증: 특징 None → 0.0, confidence 0 / 프록시 무근거 → 0.0, conf 0.30).
- `experimental: true` 항상. `rationale`에 기여 특징 명시. note에 폴백 사유 정직 기록.
- **과장 표현 없음**: "검증된 CNN/MAPE" 류 문구 코드/응답 어디에도 없음. disclaimer 성격 note 고정.
- base 없으면 `adjusted_value_won=None` (없는 값 날조 안 함).
- cv2 `try/except` 지연 import — 미설치 graceful(로컬 검증됨). 무거운 ML 모델 미로드(numpy 기초연산만).
- 90초 가드: 모든 외부호출 `asyncio.wait_for`(image 12s, geo 12s, desk 30s, proxy 12s).

## 5. 로컬 검증 로그

- `py_compile` 3파일 OK. `ruff check` All checks passed.
- repo-root import: `from apps.api.routers.avm_vision import router` → routes `[('/analyze', ['POST'])]`.
- 단위: clamp 상한, cv2 graceful(None), 영상융합(시가화 +5.0 / 식생과다 -7.0 / 무특징 0.0), 프록시융합(접도good+POI고밀 +7.0 conf0.45 / 무근거 0.0 conf0.30), road 등급 매핑 — 전부 통과.
- E2E 라이브(실키): ok=true, 좌표 확보, **image.available=true(VWorld-PHOTO 취득)**, cv2 미설치라 proxy 폴백, adjustment 0%(해당 필지 프록시 데이터 부족→보수적), adjusted=base.
- 422(빈 body) / ok:false(base·좌표 전무) 경로 확인.
- 커밋 해시: **eafc4e3** (명시 파일만 add, `git add -A` 미사용).

## 6. 프론트/QA 확정사항 (계약 대비)

- 응답 스키마 계약 준수. `image` 블록에 계약 필드(available/source/bbox/thumbnail_url) + **추가 필드** `center:[lon,lat]`, `zoom:int` 포함(프론트가 VWorld 이미지 직접 재요청해 썸네일 렌더용). `bbox`는 static getmap 특성상 null(계약 `bbox:[...]|null` 허용).
- `thumbnail_url`은 PoC에서 항상 null. 프론트는 `image.available && image.center` 일 때 VWorld getmap URL을 직접 구성(키는 프론트 NEXT_PUBLIC_VWORLD_API_KEY)하거나 미표시.
- cv2 미설치 환경(현 로컬·일부 배포)에서는 features.source는 "proxy"로 떨어짐 — 배포에 cv2 설치 시 "image"로 승격. 프론트는 `features.source` 배지로 image/proxy 구분 표시 권장.
- EXPERIMENTAL 배지·confidence·note 필수 노출(과신 방지).
