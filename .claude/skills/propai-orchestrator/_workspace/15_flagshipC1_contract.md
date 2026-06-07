# Flagship C-1 — 지형분석(경사도·토공량·지형단면) API 계약

원칙: 정직·할루시네이션 방지. 표고 소스·해상도를 응답에 명시. 소형 필지에서 저해상도 DEM은 신뢰낮음 → confidence/note로 표기. 검증된 측량 아님.

라우터 신규: `/api/v1/terrain` (apps/api/routers/terrain.py + app/services/terrain/terrain_service.py). main.py 마운트.

## 표고(DEM) 소스 — 백엔드가 라이브 정찰 후 택1(폴백체인)
1. (우선) VWorld/NGII 수치표고 API가 키로 점/그리드 표고를 주는지 라이브 확인.
2. (폴백) OpenTopoData(SRTM 30m, 무키, https://api.opentopodata.org/v1/srtm30m?locations=lat,lon|...) 또는 Open-Elevation. 국외호스트지만 Oracle 아웃바운드 가능.
- 선택 결과를 응답 `elevation_source`·`resolution_m`에 정직 기록. 소형필지(<DEM해상도²)면 note에 "광역 지형 근사, 정밀측량 아님".

## POST /api/v1/terrain/analyze
### Request
{ "address": str|null, "pnu": str|null, "target_level_m": number|null, "section_bearing_deg": number|null }
- pnu/address 둘 다 없으면 422. 좌표/필지 확인 불가 → ok:false+message.
- target_level_m: 토공 기준고(계획고). 미제공시 필지 평균표고 사용.

### Response (200)
{
  "ok": true, "address": str, "pnu": str|null, "coordinates": {"lat","lon"},
  "elevation_source": str, "resolution_m": number, "sample_count": int,
  "area_sqm": number|null,
  "slope": { "mean_pct": float, "max_pct": float, "aspect_deg": float|null, "class": "평지|완경사|경사|급경사", "detail": str },
  "earthwork": { "base_level_m": float, "cut_volume_m3": float, "fill_volume_m3": float, "net_m3": float, "balance": "절토우세|성토우세|균형", "detail": str },
  "cross_section": { "bearing_deg": float, "length_m": float, "points": [{"dist_m":float,"elev_m":float}], "min_elev_m":float, "max_elev_m":float, "relief_m":float },
  "confidence": float,  // 해상도 대비 필지크기로 산정(소형+저해상도→낮음)
  "note": str, "sources": [str]
}

## 로직(재사용/신규)
- 좌표/필지 폴리곤: app/services/external_api/vworld_service.py (geocode_address, get_parcel_by_pnu — 폴리곤 좌표). auto_zoning_service analyze_by_address.
- 표고 그리드: 필지 bbox에 NxN 격자(예 9x9~15x15) 좌표 생성 → DEM API 일괄질의(asyncio.wait_for 가드, 배치). numpy로 그리드화.
- 경사도: 인접 격자 표고차/거리 → 경사율(%), aspect, mean/max. class 매핑(평지<5%, 완경사5-15, 경사15-30, 급경사>30 등 합리적 기준).
- 토공량: base_level(target 또는 mean) 기준 각 셀 (elev-base)×셀면적 → 절토(+)/성토(-) 합. net.
- 지형단면: 필지 중심 통과 직선(bearing, 미지정시 최대경사방향) 따라 표고 샘플 → 프로필 points.
- 빈/오류: 필지 폴리곤 없으면 bbox(반경 추정)로 진행하되 area_sqm=null·note. DEM 전부 실패 → ok:false.

## 90초/가드
- DEM 일괄질의 asyncio.wait_for(배치 ≤ 1~2회), 무거운 연산 numpy 벡터화. ML 모델 없음.

## 프론트(별도)
- 패널 `components/terrain/TerrainAnalysisPanel.tsx`: 입력(주소[+계획고·단면방위]) → 3섹션:
  - 경사도: class 배지·mean/max%·aspect(나침반), 색.
  - 토공량: 절토/성토/net m³ 바, balance 배지, base_level.
  - 지형단면: points로 SVG 단면 프로파일(min/max/relief). (간단 라인차트, recharts 있으면 재사용)
  - elevation_source·resolution_m·confidence·note(해상도 한계) 명시. EXPERIMENTAL/참고용 표기.
- 배치: 부지분석(site-analysis) 화면 또는 공사비(지형→토공비 연계) 화면에 섹션 결합. apiClient v1. 토큰색·다크.
- 데이터흐름: 가능시 useProjectContextStore에 terrain 저장(공사비 토공 연계). 과설계 금지.
