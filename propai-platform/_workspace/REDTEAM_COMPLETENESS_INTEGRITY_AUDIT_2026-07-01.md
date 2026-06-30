# 사통팔땅 완성도·무결성 적대적 레드팀 감사

- 작성일: 2026-07-01
- 대상: 지도 기반 필지 입력, 부지분석 핸드오프, 법령엔진, 조례/지형/특이필지 보강, 설계 스튜디오 연동
- 기준: 목업 없는 구현, 진실원천 단일화, 실패 시 정직 표기, 법규/공공데이터 누락 방지, 사용자에게 “통과”로 오해되는 fail-open 금지

## 1. 결론

현재 상태는 **100% 완성·무결성 통과가 아니다.**

주요 경로는 많이 개선되었지만, 적대적 검증 기준에서는 다음 4개 축에서 100% 게이트를 통과하지 못한다.

1. **법령엔진 무결성**: SSOT 주경로는 존재하나, 구형 RAG 서비스·구형 compliance router·간이 rule engine이 서로 다른 정적 한도표와 fail-open 폴백을 유지한다.
2. **조례/특수조건 완전성**: 법제처/정적캐시/법정상한 경로는 있으나, 조례 원문 파싱이 정규식 중심이고 법정상한 폴백이 저장까지 된다. 임목본수도·공식 경사도·도시군관리계획·지구단위계획·산지/농지/문화재/군사/상수원 등은 아직 “검토 필요” 수준이지 실데이터 확정이 아니다.
3. **지도·필지 핸드오프 무결성**: 사통팔땅 지도 선택은 sessionStorage와 프로젝트 컨텍스트로 연결되지만, 면적 미보강 필지, 스토리지 차단, 빈 목록 제거, stale siteAnalysis, fullscreen 회귀가 충분히 테스트되지 않았다.
4. **검증 환경 무결성**: 백엔드 핵심 테스트가 현재 쉘에서 `fastapi` 미설치로 수집 중단된다. 검증 체계 자체가 재현 가능한 100% 게이트가 아니다.

레드팀 기준 현재 추정 완성도:

- 지도/필지 입력 UX 주경로: **72/100**
- 법령 SSOT 주경로: **64/100**
- 법규검토 제품 표면 전체 무결성: **58/100**
- 설계 스튜디오 연동 무결성: **61/100**

## 2. 실행 검증 기록

### 통과

- `pnpm --dir apps/web test:run components/precheck/satong-map-selection.test.ts`
- 결과: 3개 테스트 통과

### 실패/차단

- `PYTHONPATH=apps/api pytest apps/api/tests/test_zone_limits_engine_sync.py apps/api/tests/test_ordinance_limits.py apps/api/tests/test_integrated_zoning_aggregate.py apps/api/tests/test_evidence_contract.py apps/api/tests/test_design_audit_core.py -q`
- 결과: 컬렉션 중단
- 원인: `ModuleNotFoundError: No module named 'fastapi'`
- 판정: 백엔드 검증 환경 자체가 완성도 게이트를 만족하지 못함. `apps/api/pyproject.toml` 기준 의존성 설치 또는 컨테이너/venv 고정 실행이 필요.

## 3. P0 무결성 결함

### P0-1. 구형 법규 RAG 서비스가 실패를 “적합”으로 반환

파일: `apps/api/services/regulation_service.py`

- `BUILTIN_REGULATION_DB`가 7개 용도지역만 내장한다.
- Qdrant 실패 시 내장 DB로 폴백한다.
- LLM 실패 시 `is_compliant=True`, `confidence=0.3`, `violations=[]`를 반환한다.
- 기존 테스트도 이 fail-open 동작을 정상으로 고정하고 있다.

레드팀 시나리오:

- Qdrant 장애 + LLM 장애 + 자연녹지/계획관리/산지/개발제한구역 복합 필지
- 결과: 실제로는 검토 불가인데 자동 분석 실패가 “적합=True”로 보일 수 있음

필수 조치:

- LLM/RAG 실패는 `NEEDS_VERIFICATION` 또는 `UNKNOWN`이어야 한다.
- `is_compliant=True` 폴백 금지.
- 구형 RAG 서비스는 제품 PASS 판정에서 제거하거나 `LegalHub`를 통해서만 호출하게 차단.

### P0-2. 구형 `/building-compliance/legal-check`가 미등록 용도지역을 통과 처리

파일: `apps/api/routers/building_compliance.py`

- `_LEGAL_LIMITS_PCT`라는 별도 정적 표를 보유한다.
- 미등록 용도지역이면 `overall_pass=True`와 “수동 확인 필요” remarks를 반환한다.

레드팀 시나리오:

- “자연취락지구”, “계획관리지역+보전산지”, “제2종일반주거지역(7층이하)” 등 세부 케이스 입력
- 결과: 미확정인데 통과로 표시될 수 있음

