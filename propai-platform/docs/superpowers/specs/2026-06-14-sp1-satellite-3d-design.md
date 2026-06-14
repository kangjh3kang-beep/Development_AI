# SP1 위성지도 3D 준공뷰 — 설계 스펙 (design spec)

> ⚠️ **스코프 정정(실코드 검증)**: SP1은 "신규 위성-3D 씬 구축"이 아니라 **이미 가동 중인 `DigitalTwinScene`(가상준공 3D)의 작은 additive 확장**이다. 검증으로 또 하나의 false gap 확인.

작성일: 2026-06-14 · 브랜치: `feature/trust-infra-2026-06-11` · 검증: WSL 실코드 file:line(spot-verify 완료)

## 1. 이미 구현된 것 (재사용 — file:line 검증)
- `apps/web/components/digital-twin/DigitalTwinScene.tsx:14` R3F `Canvas`, `:16-17` GLTFLoader·TextureLoader — 위성-3D 씬 본체
- `:200-212` 항공 정사영상 지면 드레이프(`image_proxy_url`), `:239` TextureLoader
- `:277-280` 필지경계 `ring_enu`→LineLoop, `:341-371` `BuildingGlb` `place_at_enu`(AI매스 배치)
- `apps/api/app/services/digital_twin/scene_service.py:66 _enu_xz`(`x=(lon-lon0)*111320*cos(lat0)`, `z=-(lat-lat0)*111320`), `:76 _ring_to_enu`(소수3자리)
- `apps/api/routers/digital_twin.py:173 POST /scene`, `:343 GET /aerial-image`(VWORLD PHOTO 프록시·키 비노출)

## 2. 진짜 갭 (신규·작음·additive)
1. **`apps/web/lib/enuTransform.ts` 부재**(Glob 0건) — 프론트 ENU 좌표 순수코어(백엔드 `_enu_xz` 1:1 포팅) + vitest. 클라이언트 결정론 검산용.
2. **준공 전/후(before/after) 토글** — 현재 레이어 토글만 있고 `필지·항공만 ↔ +AI매스` 전용 비교 UI 없음 → DigitalTwinScene에 세그먼트 토글 additive(건물 group 가시성+라벨, 신규 fetch 0).
3. (Phase2) 항공 위도압축(cos lat) 분리정합 — `scene_service.py:108 _aerial_cover_m` WARN.
4. (Phase3) 이웃 반경 슬라이더(80~150m) + 보강건수 배지.

## 3. 단계 + 수용기준
### MVP (M, TDD)
- **enuTransform.ts**: `enuXZ(lon,lat,lon0,lat0)`·`ringToEnu(ring,lon0,lat0)`(소수3자리·무효입력 빈배열)·`boundsEnu(pts)`. 순수·네트워크 0.
  - vitest: 원점=[0,0]; lon+0.001°(lat0=37.5)→x≈88.34·z≈0; lat+0.001°→z≈-111.32(북=−z); 빈/부족 링→[] (throw 없음).
- **before/after 토글**: DigitalTwinScene에 세그먼트(준공 전/후) additive — `layers.building` 가시성+라벨만 제어(기존 토글 패턴 재사용, 신규 백엔드 호출 0). data-testid 부여.
- **스모크**: `e2e/digital-twin-scene.spec.ts`(design-3d-viewer.spec.ts 패턴 복제) — Canvas 마운트·before/after 토글 무크래시·pageerror 0.

## 4. 정직 캐비엇
- "준공모습"은 **AI 절차생성 근사 매스 + footprint 추정 맥락**(인허가 도면·실측 아님). 기존 badges(`AI 절차생성·인허가 아님`·`SRTM 30m`·`주변 추정`) 유지.
- 포토리얼·PBR·태양궤도 정밀 캐스트섀도 **범위 외**(기존 방향광 근사 유지).
- 항공 텍스처 EPSG:4326 위도압축(고위도 세로 ~넓게) — MVP는 가로폭 근사 유지, 정밀 분리정합은 Phase2.
- 프론트 좌표코어는 **검산용**(백엔드 ENU가 단일 진실원천·원점=필지중심).

## 5. 사용자 결정필요
- 타일 제공자: VWORLD PHOTO 유지(권장) vs Kakao SKYVIEW 추가
- 매스 소스: 기존 design_version glb 유지(권장) vs 클라이언트 절차모델
- before/after UI: 세그먼트 토글(MVP 권장) vs 슬라이더 와이프
- 전역 3D(도시단위) 여부: ±150m 맥락 유지(권장) vs 전역 확장(후속 SP)

## 6. 불변 규칙
additive·하위호환(기존 DigitalTwinScene 동작 0 변경) · 결정론(LLM 0) · 정직 · TDD · `feature/trust-infra-2026-06-11` 커밋, main 푸시 금지 · 검증: vitest + tsc + next build + e2e(design-3d-viewer 회귀 0).
