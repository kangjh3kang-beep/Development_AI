# 법령엔진 고도화 상세구현계획 — 특이토지(경사도·임목축적) 심층 법규검토 (2026-07-02)

전수조사(7-에이전트) 확정 갭의 해소 계획. 원칙(비협상): **무날조**(모든 수치·조문은 출처 확신 시에만 등록, 불확신은 법령 루트 폴백/None+정직 고지), **설명가능성**(모든 신규 산출에 근거+법령+한계 동반), **정직 게이트 보존**(NEEDS_OFFICIAL_SURVEY 확정차단은 절대 완화 금지 — '예비판정' 추가만 허용).

## T1. 경사도 고아 데이터 배선 (P1 — 최고 가성비)
**문제**: `terrain_service.py:143-160`이 SRTM 30m DEM으로 `mean_pct/max_pct` 실산출하는데 `special_parcel.py:207-216` `forest_facts.평균경사도_pct=None`(미배선), 호출부(precheck·feasibility_v2·permit_analysis)가 slope 미전달.
**구현**:
1. `detect_special_parcel(...)`에 **additive 옵션 인자** `terrain_facts: dict | None = None` 추가(계약: `{"평균경사도_pct": float, "최대경사도_pct": float, "source": "SRTM30_DEM"}`). 기존 호출부 무수정 호환(기본 None=현행 동작 100% 보존).
2. `terrain_facts` 제공 시 forest_facts에 값 주입 + `source`/`정확도한계`("30m DEM 근사 — 공식 평균경사도조사서 아님") 명기.
3. **예비판정(preliminary_assessment) 추가** — developability는 `NEEDS_OFFICIAL_SURVEY` **불변**(공식조사 없인 확정 불가), 별도 필드로:
   - 기준: 조례값(T2) 있으면 조례 기준, 없으면 산지관리법 시행령 별표4의 국가기준 **25°**(도 단위 — %↔도 변환 명시: tan(25°)≈46.6%) + "지자체 조례 별도 확인" 캐비앳.
   - DEM ≤ 기준×0.8 → `"예비 적합 가능성"`, 기준×0.8~1.0 → `"경계 — 공식조사 필수"`, > 기준 → `"예비 초과 — 부적합 가능성 높음(대체부지 검토 권고)"`. 각 판정에 산식·법령 근거·한계 동반.
4. 호출부 배선(최소 1곳 실배선 + 나머지는 인터페이스만): comprehensive/precheck 경로에서 terrain 분석 결과가 있으면 전달.
**TDD**: DEM 18°/25° 기준→예비적합, 35°→예비초과, terrain 미제공→현행 완전 동일(회귀), developability 절대 불변 단언.

## T2. 조례 경사도 기준 파서 (P1)
**문제**: `ordinance_service`는 건폐/용적률만 파싱 — 개발행위허가 경사도 기준(시군구별 17.5°/20°/25° 상이)은 미수집.
**구현**: ordinance_service에 `resolve_slope_criteria(sigungu)` 추가 — 기존 법제처 자치법규 API 텍스트에서 정규식(`경사도\s*(\d+(?:\.\d+)?)\s*도` + '개발행위' 문맥) 추출. **정적 시드값 금지**(무날조 — 값 검증 불가). 성공: `{"slope_deg": x, "ordinance_name": ..., "verified": "api_parsed"}`, 실패: `None`(캐비앳 "해당 지자체 조례 직접 확인 필요"). T1의 예비판정이 이 값을 우선 사용.
**TDD**: 파싱 성공/실패/문맥 오탐(경사도 언급이 개발행위 무관 조항) 케이스 — 목업 조례 텍스트로.

## T3. 임목축적 커넥터 + 별표4 150% 비교 (P1)
**문제**: 산림청 데이터 커넥터 부재(`입목축적_per_ha=None`), 별표4 "관할 시군구 평균 임목축적 150% 이하" 비교 불가.
**구현**:
1. `integrations/forest_service_client.py` 신규 — pluggable: env `FOREST_API_KEY`/`FOREST_API_BASE` 미설정 시 항상 `None`(정직 미확보, **현행 게이트 완전 보존**). 설정 시 조회 시도(엔드포인트는 설정 주입 — 특정 공공 API 스펙을 하드코딩 확신할 수 없으므로 어댑터 계약만: `get_forest_facts(pnu) -> {"입목축적_per_ha", "관할평균_입목축적_per_ha", "산지구분"} | None`).
2. special_parcel에 150% 비교 로직: 두 값 모두 확보 시에만 `입목축적_비율_pct` 산출 + 예비판정(별표4 근거 명기: "산지관리법 시행령 제20조 별표4"). 하나라도 None이면 비교 skip + 사유.
**TDD**: 목업 주입(120%→예비적합, 160%→예비초과), 미설정→None·게이트 불변.

