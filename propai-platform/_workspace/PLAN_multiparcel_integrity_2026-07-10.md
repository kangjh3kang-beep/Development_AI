# 다필지 통합분석 실무 정합성 100% — 구현계획 (2026-07-10)

## 라이브 증거 (용인 고기동 689 외 8필지, 프로덕션 /ko/analysis)
파편화(비연접) 9필지(자연녹지 + 산84 개발제한구역 1,785㎡ + 지목 도로 2필지)를 단일 대지로 취급:
통합 9,851㎡ → "실효 용적률 139.6%(자연녹지 법정상한 100% 초과)·실효 건폐율 35.8%·최대 연면적
13,752㎡·단독주택 50세대 3층·지하주차 229대·FAR 최적화 전 시나리오 139.6% 고정" +
같은 카드의 근거 텍스트는 "100.0% 적용" 서술(수치·근거 충돌) + "일조권: 상업/공업지역 면제"(자연녹지) +
건축가능랭킹 현행 0건 vs 개발방식 섹션 단독·전원 가능(모순).

## 근본원인 (2에이전트 교차 추적으로 확정)

| # | 근본원인 | 위치 | 심각도 |
|---|---------|------|--------|
| RC1 | zone 미매칭 필지(개발제한구역·도로 등)에 **하드코딩 폴백 200%/60%** 적용 → 면적가중 139.6%/35.8% 재현, `_far_legal`에도 복제되어 FAR 시뮬 cap=base(전 시나리오 고정) | far_tier_service.py:138-149 ← auto_zoning.py:1286-1356(_enrich) | CRITICAL |
| RC2 | **인접성 판정 미배선**: `_parcel_adjacency`(shapely 연결요소) 정답 자산이 /zoning/integrated-analysis에만 배선 — comprehensive·rough-scenario·feasibility_v2·pipeline은 검증 없이 단일 대지 취급 (geometry는 전달되는데 판정만 누락) | build_integrated_context(comprehensive_analysis_service.py:1408) | CRITICAL |
| RC3 | **비대지 필지 합산**: `compute_usable_area`(도로·구거·하천 지목 + GB BLOCKED 제외, 3계층 정산) 정답 자산 존재하나 total_area/GFA 경로 미소비 — gross 전량 합산 | special_parcel.py:1421(_aggregate total_area) | CRITICAL |
| RC4 | 세대수·주차·층수 산정이 단일 대지 전제(gate/contiguous 무시하고 무조건 산정) + special_parcel 감지가 supply_areas **이후** 실행이라 차단 불가 | comprehensive_analysis_service.py:475,854-860,959 | HIGH |
| RC5 | 허용용도 소스 3중 분열: design_geometry.ALLOWED_USES_BY_ZONE에 녹지·관리 키 누락 → 랭킹 0건 vs ZONE_PERMIT_MATRIX·별표17(단독·전원 가능=정답) | buildable_options.py:197 / design_geometry.py:151-166 | HIGH |
| RC6 | 법정초과 할루시네이션 가드(check_against_legal)가 /analysis/comprehensive 핫패스 미배선(verify/pipeline 전용) | verification/range_rules.py:134 미호출 | HIGH |
| RC7 | rebuild_area_dependent가 면적의존 문구만 재생성 — 법정/조례 서술 stale("139.6% vs 100%" 충돌) | far_tier_service.py:59-102 | MED |
| RC8 | 일조권 이분법 오라벨: 비주거 전량 "상업/공업지역 면제" 하드코딩(자연녹지에 사실오류 서술) | development_feasibility_validator.py:131-133 | MED |
| RC9 | build_multi_parcel_report(S5 다필지 최종보고, exclusion 시나리오 포함) 완성 오펀 — 소비처 0 | special_parcel.py:1740 | MED |

## 구현계획

### P0 (이번 세션 — fix/multiparcel-integrity 단일 브랜치)
- **P0-1 (RC1)**: far_tier_service 폴백 리터럴 제거 — zone 미매칭 시 eff/legal=None(무날조 정직) +
  `_aggregate_integrated_zoning`의 기존 결측 제외·warning 경로에 위임. GB/도로 필지는 blend에서
  제외되고 far_basis_note에 "용도 미확인 N필지 가중 제외" 명시. 회귀 테스트: 개발제한구역·도로·빈
  zone 혼입 시 blended=자연녹지 100 유지 + 139.6% 재현 케이스가 100으로 복원.
