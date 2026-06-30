# 사통팔땅 100% 완성도·무결성 통합 개선계획

- 작성일: 2026-07-01
- 범위: 사통팔땅 지도 기반 필지 입력, 법령엔진, 법규검토, 조례/특수조건, 건축개요·계획도면 생성, 검증/배포 게이트
- 원칙: 목업 없는 구현, 공식 원천 우선, 실패 시 fail-closed, 미확인 항목은 산출 차단 또는 명시적 재검증, 머지·배포는 통합자 수행

## 1. 결론

이전 레드팀 감사 기준으로 현재 시스템은 100% 완성·무결성을 통과하지 못한다.
주요 원인은 기능 부족이 아니라 **판정 권한이 여러 코드 경로로 분산된 구조**다.

현재 반드시 해소해야 할 P0 축:

1. LLM/RAG/조례 조회 실패가 일부 경로에서 "적합" 또는 법정상한 확정값처럼 보일 수 있다.
2. 용도지역 한도표가 여러 파일에 중복되어 동일 필지에서 서로 다른 판단이 가능하다.
3. 조례·도시군관리계획·지구단위계획·산지/농지/문화재/상수원/군사/재해 등 특수조건이 "목록 생성 -> 원천 확인 -> 반증" 흐름으로 닫혀 있지 않다.
4. 지도 선택값, sessionStorage, 프로젝트 컨텍스트, 설계 스튜디오가 완전한 단일 흐름으로 잠기지 않아 stale/누락/면적 미확정 필지가 발생할 수 있다.
5. 백엔드 검증 환경에서 `fastapi`, `sqlalchemy`가 누락되어 핵심 테스트가 재현 가능한 게이트가 아니다.

100%의 정의는 "법률 결과를 무한 보증"이 아니다.
사통팔땅 기준 100%는 다음 상태다.

- 공식 원천 조회 가능 항목은 원천, 수집시각, 시행일, 조문, 좌표/필지 식별자를 증거 원장에 남긴다.
- 원천 공백·파싱 실패·LLM 실패는 절대 PASS가 되지 않는다.
- 필지별 법규 목록 생성 에이전트가 관련 가능 법규를 먼저 닫힌 후보군으로 만든다.
- 결정론 룰 엔진이 수치/조건을 계산하고, LLM은 누락 탐색·요약·반증 보조로만 사용한다.
- 반증 루프가 "이 결론을 뒤집을 수 있는 법규·조례·도면·특수조건"을 다시 찾는다.
- 검증 환경, 단위 테스트, E2E, 적대 시나리오, 라이브 스모크가 모두 같은 기준으로 통과한다.

## 2. 공식 원천 기준

100% 게이트에서 인정하는 1차 원천은 다음과 같이 재정의한다.

| 영역 | 1차 원천 | 엔진 역할 |
|---|---|---|
| 법률·시행령·시행규칙·행정규칙 | 국가법령정보센터 Open API | 법령 본문, 시행일, 조항/별표, 위임관계, 연혁 버전 관리 |
| 자치법규 | 국가법령정보센터 자치법규/ELIS 계열 | 도시계획조례, 건축조례, 주차장조례, 경관·녹지·산지 관련 조례 파싱 |
| 필지·지적·용도지역·공간좌표 | VWorld/국토교통부 공간정보 오픈플랫폼 | 지오코딩, PNU, 지적경계, 지적도/용도지역 레이어, WMTS/WMS/WFS 기반 지도 |
| 토지이용규제 | 토지이음 | 토지이용계획, 지역·지구, 행위제한, 도시계획도, 고시/도면 확인 트리거 |
| 산지·임야 | 산림청 산지정보시스템, 산림공간정보, 임상도 | 산지구분, 보전/준보전산지, 임상, 영급, 경급, 수관밀도, 입목축적 예비 판정 |
| 경사·표고·레벨 | 국토지리정보원/공식 DEM/수치지형도 또는 인허가급 지형측량 | 평균경사, 최대경사, 표고차, 레벨, 절성토량 |
| 건축물/인허가 | 세움터/건축데이터 개방 | 건축물대장, 인허가 이력, 용도변경, 노후도, 기존 건축물 조건 |
| 실거래·시세·공시지가 | 국토교통부 실거래가, 부동산공시가격, VWorld/NED 연계 | 실거래, 공시지가, 추정가, 사업성 입력 |

