# 다필지 통합분석엔진 상세구현계획 — 완전 토지속성·실사용가능용지·반복검증·시니어 최종화 (2026-07-03)

정찰(4-에이전트) 확정: 배치 파이프라인(BatchInput 5모드·멱등 INV-M2~M5·완결성 신호)과
`_aggregate_integrated_zoning`(special_parcel.py:1207-1389, 면적가중 blended_far·혼재감지)·
`detect_multi_parcel`(:1392-1457, 차단필지·per_parcel 종합판정)이 **이미 존재**. 본 계획은 이를
확장해 정찰이 확정한 갭만 구현한다. 원칙: 무날조·정직게이트 불변·additive·TDD.

★선행 의존: 법령엔진 무결점 루프(wf_9ede28a9)가 special_parcel.py 를 편집 중 — **루프 착지 후 착수**.

## S3-A. 국계법 제84조 걸침(혼재) 규정 로직 (P0 — 법규 핵심)
**갭**: 현행은 면적가중만. 제84조의 실제 규정 미구현.
**구현**(`special_parcel.py` 확장 or 신규 `zoning/multi_zone_rule.py` — 루프 착지 후 소유권 결정):
- 제84조 규정(구현 전 조문 재확인 필수 — 무날조): 걸침 부분이 **330㎡ 이하**(도로변 띠모양 대지는 660㎡)인 경우 → 건폐율·용적률은 **가중평균**, 그 밖의 규정은 **넓은 부분(과반)** 적용. 초과 시 → **각 부분별 각각 적용**(사실상 분리 검토).
- 출력: `zone_straddle_ruling` = {applied_rule: "가중평균+과반" | "부분별각각", threshold_sqm, 근거 legal_ref(국계법 §84 — 레지스트리 키 확인/추가), per_zone_breakdown, honest_note}. 기존 `blended_far_eff_pct`는 보존(라벨만 '제84조 가중평균 적용분'으로 정확화).
**TDD**: 330 이하 혼재/초과 혼재/단일 용도지역(무적용)/도로변 띠 케이스.

## S3-B. 실사용가능용지(usable_area) 산정 (P0 — 사용자 핵심)
**갭**: usable_area 개념 부재. 도로·구거 차감, BLOCKED 제외, 조건부 구분 없음.
**구현**(신규 `app/services/zoning/usable_area.py` — 순수함수):
- 입력: per_parcel(면적·지목·developability·gate). 출력 3계층:
  `gross_sqm`(전체합) / `usable_confirmed_sqm`(POSSIBLE·CAUTION 필지) / `usable_conditional_sqm`(PRECONDITION·CONDITIONAL·NEEDS_OFFICIAL_SURVEY — 조건 목록 동반) / `excluded_sqm`(BLOCKED + 도로·구거·하천 지목, 사유별 명세).
- 지목 차감율 같은 **임의 계수 금지**(무날조) — 도로·구거는 '건축 불가 지목'으로 전액 제외하되 "합필 시 포함 가능성은 관할 확인" honest 고지. 확정 불가능한 정밀 감보율은 미산정+사유.
- detect_multi_parcel 출력에 additive 합류.
**TDD**: 혼합 세트(정상2+도로1+임야1+농지1) → 3계층 정산, 전량 BLOCKED, 전량 정상.

## S3-C. 제외 시나리오 what-if 재산정 (P1)
**갭**: blocking_parcels 제외 권고만 있고 잔여 한도 재산정 없음.
**구현**: `simulate_exclusion(parcels, exclude_pnus)` — 제외 후 `_aggregate_integrated_zoning`+usable_area 재실행 → {잔여 gross/usable, blended_far, 상실 면적, 비교표}. detect_multi_parcel에 추천 시나리오(차단 전부 제외안) 1건 자동 동반.
**TDD**: 제외 전후 정산 일치·빈 제외·전량 제외.

## S4. 반복 검증 루프(면적 3원 정합 + 수렴) (P1)
**갭**: 공부 vs 좌표 vs 입력 교차검증 부재, 불일치 수렴 정책 없음. cross_validate는 면적 미사용.
**구현**(신규 `app/services/land_intelligence/parcel_verification.py`):
- 필지별 면적 신호 수집: 공부(parcels-info area) / VWorld 좌표면적(폴리곤 있으면 dims_from_polygon 재사용) / 사용자 입력(areaInputSqm). `cross_validate()`(trust.py) 재사용 — anchor=공부, 이상치·consensus·confidence 산출.
- 수렴 정책: 괴리>임계(예: 10%) 필지는 1회 재보강(refresh) 후 재검증, 여전히 괴리면 `area_verification: {status:"discrepancy", 신호별 값, 권고:"지적측량 확인"}` 정직 표기(자동 보정 금지 — 무날조).
- detect_multi_parcel 전 단계 훅으로 배선(배치 완료 시 자동).
**TDD**: 3신호 일치/1신호 이상치/재보강 후 수렴/불수렴 정직 표기. 네트워크는 목업.

## S5. 시니어 패널 최종화 (P1)
**갭**: senior_agents 평가가 다필지 종합에 미배선.
**구현**(신규 `app/services/senior_agents/evaluators/land_assembly.py` + 어댑터):
- 입력: S3~S4 산출(매트릭스·usable·straddle·검증상태). RuleEvaluation 계약(기존 evaluators 관례) 준수로 판정: 유효면적 대비 차단 비중, 혼재 리스크, 검증 미수렴 필지, 조건부 의존도 → verdict(pass/warn/block)+사유.
- 최종 보고 계약(BaseEvidenceResponse): `multi_parcel_report` = {matrix(필지×속성×판정), usable 3계층, straddle_ruling, charges 통합(필지별 charge_notice 합산 — estimated), verification, senior_review, honest_limitations}. ★모든 수치에 근거·법령·한계.
**TDD**: 시나리오 3종(정상 합필/차단 혼재/미수렴 포함) 보고 계약 검증.

## S6. UI 매트릭스 (P1, 프론트)
multi-parcel 페이지·BulkParcelBatchPanel에 additive: 필지×판정 매트릭스(게이트 배지)·usable 3계층 게이지·제외 what-if 토글·시니어 종합 카드(정직 라벨). tsc·vitest.

## 검증 게이트 (100%)
① 신규 조문(§84) 실법령 대조 ② 정직게이트·기존 계약(INV-M2~M5) 불변 ③ 신규+인접 전 테스트 GREEN·전체 스위트 무회귀·ruff/tsc 0 ④ 성장루프 3렌즈(법리·정직성·회귀) ≥9.5 → 커밋·푸시.

## 실행 웨이브(파일 소유권)
- W0(루프 착지 후): §84 조문 재확인+레지스트리 키(소유: registry — 필요시)
- W1 병렬: A-usable_area(신규 파일) / B-parcel_verification(신규 파일) / C-land_assembly evaluator(신규 파일)
- W2: D-special_parcel 확장(§84 걸침·usable 합류·what-if·검증 훅·보고 조립 — special_parcel.py 단독 소유) / E-UI(프론트)
- W3: 성장루프 3렌즈 + 중앙 전체 게이트