필수 조치:

- 미등록/미확정 용도지역은 `overall_status="warning" | "needs_verification"`로 반환.
- `overall_pass=True` 기본값 금지.
- `_LEGAL_LIMITS_PCT`는 `legal_limits_for()`로 대체.

### P0-3. 법정 한도표가 여러 곳에 분산되어 drift 가능

확인된 중복 표:

- `apps/api/app/services/zoning/auto_zoning_service.py`의 `ZONE_LIMITS`
- `apps/api/app/services/zoning/legal_zone_limits.py`의 `ZONE_FAR_MIN`
- `apps/api/app/services/land_intelligence/ordinance_service.py`의 `NATIONAL_LIMITS`, `ORDINANCE_CACHE`
- `apps/api/routers/building_compliance.py`의 `_LEGAL_LIMITS_PCT`
- `apps/api/app/services/permit/building_code_rules.py`의 `ZONE_DEFAULTS`
- `apps/api/services/regulation_service.py`의 `BUILTIN_REGULATION_DB`

필수 조치:

- 판정용 한도는 `legal_limits_for()`/`resolve_zone_limits()` 단일 경유로 제한.
- 나머지 표는 테스트 fixture, 표시용 캐시, 또는 제거 대상으로 강등.
- “한도표 drift 검사”를 CI 필수로 추가.

### P0-4. 조례 미확보 시 법정상한 폴백을 저장한다

파일: `apps/api/app/services/land_intelligence/ordinance_service.py`

- 법제처 API와 정적 캐시가 실패하면 `source="법정상한"`, `confidence=0.60`으로 결과를 만들고 저장한다.
- 이후 자동 재조사 없이 저장본을 재사용한다.

레드팀 시나리오:

- 특정 지자체 조례가 법정상한보다 낮지만 파싱 실패
- 법정상한이 저장됨
- 다음 분석부터 계속 법정상한이 재사용되어 과대 용적률/건폐율이 산정됨

필수 조치:

- 법정상한 폴백은 저장 금지 또는 `temporary/statutory_only` TTL 저장.
- 조례 미확보 상태는 설계 확정 게이트에서 `NEEDS_LOCAL_ORDINANCE`로 차단.
- 사용자 “재분석” 없이도 조례 출처가 법정상한이면 주요 산출 전 재확인해야 함.

## 4. P1 고위험 결함

### P1-1. 조례 파서가 정규식 중심이라 별표/표/HTML 변형에 취약

파일: `apps/api/app/services/land_intelligence/ordinance_service.py`

현재 파싱은 CDATA 추출, “용도지역안에서의 건폐율/용적률” 문자열 탐색, `(\S+지역):(\d+)퍼센트` 정규식에 의존한다.

미검증 변형:

- “용도지역 안에서의”처럼 띄어쓰기 있는 조문명
- 별표 표 구조
- 제2종일반주거지역(7층 이하)
- 계획관리/보전관리/생산관리 표 분리
- 도시지역 외 지역/지구단위계획/도시군관리계획 별도 상한
- 주석/단서조항/경과조치/부칙

필수 조치:

- XML/HTML 구조 파서 도입.
- 조례별 “표/별표/조문/단서/부칙” evidence span 저장.
- 파싱 confidence와 missing_sections를 응답에 포함.

### P1-2. 임목본수도·경사도·표고는 공식 인허가급 데이터가 아니다

파일:

- `apps/api/app/services/terrain/terrain_service.py`
- `apps/api/app/services/zoning/special_parcel.py`

현재 지형분석은 OpenTopoData SRTM 30m 기반이며 “정밀 측량/검증된 토목설계 아님”을 명시한다. 산지/임야는 special parcel에서 산지전용·경사도·표고·입목축적 검토 필요를 알리지만, 공식 산림청/지자체 허가 기준 데이터를 확정하지 않는다.

필수 조치:

- 산지/임야/보전산지/준보전산지는 `FOREST_OFFICIAL_DATA_REQUIRED` 게이트 적용.
- 평균경사도, 표고, 입목축적/입목본수도, 보전산지 여부, 산사태위험, 생태자연도, 임상도, 도시생태현황도 등 데이터 커버리지 매트릭스 필요.
- 공식 데이터 미확보 시 설계안은 “참고안”으로만 표시.

### P1-3. 필지 선택 핸드오프가 면적 미보강 필지를 탈락시킬 수 있음

파일: `apps/web/components/precheck/satong-map-selection.ts`

- `satongSelectionToParcelRows()`는 `areaSqm > 0`인 필지만 백엔드 다필지 행으로 변환한다.
- 검색/PNU는 성공했지만 면적 보강이 늦거나 실패한 필지는 분석 요청에서 제외될 수 있다.

필수 조치:

