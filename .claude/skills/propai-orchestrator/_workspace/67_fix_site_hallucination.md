# 67. 부지분석 AI 해석 할루시네이션 차단 — 법정 건폐율/용적률 그라운딩 + 하드 검증기

## 사고 요약(라이브)
경기 용인 수지 신봉동 56-19(**자연녹지지역**, 1,520㎡) 부지분석에서 AI 해석이
"실효 건폐율 60% · 용적률 200%"로 산출. 법정 상한은 건폐율 20% · 용적률 100%
(국토계획법 시행령 제84·85조). 페이지 헤더(기본정보)는 20%/100%로 올바르게 표시되었으나
AI 해석만 법정의 2배를 지어냄. 상단 "검증 통과·근거 100%" 배지가 위법수치를 통과시킴.

## 1. 근본원인(2중 결함)

### 원인 A — 하드코딩 폴백이 자연녹지에 60/200을 주입(할루시네이션 발원지)
`app/services/land_intelligence/comprehensive_analysis_service.py` `_calc_effective_far()`:
```python
national_bcr = float(zone_limits.get("max_bcr_pct", zone_limits.get("bcr", 60)))   # ← 폴백 60
national_far = float(zone_limits.get("max_far_pct", zone_limits.get("far", 200)))  # ← 폴백 200
```
`zone_limits`가 None/누락이면 **용도지역과 무관하게 60/200**을 사용. 자연녹지처럼
`zone_type`은 잡혔지만(키워드/토지특성 경로) `zone_limits`가 전파 안 된 필지에서
일반주거(60/200)를 지어냄. effective = min(national, ordinance) 구조상 national이 200이면
effective도 200 → 그대로 LLM 프롬프트(`effective_far`)에 주입 → 해석이 200% 단정.
LLM이 "데이터 출처 미명시"라고 자인한 것은 실제로 페이로드에 출처 없는 폴백값이었기 때문.

### 원인 B — 검증기가 '용도지역별 법정 상한'을 대조하지 않음(미적발 이유)
`app/services/verification/range_rules.py`는 BCR>100 / FAR>2000 같은 **일반 범위**만 검사.
자연녹지 200%는 2000% 미만이라 통과 → high 이슈 0 → verdict=pass → "통과·근거 100%" 배지.
`verifier_service.verify()`는 range_issues를 pre에 합산하고 high가 있으면 fail로 보정하므로,
range 규칙이 법정초과를 high로 잡아주기만 하면 배지가 자동 정직화됨.

## 2. 법정 한도표 위치/신설
- **데이터 원본(기존)**: `app/services/zoning/auto_zoning_service.py` `ZONE_LIMITS`
  (자연녹지 20/100, 1종전용 40/100, 1종일반 60/200, 2종일반 60/250, 3종일반 50/300,
   준주거 70/500, 일반상업 80/1300 등 — 이미 정확).
- **신설 SSOT 래퍼**: `app/services/zoning/legal_zone_limits.py`
  - `normalize_zone_name()` 공백/표기변형 → 표준키(긴 키 우선 부분매칭).
  - `legal_limits_for(zone_type)` → `{zone_type, max_bcr_pct, max_far_pct, max_height_m, legal_basis}`.
  - `check_against_legal(zone_type, bcr_pct, far_pct, tolerance=0.5)` → 법정초과 시 high 이슈.
  - `LEGAL_BASIS = "국토계획법 시행령 제84·85조"` 출처 주석.
  - ※ 데이터 중복 없이 ZONE_LIMITS를 단일 출처로 재노출(검증기·그라운딩 공용).

## 3. 그라운딩 주입방식
`app/services/ai/site_analysis_interpreter.py`:
- `USER_PROMPT_TEMPLATE`에 `## 법정 한도(...)` 블록 + `## 그라운딩 규칙(위반 금지)` 4항 추가.
- `_legal_limits_block(zone_type)` 헬퍼가 탐지된 용도지역의 법정 BCR/FAR 상한을 프롬프트에 명시 주입.
- 규칙: ①법정 상한 초과 임의생성 금지 ②"실효/완화" 수치는 페이로드에 출처
  (지구단위계획·조례·특별구역)가 있을 때만 + 출처 표기 ③출처 없으면 법정값+"완화는 별도 확인" ④페이로드 외 수치 단정 금지.
- 미매칭 용도지역은 "임의 단정 금지, 페이로드 명시값만 인용" 지시.

## 4. 하드 검증기 규칙 + 배지 정직화
`app/services/verification/range_rules.py`:
- `_deep_find_str()` / `_find_str()` 추가(중첩 페이로드에서 zone_type 문자열 깊이탐색).
- 공통 BCR/FAR 범위 검사 직후 **법정 대조 블록** 추가: zone_type 발견 시
  effective/applied/max BCR·FAR을 `check_against_legal`로 대조 → 초과는 **high(=fail)**.
