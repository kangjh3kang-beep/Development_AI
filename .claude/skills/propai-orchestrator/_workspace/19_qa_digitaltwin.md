# QA 교차검증 보고 — 가상준공 3D 디지털트윈 MVP

- 대상: 백엔드 `5542262`, 프론트 `5e94e6f`
- 계약: `17_digitaltwin_plan_and_contract.md`
- 검증 방식: 읽기 전용 교차검증 + tsc 직접 실행 + Python AST 파싱. 코드 수정/배포/push 없음.

## 종합 판정: **조건부 GO (WARN 1건 선해결 권고)**

치명(FAIL) 없음. tsc 0 / Python 파싱 OK / 라우터 마운트·계약 정합·좌표 부호 일치·glb 이중이동 없음 확인.
단 **항공 텍스처(aerial)가 프로덕션 split-origin에서 동작 불가**(WARN, 항목 4). 기본 OFF·폴백 존재라 크래시는 없으나 "항공" 레이어는 프로덕션에서 깨진다. 배포 가능하되, 항공 레이어를 켰을 때 정상 동작시키려면 선수정 권고.

---

## 항목별 판정표

| # | 항목 | 판정 | 근거(file:line) |
|---|------|------|----------------|
| 1 | ★ENU 좌표 정합 | **PASS** | 부호·축·원점 전부 일치 |
| 2 | 계약 정합(필드↔types↔계약) | **PASS** | 누락·타입 불일치로 깨지는 렌더 없음 |
| 3 | 건물 glb 배치(이중이동) | **PASS** | glb 로컬원점 중심화 + group.position만 적용 |
| 4 | 항공 텍스처 CORS/동일오리진 | **WARN** | 상대 URL이 프론트 오리진으로 해석 → 프로덕션 split-origin 404 |
| 5 | 정직성 가드 | **PASS** | 배지 백엔드 산출+프론트 노출, 추정/실측 시각구분, 비건물 제외 |
| 6 | 엣지/성능 | **PASS** | 422·ok:false·평면폴백·ssr:false·HDR무·autoRotate게이트·88s가드 |
| 7 | 회귀/품질 | **PASS** | 무파괴 추가·마운트정상·tsc0·apiClient보존. WARN: bbox_m.size_m 부재 |

---

## 1. ★ENU 좌표 정합 (PASS)

핵심: 백엔드 4개 레이어와 프론트 가정이 **동일 원점·동일 부호**인가.

- 백엔드 ENU 정의: `scene_service.py:62-69` `_enu_xz` → `x=(lon-lon0)*111320*cos(lat0)`, `z=-(lat-lat0)*111320` (북쪽이 -z, 남쪽이 +z).
- terrain verts: `terrain_service.py:396-419` 동일 수식. `xs/zs=linspace(-half,half)`, `la=lat-(zv/m_per_deg_lat)`(z증가=남=lat감소), `lo=lon+(xv/m_per_deg_lon)`(x증가=동). **terrain의 (x,z)→위경도 매핑이 `_enu_xz`의 역변환과 정확히 일치** → ring/neighbors/terrain 모두 동일 원점·동일 부호. 레이어 어긋남 없음.
- parcel.ring_enu / neighbors.footprint_enu: `_ring_to_enu`(`scene_service.py:72-80`)가 `_enu_xz` 사용 → terrain과 동일계.
- building.place_at_enu: `[0, elev0, 0]`(`scene_service.py:225`) = 원점. 일관.
- 프론트 가정: terrain verts를 `positions[i*3+0..2]=v[0],v[1],v[2]`로 그대로 사용(`DigitalTwinScene.tsx:78-80`), parcel은 `Vector3(p[0], baseY, p[1])`(:138)로 (x,z) 그대로, neighbor footprint도 `shape.moveTo(p[0],p[1])` 후 `rotateX(-90°)`로 XZ 평면 적립(:154-162). 모두 백엔드 (x,z)를 (X,Z)로 직결 → **부호·축 일치, 남북/동서 반전 없음**.

비고(비차단): `types.ts:9` 주석 "z=북(−위도방향)"은 표현이 모호하나(실제는 z=남이 +), 수식·코드 동작은 정확. 주석만 정리 권장.

## 2. 계약 정합 (PASS)