- 면적 미확보 필지는 제외가 아니라 `needs_enrichment` 상태로 전달.
- 백엔드가 PNU/주소로 면적을 재보강하고, 실패 시 명시 오류를 반환.
- “면적 없는 필지 포함 다필지” 테스트 추가.

### P1-4. 선택 목록을 비울 때 프로젝트 컨텍스트가 stale 될 수 있음

파일: `apps/web/components/precheck/SatongMapShell.tsx`

- `removeParcel()`은 남은 필지가 있을 때만 컨텍스트/스토리지 업데이트를 호출한다.
- 마지막 필지를 제거하면 `selectedParcels`는 비지만 기존 프로젝트 컨텍스트에 이전 필지가 남을 수 있다.

필수 조치:

- 마지막 필지 제거 시 siteAnalysis의 address/pnu/parcels/area/zone을 명시 clear.
- stale context 감지 테스트 추가.

### P1-5. 지도 fullscreen 회귀 테스트 부재

파일:

- `apps/web/components/map/ParcelPickerMap.tsx`
- `apps/web/hooks/useMapFullscreen.ts`

현재 VWorld 기본 타일 + OSM fallback + Leaflet fullscreen hook은 코드상 존재한다. 하지만 실제 사용자가 보고한 “fullscreen 후 black out, 종료 후 지도 미복구” 시나리오에 대한 e2e 테스트가 없다.

필수 조치:

- Playwright로 `precheck → 지도 로딩 → fullscreen on/off → 타일/컨테이너 픽셀 nonblank → 재클릭 가능` 테스트 추가.
- VWorld tile proxy 실패 시 OSM fallback 사용 여부와 사용자 경고 표시 검증.
- 네이티브 fullscreen과 CSS fallback 양쪽 검증.

## 5. P2 설계·도면 생성 파이프라인 결함

### P2-1. 설계 스튜디오가 stale 부지분석 결과를 감지하지만 차단하지 않음

화면상 “부지분석 데이터가 다른 주소의 결과입니다” 경고가 확인된다. 이는 좋은 신호지만, 설계/도면 생성이 계속 가능하면 사용자는 다른 필지 기준 도면을 생성할 수 있다.

필수 조치:

- 주소/PNU/site hash 불일치 시 “심층 설계 분석”, “도면 생성”, “CAD/BIM 편집실 이동” 차단.
- “부지분석 다시 실행”만 primary action으로 노출.

### P2-2. 간이 건축법규 룰엔진의 법적 근거 표기가 일부 부정확

파일: `apps/api/app/services/permit/building_code_rules.py`

- 주석과 `legal_basis`에서 건폐율/용적률을 “건축법 시행령 제84/85조”로 표기한다.
- 실제 근거는 국토계획법 시행령 제84조/제85조다.

필수 조치:

- legal reference registry 기반으로만 법령명/조문명을 표시.
- 자유문자열 근거는 테스트에서 금지.

### P2-3. 룰엔진 기본값이 실제 법규 검토처럼 보일 수 있음

파일: `apps/api/app/services/permit/building_code_rules.py`

- `max_bcr` 기본 60, `max_far` 기본 200이 남아 있다.
- `ZONE_DEFAULTS`는 관리지역/농림/자연환경보전 등을 포함하지 않는다.

필수 조치:

- 입력 부족은 기본값 계산이 아니라 `WARNING/NEEDS_DATA`.
- 관리지역/농림/자연환경보전은 SSOT `legal_limits_for()`로 자동 보완.

## 6. 적대적 시나리오 세트

다음 시나리오는 100% 게이트에 반드시 포함해야 한다.

1. **Qdrant down + LLM down**: 자동 법규 검토가 PASS를 반환하지 않아야 한다.
2. **미등록 용도지역**: `overall_pass=True`가 나오면 실패.
3. **자연녹지지역 20%/100%/4층**: 실효 가능 연면적은 `건폐율 × 층수` 제약을 반영해야 한다.
4. **계획관리지역 40%/100%**: 자연녹지와 달리 40% 건폐율로 용적 100% 활용 가능성을 별도 산정해야 한다.
5. **제2종일반주거지역(7층 이하)**: 일반 제2종과 별도 조례/고시 값을 적용해야 한다.
6. **보전산지+임야**: 산지전용, 평균경사, 표고, 입목축적/임목본수도, 대체산림자원조성비가 없으면 확정 설계 금지.
7. **농지+도시지역**: 도시지역 안 농지도 농지전용 협의/신고와 농지보전부담금 검토가 필요.
8. **문화재/군사/상수원/개발제한구역**: 용도지역 한도가 맞아도 행위제한 우선.
9. **다필지 혼재 용도지역**: 면적가중, 대표용도지역, 가장 제한적인 조건을 모두 별도 산출해야 한다.
10. **면적 없는 PNU 선택**: 분석 요청에서 삭제되지 않고 보강 큐로 전달되어야 한다.
11. **마지막 필지 삭제**: 프로젝트 컨텍스트가 완전히 비워져야 한다.
12. **fullscreen on/off**: 지도 타일 nonblank, 컨트롤 회복, 필지 클릭 가능 상태를 검증.
13. **VWorld tile 실패**: OSM fallback은 “임시 지도”로 표시되고 법적 정본 지도처럼 보이면 실패.
14. **조례 파싱 실패**: 법정상한은 `statutory_only`로 표기되고 산출 확정은 차단.
15. **부지분석 주소와 설계 주소 불일치**: 설계 실행 차단.