공식 원천 링크:

- 국가법령정보센터 Open API: https://open.law.go.kr/
- VWorld 공간정보 오픈플랫폼: https://www.vworld.kr/
- VWorld API: https://api.vworld.kr/
- 토지이음: https://www.eum.go.kr/
- 산림청 산지정보시스템: https://www.forestland.go.kr/
- 산림공간정보서비스: https://map.forest.go.kr/
- 공공데이터포털: https://www.data.go.kr/

## 3. 목표 아키텍처

### 3.1 단일 판정 흐름

모든 법규·설계·인허가 산출은 아래 파이프라인만 통과한다.

1. `ParcelIdentity`
   - address, PNU, bcode, lon/lat, cadastral geometry, area, jimok, jurisdiction, source를 고정한다.
2. `OfficialDataEnvelope`
   - VWorld/토지이음/법령/조례/산림/DEM/건축물/거래 원천을 수집한다.
   - 각 항목은 `source`, `retrieved_at`, `effective_date`, `confidence`, `stale`, `requires_recheck`를 가진다.
3. `LawScopeInventory`
   - 해당 필지에 적용 가능성이 있는 법률·시행령·시행규칙·조례·고시·계획·특수조건 목록을 생성한다.
   - LLM은 후보 확장만 담당하고, 최종 후보는 공식 원천에서 검증된 항목만 채택한다.
4. `DeterministicRuleKernel`
   - 용도지역, 조례, 건폐율, 용적률, 높이, 층수, 대지안공지, 일조, 주차, 도로, 피난방화, BF, 산지/농지 조건을 결정론으로 계산한다.
5. `CounterEvidenceLoop`
   - "이 결과를 뒤집는 조건"을 다시 찾는다.
   - 누락 가능성이 있으면 `PASS` 금지, `NEEDS_VERIFICATION`으로 강등한다.
6. `EvidenceLedger`
   - 적용/비적용 사유, 원문 링크, 조문, 수치, 산식, 버전 hash를 저장한다.
7. `OutputGate`
   - 후보지 진단서, 인허가 체크리스트, 시장 리포트, 건축개요·CAD 계획도면을 같은 검증 상태로 내보낸다.

### 3.2 판정 상태 표준화

기존 `true/false` 중심 판정을 폐기하고 아래 상태로 통일한다.

| 상태 | 의미 | 사용자 표기 | 하류 산출 |
|---|---|---|---|
| `PASS` | 공식 원천과 반증 루프 통과 | 적합 | 산출 가능 |
| `FAIL` | 위반 또는 불가능 확인 | 부적합 | 보완안만 산출 |
| `NEEDS_VERIFICATION` | 원천 공백, 조례 미확정, 특수조건 미확정 | 확인 필요 | 확정 산출 차단, 예비안만 허용 |
| `UNKNOWN` | 입력 부족, 서비스 장애, 파싱 실패 | 판단 불가 | 산출 차단 |
| `N/A` | 해당 없음 | 해당 없음 | 산출 영향 제외 |

금지 규칙:

- `UNKNOWN`을 `PASS`로 변환 금지.
- LLM 실패를 `is_compliant=True`로 반환 금지.
- 미등록 용도지역을 `overall_pass=True`로 반환 금지.
- 법정상한 폴백을 "조례 실효값"처럼 저장/표시 금지.

## 4. 현 코드 결함별 통합 개선안

### 4.1 P0-1. RegulationService fail-open 제거

대상:

- `apps/api/services/regulation_service.py`
- `apps/api/tests/test_regulation_service.py`
- `apps/api/tests/test_builtin_regulation_db.py`

문제:

- Qdrant 실패 시 7개 내장 DB로 폴백한다.
- LLM 실패 시 `is_compliant=True`, `confidence=0.3`을 반환한다.
- 테스트가 이 동작을 정상으로 고정한다.

개선:

1. `ComplianceStatus` enum을 도입한다.
2. `_analyze_compliance` 예외 시 `status=UNKNOWN`, `is_compliant=None`, `requires_manual_review=True` 반환.
3. 내장 DB는 표시/테스트 fixture로만 강등하고 제품 PASS 판정에서 제외.
4. 기존 테스트를 "실패 시 적합 금지" 테스트로 교체.

