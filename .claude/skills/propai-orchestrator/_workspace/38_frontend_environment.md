# 38 · 프론트엔드 — 환경분석(Flagship C-2): 일조·조망·스카이라인

## 1. 신규/변경 파일 · 배치
- 신규 `apps/web/components/environment/types.ts` — 응답 계약 타입(EnvironmentResult 등), 백엔드 `POST /api/v1/environment/analyze` 스키마 1:1.
- 신규 `apps/web/components/environment/EnvironmentAnalysisPanel.tsx`(client) — 입력+결과 3섹션 패널.
- 수정 `apps/web/app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` — import(11) + 마운트(480), 지형분석(C-1) 패널 직후 배치. terrain·디지털트윈 패널 사이로 환경분석 자연 결합.
- 커밋 `3a58115` (3 files, +591). push 안 함.

## 2. 구현 상세
### 입력
- 주소(필수, 상위 siteData.address 프리필) + 선택 층수/높이(design_params) + 계절 토글(동지 winter / 하지 summer / 춘추분 equinox, 기본 winter). 실행 버튼.
- 요청: `apiClient.post<EnvironmentResult>("/environment/analyze", { body:{ address, pnu, design_params:{floors,height_m}, season } })`. v1(apiClient.post = /api/v1/* 베이스).

### 일조(태양궤적 시각화)
- **태양궤적**: `sun_positions[{hour,altitude_deg,azimuth_deg}]` → recharts `LineChart`(x=hour, y=altitude_deg, 색 amber #f59e0b). 지평선(고도 0) ReferenceLine. 툴팁에 고도·방위 동시 표기. 고도>-2만 필터(지평선 위). 표본<2면 "표본 부족" 폴백.
- grade 배지: 양호(emerald)/보통(amber)/불리(red) 의미색. 동지 일조시간(sunlight_hours_winter) 카드.
- 정북 일조사선: applies시 required_m·detail, 미적용시 detail("상업지역 등 미적용") 표기.

### 조망
- **개방도 게이지**: 반원형 SVG 아크(0~100, 66↑emerald/33↑amber/이하red) + 바늘. blocked_ratio_pct 카드. best_directions 나침반(🧭) 칩(emerald). 없으면 "트인 방향 없음".

### 스카이라인
- position 배지: 돌출(amber)/조화(emerald)/매몰(blue) 의미색 + desc. subject vs neighbor_avg/max 3개 높이 비교 바(max 정규화).

### 정직성(비협상)
- badges.note → amber 경고 박스. badges.basis[] → 불릿 리스트(text-hint). sources → 출처 라인.
- ok:false → message 폴백 에러. 로딩(busy)·에러(err) 처리. 패널 헤더 "약식" 배지.

## 3. 검증
- `npx tsc --noEmit` EXIT 0.
- `npx eslint components/environment/*.tsx *.ts` EXIT 0(신규 0).
- git diff 확인: apiClient import 보존(L23), 린터 되돌림 없음. page.tsx +4줄(import+마운트)만.

## 4. 커밋
- 해시 `3a58115`, 메시지 `feat(environment): 환경분석 패널 — 일조(태양궤적·일조시간·정북사선)·조망·스카이라인`.
- footer: Co-Authored-By: Claude Opus 4.8 (1M context).

## 5. 백엔드 정합
- 응답 필드 전부 매핑: ok/message/address/zone_type/lat/lon/subject{height_m,floors,neighbor_count}/solar{sun_positions,sunlight_hours_winter,north_setback{applies,required_m,detail},summary,grade}/view{openness_score,best_directions,blocked_ratio_pct,summary}/skyline{subject_height_m,neighbor_avg_m,neighbor_max_m,position,summary}/badges{note,basis}/sources.
- grade("양호|보통|불리")·position("돌출|조화|매몰")·season("winter|summer|equinox") 리터럴 유니온 정확 일치(37_backend_environment.md §6).
- 다크·토큰색(--surface-*, --line, --accent-strong, --text-*) 일관, 과설계 없음, 기존 무파괴(terrain 패턴 재사용).