## 7. 100% 게이트 재정의

### 법령엔진 게이트

- 모든 법규 PASS에는 `source`, `legal_ref_key`, `evidence_span`, `confidence`, `retrieved_at`, `jurisdiction`이 있어야 한다.
- `unknown`, `fallback`, `statutory_only`, `llm_unverified`는 PASS가 될 수 없다.
- 지자체 조례 미확보 시 설계 확정 산출물은 생성 금지.
- 구형 정적 표가 `LegalHub`를 우회하면 CI 실패.

### 지도/필지 게이트

- 기본 지도는 VWorld/국토부 계열이 1순위여야 한다.
- Leaflet/OSM은 엔진/렌더링 fallback일 뿐, 법적 지적정본으로 표기 금지.
- 선택 필지 목록은 검색/엑셀/지도 모두 동일 데이터 모델로 통합되어야 한다.
- 면적·PNU·용도지역 누락 필지는 삭제가 아니라 보강 상태로 유지.
- fullscreen/레이어/필지 클릭 e2e nonblank 테스트 통과 필수.

### 설계·도면 게이트

- site hash가 현재 필지선택과 다르면 설계 실행 차단.
- 1차 법규/토지속성 분석, 2차 Top-N 건축개요, 3차 CAD/매스 생성이 한 화면의 상태머신으로 연결되어야 한다.
- 텍스트/음성 명령은 도면 편집 상태에 연결되어야 하고, 명령 결과는 audit log에 남아야 한다.
- 산지/농지/문화재/군사/상수원 등 특수 게이트 미해소 시 “확정 도면” 금지.

## 8. 구현 우선순위

### Phase A: fail-open 제거

1. `RegulationService._analyze_compliance` 실패 응답을 `is_compliant=False`가 아니라 `status="needs_verification"` 구조로 변경.
2. `/building-compliance/legal-check` 미등록 용도지역 `overall_pass=True` 제거.
3. 구형 정적 한도표 우회 경로를 `legal_limits_for()`로 교체.
4. 기존 fail-open 테스트를 실패 검증 테스트로 수정.

### Phase B: 법령 SSOT와 조례 evidence 강화

1. `LawScopeInventory` 구축: 필지별 확인해야 할 법규/조례/계획/고시/공공데이터 목록을 먼저 생성.
2. 조례 파서를 XML/HTML/별표 대응 구조 파서로 보강.
3. 법정상한 폴백 저장 금지 또는 TTL+statutory_only 저장.
4. 조례 evidence span과 파싱 confidence 저장.

### Phase C: 산지·지형·임목본수도 게이트

1. 임야/산지 판정 시 공식 데이터 required flag 생성.
2. 공식 평균경사도/표고/임상도/입목축적/산지구분 데이터 매핑.
3. 미확보 시 설계 확정 차단, 참고안만 허용.

### Phase D: 지도·필지 핸드오프 무결성

1. `selectionToSiteAnalysisPatch` clear 동작 추가.
2. 면적 없는 필지도 `needs_enrichment`로 유지.
3. VWorld/국토부 기본지도 tile proxy 상태 표시.
4. fullscreen e2e nonblank 테스트 추가.

### Phase E: 설계 스튜디오 통합 상태머신

1. current site basis 불일치 시 실행 차단.
2. 법규/토지속성 분석 → Top-N 건축개요 → CAD/매스 생성 → 명령 편집을 한 화면 상태머신으로 통합.
3. 모든 산출물에 site hash, law hash, ordinance hash, design hash 기록.

## 9. 완료 판정

현재는 “구현 진행 가능” 상태이나, “완성도 100%” 또는 “99% 이상 무결성”으로 선언하면 안 된다.

다음 조건을 모두 만족해야 완료 판정 가능:

- 백엔드 법령/조례/특이필지 테스트 재현 가능.
- 프론트 지도 fullscreen/레이어/필지선택 e2e 통과.
- fail-open 경로 0개.
- 법정 한도표 판정 경로 1개.
- 조례 미확보/공식 지형 미확보/임목본수도 미확보는 확정 산출 차단.
- stale site basis 설계 실행 차단.
- 모든 산출물에 provenance/evidence/audit hash가 남음.

