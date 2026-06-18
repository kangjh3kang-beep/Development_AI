# 얕은 분석경로 안티패턴 — 전역 스윕 결과 + 수정 트래커

작성 2026-06-19. 근거: Workflow `shallow-zone-analysis-sweep`(4에이전트). 패턴 = 결함A(용적률을 국가 법정상한으로 표시·실효 조례 미반영) + 결함B(detect_special_parcel 미실행 — 임야/산지/농지/GB/맹지/학교용지 게이트 누락). 정답 기준선 = `/zoning/analyze`(analyze_zoning) + `_enrich_effective_and_special`(parcels-info·land-report, 이미 수정됨).

표준 해법: `calc_effective_far`(조례 OrdinanceService 시군구 캐시) + `detect_special_parcel` 게이트. 다필지는 `_enrich_effective_and_special`/`detect_multi_parcel`(orchestrator.py:66-70) 재사용.

## 진짜 오점 16곳 (우선순위 = fix_order)

| # | 위치 | 결함 | 표시/분석 | 심각도 | 상태 |
|---|------|------|-----------|--------|------|
| 1 | routers/permits.py:61-117 (/permits/compliance-check) | AB | 표시 | HIGH | ⬜ Wave1 |
| 2 | development/scenario_simulator.py:196-512 (/development-methods/scenarios) | AB | 표시 | HIGH | ⬜ Wave1 |
| 3 | feasibility_service_v2.py:124-249 (auto_recommend_top3) | AB | 분석(ROI오염) | HIGH | ⬜ Wave2 |
| 4 | zoning/development_type_analyzer.py:275-320 ← project_pipeline.py:668 | AB | 표시 | HIGH | ⬜ Wave2 |
| 5 | web AutoZoningBadge.tsx:162-163 (칩 법정 무라벨) | AB | 표시 | HIGH | ⬜ Wave3 |
| 6 | web SiteInitiator.tsx:137 ("용적 X% 개발가능" 단정) | AB | 표시 | HIGH | ⬜ Wave3 |
| 7 | web LandIntelligencePanel.tsx:506,563-813 | AB | 표시 | HIGH | ⬜ Wave3 |
| 8 | precheck_service.py:496-625 + PreCheckWorkspace.tsx (B만, 실효는 정상) | B | 표시 | MED | ⬜ Wave2 |
| 9 | permit/permit_analysis_service.py:113-184 (_enrich_site, LLM 그라운딩) | B | 표시 | MED | ⬜ Wave2 |
| 10 | v2_feasibility.py:547-564 (GFA 역산 게이트) | B | 분석 | MED | ⬜ Wave2 |
| 11 | web DesignStudio.tsx:347-537 (kr-building-regulations 하드코딩) | A | 표시 | MED | ⬜ Wave3 |
| 12 | web site-analysis/page.tsx:743-762 (ordinance effectiveFar에 법정 시드) | A | 분석 | MED | ⬜ Wave3 |
| 13 | zoning/auto_zoning_service.py:99-159 (★결함A 공통근원·실효 미충전) | B/근원 | 분석 | MED | ⬜ Wave2(근원) |
| 14 | regulation_analysis_service.py:62-147 (special 노드 부착) | B | 표시 | LOW | ⬜ Wave4 |
| 15 | web ProjectAnalysisSummary.tsx:174 (실효를 '법정'으로 역오라벨) | A | 표시 | LOW | ⬜ Wave3 |
| 16 | web G2BBidAnalysisModal.tsx:350 (법정 무라벨 칩) | A | 표시 | LOW | ⬜ Wave4 |

오탐(제외): building_compliance.py `_LEGAL_LIMITS_PCT` — 설계 적합성 검증 컨텍스트(계획값 vs 법정한도 대조)라 법정 사용 정당+디스클레이머 부착. development_method_service `_calculate_bcr`=비용효익비(far 무관). 정답 다수: analyze_zoning·orchestrator·comprehensive·SiteAnalysisDetail·GlobalAddressSearch·RegulationHierarchyView·ModuleInputForm·AutoRecommendPanel 등(실효/trio 사용).

## 수정 웨이브(각 리뷰→배포)
- **Wave1(HIGH 할루시네이션·독립)**: #1 permits compliance-check(1300% 디폴트 제거), #2 scenario_simulator(실효+detect_multi_parcel 게이트).
- **Wave2(백엔드 근원+분석)**: #13 analyze_by_address 실효 옵션충전(근원), #3 auto_recommend_top3, #4 development_type_analyzer, #8 precheck, #9 permit_analysis, #10 v2_feasibility — 공용 게이트 재사용.
- **Wave3(프론트 표시 배치, 저위험·store 기존 effectiveFarPct/specialParcel 소비)**: #5,6,7,11,12,15.
- **Wave4(LOW)**: #14,16.
