# 112 · 법규검토 규제 체크리스트(rule-check) 프론트 연결

## 대상
- `propai-platform/apps/web/components/projects/ProjectLegalWorkspaceClient.tsx` (프론트만, 단일 파일)
- 신규 의존성 0. push/배포 없음.

## 배경
가짜 체크리스트를 제거했던 자리에 실데이터 백엔드 `POST /api/v1/building-compliance/rule-check`(인증불필요, 규칙기반 `BuildingCodeRuleEngine.check_all` 직렬화)를 연결.

## 호출·요청필드 정합 (RuleCheckRequest Read 확인)
백엔드 `routers/building_compliance.py:394` `RuleCheckRequest` — 전부 optional/0 graceful. 프론트가 컨텍스트에 있는 값만 전달:
- `zone_code` ← `siteAnalysis.zoneCode` (autoZoneCode)
- `land_area_sqm` ← `siteAnalysis.landAreaSqm ?? 0`
- `max_bcr` ← `siteAnalysis.ordinance.effectiveBcr ?? designData.bcr ?? null` (미입력 시 백엔드가 zone_code로 보완)
- `max_far` ← `siteAnalysis.ordinance.effectiveFar ?? designData.far ?? null`
- `building_type` ← `designData.buildingType ?? undefined`
- `total_gfa_sqm` ← `designData.totalGfaSqm ?? 0`
- `floor_count_above` ← `designData.floorCount ?? 0`
- `building_height_m` ← `floorCount × 3.3` (없으면 0)
- 나머지(building_area_sqm·unit_count·parking_count·setback_m·north_boundary_m·floor_count_below 등): 컨텍스트에 미존재 → 미전송, 백엔드 graceful(0/None) → 해당 룰은 검토필요/해당없음으로 정직 반환. **가짜 status 생성 안 함.**

응답 타입 `RuleCheckResponse`(백엔드 `:428`와 정합): `results[]{rule_id,rule_name,legal_basis,status,required_value,actual_value,message}` + `overall_status` + `pass/fail/warning/na_count` + `summary`.

## 자동 로드·무한루프 가드
- 진입 시 `autoZoneCode`(부지분석 용도지역 확정) 있으면 1회 자동 호출.
- `ruleLoadedKeyRef`로 `(주소::용도지역)` 조합당 1회만. `ruleResult || ruleLoading`이면 skip.
- 실패 시 키 해제(다음 변경에서 재시도 가능). timeoutMs 60000.
- 기존 종합분석(/regulation/analyze)·legal-check 자동로드·store 환류는 전부 보존(별도 ref·state).

## 8항목 렌더 (배치)
배치 순서: ②종합 규제 분석(/regulation/analyze) → **③규제 체크리스트(rule-check, 신규)** → ④계획값 대조 정량 적합성(legal-check 보조).
각 항목 카드:
- 항목명 `rule_name` + 상태배지(status별: 적합=accent / 부적합=error / 검토필요=spot / 해당없음=tertiary, `ruleStatusMeta` 헬퍼, 백엔드 status 그대로 매핑)
- `관련 조항: legal_basis`
- 이유 `message`
- `기준: required_value` / `현재(계획): actual_value` (있을 때만)
- 카드 헤더 우측에 summary 카운트(적합/부적합/검토필요/해당없음).
무자료/실패: graceful 정직 표기(빈 상태 안내 / 에러 박스).

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff: 351 insert / 2 delete, **import 제거 0건**(NO IMPORT REMOVALS 확인), 신규 의존성 0.

## 미진사항
- building_area_sqm·unit_count·parking_count·setback_m·north_boundary_m는 현재 컨텍스트 스토어(DesignData/SiteAnalysisData)에 필드 없음 → 미전송. 해당 룰(주차·일조 일부·건축선후퇴)은 검토필요/해당없음으로 표기. 추후 설계 스튜디오/주차계획 컨텍스트 확장 시 전달값 보강 가능.
- 수동 재실행 버튼 미추가(자동 1회 + 컨텍스트 변경 시 재호출로 충분). 필요 시 후속.
