# 18 · 가상준공 3D 디지털트윈 MVP — 백엔드 구현 보고

커밋: **5542262** `feat(digital-twin): 가상준공 3D 씬 백엔드 — 필지·지형메시·항공·주변·건물 좌표정합 페이로드`

## 1. 신규/변경 파일·엔드포인트·마운트
| 종류 | 경로 | 내용 |
|------|------|------|
| 변경 | `apps/api/app/services/terrain/terrain_service.py` | `build_terrain_mesh(lat,lon,half_m=150,n=21)` 신규(추가만, 기존 `analyze_terrain` 무파괴). 기존 `_fetch_dem`·ENU 수식 재사용. |
| 신규 | `apps/api/app/services/digital_twin/scene_service.py` | 씬 합성 본체 `build_scene(address,pnu,design_version_id)`. 270줄. |
| 변경 | `apps/api/routers/digital_twin.py` | 기존 IoT 라우터에 `POST /scene` + `GET /aerial-image`(항공 프록시) 추가(기존 4개 라우트 무파괴). |

- 엔드포인트: `POST /api/v1/digital-twin/scene`, `GET /api/v1/digital-twin/aerial-image`
- 마운트: **신규 추가 없음** — `routers/digital_twin.py`가 이미 `main.py:373`(`app.include_router(digital_twin.router, prefix="/api/v1/digital-twin")`)에 마운트되어 있어 그 라우터에 라우트를 추가함. import는 `main.py:59`.
- `app/services/digital_twin/__init__.py`는 기존 존재(변경 없음).

> 설계 판단: 계약서가 "신규 routers/digital_twin.py"라 했으나 동일명 파일이 이미 IoT 상태 라우트로 같은 prefix에 마운트되어 있었음. 두 번째 라우터/중복 마운트를 만들면 prefix 충돌·복잡도 증가 → 기존 라우터에 공개 라우트를 얇게 추가(terrain.py 위임 패턴 준용)하는 최소 디프를 채택. 무파괴 보장.

## 2. build_terrain_mesh 출력형
- `verts`: `[[x,y,z],...]` (x=동, y=표고m, z=남). n=21 → **441개**.
- `indices`: 평탄 삼각 인덱스 배열, **2400개**(= 800 삼각형 = 2·(n-1)²). 정점 idx = row·n+col.
- 기타: `elev0`(중심셀 표고), `nx`/`nz`(=21), `bbox_m{x_min,x_max,z_min,z_max,half_m}`, `min/max_elev_m`, `relief_m`, `valid_ratio`, `source`, `resolution_m(30)`.
- 결측 표고는 유효 표고 평균으로 보간(메시 연속성). 전부 실패 → `None`(호출측 terrain=null, badges에 미취득 명시).

## 3. 라이브 호출 결과 (서울특별시 강남구 역삼동 736, 로컬 .venv·루트 .env 키)
- `ok=true`, lat0=**37.499643**, lon0=**127.034269**, pnu=**1168010100107360000**
- parcel.ring_enu: **5점**(폴리곤 닫힘), center_enu=[0,0], ring[0]≈[-16.55,-6.47]m
- terrain.verts=**441**, indices=**2400**(800 tri), elev0=**52.0m**, nx/nz=21, relief=**61.0m**, valid_ratio=**1.0**, 중심 vert=[0,52,0]
- aerial.image_proxy_url=`/api/v1/digital-twin/aerial-image?lat=37.499643&lon=127.034269&zoom=18`, cover_m=**242.6**, zoom=18
- aerial 프록시 실스트림 검증: VWorld PHOTO PNG **690,965 bytes**(매직 `\x89PNG`) 취득 OK
- neighbors=**60동**(상한 60), 샘플 height_m=9.0/estimated=true/footprint 4점
- building=**null**(design_version_id 미지정)
- badges: confidence=**0.6**, terrain_source="OpenTopoData SRTM 30m (공개 무료, NASA SRTM)", neighbors_estimated=true

## 4. 좌표정합(ENU) 방식·정직성 badges
- **단일 원점 ENU 로컬평면**: 원점=필지중심(lon0,lat0). `x=(lon-lon0)·111320·cos(lat0)`, `z=-(lat-lat0)·111320`, `y=표고`. terrain_service 수식과 동일(우수좌표, 남=+z).
- 4재료 모두 동일 원점 정합: 필지 ring·지형 메시·주변 footprint는 ENU 미터, 건물 glb는 `place_at_enu=[0,elev0,0]`(group 변환으로 앉힘, glb 재배치 금지), 항공은 center+zoom+cover_m로 지면 드레이프.
- 정직성 badges(비협상): `terrain_source`/`terrain_resolution_m(30)`/`confidence(=0.6·valid_ratio)`/`neighbors_estimated:true`/`note`(표고 SRTM 광역·실측 아님, 주변=footprint 추정 9m, 매스=AI 절차생성·인허가도면 아님, 실측=실선·추정=점선/반투명). 비건물 지목(도로·하천·구거·제방·유지 등) 압출 제외.

## 5. 커밋 해시
**5542262a3cf76b0887c1cf3d1eb5660a732fed6c** (push·SSH배포 안 함)

## 6. 프론트/QA 확정사항
1. **scene 엔드포인트**: `POST /api/v1/digital-twin/scene` Body `{address?, pnu?, design_version_id?}`. 둘 다 없으면 **422**. 좌표/필지 불가 → `{ok:false, message}`.
2. **항공 텍스처**: `aerial.image_proxy_url`(상대경로)을 apiClient baseURL과 합쳐 `<TextureLoader>`로 직접 로드. 키 비노출(서버 대리). `aerial.cover_m`(역삼동 242.6m)로 지면 plane 폭 산정 — 지형 bbox(±150m=300m)보다 약간 좁음(zoom18 근사, "대략 정합"). 더 넓은 커버 필요시 `zoom=17`로 재요청(cover≈2배).
3. **terrain**: `verts[[x,y,z]]`+`indices`를 BufferGeometry에 그대로 주입(인덱스 삼각). vertexColors 표고 그라데이션 또는 항공 드레이프. `terrain`이 **null일 수 있음**(DEM 장애) → 평면 폴백 + badges.note 노출.
4. **parcel**: `ring_enu[[x,z]]`(y=elev0 또는 0에 깔기). 실측이므로 **실선/채움**.
5. **neighbors**: `footprint_enu[[x,z]]` + `height_m` 압출. **추정 → 점선/반투명 회색** 필수. `estimated:true`.
6. **building**: null 또는 `{glb_url, method:"POST", place_at_enu:[0,elev0,0]}`. glb 라우트는 **POST**(매스 페이로드 동봉 필요) — design_v61 `/{id}/bim/model.glb` 패턴. design_version_id 미지정 시 building=null이어도 씬 정상.
7. **정직성 배지 UI 필수**: badges의 terrain_source·resolution_m·confidence·"주변건물 추정"·"AI 절차생성 매스" 표기.
