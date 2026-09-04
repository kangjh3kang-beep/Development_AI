# 실효 용적률(effective FAR) SSOT 전역 단일화 실행계획 (2026-07-16)

- **트리거**: 사용자 질문 — "실효용적률 계산 법규·인허가·설계 엔진이 유기적으로 연동돼 체계적 계산 파이프라인/워크플로우로 구축됐나? 하드코딩 아닌 실무 계산방식인가?"
- **감사 근거**: 엔진연동 정밀감사(origin/main fcc8aa9d, 읽기전용). file:line 확정.

## 0. 사용자 질문에 대한 정직한 답
**Q1. 하드코딩인가? → 아니오(명확).** `calc_effective_far`(far_tier_service.py:192-492)는 용도지역 고정 룩업이 아니라 **계층 min-계산**: 법정범위(§84/§85 SSOT)·조례(ELIS/법제처 실조회 or 정직강등)·계획상한(지구단위)·인센티브(근거有 시만 §46 완화식)·**구조상한(건폐율×층수)**. far_basis가 어느 계층이 바인딩됐는지 정직 반환. 자연녹지 20×4=80 실계산. 법정 상수는 정당(법이 상수)·#320이 오값표 SSOT 교정.

**Q2. 유기적 단일 파이프라인인가? → 부분적(~72%).**
- ✅ **완전 SSOT 단일경유**: 수지(feasibility_v2:299-324 — eff_far→GFA→세대→매출→ROI, far_reliable 플래그)·종합분석(comprehensive:427)·다필지 가중(blended_far_eff_pct에 구조상한 전파).
- ✗ **독자 재계산·발산 3표면**:
  1. **규제분석**(regulation_analysis:73,248-254): calc_effective_far 미경유·naive `eff||ord||legal` 폴백 → 구조상한 누락 → 자연녹지 **100%**. **→ #333이 봉합 중**.
  2. **인허가분석**(permit_analysis:191-207): `min(법정,조례)`만·구조상한 미적용 → 자연녹지 **100%**. **미봉합.**
  3. **설계엔진**(auto_design_engine:47-87,331-427): 자체 보수 static ZONE_LIMITS를 hard cap. effective FAR는 `ordinance_far_pct`로 opt-in 유입·상향불가(min-clamp). calc_effective_far 직접 미호출. (단 자연녹지는 static 12m 높이캡→~4층→FAR≈80% **우회 달성** — 결과는 근사 정합이나 SSOT 경유는 아님.)

**결론**: 계산 실체는 실무 계층산정(하드코딩 아님). 그러나 규제·인허가·설계 표면이 실효FAR를 독자 재계산해 자연녹지 등에서 80% vs 100% 발산. **★"2026-06-19 산/임야 과대표시" 버그클래스가 규제/인허가 표면에 잔존** — 공용헬퍼 일원화로 봉합해야 한 곳 고치면 전역 수렴.

## 1. 작업 패키지

### WP-U0 (진행 중): 규제분석 발산 봉합 = **PR #333**
- regulation_analysis가 `comp["effective_far"]`(SSOT 80%) 소비. R1 완료·리뷰 REVISE 반영 중(혼합다필지 구조상한 게이트·sweep 주장 정정).

### WP-U1 (HIGH·다음 착수): 인허가분석엔진 실효FAR 단일화
- **근본**: `permit_analysis_service.py:191-207`이 `eff_far=min(legal, ordinance.effective_far)`·구조상한 미적용 → 자연녹지 100% 과대. 인허가 가능성 판정이 과대 실효FAR로 오도(과대낙관 — site_hallucination_guard 정책 위반).
- **수정(공용화)**: permit의 실효FAR 산정을 `far_tier_service.calc_effective_far`(또는 comp["effective_far"]) 단일경유로 전환. 구조상한 반영. AutoZoning enrichment 경로(`_enrich_site`, site에 max_far 미주입 케이스)가 SSOT를 타게. far_basis·far_reliable 정직 전파.
- **게이트**: 자연녹지 인허가분석 실효FAR=80%(설계·규제와 동일). 층수클램프 없는 지역 무영향(250% 유지) 회귀테스트.

### WP-U2 (MEDIUM): 설계엔진 hard cap 승격 + 일조 역피드백
- (a) auto_design_engine의 static ZONE_LIMITS hard cap을 `calc_effective_far` national_far 기준으로 승격(상향 허용·SSOT 정합). ★단 "전형 조례 수준 보수" 정책·≤국가상한 가드(test_zone_limits_engine_sync)와 충돌 없게 — 설계 기본값은 보수 유지하되 실효FAR 입력은 SSOT 경유. 위험도 있어 신중.
- (b) 일조 후퇴(compute_north_step_profile) 결과를 표시 실효FAR 계층에 **역주입** — 현재 구조상한은 건폐율×층수만, 정북일조 실효높이 미반영으로 주거지 고층 실효연면적 과대 가능. `_structural_cap_for`에 일조높이 클램프 계층 추가.

### WP-U3 (LOW·위생): 잠복 그림자표·근사계수 정직화
- `far_incentive_calculator.NATIONAL_FAR_LIMITS`(:64-88) = ZONE_LIMITS 중복 그림자표(현재 값일치·far_tier가 national 주입해 무해하나 drift 위험) → ZONE_LIMITS 위임 또는 parity 테스트.
- 인센티브 alpha 고정계수(주거1.5·상업1.2·공업1.3)를 "근사(참고)" 정직 표기 또는 실 조례 스케줄 연동(백로그).
- 조례 정적캐시 의존 명시(ELIS 실패 시 캐시 폴백 정직 표기).

## 2. 실행 순서·게이트
- WP-U1(permit)은 regulation_analysis와 **다른 파일**이라 #333과 무충돌 → #333 반영 중 병행 착수 가능(origin/main 기준).
- 성장루프: 구현→적대리뷰(★수치 정확성·설계/규제/인허가 3표면 동일 80% 교차검증·회귀 층수클램프 없는 지역 무영향)→R2→CI→머지→168 배포→라이브(자연녹지 부지 3화면 실효FAR 일치 확인).
- 무목업·정직: 실효 미산정=미산정, far_basis 정직 전파. 원장(record_user_analysis) 계약 무변이.
- 완성도 기준선: 엔진연동 ~72% → 목표 95%+(수지·종합·규제·인허가·설계 5표면 실효FAR SSOT 단일경유).

## 3. 참고 근거(file:line)
far_tier_service.py:192-492(계층계산)·59-78(구조상한)·229(정직강등) / legal_zone_limits.py:153-184·51-55(층수근거) / feasibility_service_v2.py:299-324(수지 SSOT) / regulation_analysis_service.py:73·248-254(#333 봉합) / permit_analysis_service.py:191-207(WP-U1) / auto_design_engine.py:47-87·331-427(WP-U2) / far_incentive_calculator.py:64-88(WP-U3 그림자표) / comprehensive_analysis_service.py:1628-1698(다필지 가중).