100% 게이트:

- `rg "is_compliant.*True" apps/api/services apps/api/routers`에서 실패 폴백 0건.
- LLM 장애, Qdrant 장애, empty docs, invalid JSON 4개 케이스 모두 `UNKNOWN` 또는 `NEEDS_VERIFICATION`.

### 4.2 P0-2. `/building-compliance/legal-check` 미등록 통과 제거

대상:

- `apps/api/routers/building_compliance.py`
- `apps/api/app/services/zoning/legal_zone_limits.py`
- `apps/api/app/services/zoning/zone_limit_contract.py`

문제:

- `_LEGAL_LIMITS_PCT` 별도 표가 존재한다.
- 미등록 용도지역이면 `overall_pass=True`를 반환한다.

개선:

1. `_LEGAL_LIMITS_PCT`를 제거하거나 read-only display map으로 강등한다.
2. 모든 한도 조회를 `legal_limits_for()` 또는 `resolve_zone_limits()`로 교체한다.
3. 미등록/미확정은 `overall_status=NEEDS_VERIFICATION`, `overall_pass=False` 또는 nullable로 반환한다.
4. 응답에 `source=SSOT`, `source_version`, `legal_refs`를 포함한다.

100% 게이트:

- unknown zone 테스트에서 PASS 금지.
- 자연녹지, 계획관리, 농림, 자연환경보전, 취락지구, 지구단위계획 상한 케이스 통과.

### 4.3 P0-3. 법정 한도표 drift 제거

대상 중복 표:

- `apps/api/app/services/zoning/auto_zoning_service.py`
- `apps/api/app/services/zoning/legal_zone_limits.py`
- `apps/api/app/services/land_intelligence/ordinance_service.py`
- `apps/api/routers/building_compliance.py`
- `apps/api/app/services/permit/building_code_rules.py`
- `apps/api/services/regulation_service.py`
- `apps/api/app/services/cad/design_spec.py`

개선:

1. `LegalZoneLimitsRegistry`를 단일 export로 만든다.
2. 기존 표는 다음 세 종류만 허용한다.
   - SSOT
   - 캐시 원천
   - 테스트 fixture
3. 소스 스캔 테스트를 추가해 판정 코드에서 금지 표 이름을 직접 참조하면 실패시킨다.
4. CAD/design_spec도 같은 SSOT를 import하도록 통합한다.

100% 게이트:

- `_LEGAL_LIMITS_PCT`, `ZONE_DEFAULTS`, `BUILTIN_REGULATION_DB`가 제품 판정 경로에서 직접 사용되지 않는다.
- 동일 용도지역의 bcr/far/floor 값이 모든 엔진에서 동일 provenance로 나온다.

### 4.4 P0-4. 조례 폴백 저장 금지

대상:

- `apps/api/app/services/land_intelligence/ordinance_service.py`
- `apps/api/app/services/precheck/precheck_service.py`
- `apps/api/app/services/land_intelligence/far_tier_service.py`

문제:

- 법제처 API와 정적 캐시 실패 시 법정상한을 `source="법정상한"`으로 저장한다.
- 이후 분석에서 조례 미확정 상태가 재사용될 수 있다.

개선:

1. `OrdinanceResolution` 상태를 분리한다.
   - `confirmed`
   - `cache_stale`
   - `statutory_only`
   - `unavailable`
2. `statutory_only`는 영구 저장 금지 또는 짧은 TTL 캐시만 허용.
3. 하류 산출에서 `statutory_only`면 "확정 조례"로 표시 금지.
4. 조례 파싱 실패 원인을 `api_missing_key`, `api_timeout`, `no_ordinance_match`, `parse_failed`, `zone_not_found`로 구분한다.

100% 게이트:

- 조례 미확정으로 나온 용적률은 설계 최종안/CAD 확정 산출을 차단한다.
- 사용자가 "예비안 생성"을 명시할 때만 statutory-only 기준으로 산출한다.

## 5. 법규검토 에이전트 구축안

### 5.1 역할