- terrain{verts,indices,elev0,nx,nz,bbox_m}: 백엔드 `terrain_service.py:454-466` 전부 산출, `types.ts:20-27` 일치.
- parcel.ring_enu/center_enu: `scene_service.py:104` ↔ `types.ts:14-17` 일치.
- aerial{image_proxy_url,center,zoom,cover_m}: `scene_service.py:215-222` ↔ `types.ts:30-35` 일치(추가로 basemap/note 있으나 프론트 무해 무시).
- neighbors[{footprint_enu,height_m,estimated}]: `scene_service.py:145-151` ↔ `types.ts:38-42` 일치(pnu/jimok 추가는 무해).
- building{glb_url,place_at_enu}: `scene_service.py:224-227` ↔ `types.ts:45-48`. 백엔드는 glb 없으면 `building=None`, 프론트는 `payload.building?.glb_url` 가드(`DigitalTwinScene.tsx:264`) → 깨짐 없음.
- badges/sources: 일치.
- 깨지는 렌더 없음.

## 3. 건물 glb 배치 — 이중이동 방지 (PASS)

- 백엔드: glb URL과 `place_at_enu=[0,elev0,0]`만 반환, 좌표 오프셋을 glb에 주입하지 않음(`scene_service.py:224-225`).
- glb 자체가 로컬 원점 중심: `ifc_to_gltf_service.py:78-87` 전체 정점에서 `center=all_pos.mean()` 후 `pos = verts - center` → **로컬원점 중심 전제 유지**.
- 프론트: `<group position={place_at_enu}>` 에만 적용, glb 내부 기하 미변경(`DigitalTwinScene.tsx:231-233`). **이중이동 없음.**

## 4. 항공 텍스처 CORS/동일오리진 (WARN) — 선수정 권고

문제: `aerial.image_proxy_url`은 **상대 경로** `"/api/v1/digital-twin/aerial-image?..."`(`scene_service.py:89`). 프론트는 이 문자열을 `useLoader(TextureLoader, url)`에 **그대로** 전달(`DigitalTwinScene.tsx:120,131`) → apiClient를 거치지 않음.

- apiClient는 `/digital-twin/scene` 호출 시 `resolveApiOrigin()+"/api/v1"+path`로 **절대 API 오리진**(`https://api.4t8t.net`)에 보냄(`api-client.ts:82-89, 36-46`).
- 그러나 TextureLoader에 넘긴 **상대 URL은 브라우저가 "현재 페이지 오리진"(프론트=Cloudflare 도메인) 기준으로 해석** → `https://<frontend>/api/v1/digital-twin/aerial-image`. 프론트 오리진에는 해당 엔드포인트가 없고(Next.js rewrites 없음 — `next.config.mjs` 확인) → **404/로드 실패**.
- 영향: 프로덕션 split-origin(프론트 Cloudflare ↔ 백엔드 api.4t8t.net)에서 항공 드레이프 불가.
- 완화: 항공 레이어 **기본 OFF**(`DigitalTwinScene.tsx:355` `aerial:false`), 실패 시 Suspense fallback 다크 머티리얼(:119) → 크래시는 없음. 그래서 FAIL이 아닌 WARN.
- 로컬(localhost) 단일 오리진에서는 우연히 동작.

수정지시(택1):
1. 백엔드가 절대 URL 반환: `scene_service.py:_aerial_proxy_url`이 설정된 API 베이스(예 `settings`의 공개 API origin)를 prefix. 단 WebGL은 cross-origin 이미지에 `crossOrigin='anonymous'`(three TextureLoader 기본) + 서버 `Access-Control-Allow-Origin` 필요 → 현 CORS(`middleware.py:99-102` env `CORS_ORIGINS`)에 프론트 오리진 포함 확인.
2. (권장) 프론트가 apiClient 오리진으로 절대화: `TerrainMesh`/`AerialMaterial`에 넘기기 전 `getRuntimeConfig`/`resolveApiOrigin` 기반으로 `image_proxy_url`을 절대 URL로 변환하고, three TextureLoader에 `crossOrigin` 보장. 동시에 백엔드 CORS에 프론트 도메인 등재.

키 비노출: 항공 키는 서버가 VWorld 대리 호출(`routers/digital_twin.py:199-207`), 프록시 URL에 키 없음 → **키 비노출 OK**.

## 5. 정직성 가드 (PASS)

