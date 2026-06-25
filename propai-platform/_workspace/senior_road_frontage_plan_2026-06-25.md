# 시니어 접도(도로폭) 데이터 확보 → 심의 접도 CSP 활성 — 구현계획 (2026-06-25)

## 상세조사 결론 (수집·분석)
도로폭/접도 분석 **빌딩블록이 이미 존재** → 신규 엔진 구축이 아니라 **배선**이 정답(CLAUDE.md 중복방지·공용화):
- `land_info_service.estimate_road_width_m(road_side)` — 토지대장 '도로접면'(광대로/중로/소로/세로/맹지) → 대표 너비(m). 출처: 부동산 가격공시 토지특성조사표.
- `land_info_service.compute_precise_road_width_m` — 연속지적도 도로필지 MRR 짧은변(geospatial 정밀 측정).
- `auto_zoning_service`가 `get_land_characteristics(pnu)` 호출(road_side 보유 경로) — 그러나 출력에 road_width_m 미노출.
- `development_feasibility_validator._check_road` — dev_type별 도로폭/접도 요건 검증(M01~M13).
- `comprehensive_analysis road_width_m` 노출. 다수 서비스가 road_width_m 1급 필드로 사용.
- 심의 evaluator(deliberation.py)는 **이미 road_width_actual≥road_width_required CSP 지원**.

## 갭
- road_width_m이 프론트 siteAnalysis store에 미반영 → 심의 접도 CSP가 inputs 못 받음.
- 건축법 44조·시행령 28조 일반 접도요건(연면적 기준)이 standalone 룰로 없음(dev_type 검증만).

## 구현 (end-to-end 배선·full-stack·무목업)
1. **백엔드 auto_zoning_service**: 출력에 `road_width_m` 추가 — 이미 fetch하는 land_characteristics의 road_side를 `estimate_road_width_m`로 환산(DRY·신규계산 0·미확보 시 null).
2. **프론트 store**: `siteAnalysis.roadWidthM` additive(default null).
3. **프론트 AutoZoningBadge**: auto_zoning 응답의 road_width_m → roadWidthM 캡처.
4. **build-inputs 심의**: road_width_actual=roadWidthM(pos)·road_width_required=건축법 44조(연면적≥2000㎡→6m·else 4m, 결정론 룰). 둘 다 present → 접도 조항. 미확보(null) 생략(무목업).

## 검증 (성장루프)
- 백엔드: auto_zoning road_width_m pytest(road_side→너비·null graceful).
- 프론트: build-inputs 접도 매핑·required 룰·null 생략 테스트. type-check·lint·next build.
- end-to-end: 도로 4m < 필요 6m(연면적 2500㎡) → 심의 CSP 접도 위반 BLOCK 라이브.
- 무회귀: 전체 senior + store + 백엔드 pytest. 코드리뷰 ACCEPT.

## 정직성
- road_width_m은 도로접면 추정(대표값) — provenance 표기. 정밀 geospatial은 별경로(있으면 우선).
- 건축법 44조 required는 결정론 법규룰(verified). 미확보 도로폭은 생략(거짓 위반 방지).