`LawScopeAgent`는 법률 판단을 직접 확정하지 않는다.
역할은 해당 필지 리스트에서 반드시 확인해야 할 법규·공공데이터·도면·고시 목록을 빠짐없이 만드는 것이다.

입력:

- 필지 리스트: PNU, 주소, 면적, 지목, 용도지역, 용도지구, geometry
- 관할: 시도, 시군구, 읍면동, 도시계획권역
- 공간조건: 도로 접도, 경사, 표고, 인접시설, 산지/농지/하천/문화재/군사/상수원 가능성
- 목표 산출물: 후보지 진단서, 인허가 체크리스트, 시장 리포트, 건축개요/CAD 계획도면

출력:

- `required_laws[]`: 법률/시행령/시행규칙/조례/고시/도시군관리계획 목록
- `required_datasets[]`: 지적, 토지이용계획, 산지, 농지, DEM, 건축물, 실거래, 공시지가 등
- `blocking_unknowns[]`: 확인 전 산출 차단 항목
- `rule_specs[]`: 결정론 룰 엔진이 실행할 항목
- `counter_checks[]`: 반증 질문 목록

### 5.2 법규 목록 생성 프롬프트 골격

```text
당신은 사통팔땅의 법규검토 스코프 생성 에이전트다.
법적 적합 여부를 확정하지 말고, 입력 필지에 적용 가능성이 있는 확인 대상 목록만 생성한다.

입력:
- 필지: {parcel_identity}
- 공식 원천 수집 결과: {official_data_envelope}
- 목표 산출물: {target_outputs}

작업:
1. 적용 가능 법률·시행령·시행규칙·조례·고시·도시군관리계획·지구단위계획을 나열한다.
2. 산지, 농지, 임야, 개발제한구역, 문화재, 군사, 상수원, 하천, 재해, 학교, 공원, 도로, 경관, 환경 조건을 별도 스캔한다.
3. 각 항목마다 공식 원천 확인 필요 여부와 확인 실패 시 차단할 산출물을 지정한다.
4. 이 결론을 뒤집을 수 있는 누락 조건을 counter_checks에 적는다.

금지:
- 법령 원문 근거 없이 PASS로 확정하지 말 것.
- 조례 미확정 상태를 실효값으로 쓰지 말 것.
- 원천 공백을 일반값으로 대체하지 말 것.
```

## 6. 특수조건 세밀 분석 확장

반드시 `LawScopeInventory`에 포함할 조건:

| 조건 | 데이터 | 법규/검토 포인트 | 산출 영향 |
|---|---|---|---|
| 임야/산지 | 산지구분도, 보전산지, 임상도 | 산지관리법, 산지전용허가, 산림조사서 | 개발 가능성, 사업기간, 비용 |
| 임목본수도/입목축적 | 임상, 영급, 경급, 수관밀도, 표준지/현장조사 | 산지전용 심사 기준, 지자체 기준 | 인허가 가능성, 보완자료 |
| 경사도/표고/레벨 | 공식 DEM/수치지형도/측량 | 개발행위허가, 절성토, 재해위험 | 건축 가능 면적, 공사비 |
| 지구단위계획 | 지구단위계획구역, 결정도서 | 용도, 높이, 배치, 건축선, 공개공지 | 설계 제약 최우선 |
| 도시군관리계획 | 도시계획시설, 고시도면 | 도로, 공원, 학교, 녹지, 기반시설 | 수용/저촉/기부채납 |
| 도로 접도 | 도로폭, 접면, 막다른도로 | 건축법 도로, 건축선, 차량 진출입 | 허가 가능성, 주차/동선 |
| 농지 | 농업진흥지역, 농지전용 | 농지법, 전용부담금 | 개발 가능성, 기간/비용 |
| 문화재/매장유산 | 문화재보호구역, 조사대상 | 문화재보호법/매장유산 | 사업기간, 조사비 |
| 환경/상수원/하천 | 상수원보호, 하천구역, 생태자연도 | 관련 개별법 | 개발 제한/협의 |
| 군사/비행/고도 | 군사시설보호, 비행안전 | 군사기지법, 항공 관련 제한 | 높이/용도 제한 |

원칙:

- SRTM 30m 같은 참고 DEM은 예비 위험도에만 사용한다.
- 인허가 산출에는 공식 DEM 또는 측량 필요 상태를 명시한다.
- 데이터가 없으면 "기본값"을 넣지 않고 `blocking_unknown`으로 남긴다.

## 7. 사통팔땅 지도 시스템 통합 개선안

### 7.1 기본 지도 정책

기본 엔진은 VWorld/국토부 기반으로 고정한다.
Leaflet은 렌더링 라이브러리로 사용할 수 있지만, 사용자에게 Leaflet/OSM이 기본 지도처럼 보이거나 Leaflet 전단 팝업이 뜨면 실패다.

기본 레이어:

1. VWorld 기본지도
2. VWorld 지적/연속지적도
3. 용도지역/용도지구
4. 토지이음 확인 대상/행위제한
5. 공시지가/실거래/분양/공·경매
6. 건축물 노후도/용도/층수
7. 산지/임상/경사/표고
8. 위성/항공뷰/로드뷰/교통·편의 POI

### 7.2 지도 UX 기준

- 검색창은 지도 상단에 통합한다.
- 엑셀 파일 선택/양식 다운로드는 검색 입력 옆에 배치한다.
- 왼쪽 패널은 선택 필지 목록과 필지 상세 카드만 담당한다.
- 오른쪽 팝업 패널은 레이어 설정, 필터, 범례, 반경 분석만 담당한다.
- 지도 위 아이콘 레일은 카테고리별 레이어 토글을 담당한다.
- 전체화면은 지도와 컨트롤이 함께 살아 있어야 하며 블랙아웃이 있으면 P0 회귀다.

100% 게이트:

- 전체화면 진입/해제 후 타일이 보인다.
- VWorld 타일 실패 시 공식 오류 메시지와 재시도 버튼이 보이고, OSM 전단 또는 무근거 기본지도 자동 대체는 금지한다.
- 레이어 토글은 실제 지도 표현, 범례, 선택 필터, EvidenceLedger 상태를 모두 바꾼다.
- 필지 선택 후 부지분석/인허가/시장/설계로 이동해도 같은 필지 목록이 유지된다.
- 마지막 필지 제거 시 sessionStorage와 project context가 모두 비워진다.

## 8. 건축개요·CAD 계획도면 생성 시스템 개선안

### 8.1 단일 화면 파이프라인

설계 스튜디오는 별도 단계 이동이 아니라 한 화면에서 아래 순서로 진행한다.

1. 조건 확인
   - 필지, 용도지역, 조례, 특수조건, 도로, 경사, 산지/농지, 도시계획을 한 번에 확인한다.
2. 추천안 만들기
   - 법규·토지속성·사업성·분양성·인허가 리스크를 종합해 건축물 종류 1~3순위를 추천한다.
3. 건축개요 Top-N
   - 각 순위별 건폐율, 용적률, 실효용적률, 층수, 세대수, 주차, 사업기간, 인허가 가능성을 생성한다.
4. 도면 편집
   - 선택안 기준으로 2D 배치, 매스, 동선, 주차, 일조, CAD/BIM 데이터를 생성한다.
5. 텍스트/음성 명령
   - "층수 1층 줄여", "주차 동선 분리", "일조 위반 피해서 재배치" 같은 명령을 같은 화면에서 실행한다.

### 8.2 산출 차단 규칙

- 필지 기준이 stale이면 설계 산출 차단.
- 조례가 statutory-only이면 "확정 설계안" 차단, "예비안"만 허용.
- 특수조건 blocking_unknown이 있으면 Top-N 추천에 리스크 배지를 붙이고 CAD 확정 내보내기를 막는다.
- 법정상한/조례/도시군관리계획/지구단위계획이 충돌하면 더 엄격하거나 우선순위가 높은 규정으로 계산하고 근거를 남긴다.

100% 게이트:

- 자연녹지지역 20/100/4층 케이스에서 실효 건축가능연면적 80% 계산 근거가 표시된다.
- 계획관리지역 40/100 케이스는 용적률 100% 활용 가능성이 별도 케이스로 계산된다.
- 용도지역이 같아도 조례/지구단위/도로/일조/높이/산지 조건이 다르면 추천안이 달라진다.
- 설계 스튜디오의 모든 숫자는 EvidenceLedger의 수치와 일치한다.