## T4. 조문 등록 + 부담금 산식 브리지 (P1)
**레지스트리 추가**(★조문 번호는 구현 에이전트가 반드시 재확인 — 불확신 시 조문 없이 법령 루트 등록이 규칙):
- `farmland_preservation_charge` — 농지법 **제38조**(농지보전부담금) [확실]
- `farmland_conversion_report` — 농지법 **제35조**(농지전용신고) [확실]
- `forest_land_classification` — 산지관리법 **제4조**(산지의 구분: 보전/준보전) [확실]
- `forest_replacement_charge` — 산지관리법 **제19조**(대체산림자원조성비) [확실 — ★전수조사 검증관의 '제47조' 주장은 오류로 판정, 제19조가 정본]
- `forest_permit_criteria` — 산지관리법 시행령 **제20조**(산지전용허가기준·별표4) [확실]
- `dev_permit_criteria` — 국토의 계획 및 이용에 관한 법률 시행령 **제56조**(개발행위허가의 기준·별표1의2) [확실]
**부담금 브리지** `app/services/feasibility/land_conversion_charges.py` 신규(순수 계산):
- 농지보전부담금 = 개별공시지가 × **30%**(㎡당 상한 **50,000원**) × 전용면적 [농지법 시행령 산정기준 — 확실] + `confidence: "estimated"`, 감면 미반영 정직 고지.
- 대체산림자원조성비 = (고시 단가 + 공시지가×1%) × 면적. **연도별 고시 단가는 하드코딩 금지** — 설정 주입(`ForestChargeRates(year, 준보전, 보전, 전용제한)` 명시적 입력) 없으면 산식 설명+None 반환(무날조).
- special_parcel 농지/임야 게이트의 `honest_disclosure`에 부담금 존재 고지 + legal_ref 연결.
**TDD**: 산식 정산(공시지가 10만원/㎡·1000㎡ → 3,000만원; 상한 발동 케이스 20만원/㎡→5만원 캡), 단가 미주입→None+산식설명.

## T5. P2 레지스트리 확충
법령명 확실 항목만(조문 불확신 시 루트 등록): 자연환경보전법(생태·자연도 — 제34조 [확실]), 매장문화재 보호 및 조사에 관한 법률(루트 — 지표조사 조문은 재확인 후), 급경사지 재해예방에 관한 법률(루트), BEEC 고시 `build_admrule_url("건축물 에너지효율등급 및 제로에너지건축물 인증 기준")`(행정규칙 카테고리 — 기존 빌더 활용), 장애인등편의법 시행령(별표 — 루트).

## 검증 게이트 (100% 완성 정의)
1. 신규 법령 인용 **전수 목록화 → 법리 검증관 실법령 대조**(오인용 0 — 불확신 항목은 루트 폴백 강등으로 해소).
2. **정직 게이트 보존 실증**: NEEDS_OFFICIAL_SURVEY developability가 어떤 입력에서도 완화되지 않음(테스트 단언).
3. 신규 테스트 전부 GREEN + **전체 backend 스위트 무회귀** + ruff 0(신규 파일).
4. 성장루프 3렌즈(법리정합·무날조/정직성·회귀) ≥9.5.
5. 통과 시 커밋·푸시(feature 브랜치+PR).

## 파일 소유권(병렬 충돌 방지)
- W1(1차 병렬): A-registry(`legal_reference_registry.py` 단독 소유, T4·T5 등록) / B-connector(`integrations/forest_service_client.py`+테스트 신규) / C-charges(`land_conversion_charges.py`+테스트 신규) / D-ordinance(`ordinance_service.py` slope 파서+테스트)
- W2(2차, W1 산출 소비): E-gate(`special_parcel.py` 단독 소유 — T1 배선+T3 비교+예비판정+T4 고지, 관련 테스트) / F-callers(호출부 1곳 실배선+계약 테스트)
