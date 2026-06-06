# 37 · 백엔드 — 환경분석(Flagship C-2): 일조·조망·스카이라인

## 1. 변경/신규 파일 · 엔드포인트 · 마운트
- 신규 `apps/api/app/services/environment/__init__.py`
- 신규 `apps/api/app/services/environment/environment_service.py` — 분석 본체(천문식 태양위치·약식 일영·정북사선·개방도·스카이라인)
- 신규 `apps/api/routers/environment.py` — `POST /api/v1/environment/analyze`(얇은 위임)
- 수정 `apps/api/main.py` — `environment` import(63) + `include_router(prefix="/api/v1/environment", tags=["환경분석"])` (terrain 마운트 직후)
- 엔드포인트: `POST /api/v1/environment/analyze`
  - Req: `{address?, pnu?, design_params?{floors,height_m,floor_height_m}, season?(winter|summer|equinox, 기본 winter=동지)}`
  - address/pnu 둘 다 없음 → 422. 좌표/필지 불가 → `{ok:false, message, sources}`.
  - 90초 가드(ENV_TIMEOUT_S=88, 주변조회 30s, 용도지역 30s). numpy 천문계산만, ML/heavy 의존 0.

## 2. 핵심 로직
### 일조(solar)
- **태양 위치**: NOAA 근사식(numpy/math만). Cooper 적위 + Spencer equation of time + 경도/시간대 보정(KST 135°E) → 시간각 → 고도(asin)·방위(atan2, 정북0·시계방향). 05~19시 정시 15개 궤적(`sun_positions` — 3D 렌더 보조).
- **약식 일영(그림자) 가림**: 주변 footprint(ENU)를 `_neighbor_polar`로 (거리·방위·추정고) 극좌표화 → 동지 9~15시 30분 간격 표본마다 태양 방위 ±18° 내 이웃의 '상단 올려본각 > 태양고도'면 가림 → 미가림 비율×6h = `sunlight_hours_winter`. 등급 양호(≥4h)/보통(≥2h)/불리.
- **정북 일조사선**: 건축법 제61조·시행령 제86조. 전용/일반주거지역만 적용. 높이 ≤10m→1.5m, >10m→높이/2 이격. 상업·공업 등 비적용 명시.

### 조망(view)
- 건물 상부에서 8방위(45°) 섹터별 이웃 최대 올려본각 → 개방도(0°개방~45°가림 정규화) → `openness_score`(0~100)·`blocked_ratio_pct`·`best_directions`(개방 ≥0.6 상위4).

### 스카이라인(skyline)
- 대상 높이 vs 주변 평균/최고(numpy). >최고×1.3 또는 >평균×2 → 돌출, <평균×0.6 → 매몰, 그 외 조화. 데이터 부족 시 조화·판단보류.

## 3. 정직성(비협상)
- `badges.note`: "약식 계산·정밀 일조분석/측량 아님·참고용. 건축사 검토 필요."
- `badges.basis`: 태양위치=천문 근사식(대기굴절·지형차폐 미반영), 일영=footprint 추정고 2D 평면투영, 정북사선=기본규정값(조례·완화 미반영), 개방도=8방위 올려본각(수목·원경 미반영).
- `sources`: VWorld(필지·주변·용도), NOAA 천문식, 건축법 제61조.
- 주변건물 높이는 scene_service 추정 기본(9m) — 실측 아님(badges 명시). footprint-only 데이터 한계 정직 노출.

## 4. 로컬 검증(.venv)
- AST OK ×3(service/router/main). app import OK, 라우트 `/api/v1/environment/analyze` 마운트 확인.
- **태양고도 합리성**: 서울(37.5665) 동지 정오 **28.54°**(이론 ~29°), 하지 정오 **74.16°**(이론 ~76°), 방위 남측(~172°/151°), 06/18시 음수(지평선 아래). → 천문식 정확.
- 정북사선: 2종일반주거 30m→15.0m, 8m→1.5m, 상업 비적용. 합리.
- 합성 이웃: 남 30m건물(20m)이 대상16m 일조 가림 True / 대상40m False, 개방도·돌출(80m) 판정 정상.
- **실주소 1회**(강남 테헤란로152): ok:true, zone=제2종일반주거지역, lat/lon 실좌표, 주변 60필지, 15층(49.5m) 동지 6.0h·양호, 정북사선 적용, openness 100, skyline 돌출. PASS.
- 422: 빈 요청 → 422 확인.
- ruff: F401/I001 수정. 잔여는 SIM108(ternary 권고)·방어적 float/int 캐스트 경고만(에러 아님).

## 5. 커밋
- 메시지: `feat(environment): 환경분석 — 일조(일조시간·정북사선)·조망(개방도)·스카이라인`
- 해시: (아래 보고 참조)

## 6. 프론트/QA 정합
- 응답 스키마: `{ok, address, pnu, zone_type, lat, lon, subject{height_m,floors,neighbor_count}, solar{sun_positions[{hour,altitude_deg,azimuth_deg}], sunlight_hours_winter, north_setback{applies,required_m?,detail}, summary, grade}, view{openness_score, best_directions[], blocked_ratio_pct, summary}, skyline{subject_height_m, neighbor_avg_m, neighbor_max_m, position, summary}, badges{note,basis[]}, sources[]}`
- **3D 렌더 보조**: `solar.sun_positions`(시각별 고도/방위) → 디지털트윈 태양궤적/그림자 시뮬레이션 직접 사용 가능. `subject.height_m`로 매스 높이 정합.
- 계약서(15_flagshipC1) 정북사선·약식 정직성 톤 일치. terrain(C-1)과 동일 `_resolve_location` 출처·동일 90초 가드 패턴.