## 9. 적대적 반복검증 매트릭스

각 구현 단계마다 아래 시나리오를 모두 재실행한다.

| 번호 | 시나리오 | 기대 결과 |
|---|---|---|
| R1 | Qdrant 장애 + LLM 장애 | UNKNOWN, PASS 금지 |
| R2 | 미등록 용도지역 | NEEDS_VERIFICATION, 산출 차단 |
| R3 | 조례 API 장애 | statutory_only, 확정 설계 금지 |
| R4 | 정적 조례 캐시 오래됨 | cache_stale, 재분석 CTA |
| R5 | 자연녹지 20/100/4층 | 실효 FAR 80% 설명 |
| R6 | 계획관리 40/100 | FAR 100% 활용 가능성 계산 |
| R7 | 지구단위계획 상한 존재 | 지구단위 우선 적용 |
| R8 | 산지/임야/보전산지 | 산지전용/임목/경사 blocking_unknown |
| R9 | 농지/농업진흥지역 | 농지전용 blocking_unknown |
| R10 | 다필지 혼합 용도지역 | 면적가중/필지별 개별 룰 병행 |
| R11 | 면적 없는 필지 선택 | 보강 전 산출 차단, 목록 유지 |
| R12 | 마지막 필지 삭제 | context/storage 모두 clear |
| R13 | 전체화면 진입/해제 | 지도 타일/컨트롤 유지 |
| R14 | VWorld 타일 장애 | 공식 오류/재시도, 무단 OSM 전환 금지 |
| R15 | stale siteAnalysis | 설계/시장/인허가 산출 차단 |
| R16 | 법령 변경 감지 | 해당 evidence stale 처리 |
| R17 | 법규 목록 에이전트 누락 | counter_check가 누락 후보 재탐색 |
| R18 | 법정상한과 조례 충돌 | min/우선순위 규칙과 근거 표시 |
| R19 | 도시계획시설 저촉 | 개발 가능성/사업기간 리스크 반영 |
| R20 | 텍스트/음성 도면 수정 | 같은 화면에서 재계산/근거 갱신 |

## 10. 단계별 구현계획

### Phase 0. 검증환경 고정

목표:

- 백엔드 테스트가 로컬/CI/컨테이너에서 동일하게 실행되도록 만든다.

작업:

1. `apps/api` 의존성 설치 경로를 문서화하고 CI와 동일 명령을 스크립트화한다.
2. `fastapi`, `sqlalchemy` 누락 상태를 테스트 전 단계에서 감지한다.
3. redteam 전용 pytest/vitest/playwright 명령을 `scripts/redteam-verify.sh`로 묶는다.

게이트:

- 백엔드 핵심 테스트 수집 성공.
- 프론트 지도/필지 선택 테스트 통과.
- 테스트 환경 누락이면 구현 완료 판정 금지.

### Phase 1. Fail-open 제거

작업:

1. `ComplianceStatus` 공통 타입 추가.
2. `RegulationService` 실패 반환 수정.
3. `/building-compliance/legal-check` 미등록 통과 제거.
4. fail-open 고정 테스트를 fail-closed 테스트로 교체.

게이트:

- `is_compliant=True` 실패 폴백 0건.
- `overall_pass=True` 미등록 폴백 0건.

### Phase 2. 법정/조례/용도지역 SSOT 통합

작업:

1. `legal_limits_for()`/`resolve_zone_limits()`를 판정 단일 경로로 승격.
2. `_LEGAL_LIMITS_PCT`, `ZONE_DEFAULTS`, `BUILTIN_REGULATION_DB` 직접 참조 제거.
3. CAD/design_spec, permit, compliance, scenario, feasibility, persona 경로 통합.
4. drift 스캔 테스트 추가.

게이트:

- 모든 판정 경로가 같은 용도지역 한도를 반환.
- 중복 표 직접 참조 테스트 0건.

### Phase 3. 조례·도시계획·특수조건 원천화

작업:

1. 조례 결과 상태를 `confirmed/cache_stale/statutory_only/unavailable`로 분리.
2. statutory-only 영구 저장 금지.
3. 토지이음/VWorld/산림/DEM/건축물 원천 envelope 추가.
4. 산지, 임목본수도, 경사, 표고, 농지, 문화재, 상수원, 군사, 도시계획시설 blocking rules 추가.

