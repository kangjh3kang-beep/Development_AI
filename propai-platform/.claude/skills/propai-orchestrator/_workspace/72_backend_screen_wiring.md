# 72 — 백엔드: 부지분석 고도화 수정의 실화면 경로 반영(배선)

## 1. 두 경로 데이터흐름 · 공용화 방식(재사용 확인)
화면 `projects/[id]/site-analysis/page.tsx`(L3) 호출:
- `/zoning/analyze`(routers/auto_zoning.py) → `AutoZoningService.analyze_by_address` + `SiteAnalysisInterpreter`(AI 해석). **종전: interp 입력에 zone_type+max_far_pct만 전달(그라운딩 빈약).**
- `/zoning/comprehensive`(auto_zoning.py) → `LandInfoService.collect_comprehensive`. **종전: effective_far·far_basis_detail·upzoning 미반환.**
- 화면 미호출 `/analysis/comprehensive`(ComprehensiveAnalysisService)에만 `_calc_effective_far`·`_calc_upzoning` 존재 → 화면 미반영이 근본원인.

**공용화(SSOT)**: 신규 `app/services/land_intelligence/far_tier_service.py`로 4함수를 **모듈 레벨**로 추출.
- `calc_effective_far(base, zone_type, land_area)` — 실효용적률 계층(법정범위→조례→계획상한→인센티브)+`far_basis_detail`.
- `simulate_far_optimization(...)`
- `calc_upzoning(base, zone_type, land_area, location, dev_plans)` — 종상향 잠재 시나리오(예상치).
- `ordinance_far_cache_resolver(sigungu, zone_type)` — 조례 캐시 동기 resolver.
`ComprehensiveAnalysisService`는 인스턴스가 `LandInfoService`를 생성하므로(순환참조 위험) **메서드를 신규 모듈로 승격**하고, 기존 `_calc_effective_far`/`_calc_upzoning`은 **얇은 위임자(thin delegator)**로 남겨 로직 복제 0건. `LandInfoService.collect_comprehensive`도 동일 모듈 함수만 호출.

## 2. 변경 파일
- 신규 `apps/api/app/services/land_intelligence/far_tier_service.py` (SSOT).
- 변경 `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py` — 4함수 본문 삭제→위임, sec1은 `base["effective_far"]` 재사용(중복계산 방지), 미사용 import(calc_far_incentive·OrdinanceService) 제거.
- 변경 `apps/api/app/services/land_intelligence/land_info_service.py` — `collect_comprehensive` Phase4 추가(effective_far·upzoning 산출·동봉).
- 변경 `apps/api/routers/auto_zoning.py` — `/zoning/analyze` 인터프리터 입력에 법정한도·effective_far 계층·upzoning 주입+응답 동봉.

## 3. collect_comprehensive 추가 필드(프론트 cf6dfda 정합)
- `effective_far`(객체: `effective_far_pct`·`far_basis_detail{법정범위·조례값·계획상한·인센티브·최종근거·데이터출처·조례확인필요}`·`annotations` 등).
- `upzoning`(객체: `current_zone`·`scenarios`·`potential_far_range`·`summary`).
- `upzoning_scenarios`(리스트), `potential_far_range`(객체).
프론트 page.tsx L666~687이 옵셔널 캡처하던 필드명과 정확히 일치 → 프론트 무변경 렌더.

## 4. 인터프리터 그라운딩/종상향 주입 위치
`routers/auto_zoning.py` `analyze_zoning`:
- `zone_limits`(max_far/max_bcr/legal_basis) — 법정한도 명시 주입(무근거 200% 차단).
- `effective_far` — far_tier_service.calc_effective_far(result, ...) 결과(법정범위·far_basis_detail·annotations 포함).
- `upzoning`/`upzoning_scenarios`/`potential_far_range` — calc_upzoning 결과(예상치 라벨 유지).
인터프리터는 `_legal_limits_block(zone_type)`로도 독립 그라운딩하며, `_extract_compact_data`가 effective_far(annotations)·upzoning(scenarios top3, is_estimate=True)를 발췌.

## 5. 중복계산 방지
- `collect_comprehensive`가 effective_far/upzoning을 1회 산출→`base`에 동봉. `ComprehensiveAnalysisService.analyze`의 sec1은 `base.get("effective_far") or self._calc_effective_far(...)`로 **재사용**(폴백만 재계산).
- `/zoning/analyze`는 collect_comprehensive와 분리 호출(AutoZoning 결과 사용)이라, 동일 SSOT 함수를 AutoZoning result에 1회 적용(별도 호출 간 중복 없음).

## 6. 단위/통합 검증(화면경로 필드 반환 확증) — 외부 LLM·DB 무호출
- `py_compile` 4파일 PASS, 앱 부팅 OK(735 routes, /zoning/analyze·/comprehensive 등록).
- 단위(far_tier_service, 자연녹지 더미): effective_far_pct=**100**(200 아님), far_basis_detail 7키 채움(법정범위 50~100/bcr20·조례확인필요True), upzoning scenarios=3·potential_far_range 존재.
- 통합(collect_comprehensive, 외부단계 스텁): effective_far·far_basis_detail·upzoning·upzoning_scenarios(3)·potential_far_range 반환 확인(effective=100).
- 통합(/zoning/analyze interp 입력 캡처, LLM 스텁): interp 입력에 zone_limits.max_far=100·effective_far.effective_far_pct=100·far_basis_detail·upzoning_scenarios=3 포함, 응답에도 effective_far·upzoning 동봉.
- 기존 `tests/test_legal_zone_limits.py` **45 passed**(검증기 회귀 포함 무파괴).

## 7. 커밋
- `bd0a099` fix(site-analysis): 화면경로 통합 — collect_comprehensive에 실효용적률 계층·종상향 배선+인터프리터 그라운딩 주입.

## 8. 라이브 재검증(기대)
- 자연녹지 부지 `/zoning/comprehensive`: effective_far_pct=100(종전 화면이 zone_limits 폴백 200 표시하던 것 → 100 계층 표시), far_basis_detail로 "조례 확인필요" 라벨, 종상향 카드(1·2종일반 목표·예상 FAR 범위·가능성 등급) 표시.
- `/zoning/analyze` AI 해석: effective_far_interpretation이 법정 50~100% 그라운딩으로 서술(무근거 200% 차단), upzoning_interpretation이 현행과 분리된 예상치로 출력.

## 9. 검증기 정합
- `verification/range_rules._strip_scenarios`가 `upzoning`/`upzoning_scenarios`/`potential_far_range` 키를 재귀 제거(_SCENARIO_KEYS) → 신규 동봉 필드가 현행 위법 오적발을 일으키지 않음(45 테스트 회귀 PASS로 증명).

## 10. 미진/후속
- `/zoning/analyze`의 effective_far는 AutoZoning result(local_ordinance 미포함) 기반이라 조례/계획 상세는 `/zoning/comprehensive` 응답이 더 풍부(화면은 comprehensive를 별도 캡처하므로 표시 충분).
- 라이브(실키) 재검증은 SSH/프로덕션 금지 제약상 미수행 — 로컬 더미/스텁으로 필드 반환·그라운딩만 확증.
- ruff I001(in-function import 정렬)은 원본 코드 패턴 그대로 이식한 것(코드베이스 전반 동일 관행), auto_zoning:255 세미콜론·comprehensive:586 unused address는 본 작업 무관 기존 항목으로 미수정(스코프 유지).
