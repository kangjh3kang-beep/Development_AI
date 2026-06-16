# P4-B 인구밀도 지도 레이어 — 조사 결과 + 구현 계획 (2026-06-16)

작성: 배포 코디네이터 세션 · 상태: **조사 완료 · 구현 착수 전(별도 작업)**
목적: 시장·시세 분석 지도에 **인구밀도 코로플레스 레이어** 추가(P4의 두 번째 레이어). P4-A(공시지가)와 달리 신규 외부연동이 필요해 분리.

> 결론: **실현 가능**(SGIS가 경계 GeoJSON + 인구 제공). 단 P4-A처럼 "기존 데이터 재사용"이 아니라 **SGIS 경계 신규 연동 + 좌표계 변환 + adm_cd 매핑**이 필요한 중간규모 작업.

---

## 1. 조사 결과 (feasibility)

### 1.1 데이터 소스 — SGIS(통계지리정보, sgis.kostat.go.kr) ✅ 가용
| 항목 | 엔드포인트 | 비고 |
|------|-----------|------|
| 인증 | `OpenAPI3/auth/authentication.json` (consumer_key+secret→accessToken) | ★플랫폼에 **SGIS_CONSUMER_KEY/SECRET 이미 보유**(인구 분석에 사용 중) |
| **행정구역 경계** | `OpenAPI3/boundary/hadmarea.geojson?adm_cd=&year=` | **GeoJSON Polygon 반환** — 코로플레스 핵심 |
| 인구(통계주제도) | `OpenAPI3/themamap/CTGR_001/list.json` + data | 동/집계구별 인구 |
| 인구·가구(기존 연동) | 플랫폼이 이미 demographics로 인구·연령·가구 숫자 수신 | 밀도 계산의 분자 |

출처: [SGIS OpenAPI](https://sgis.kostat.go.kr/developer/html/openApi/api/data.html) · [행정경계 admGrid](https://sgis.kostat.go.kr/developer/html/newOpenApi/api/dataApi/admGrid.html) · [통계주제도 인구·가구](https://sgis.kostat.go.kr/developer/html/newOpenApi/api/dataApi/thematicMapCTGR.html)

### 1.2 밀도 계산
**인구밀도 = 행정동 인구 / 행정동 면적(㎢).** 경계 GeoJSON의 면적은 polygon에서 산출(shapely) 또는 SGIS 제공 면적 사용.

---

## 2. 핵심 리스크·함정 (★구현 전 반드시 확인)
1. **★좌표계**: SGIS 경계 GeoJSON 기본 = **UTM-K(EPSG:5179)**. 카카오맵은 **WGS84(EPSG:4326)** → **재투영 필수**(pyproj Transformer). SGIS `pg` 파라미터로 WGS84 직접 요청 가능 여부 선확인(가능하면 변환 생략).
2. **adm_cd 매핑**: 대상 주소 → 행정동코드(adm_cd) + **반경 내 인접 동들**의 adm_cd 목록 확보 필요. 주소→bcode(법정동)는 있으나 SGIS는 **행정동**(adm_cd) 기준 → 법정동↔행정동 매핑 또는 SGIS stage(시도→시군구→읍면동) 순회.
3. **accessToken 수명**: SGIS 토큰 만료(보통 4h) → 캐시+갱신. 기존 인구 연동이 이미 처리하면 재사용.
4. **응답 크기/성능**: 반경 내 동 N개 × polygon → GeoJSON 용량. 동 단위(집계구 아님)로 제한해 경량화.
5. **무자료 정직표기**: 경계/인구 누락 동은 회색+"무자료"(가짜 밀도 금지, P4-A priceColor 패턴 동일).

---

## 3. 구현 계획 (단계별)

### Phase B-1 — 백엔드 SGIS 경계 클라이언트 (신규)
- `app/services/external_api/sgis_boundary_service.py`(신규): authenticate(token 캐시) → `get_hadmarea_geojson(adm_cd, year)` → WGS84 재투영(pyproj, 이미 의존성 있음).
- 신규 엔드포인트 `POST /market/population-density` : 입력 {address|lat/lon, radius_m} → ① 주소→adm_cd + 반경 내 인접 adm_cd 목록 ② 각 동 경계 GeoJSON ③ 각 동 인구(기존 demographics 재사용) ④ 밀도 산출 → `{features:[{adm_cd, name, geometry, population, area_km2, density}], center, legend:{min,max}}`. 실패/무자료=정직표기.

### Phase B-2 — 프론트 인구밀도 레이어 (NearbyTransactionsMap 또는 신규 DensityLayer)
- P4-A의 `priceColor` 코로플레스 패턴 재사용 → `densityColor(density, min, max)` 5단계.
- 시장지도(P2 오버레이)에 **레이어 토글 추가**: [실거래 | 분양 | **인구밀도**]. 인구밀도 ON 시 동 경계 polygon을 밀도색으로 채움 + 범례(명/㎢) + 팝업(동명·인구·밀도).
- 카카오맵 Polygon으로 렌더(ParcelBoundaryMap의 polygon 렌더 패턴 차용).

### Phase B-3 — 검증
- 백엔드: 의정부·강남 등 라이브 호출 → 동별 인구·면적·밀도 + 경계 WGS84 좌표 정합(지도 위 위치 정확). 좌표계 오류 시 동이 엉뚱한 위치에 찍힘 = 최우선 검증.
- 프론트: 토글 ON→밀도 코로플레스 렌더, 범례·팝업, 무자료 회색.

---

## 4. 예상 규모·의존성
- 백엔드: 신규 서비스 1 + 엔드포인트 1 (~200줄). pyproj(재투영) 이미 설치됨.
- 프론트: densityColor + 레이어 토글 + polygon 렌더 (~150줄).
- **선결 확인(착수 전)**: ① SGIS 토큰 발급 라이브 테스트(키 유효성) ② boundary/hadmarea.geojson 1건 호출로 좌표계(UTM-K vs WGS84·pg 파라미터) 확정 ③ 주소→adm_cd 매핑 경로 확정.

## 5. 권고
- P4-A(공시지가)는 완료·배포. **P4-B는 §4 선결 3건(SGIS 토큰·좌표계·adm_cd)을 라이브로 확정한 뒤 Phase B-1부터 착수**하면 안전. 좌표계 변환이 유일한 기술 리스크이며 pyproj로 해결 가능.
- 대안(경량): 동 경계 대신 **격자(admGrid) 또는 동 중심점 버블**(인구비례 원)로 시작하면 좌표계·경계 복잡도를 낮추고 빠르게 가치 제공 가능 → P4-B를 2단계(버블 먼저 → 경계 코로플레스 후속)로 분할 권장.
