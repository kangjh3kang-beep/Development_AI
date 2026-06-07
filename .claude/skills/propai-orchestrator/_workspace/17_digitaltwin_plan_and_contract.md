# 가상준공 3D 디지털트윈 — 반영계획 + MVP 구현 계약

## 핵심 발견(architect 코드검증)
- 4대 재료 모두 라이브 존재: VWorld 필지폴리곤(EPSG4326)·항공PHOTO·SRTM DEM격자·건물glTF. **빠진 것=좌표정합 합성 레이어**.
- ★메모리 교정: BIMViewer3D=CSS 가짜3D. 진짜 Three.js=`components/design/CadBimIntegrationPanel.tsx`(@react-three/fiber+GLTFLoader). MVP는 이걸 모태로 확장.
- glTF는 로컬 원점 중심화(ifc_to_gltf_service.py:82-87) → 씬에서 group 변환으로 앉힌다(glb 재배치 금지).
- VWorld LoD 3D건물 API 없음 → 주변건물=footprint 압출 추정(D8 배지).
- 좌표정합=ENU 로컬평면(lat0,lon0 원점, x=(lon-lon0)*111320*cos(lat0), z=-(lat-lat0)*111320). terrain_service.py:251 수식 재사용.

## 독자 차별점 8선(요약)
D1 가상준공 위 전주기 오버레이(ROI/ESG/인허가/검증 building-anchored HUD) ★최우선·난이도하
D2 검증배지·해시체인 "신뢰 트윈" ·하  D3 미래 스카이라인(조닝시그널)·중  D4 실시간 일조/조망 3D·중
D5 분양 VR 조감도·중  D6 공정 타임랩스·중  D7 대안설계 A/B 동일맥락·중  D8 정직성(추정/실측 구분)·하

## 기술: Three.js 확장 채택(Cesium은 Phase4 도시규모서 재평가)

## 단계
- Phase0 좌표정합 PoC(하). Phase1 MVP(중)★즉시. Phase2 전주기오버레이+신뢰(중). Phase3 일조/주변(중상). Phase4 분양VR/공정/미래(상,ERP의존).

---

# MVP 구현 계약 (Phase 0+1) — 즉시 착수

## 백엔드
신규 `POST /api/v1/digital-twin/scene` (routers/digital_twin.py + app/services/digital_twin/scene_service.py, main.py 마운트).
### Request: { address?, pnu?, design_version_id?(있으면 해당 glb) }
### Response(200):
{
  "ok": true, "address","pnu","lat0","lon0",
  "parcel": { "ring_enu": [[x,z],...], "center_enu":[0,0] },   // 필지 폴리곤을 ENU 미터로 변환
  "terrain": { "verts": [[x,y,z],...], "indices":[...], "elev0": float, "nx":int,"nz":int, "bbox_m":{...} },
  "aerial": { "image_proxy_url": str, "center":[lon,lat], "zoom":int, "cover_m": float },  // 지면 텍스처(기존 vworld 항공 프록시)
  "neighbors": [ { "footprint_enu":[[x,z]...], "height_m": float, "estimated": true } ],   // 주변 footprint 압출(없으면 [])
  "building": { "glb_url": str|null, "place_at_enu":[0, elev0, 0] },                        // 우리 건물 glb(있으면)
  "badges": { "terrain_source": str, "terrain_resolution_m": float, "confidence": float, "neighbors_estimated": true, "note": str },
  "sources": [str]
}
### 로직(재사용)
- terrain_service: `build_terrain_mesh(lat,lon,...)` 신규 — 기존 grid(11x11→21x21 상향) → ENU verts+삼각 indices+elev0 반환. 기존 analyze 격자 재사용.
- vworld_service: get_parcel_by_pnu(폴리곤)→ENU 변환, getmap PHOTO(항공 프록시 url, 기존 avm_vision 패턴), get_parcels_in_bbox(주변 footprint→압출 height 추정 기본 9m 또는 건축물대장 층수 가능시).
- building glb: design_v61 `/design/{id}/bim/model.glb` 존재 시 url. 없으면 building=null(트윈은 지형+항공+필지만으로도 ok).
- 병렬 asyncio.gather, wait_for 가드. 좌표·필지 불가→ok:false. pnu/address 둘다 없음→422.
- 정직성: badges에 출처·해상도·confidence·neighbors_estimated·note(terrain note 재사용).

## 프론트
신규 `components/digital-twin/DigitalTwinScene.tsx`(client, **CadBimIntegrationPanel 모태**: @react-three/fiber+GLTFLoader). `dynamic(ssr:false)` 마운트(1102/SSR 회피·HDR Environment 금지·autoRotate 게이트).
- 입력: 주소(필수). 실행→/digital-twin/scene.
- 씬 합성: 지형메시(verts/indices, vertexColors 표고그라데이션 또는 항공텍스처 드레이프) + 필지 ring 경계선(실선) + 건물 glb(place_at_enu 위치, group 변환으로 앉힘) + 주변 footprint 압출(반투명 회색 점선=추정) + directionalLight.
- 레이어 토글(지형/항공/필지/건물/주변). 카메라 orbit.
- **정직성 배지 필수**: terrain_source·resolution_m·confidence·"주변건물 추정"·"AI 절차생성 매스·실측 아님". 실측=실선/채움, 추정=점선/반투명 시각구분.
- 배치: 부지분석 또는 프로젝트 상세에 "가상준공 3D" 섹션/탭. apiClient v1. 토큰색·다크.
- types.ts(계약 스키마).

## 정직성 가드(비협상)
표고 SRTM30m·실측아님, 주변=footprint 추정, 매스=AI절차생성·인허가도면 아님, 항공=촬영시점 상이가능. 추정/실측 시각 구분.

## 검증/제약
- 백엔드 로컬 .venv: import/라우트, 실주소 라이브 1회(scene 페이로드 verts/parcel/aerial 생성 확인). 프론트 tsc 0/eslint 0. git add 명시경로만(-A 금지). footer Co-Authored-By: Claude Opus 4.8 (1M context).
- 배포=Micro(현 프로덕션). A1은 pull로 자동 반영.