- 배지 정직화: `verifier_service.verify()`가 range_issues를 pre에 합산하고 high면 verdict=fail
  강제(기존 로직). 따라서 위법수치 존재 시 "통과·근거 100%" 불가, fail로 표면화.

## 5. 단위테스트 결과 (`tests/test_legal_zone_limits.py`, 14 passed)
- 자연녹지 용적률200% → high(fail) 적발 ✔ (라이브 사고 재현)
- 자연녹지 건폐율60% → high 적발 ✔
- 자연녹지 100%/20% → pass ✔
- 1종일반 용적률200% → pass(법정 内) ✔
- 1종일반 용적률250% → high ✔
- 미매칭 용도지역 9999% → 무플래그(일반규칙 위임) ✔
- 반올림 오차 100.3% → 통과 ✔
- `run_range_checks("site", {zone_type:자연녹지, far:200, bcr:60})` → high 2건 ✔
- 중첩 페이로드 zone_type 탐색 → high ✔
- 그라운딩 블록 주입 확인(자연녹지 20%/100% 텍스트 포함) ✔
- 근본원인 결정론 재현: `_calc_effective_far(zone_limits=None, '자연녹지')` → national/effective 20/100 (과거 60/200 아님) ✔
- 앱 부팅 OK(735 routes), py_compile OK.

## 6. 자동교정/경고 표기방식(투명·은폐 금지)
- **결정론 교정**: zone_limits 누락 시 폴백을 `legal_limits_for(zone_type)`로 도출 →
  자연녹지는 자동으로 20/100. effective=min(national,ordinance)이라 법정초과 원천 차단.
- **검증 경고**: 만약 LLM/다운스트림이 여전히 법정초과 수치를 내면, 검증기가
  `법정한도초과` high 이슈 + note에 "법정 상한 X% · 출처 미확인 시 할루시네이션 의심 · 법정값 권고"를 삽입.
  배지는 fail로 표면화(거짓 신뢰 차단).
- 기존 annotations(comprehensive_analysis)는 이미 "법정상한 vs 조례 중 낮은 값" 투명서술 유지.

## 7. 커밋
- 메시지: `fix(site-analysis): 부지분석 할루시네이션 차단 — 법정 건폐율/용적률 그라운딩+하드 검증기(자연녹지 용적률200%→법정100% 적발)`
- (해시는 커밋 후 본 문서 하단에 기록)

## 8. 라이브 재검증 방법(배포 후)
1. **부지분석 재실행**: 수지 신봉동 56-19(자연녹지) 분석 → AI 해석 `effective_far_interpretation`이
   용적률 100%·건폐율 20%로 서술되어야 함(200%/60% 금지). "완화는 출처 확인 필요" 문구 동반.
2. **검증 엔드포인트** `POST /api/v1/verify/analysis`:
   ```json
   {"analysis_type":"site",
    "source":{"zone_type":"자연녹지지역","land_area_sqm":1520},
    "output":{"effective_far_pct":200,"effective_bcr_pct":60}}
   ```
   기대: `verdict="fail"`, issues에 `법정한도초과` high(용적률200%·건폐율60%).
   정상값(100/20) 입력 시 해당 high 없음.
3. 1종일반 200% 입력 → 통과(법정 内), 250% → fail.

## 9. 일반화 여지(다른 수치 할루시네이션)
- `check_against_legal`는 BCR/FAR 전용이나, `range_rules.py`에 이미 취득세율 상한·평당공사비·
  ROI·시세/공시지가 배수 규칙 존재 → 동일 패턴으로 확장 가능.
- 향후: 페이로드 사실(면적·공시지가)과 해석 본문 수치의 일반 정합 대조(deep diff)로 확장 시
  텍스트 파싱(정규식)으로 LLM 출력 내 수치 추출 → 페이로드 대조 규칙 추가 권장.
- SSOT(legal_zone_limits)를 building_compliance/permit_validator 등 타 모듈도 재사용하면
  용도지역 한도 단일출처화 가능.

## 변경 파일
- `app/services/zoning/legal_zone_limits.py` (신설, SSOT 래퍼)
- `app/services/land_intelligence/comprehensive_analysis_service.py` (폴백 60/200 → 법정도출)
- `app/services/ai/site_analysis_interpreter.py` (그라운딩 블록 + _legal_limits_block)
- `app/services/verification/range_rules.py` (법정대조 하드규칙 + 문자열 깊이탐색)
- `tests/test_legal_zone_limits.py` (신설, 14 테스트)
