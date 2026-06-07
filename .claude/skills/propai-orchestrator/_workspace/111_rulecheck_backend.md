# 111 — 법규 항목별 정량검토 라우트(rule-check) 백엔드

## 목표
이미 구현된 `BuildingCodeRuleEngine`(8개 룰·조문)를 라우터로 노출. 새 룰 로직 작성 없이 `check_all` 결과를 그대로 직렬화.

## check_all 시그니처·입력 (Read 확정)
`app/services/permit/building_code_rules.py:71-107`
```
BuildingCodeRuleEngine().check_all(design_params: dict, site_params: dict) -> list[RuleCheckResult]
```
- design_params: building_area_sqm, total_gfa_sqm, floor_count_above, floor_count_below,
  building_height_m(없으면 층수×3.3), unit_count, building_type, setback_m, parking_count,
  floor_area_per_floor_sqm
- site_params: land_area_sqm, max_bcr(%), max_far(%), max_height(m, 0=제한없음), zone_type(용도지역명), north_boundary_m
- `RuleCheckResult`(pydantic): rule_id, rule_name, legal_basis(조문), status(ComplianceStatus: pass/fail/warning/n/a), required_value(str), actual_value(str), message
- 8개 룰: BL-001 건폐율(시행령§84), BL-002 용적률(§85), BL-003 높이(법§60·61), BL-004 건축선후퇴(법§46·47), BL-005 주차(주차장법시행령§6), BL-006 일조(법§61), BL-007 피난방화(시행령§34·46), BL-008 장애인편의(장애인등편의법§4)

## 라우터 위치/마운트
- 파일: `propai-platform/apps/api/routers/building_compliance.py` (legal-check 동일 파일)
- 엔진 import 경로: `from app.services.permit.building_code_rules import ...`
- main 마운트: `apps/api/main.py:366` `prefix="/api/v1/building-compliance"` → 신규 `/rule-check` 자동 등록(추가 등록 불필요). 인증 의존성 없음(legal-check와 동일 정책).

## 신규 라우트 `POST /api/v1/building-compliance/rule-check`
요청(`RuleCheckRequest`, 전부 optional/0 graceful):
- site: zone_code, land_area_sqm, max_bcr, max_far, max_height_m, north_boundary_m
- design: building_type, building_area_sqm, total_gfa_sqm, floor_count_above, floor_count_below, building_height_m, unit_count, setback_m, parking_count, floor_area_per_floor_sqm

처리:
- zone_code를 ZONE_DEFAULTS 키와 부분일치 → zone_type(엔진 건축선후퇴/일조 분기용)
- max_bcr/max_far/max_height 미입력 시 `_LEGAL_LIMITS_PCT`(부분일치, 기존 모듈상수) 보완. 그래도 없으면 60/200/0 기본.
- `BuildingCodeRuleEngine().check_all` 호출 → 8개 RuleCheckResult를 그대로 직렬화.

응답(`RuleCheckResponse`):
- zone_code, zone_name(매칭), overall_status(fail>warning>pass), pass/fail/warning/na_count, results[8](RuleCheckItem: rule_id, rule_name, legal_basis, status, required_value, actual_value, message), summary

## 8항목 샘플 응답 (populated: 제2종일반주거, 대지1000㎡, 건축600/연면적2400㎡, 5층16.5m, 24세대, 주차20대)
- BL-001 건폐율 [pass] 시행령§84 | 60% 이하 / 60.0%
- BL-002 용적률 [pass] 시행령§85 | 250% 이하 / 240.0%
- BL-003 높이 [n/a] 법§60·61 | 제한없음 / 16.5m(5층)
- BL-004 건축선후퇴 [pass] 법§46·47 | 2.0m 이상 / 2.0m
- BL-005 주차 [fail] 주차장법시행령§6 | 최소24대(24세대×1.0) / 20대 → 4대 부족
- BL-006 일조 [warning] 법§61 | 북측 8.2m 이상 / 미입력
- BL-007 피난방화 [warning] 시행령§34·46 | 직통계단2개소 / 5층 480㎡
- BL-008 장애인편의 [warning] 장애인등편의법§4 | 경사로·주차구획 / 공동주택24세대
→ overall=fail, pass3/fail1/warn3/na1

## 검증
- `py_compile`: COMPILE_OK
- lsp_diagnostics: ZONE_DEFAULTS 미import 1건 → 함수내 import에 추가하여 0 errors
- 엔진 스모크(venv py3.12): populated 8개·empty 8개 정상(empty: pass2/na4/warn2)
- 라우트 핸들러 직접 호출(PYTHONPATH=repo root):
  - populated → overall=fail, 8 results
  - zone-only(설계값 0) → overall=warning, far_limit 300% 자동보완, 8 results
  - blank(zone 없음) → overall=warning, zone_name=None, 적합2/검토필요2/해당없음4
- git diff: +143줄, 삭제 0 (top-level import 보존, 린터 트랩 없음). 신규 의존성 0.

## 미진사항/주의
- 엔진 quirk: 설계값 0일 때 건폐율/용적률은 0%≤상한이라 "pass"로 나옴(가짜 pass 아님—엔진 기존 동작, 변경 금지 지시 준수). 프론트에서 actual_value="0.0%"로 입력없음 인지 가능.
- `python3.10`(시스템)엔 StrEnum 없음 → 반드시 `apps/api/.venv`(3.12)로 실행.
- 프론트 연동은 별도 executor 담당(미터치).
- push/배포/git add 미수행(지시 준수).