- **P0-2 (RC2·RC3·RC4 최소봉합)**: build_integrated_context에 정답 자산 결합 —
  ① geometry 보유 시 `_parcel_adjacency` 판정 → integrated에 contiguous/components 신호,
  ② `compute_usable_area` 결합 → usable_confirmed_sqm/excluded 명세를 integrated에 포함,
  land_area 소비는 usable 기준(gross 병기), ③ comprehensive `_calc_supply_areas`는
  비연접(contiguous=False) 또는 gate=BLOCK 시 산정 억제 + "연접·산입가능 필지 기준 재선택 안내"
  정직 게이트. 전 표면(comprehensive/rough/feasibility_v2/pipeline)이 단일 통로로 전파.
- **P0-3 (RC6)**: comprehensive analyze 말미에 check_against_legal 경량 배선 — 법정초과 검출 시
  값 강등(법정상한 클램프 금지·정직 경고 표면화, 무날조).
- **P0-4 (RC8)**: _check_daylighting zone family 분기 — 주거=사선 검토, 상업/공업=면제,
  녹지·관리·농림·보전="§61 사선제한 비적용(전용·일반주거 한정)" 정확 서술.
- **P0-5 (RC7)**: 통합 override 시 법정/조례 비교 서술 annotation 재생성(부분갱신 결함 해소).
- **P0-6 (RC5)**: buildable_options 허용용도를 별표 SSOT(development_type_analyzer /
  ZONE_PERMIT_MATRIX)로 수렴 — 녹지·관리 랭킹 정상화, 3소스 모순 제거.

### P1 (후속 백로그 — 보드 기록)
- 연접 클러스터별 개발단위 분해 제안(components>1 → 클러스터별 개발안) — GAP-3
- build_multi_parcel_report(S5) 소비처 배선(RC9) — 종합분석/보고서에 노출
- 프론트 effectiveLandAreaSqm usable 반영 + 파편화 경고 배지 UI
- DAG feasibility 노드 ssotInputs feasibilityData 미선언(dead-path) 조사 — PR#224 후속과 병합
- (QA 1차 추가) usable 면적 채택을 rough/feasibility_v2/pipeline에도 전파(현재 comprehensive만 —
  스코프 명시로 정리, 수지·개략수지와 종합분석 간 면적 기준 불일치 해소는 P1)
- (QA 1차 추가) 연접 세트에 GB 필지 혼입 시 supply 게이트 표면화(현재 면적 제외만)

## QA 성장루프 이력
- 1차 REQUEST CHANGES: [HIGH] 빈 zone 단일필지 — P0-1 None 전파가 _calc_supply_areas
  min(None,·)에 도달해 500 크래시(실증 재현. 종전엔 '오답이지만 완주' → 정직 게이트로 라우팅 필요)
  · [MED] blocked_reason 프론트 조용한 미표시(undefined평/₩NaN 행) · [MED] 토지 취득원가가
  usable 기준으로 축소(제외 필지도 매입 대상 — gross 복원, 면적 기준 이원화 명시) ·
  [MED] usable 전파 스코프 과대 주장 · [LOW] 신규 블록 블라스트 격리 등.
  → F1~F5 후속 반영 중. P0-1 게이트 위치·게이트 시맨틱(미확인≠불가)·P0-3 순수성·P0-6 별표
  수렴·139.6→100.0 복원 테스트는 정확성 확인됨(37/37 표적 통과).

### 성장루프 게이트
구현 → 회귀 테스트(139.6% 케이스 100% 복원·비연접 게이트·usable 제외) → pytest/eslint/tsc/build →
QA 코드리뷰(REQUEST CHANGES 루프) → 전파 스윕(다른 build_integrated_context 소비처 회귀 확인) → PR.

## 검증 기준(완결 판정)
1. 고기동 9필지 재현 케이스: 실효 용적률 ≤100%(자연녹지)·근거 텍스트 일치·시뮬 인센티브 정상 작동
2. 비연접 필지 세트: 통합 개발안 억제 + 정직 안내(연접 클러스터/제외 명세)
3. 도로·GB 필지: 대지면적 산입 제외 명세 표기
4. 자연녹지 건축가능랭킹: 현행 단독·전원 등 별표 기준 표시(0건 모순 해소)
5. 일조권 서술: 용도지역 사실 정합
