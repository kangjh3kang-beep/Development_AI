# Flagship C-1 — 지형분석 백엔드 구현 보고 (2026-06-05)

커밋: `f847d6a` — feat(terrain): 지형분석(경사도·토공량·지형단면) 백엔드 — DEM 기반

## 1. 신규/변경 파일·엔드포인트·마운트
- 신규 `apps/api/routers/terrain.py` — 얇은 라우터. `POST /analyze`. address/pnu 둘 다 없으면 422.
- 신규 `apps/api/app/services/terrain/terrain_service.py` — 본체(475줄).
- 신규 `apps/api/app/services/terrain/__init__.py`.
- 변경 `apps/api/main.py` — import 블록에 `terrain` 추가(L93), 마운트 추가(L407):
  `app.include_router(terrain.router, prefix="/api/v1/terrain", tags=["지형분석"])`
- 엔드포인트: **POST /api/v1/terrain/analyze**
  Request: `{address?, pnu?, target_level_m?, section_bearing_deg?}` (계약 그대로)
  Response: 계약 스키마 100% 준수(ok/address/pnu/coordinates/elevation_source/resolution_m/
  sample_count/area_sqm/slope/earthwork/cross_section/confidence/note/sources).

## 2. DEM 소스 라이브 정찰 결과 (★중요)
- **VWorld 좌표·필지: 동작** (제공키 7C8CD147…). 역삼동 736 geocode → PNU 1168010100107360000,
  get_parcel_by_pnu 폴리곤 취득 OK. **좌표·필지 폴리곤에만 사용**.
- **VWorld/NGII 표고 점/그리드 API: 미존재.** LT_C_DEM/getDEM/ned getDem 등 라이브 시도 →
  전부 INVALID_RANGE / URL_TYPE / NOT_FOUND. NGII DEM은 WCS/파일(타일) 기반이라
  단순 점-표고 JSON 엔드포인트가 공개되지 않음. → 표고는 VWorld로 불가.
- **채택: OpenTopoData SRTM 30m (무키) — 라이브 동작 확인.**
  `https://api.opentopodata.org/v1/srtm30m?locations=lat,lon|...`
  실측 예시(강남 역삼 인근): lat/lon 5점 → [61, 66, 54, 58, 66] m, 응답 ~0.67s.
  배치 100점/req·1req/s 제한 준수(분할시 sleep 1.05s). 단일 11x11=121점은 2배치(100+21)로 처리.
- 응답 `elevation_source`="OpenTopoData SRTM 30m (공개 무료, NASA SRTM)", `resolution_m`=30.0.

## 3. 산정 로직 + 과신방지
- **격자**: 필지 bbox(폴리곤) 또는 좌표±50m → 11x11 격자. 필지가 1셀(<30m)보다 작으면 bbox를 30m로 패딩.
- **경사도**: np.gradient 중앙차분(dz/dx,dz/dy)→ slope%=sqrt(gx²+gy²)*100. mean/max, aspect(내리막 방위).
  class: 평지<5 / 완경사5-15 / 경사15-30 / 급경사>30.
  ★**sub-resolution 보정**: 격자 간격이 DEM 30m보다 촘촘하면 SRTM 정수-m 양자화로 경사가 과대해짐
  → 수평 baseline을 max(격자간격, 30m)로 클램프. (보정 전 역삼동 42%급경사→보정 후 4.58%평지, 정상화)
- **토공량**: base=target_level_m 또는 평균표고. 셀별 (elev-base)*셀면적 → 절토(+)/성토(-)/net.
  balance: |net|<max(cut,fill)*0.1 → 균형. detail에 "다짐/팽창률 미반영" 명시.
- **단면**: 중심 통과 직선(bearing 미지정시 최대경사=aspect 방향). 31샘플, bbox 클램프, 최근접 격자 표고.
- **confidence/note**: base 0.6×표고취득률. 필지<900㎡(1셀) → ×0.4 + note 경고("필지 내 미세지형 분해 불가").
  4셀 미만 → ×0.7. 폴리곤 없으면 ×0.8(area_sqm=null). 항상 "참고용(EXPERIMENTAL)·정밀측량/검증토목설계 아님".

## 4. 로컬 라이브 호출 결과 (.venv, 실주소)
역삼동 736 (필지 630.9㎡, conf 0.24):
- slope: mean 4.58% / max 10.67% → 평지, aspect 남서(232°)
- earthwork(평균표고 기준): cut 2070 / fill 2070 / net 0 → 균형
- earthwork(target=50 지정): cut 3161 / fill 527 / net 2634 → 절토우세
- cross_section: relief 5m, 27 points
- note: "필지 631㎡가 DEM 1셀(≈900㎡)보다 작아 … 광역 지형 근사"
- 빈요청 → 라우터 422. 좌표/DEM 실패 → ok:false+message.
검증: AST OK / `from routers.terrain import router` OK / 풀앱 마운트 `/api/v1/terrain/analyze` OK(runtime PYTHONPATH=/app:/app/apps/api).

## 5. 커밋 해시
`f847d6a` (4 files, +522). 명시 경로만 add, footer Co-Authored-By 포함. push·SSH배포는 오케스트레이터.

## 6. 프론트/QA 확정사항 (계약 대비)
- 계약 스키마 변경 없음. 모든 필드 그대로 구현.
- **표고 소스 확정 = OpenTopoData SRTM 30m** (VWorld DEM 미지원). resolution_m=30 고정.
- slope.aspect_deg는 내리막(downhill) 방위(북=0,시계). null 가능(평탄). 프론트 나침반 표기시 _aspect_to_compass와 동일 8방위 매핑 사용.
- cross_section.bearing_deg: 입력 미제공시 백엔드가 최대경사방향으로 자동결정 → 응답값 그대로 표기.
- 소형 필지(<900㎡)는 confidence가 매우 낮게(0.2~0.3) 나오는 게 **정상**(SRTM 한계). 프론트는 confidence·note를 반드시 노출.
- 배포 주의: Oracle 백엔드는 .env VWORLD_API_KEY 실키 필요(로컬 .env는 더미). 표고(OpenTopoData)는 무키이나 국외 아웃바운드 필요.