- badges 백엔드 산출: terrain_source·resolution_m·confidence·neighbors_estimated·note 전부(`scene_service.py:244-255`). confidence는 valid_ratio 기반 동적(:231).
- 프론트 노출: `HonestyBadges`(`DigitalTwinScene.tsx:280-306`)가 출처·해상도·신뢰도·"주변건물 추정"·"AI 절차생성·실측/인허가 아님"·note 표시.
- 시각구분: 필지=실선 LineLoop(:142-144), 주변=반투명 회색(opacity 0.32)+점선 EdgesGeometry(lineDashedMaterial, :174-191) → 추정/실측 구분 충족.
- 매스 AI 고지: 배지 문구·sources(:40) 명시.
- 비건물 지목 제외: `scene_service.py:129,134` 도로·하천·구거·제방·유지·수도용지·철도용지 압출 제외 → 농로·배수로 오압출 방지.

## 6. 엣지/성능 (PASS)

- address·pnu 둘다 없음 → 422: `routers/digital_twin.py:180-181`.
- 좌표/필지 불가 → ok:false: `scene_service.py:181-187`.
- terrain null → 평면폴백: terrain None이면 elev0=0, 배지 note "평면 대체"(`scene_service.py:213,238-242`), 프론트 `layers.terrain && payload.terrain` 가드(:257).
- building null 허용: `scene_service.py:227`, 프론트 토글/렌더 가드(:264, 457).
- dynamic ssr:false: `page.tsx:` 동적 import `{ ssr:false }`(diff 확인).
- HDR Environment 미사용: 컴포넌트에 `Environment`/HDR 없음(ambient+directional만, :253-255).
- autoRotate 게이트: `entered` state, 진입 버튼 클릭 전 autoRotate=false(:268, 352, 490-501).
- 90초 가드: 백엔드 `SCENE_TIMEOUT_S=88`(:32, :210), 프론트 `timeoutMs:90000`(:382).

## 7. 회귀/품질 (PASS, WARN 1)

- terrain analyze 무파괴: `build_terrain_mesh`는 신규 함수 추가만(diff `+97` lines, 기존 `analyze_terrain` 무변경).
- digital_twin 라우터 기존 IoT 4라우트 무파괴: status/snapshot·status/latest·asset-intelligence·anomalies 그대로 유지, /scene·/aerial-image 추가만(`routers/digital_twin.py:29-160` 기존 + :163~ 신규).
- main.py 마운트 정상: `main.py:59` import, `main.py:373` `prefix="/api/v1/digital-twin"` → /scene·/aerial-image 풀패스 정상.
- site-analysis page 기존 무파괴: import 1줄 + 패널 1줄 추가만(diff 확인).
- tsc: **0 errors**(직접 실행 `tsc --noEmit`, exit 0, digital-twin 관련 0).
- apiClient import 보존: `DigitalTwinScene.tsx:19` `import { apiClient }` 존재, page.tsx 기존 apiClient import 유지.
- WARN(비차단): 프론트 카메라 span이 `bbox_m?.size_m`를 읽으나(`DigitalTwinScene.tsx:248,477-479`) 백엔드 bbox_m에는 `size_m` 키 없음(`terrain_service.py:457-461`은 x_min/x_max/z_min/z_max/half_m만). → undefined로 `aerial.cover_m ?? 200`에 폴백되어 카메라 거리 산정은 동작하나 의도한 size_m은 영원히 미사용. 수정: 백엔드 bbox_m에 `"size_m": round(2*half_m,1)` 추가하거나 프론트를 `half_m*2`/`cover_m`로 변경.

---

## FAIL/WARN 요약 수정지시

- **WARN-1 (항목4, 선수정 권고)**: aerial.image_proxy_url 절대화 + CORS 정합. 미수정 시 항공 레이어만 프로덕션 비동작(기본 OFF·폴백 존재라 배포는 가능).
- **WARN-2 (항목7, 경미)**: terrain.bbox_m에 `size_m` 추가 또는 프론트 span을 `half_m*2`로 교체(현재도 cover_m 폴백으로 동작).
- 비차단: `types.ts:9` z축 주석 문구 정리.

## 검증 산출물
- tsc: exit 0, error TS 0건, digital-twin 0건.
- Python AST: scene_service.py / terrain_service.py / digital_twin.py 파싱 OK.
- 라우터 마운트: main.py:59·373 확인.
- 라이브 1회 호출(실주소 scene 페이로드)은 본 읽기검증 범위 밖(서버/키 의존) — 배포 후 1회 라이브 확인 권장(verts/parcel/aerial 생성, 항공 토글 시 텍스처 로드 여부).
