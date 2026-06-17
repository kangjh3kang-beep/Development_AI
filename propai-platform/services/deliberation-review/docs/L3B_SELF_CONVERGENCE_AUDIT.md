# L3-B 자기수렴 감사 — 고정점 보고서

페이즈: **L3-B**(공학/시뮬 엔진 — 일조/피난/주차/조망 결정론 모델). 위원 재량 무관 정량 지표.
선행: R0~R3. A절 재사용 + INV-19(모델 명시 method_trace)/INV-20(시뮬 파라미터 주입)/INV-21(입력 신뢰도 전파·결손 UNAVAILABLE).

## 회차별 신규 결함수 (단조감소)

| 회차 | 신규 결함 | 조치 |
|------|-----------|------|
| 1 | **2** — ① `run_egress`가 `travel_distance` 결손 시 KeyError 크래시(INV-21 위반) ② sunlight method_trace가 정오 단일 그림자 근사라는 모델 한계 미표면화(감사 D절) | ① 결손 가드 → UNAVAILABLE + 테스트 ② assumptions에 근사 한계 명시 + 테스트 |
| 2 | **0** | **고정점 도달** |

단조감소: **2 → 0**.

## 감사 D절 — 모델 가정 한계 표면화 재추적
- 모든 SimMetric은 method_trace(model/assumptions/inputs/basis) 동반. sunlight는 "정오 단일 그림자 근사(일중 변화 미반영)·지형/식재 무시·노출비례 선형 근사"를 assumptions로 표면화. egress/parking은 모델·근거조문·입력 기록. 필수 입력 결손은 UNAVAILABLE.

## INV 위반 0 체크리스트
- [x] INV-19 모델 명시 — emit가 method_trace 없는 값 차단, 가정/한계 표면화.
- [x] INV-20 시뮬 파라미터 주입 — 모델 상수(축경사/시간각/기준시간/보행속도/회전반경)는 sim_params.json. AT-2 static_scan 0.
- [x] INV-21 입력 신뢰도 전파 — confidence=geom_conf 상속, 필수 결손(계단/보행거리/회전반경/위도기하)→UNAVAILABLE.
- [x] INV-1..18(승계) — 결정론(LLM 미사용)·재현성·파라미터화 유지.

## 게이트 결과
- 수용 테스트: **85 passed**(누적; L3-B AT-1..7 + 결손가드/한계표면화 보강).
- 마이그레이션: `0007_l3b` 실DB(review) — sim_metric, sim_param.
- 정적 스캔: sim 소스 하드코딩 0. 린트: ruff clean.

**결론: L3-B DoD 충족 — 고정점.** 다음 = L4(유사사례 비교·성숙도 게이팅).
