# 프론트엔드 — 가상준공 3D 디지털트윈 MVP 구현 보고

## 1. 신규/변경 파일 · 배치 위치
- 신규 `apps/web/components/digital-twin/types.ts` — 백엔드 계약 타입(`DigitalTwinScenePayload` 등 ENU 좌표 기반).
- 신규 `apps/web/components/digital-twin/DigitalTwinScene.tsx` — client, @react-three/fiber 씬 본체(default export).
- 변경 `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` — 부지분석 결과 단계, 기존 `TerrainAnalysisPanel` 바로 아래에 `dynamic(ssr:false)`로 마운트(신규 라우트 대신 기존 부지분석 화면에 결합).

## 2. Three.js 합성 방식 · 모태 재사용
모태 `components/design/CadBimIntegrationPanel.tsx`의 진짜 패턴을 그대로 확장:
- `Canvas` / `OrbitControls(makeDefault)` / `ambientLight`+`directionalLight` / `GLTFLoader`(`three/examples/jsm/loaders/GLTFLoader.js`, 모태와 동일 import) / HDR Environment 미사용 / `dynamic(ssr:false)`.
- **지형메시**: `terrain.verts/indices` → `BufferGeometry`(position + index + computeVertexNormals). 기본은 표고 그라데이션 `vertexColors`(청록→초록→황→적갈), "항공" 토글 시 `aerial.image_proxy_url`을 `TextureLoader`(useLoader, Suspense fallback)로 동일 메시에 드레이프(XZ 평면투영 UV). MVP 안정 기본값=vertexColors, 항공은 토글.
- **필지 경계**: `parcel.ring_enu` → `lineLoop` + `lineBasicMaterial`(실선, 강조색 #3b82f6). y는 `elev0+0.6`(지형표고 근처).
- **건물**: `building.glb_url` 있을 때만 `GLTFLoader.loadAsync` 후 `<group position={place_at_enu}>`에 primitive로 앉힘. **glb 내부 기하 재배치 금지 — group.position만 사용**. 로드 실패는 무시(지형·필지는 계속 표시).
- **주변건물**: `neighbors[].footprint_enu` → `Shape` → `ExtrudeGeometry(depth=height_m)`, `rotateX(-90°)`로 XZ 지면에 세움. **반투명 회색 채움(opacity 0.32, depthWrite:false) + 점선 윤곽**(`EdgesGeometry`+`lineDashedMaterial`, callback ref로 `computeLineDistances()` 호출). 추정 시각구분 충족.
- 카메라/조명/회전 거리는 `terrain.bbox_m.size_m`(없으면 `aerial.cover_m`/기본 200) 기준 동적 산정.

## 3. tsc / eslint 결과
- `npx tsc --noEmit` → EXIT 0.
- `npx eslint components/digital-twin/DigitalTwinScene.tsx components/digital-twin/types.ts` → 0 errors / 0 warnings.
- 페이지의 기존 lint 2 errors(L337 hero 큰따옴표 unescaped) + 2 warnings(`useEffect`, map의 `i`)는 **모두 내 변경 이전부터 존재(HEAD 확인)**. 내가 추가한 라인(dynamic import + JSX 1줄)은 신규 lint 이슈 0.

## 4. 커밋
- `5e94e6f` feat(digital-twin): 지도 위 가상준공 3D 씬 — 지형·필지·건물·주변 합성 뷰
- 3 files changed, 609 insertions(+). push 안 함. 명시 경로만 staged(`-A` 미사용). apiClient import 보존 확인(diff상 미변경).

## 5. 백엔드/QA 정합 사항
- **좌표 ENU**: 프론트는 `verts[x,y,z]`에서 y=표고(up), x/z=수평으로 사용. `parcel.ring_enu`/`neighbors.footprint_enu`는 `[x, z]` 2튜플로 가정(y는 elev0 기준). 백엔드 ENU 수식(x=(lon-lon0)·111320·cosφ, z=−(lat-lat0)·111320)과 z부호 일치 필요 — 불일치 시 필지/주변이 남북 반전됨.
- **glb 배치**: `building.place_at_enu=[x, elev0, z]`를 group.position에 그대로 사용. glb는 로컬 원점 중심(ifc_to_gltf_service) 전제 — 백엔드가 추가 오프셋을 glb에 넣으면 이중 이동되니 금지.
- **bbox_m.size_m**: 카메라/조명/회전반경 기준 키로 사용. 없으면 `aerial.cover_m`→200 폴백하나, 백엔드가 `bbox_m.size_m`(대략 격자 한 변 m) 제공 시 프레이밍 최적.
- **항공 텍스처**: `image_proxy_url`은 CORS 허용 동일오리진 프록시여야 WebGL 텍스처 로드 가능(crossOrigin). 실패 시 회색 fallback 머티리얼로 graceful.
- **정직성 배지**: `badges.terrain_source/terrain_resolution_m/confidence/note` 그대로 렌더 + 고정 문구("주변건물 추정", "AI 절차생성·실측 아님"). 백엔드는 `ok:false`+`message`로 실패 통보(좌표·필지·지형 미확보).
- 입력: 주소 필수(부지분석 `siteData.address` 자동 주입) 또는 pnu. `design_version_id`는 옵션으로 전달(현재 page에서는 미전달 → 자동 glb).