게이트:

- 특수조건 공백은 PASS가 아니라 blocking_unknown.
- 임야/산지/농지/지구단위/도시계획시설 샘플 통과.

### Phase 4. LawScopeAgent + EvidenceLedger

작업:

1. 필지별 법규 목록 생성 에이전트 구현.
2. 공식 원천 검증 후 `LawScopeInventory` 저장.
3. 적용/비적용 근거를 `EvidenceLedger`에 저장.
4. CounterEvidenceLoop 구현.

게이트:

- 산출물마다 근거 원장 ID가 있다.
- 반증 루프가 누락 후보를 생성하고, critical 누락 시 PASS를 막는다.

### Phase 5. 사통팔땅 멀티지도 완성

작업:

1. VWorld 기본 지도 강제.
2. Leaflet 전단/OSM 자동 기본 노출 제거.
3. 레이어별 실제 데이터 연결: 지적, 용도지역, 공시지가, 실거래, 노후도, 산지, 경사, 위성/로드뷰.
4. 전체화면 블랙아웃 회귀 테스트 추가.
5. 필지 선택 context/storage 동기화 강화.

게이트:

- 전체화면/해제 후 지도 비블랭크.
- 필지 선택 후 산출 화면 이동 시 동일 목록 유지.
- 레이어 토글이 실제 지도·범례·패널을 동시에 바꾼다.

### Phase 6. 설계 스튜디오 통합 파이프라인

작업:

1. stale siteAnalysis 차단.
2. 조건 확인 -> 추천안 -> 건축개요 Top-N -> CAD/BIM 편집을 한 화면으로 통합.
3. 텍스트/음성 명령을 도면 편집 화면에 재연결.
4. 법규/사업성/분양성/인허가 가능성 점수 산식과 근거 연결.

게이트:

- 같은 필지에서 법규 변경 시 추천안/도면/사업성 재계산.
- 확정 불가 상태에서 확정 도면 내보내기 금지.

### Phase 7. 통합 레드팀 게이트

작업:

1. 20개 적대 시나리오 자동화.
2. 코드 스캔 금지 패턴 추가.
3. UI 스냅샷/비블랭크/레이어 상호작용 검증.
4. 통합자 배포 전 preflight 보고서 생성.

게이트:

- P0 0건.
- P1에 사용자 오판 가능성 있는 항목 0건.
- 백엔드/프론트/지도 E2E/법규 시나리오 모두 통과.
- 보고서에 "검증 불가" 항목이 있으면 100% 판정 금지.

## 11. 반복검증 결과: 현재 판정

2026-07-01 재검증 결과:

- 프론트 선택 변환 테스트: 통과
  - `pnpm --dir apps/web test:run components/precheck/satong-map-selection.test.ts`
  - 3개 테스트 통과
- 백엔드 검증 환경: 실패
  - `fastapi: missing`
  - `sqlalchemy: missing`
  - pytest 자체는 있으나 핵심 API 테스트 수집 불가
- 코드 스캔: P0 패턴 존재
  - `RegulationService` 실패 시 적합 반환
  - `/building-compliance/legal-check` 미등록 용도지역 통과
  - `_LEGAL_LIMITS_PCT`, `ZONE_DEFAULTS`, `BUILTIN_REGULATION_DB` 판정 경로 잔존
  - 조례 미확정 법정상한 저장 경로 존재

따라서 현 상태는 100%가 아니며, **Phase 0 -> Phase 1 -> Phase 2**를 먼저 완료하지 않으면 지도/설계 UI를 더 고도화해도 제품 무결성은 통과할 수 없다.

## 12. 통합자 전달 기준

이 작업 브랜치에서 수행할 범위:

- 구현, 테스트, 문서화, 커밋, 푸시

통합자에게 맡길 범위:

- 메인 브랜치 머지
- Oracle/운영 배포
- 라이브 도메인 최종 배포 승인

배포 요청 시 포함할 자료:

1. 구현 커밋 SHA
2. redteam verification report
3. P0/P1 해소 목록
4. 실패/미확인 항목 0건 증명
5. 라이브 검증 체크리스트

