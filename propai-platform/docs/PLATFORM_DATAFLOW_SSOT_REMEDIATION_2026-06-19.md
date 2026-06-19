# 플랫폼 사업성 분석 데이터흐름 SSOT 일관성 — 근본원인·해결계획 (2026-06-19)

오케스트레이터 6-에이전트 추적(SiteScore→부지→빌더블→세대믹스→M03 수지/ROI 데이터흐름). 근거 file:line.
증상: SiteScore 공시지가 1,816,000인데 M03 공시지가=0·분양가=0·세대수=0 → ROI −100%·NPV −749억; 세대믹스 323세대 vs
슬라이더 40세대; 빌더블 현실최고층 4층; 요약 '단일 데이터원'이 '분석 전'/'—'(빈).

## 근본원인 (정직 진단 — 표면은 요약/ROI이나 원인은 전부 상류 단선)

| # | 근본원인 | sev | 근거 |
|---|---|---|---|
| 1 | **이중 store** — M03이 SSOT 아닌 휘발성 `useFeasibilityV2Store`(persist·snapshot 밖) 사용 → 프로젝트 전환 시 DEFAULT_INPUT(전부 0) 리셋 | HIGH | use-feasibility-v2-store.ts:156·132-154; useProjectContextStore.ts:399-415 |
| 2 | **매출 파라미터 자동시드 부재** — total_households·avg_sale_price_per_pyeong 미시드 → revenue=0 → ROI −100% | HIGH | ModuleInputForm.tsx:98-101; revenue_engine.py:58·87 |
| 3 | **세대수 write/read 3중 단선** — 세대믹스 323이 designData.unitCount·M03 total_households에 안 박힘(고아 write totalRevenueWon만); 슬라이더 40은 dead input(백엔드 미전송·max300) | HIGH | UnitMixOptimizerPanel.tsx:205-212; GenerativeDesignPanel.tsx:381 |
| 4 | **진입경로 환류 비대칭** — 자동 파이프라인은 공시지가 SSOT 미기록(백엔드 전송만); site-analysis 경로는 pnu+가격 둘 다 요구. SiteScore는 estimatedValue 폴백으로 표시→store 괴리 | HIGH | ProjectPipelinePanel.tsx:785·852; site-analysis/page.tsx:769; SiteScoreCard.tsx:30 |
| 5 | **용도지역 한도 2갈래 분기** — 빌더블 ZONE_DEFAULTS(제2종 FAR250) vs CAD ZONE_LIMITS('2R' FAR200). 현실최고층 round 내림(4.167→4, ceil이어야 5) | MED | building_code_rules.py:49; auto_design_engine.py:37; solar_envelope_service.py:184 |
| 6 | **빌더블 카드 읽기전용** — effective_gfa를 표시만, designData 미write → 한도 SSOT 미편입. M03 연면적 29,937.5는 land×far 역산 우연 일치 | MED | BuildableEnvelopeCard.tsx:40-81; ModuleInputForm.tsx:80-86 |

## SSOT 목표 아키텍처
`useProjectContextStore`를 프로젝트 단위 **단일 진실원**으로, M03 전용 store를 **SSOT 파생 어댑터**로 강등.
- **siteAnalysis**(원데이터): land/zone/pnu/officialPrices 항상 채움. estimatedValue 폴백은 별도 필드로 분리(표시값=시드값 보장).
- **designData**(설계 파생): GFA/floor/bcr/far + unitCount/unitTypes + buildableGfaSqm(빌더블 검증 한도). land×far 역산은 후순위.
- **feasibilityData**(수지 결과 미러) + **feasibilityInputs**(세대수·분양가·면적·공시지가) persist/snapshot 포함 → 전환 복원.
- **regLimits**: 용도지역 FAR/BCR/일조 단일 테이블(엔진 reg/zone-limits 차용, 2R↔제2종 매핑) — FAR200/250 불일치 제거.
- **read/write 규약**: 각 stage는 SSOT read + 자기 산출만 write. M03 result는 store 내부에서 commit(화면 마운트 의존 제거) + revenue>0 게이트(쓰레기값 전파 차단).

## 필드 교차검증 (각 9.5 게이트 단위)
1. **동일 사실 다출처 일치**: 공시지가·세대수·연면적을 SSOT selector 1곳에서 산출→전 소비처 동일값. ±임계 초과 시 `fieldConflicts` stamp + '출처 불일치' 배지(엔진 cross_validate FD 차용 #10).
2. **단위 변환 검증**: 원/㎡↔원/평(×3.3058)·㎡↔평·세대↔면적 단일 유틸 + 역산 vs 직접 상대오차>5% 경고.
3. **필수 prefill 누락 표면화**: M03 calculate 전 required(공시지가·세대수·분양가) 0/null이면 'baselineNeedsInput' 게이트(revenue=0 −100% 통과 차단; P3 거부게이트 차용 #9).
4. **한도 정합 대조**: solar_envelope vs auto_design FAR/BCR/층수를 reg/zone-limits SSOT와 대조(P5 reg-source 차용 #8).
5. **provenance**: source:'user' 필드는 자동시드가 덮지 않음 + '사용자 수정값 사용 중' 표기.

## 우선순위 구현계획 (성장루프·9.5 게이트 단위)
| 순위 | 항목 | effort | conf |
|---|---|---|---|
| Q1 | 현실최고층 round→ceil(solar_envelope:184) | S | HIGH |
| Q2 | 세대믹스→designData.unitCount + setInput(total_households) write | S | HIGH |
| Q3 | M03 자동시드에 total_households(=unitCount)·avg_sale_price·avg_area 추가 | S | HIGH |
| Q4 | 공시지가 환류 통일(자동 파이프라인 + pnu 의존 제거 + 폴백 분리) | M | HIGH |
| R1 | M03 result commit을 store 내부로 + revenue>0 게이트 | M | MED |
| R2 | M03 입력 persist/snapshot 편입(전환 복원) — 이중 store 해소 | L | MED |
| R3 | 용도지역 한도 SSOT 통합(FAR200/250) + 빌더블 한도 SSOT 편입 | M | MED |
| R4 | 필드 교차검증 5종 구현(다출처 일치·단위·prefill 게이트·한도 정합·provenance) | M~L | MED |

권고: Q1~Q4(quick wins) 선행 → 가시 버그(현실최고층·세대수·ROI−100%·공시지가) 즉시 해소 → R1~R4로 구조적 SSOT 단일화·교차검증 완성.

---
*근거 전문: 워크플로 wevdqbk6j(5트랙 추적+종합). 후속 구현 기준선. 각 항목 성장루프·9.5 적대게이트로 검증 후 커밋.*
