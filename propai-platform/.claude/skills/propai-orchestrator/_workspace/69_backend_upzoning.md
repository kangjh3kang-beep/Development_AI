# 69 — 백엔드: 종상향/종변경 잠재력 분석 (upzoning potential)

## 1. 조사 (기존 자산 재사용)
- `app/services/zoning/legal_zone_limits.py` — `legal_limits_for`(법정 min/max FAR·BCR), `normalize_zone_name`, `LEGAL_BASIS`, `check_against_legal`(근거기반 3단 판정), `_has_relaxation_basis`(완화근거 키워드/필드 탐색). → 목표 용도지역 법정범위 도출 + 검증기 정합에 재사용.
- `app/services/land_intelligence/ordinance_service.py` — `ORDINANCE_CACHE` `{시도: {용도지역: {bcr, far}}}` 정적 캐시. → 목표 용도지역 조례 용적률 동기 resolver로 재사용(외부 API 미호출).
- `app/services/development/scenario_simulator.py` — 정책별(지구단위/도시개발/가로주택/모아주택/역세권) 적용판정 존재. 종상향 경로 카탈로그·판정 규칙을 정합되게 매핑(중복 신설 없이 신규 분석기는 '종상향 후 예상 용적률 projection'에만 집중).
- `app/services/land_intelligence/comprehensive_analysis_service.py` — Section1~7 구조. Section8(upzoning) 추가.
- `app/services/ai/site_analysis_interpreter.py` — 해석 프롬프트/expected_keys/compact 페이로드.

## 2. 신규/변경 파일
- 신규 `app/services/zoning/upzoning_potential.py` — `UpzoningPotentialAnalyzer` 규칙엔진.
- 변경 `app/services/land_intelligence/comprehensive_analysis_service.py` — `_calc_upzoning`+`_ordinance_far_cache_resolver`, 결과에 `upzoning`/`upzoning_scenarios`/`potential_far_range`.
- 변경 `app/services/ai/site_analysis_interpreter.py` — 종상향 해석 프롬프트 + `upzoning_interpretation` expected_key + compact `upzoning` 섹션(top3).
- 변경 `app/services/verification/range_rules.py` — 현행 검증 시 잠재 시나리오 서브트리 제외(`_strip_scenarios`).
- 변경 `tests/test_legal_zone_limits.py` — 종상향 7 테스트 추가(38→45).

## 3. 종상향 경로 규칙 / 시나리오 구조 / feasibility
- 경로 카탈로그 `PATHS`: 도시개발사업·지구단위계획수립·정비사업·역세권활성화·역세권시프트·공공주택지구·가로주택·모아주택. 각 경로 = label·legal_basis·timeline_est·면적/역세권/주거 요건·note.
- `UPZONE_TARGETS`: 현재 용도지역→현실적 목표(예 자연녹지→1·2종일반). `ZONE_PATHS`: 현재 용도지역별 적용 가능 경로.
- 목표 FAR `_target_far_pct`: 조례 resolver 우선(min(조례, 법정상한)), 없으면 법정 min~max + "조례 확인필요".
- feasibility 등급화 `_grade`: 면적요건(±)·역세권(±)·주거요건(−)·다필지 인접성(±)·정책부합 전제·공공시행(−)·규제 블로커(개발제한/상수원/자연공원 등 −2). score≥1 상 / ≥−1 중 / else 하. 부족 데이터는 "확인필요"로 정직 표기.
- 시나리오 키: path·path_key·target_zone·expected_far_pct_low/high·expected_far_source·conditions[]·feasibility·feasibility_reason·legal_basis·timeline_est·caveats[]·is_estimate(True)·marker.

## 4. 현행/잠재 2계층 분리 + 검증기 정합
- 모든 시나리오는 `is_estimate=True`·`marker="potential_upzoning_scenario"`·disclaimer·caveats 동반(단정 금지).
- 검증기 `range_rules.run_range_checks`: 현행 zone 엄격검사(`effective_far`/`far` + `_has_relaxation_basis`) 직전에 `_strip_scenarios`로 `upzoning`/`upzoning_scenarios`/`potential_far_range` 컨테이너 및 marker/is_estimate+target_zone dict를 제거한 사본 사용.
  - 효과: 잠재 시나리오의 `legal_basis`(지구단위계획/종상향/역세권/완화 키워드)·expected_far(목표 250%)가 현행 무근거 초과 판정을 오염시키지 않음.
  - 현행 무근거 200%(자연녹지)는 종상향 섹션 유무와 무관하게 여전히 **high**. (회귀 테스트로 증명)

## 5. interpreter 종상향 해석
- USER_PROMPT에 "종상향/종변경 잠재력(★현행과 별도 — 예상치)" 블록: ①현행 혼동 금지 ②목표지역 기준 예상치 명시 ③가능성·근거법령·전제 동반 ④비단정 표현 ⑤scenarios 빈 경우 미매핑 안내.
- `upzoning_interpretation` expected_key 추가. compact 페이로드에 top3 시나리오만 발췌(토큰 절약).

## 6. 단위테스트 (.venv pytest) — 45 passed
- 자연녹지 충분면적→시나리오·target 일반주거·expected_far>100·feas 상 존재.
- 조례 resolver 주입→서울 1종일반 150% 반영.
- 소형(300㎡)→전부 feas 하·면적미달 사유.
- 농림(미매핑)→시나리오 0·확인필요.
- 규제구역(개발제한)→feas 하향·caveat 해제 선행.
- ★검증기: 현행 100%+잠재 250% → 현행 high 없음.
- ★★검증기(핵심): 현행 200% 무근거 + 종상향 섹션 → 여전히 high.

## 7. 커밋
- (아래 git log 참조)

## 8. 라이브 재검증 시나리오
- `POST /api/v1/zoning/comprehensive` (또는 부지분석 종합) 응답에 `upzoning`/`upzoning_scenarios`/`potential_far_range` 포함 확인.
- 자연녹지 대형 부지 주소: scenarios 다건·feas 상/중·예상 FAR 범위.
- 부지분석 인터프리터 카드: `upzoning_interpretation`가 현행과 분리된 예상치로 렌더되는지(프론트 작업 필요 시 후속).

## 9. 미진/후속
- `_calc_upzoning`은 `parcel_count=1`·`adjacency_contiguous=None` 고정 — 다필지 통합개발 시 shapely 인접성 결과를 전달하도록 후속 연동 가능.
- 역세권 판정은 location.transportation.nearest_subway ≤500m 단순규칙 — 추후 노선/환승 가중 가능.
- 조례 resolver는 정적 ORDINANCE_CACHE 폴백만 사용(실시간 조례 API 미연동, 의도된 동기·무외부호출 설계).
- 프론트 카드 노출(현행/잠재 2계층 UI)은 별도 프론트 작업.
