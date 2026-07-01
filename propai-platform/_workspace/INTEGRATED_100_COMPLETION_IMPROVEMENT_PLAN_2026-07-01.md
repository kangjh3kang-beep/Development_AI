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

## 13. 2차 계획 레드팀 감사: 계획 자체의 취약점

이 섹션은 앞선 계획을 다시 공격 대상으로 삼아 작성했다.
목표는 "무엇을 만들지"가 아니라 "이 계획대로 해도 100%에 실패할 수 있는 이유"를 제거하는 것이다.

### 13.1 계획 취약점 P0

#### Plan-P0-1. 공식 원천을 나열했지만 API별 획득 가능성 게이트가 부족하다

위험:

- VWorld, 토지이음, 국가법령정보, 산림청, 공공데이터는 각각 인증키, 도메인 제한, 다운로드 방식, 좌표계, 이용약관, 실시간 API 여부가 다르다.
- "연동한다"는 문장만으로는 구현 가능성과 운영 안정성이 검증되지 않는다.
- 토지이음처럼 화면 열람 중심인 원천은 API/크롤링/링크아웃/수동확인 중 어떤 방식이 합법·안정적인지 별도 결정이 필요하다.

보강:

1. 원천마다 `ConnectorReadiness`를 만든다.
   - `available_api`
   - `credential_required`
   - `domain_required`
   - `rate_limit_known`
   - `license_checked`
   - `geometry_supported`
   - `fallback_policy`
2. 원천 사용 전 `source_contract_test`를 통과해야 한다.
3. API가 없거나 약관상 자동수집이 부적절하면 `manual_verification_required`로 분기한다.
4. 지도에는 "공식 원천 확인 링크"와 "자동수집 불가/수동확인" 상태를 명확히 표시한다.

100% 게이트:

- 각 원천은 `ready`, `limited`, `manual_only`, `unavailable` 중 하나로 분류된다.
- `limited/manual_only/unavailable` 원천은 PASS 산출에 직접 사용되지 않는다.

#### Plan-P0-2. 법규 목록 생성 에이전트가 누락을 만들 수 있다

위험:

- LLM 기반 후보 생성은 특이사례를 누락할 수 있다.
- "관련법규 리스트 생성" 자체가 틀리면 이후 결정론 엔진이 아무리 정확해도 누락 법규를 검토하지 못한다.

보강:

1. `LawScopeAgent`를 단독 LLM이 아니라 4중 앙상블로 구성한다.
   - deterministic trigger: 지목, 용도지역, 용도지구, 면적, 도로, 산지/농지/하천 등 코드 기반 트리거
   - official relation graph: 국가법령정보 관련법령/위임관계/자치법규 연계 API
   - spatial trigger: VWorld/토지이음/산림/DEM 공간 레이어 교차
   - LLM adversarial expansion: "누락될 수 있는 특이 법규" 탐색
2. 최종 scope는 네 경로의 합집합으로 만들고, 제거는 사람이 읽을 수 있는 비적용 사유가 있을 때만 허용한다.
3. `ScopeCoverageTest`를 만든다.
   - 산지
   - 농지
   - 개발제한구역
   - 문화재
   - 군사시설
   - 상수원
   - 하천
   - 도시계획시설
   - 지구단위계획
   - 도로 접도
   - 급경사/고저차
   - 학교/공원/공공시설 저촉

100% 게이트:

- 필지당 `scope_generation_paths >= 3`.
- critical domain 누락 시 자동 PASS 금지.
- LLM이 만든 법규는 공식 원천 ID와 매칭되지 않으면 후보 상태로만 남긴다.

#### Plan-P0-3. "법령엔진"과 "설계엔진"의 경계가 아직 모호하다

위험:

- 설계엔진이 편의를 위해 기본값을 넣으면 법령엔진의 fail-closed 원칙을 우회할 수 있다.
- CAD/design_spec, persona, feasibility, scenario 경로에 오래된 한도표가 남아 있으면 사용자에게 다른 숫자가 보인다.

보강:

1. `LegalVerdictEnvelope` 없이는 설계엔진이 확정 산출을 만들 수 없게 한다.
2. 설계엔진 입력은 다음 중 하나만 허용한다.
   - `PASS` verdict: 확정안 생성 가능
   - `NEEDS_VERIFICATION` verdict: 예비안만 가능
   - `UNKNOWN/FAIL`: 확정/예비 산출 모두 제한 또는 보완안만 가능
3. 설계엔진 내부 기본값은 `assumption_registry`에 등록하고 UI에 "가정"으로 노출한다.
4. 설계 산출물의 모든 숫자는 `legal_verdict_id`와 `evidence_ledger_id`를 참조한다.

100% 게이트:

- `design-studio`에서 stale/unknown 필지로 확정 CAD 다운로드 불가.
- 설계 기본값이 법규 수치처럼 표시되는 UI 0건.

#### Plan-P0-4. 검증 환경 복구가 선행 단계로 더 강하게 잠겨야 한다

위험:

- 현재 로컬 쉘에서 `fastapi`, `sqlalchemy`가 누락되어 백엔드 테스트 수집이 실패한다.
- 테스트가 실행되지 않는 상태에서 계획/구현 완료를 선언하면 false assurance가 된다.

보강:

1. Phase 0을 "권장"이 아니라 모든 구현의 선행 차단 게이트로 승격한다.
2. `scripts/redteam-verify.sh`는 의존성 검사 실패 시 즉시 non-zero 종료한다.
3. 백엔드 검증은 최소 두 경로를 제공한다.
   - local venv/uv/pip 경로
   - Docker/CI 경로
4. `pytest collection` 자체를 독립 게이트로 둔다.

100% 게이트:

- 테스트 미실행/수집 실패 상태에서는 어떤 Phase도 완료 처리하지 않는다.

### 13.2 계획 취약점 P1

#### Plan-P1-1. 데이터 품질 등급이 더 세밀해야 한다

기존 `confidence`만으로는 부족하다.

보강 데이터 품질 모델:

| 필드 | 의미 |
|---|---|
| `source_authority` | official, public_open_data, partner, user_upload, inferred |
| `collection_mode` | api, file_download, manual_link, user_input, derived |
| `freshness` | current, stale, unknown |
| `spatial_precision` | parcel, building, road_segment, grid, centroid, unknown |
| `legal_effect` | binding, advisory, reference, unknown |
| `verification_state` | verified, cross_checked, single_source, disputed, failed |
| `blocking_level` | none, warn, block_preliminary, block_final |

100% 게이트:

- `legal_effect=unknown`인 데이터는 확정 법규판정에 사용 금지.
- `spatial_precision=centroid/grid`인 경사·산지·도로 데이터는 인허가 확정값으로 사용 금지.

#### Plan-P1-2. 지도 레이어의 "보이는 것"과 "계산되는 것" 분리가 필요하다

위험:

- WMS 이미지는 눈에는 보이지만 계산 가능한 geometry가 없을 수 있다.
- WFS/GeoJSON 없이 이미지 레이어만 켜면 사용자에게 분석이 된 것처럼 보이지만 실제 계산은 불가능하다.

보강:

1. 각 레이어를 `visual`, `queryable`, `computable`로 분류한다.
2. 필지 분석에 쓰는 레이어는 `computable=true`여야 한다.
3. WMS-only 레이어는 UI에 "시각 참고"로 표기한다.
4. 지도 클릭 시 어떤 computable layer가 실제 판정에 들어갔는지 EvidenceLedger에 기록한다.

100% 게이트:

- 시각 레이어만 켠 상태에서 법규/사업성 확정 산출 금지.
- 사용자가 본 레이어와 엔진이 사용한 데이터가 다르면 불일치 경고 표시.

#### Plan-P1-3. 다필지 병합의 법적 단위와 사업 단위가 분리되어야 한다

위험:

- 다필지 합산 면적은 사업성 계산에는 맞을 수 있지만, 법규는 필지별/대지단위/합필 가능성에 따라 달라진다.
- 혼합 용도지역을 단순 면적가중하면 특정 행위제한이나 도로 접도 조건을 놓칠 수 있다.

보강:

1. `ParcelGroup`에 세 단위를 둔다.
   - selected parcels
   - legal lots
   - development site candidate
2. 합필 가능성, 도로, 소유권, 지목, 용도지역 경계를 별도 판정한다.
3. 면적가중 수치와 필지별 blocking rule을 병렬 실행한다.

100% 게이트:

- 혼합 용도지역 다필지는 "면적가중 결과"와 "가장 엄격한 필지별 제한"을 함께 표시한다.

#### Plan-P1-4. "특이사례" 회귀 데이터셋이 필요하다

보강:

- `/tests/fixtures/redteam_parcels/`를 만든다.
- 실제 주소를 저장하기 어려우면 PNU/법규조건을 비식별화한 fixture를 둔다.
- 최소 30개 케이스:
  - 자연녹지
  - 계획관리
  - 보전관리
  - 농림
  - 자연환경보전
  - 개발제한구역
  - 보전산지
  - 준보전산지
  - 농업진흥지역
  - 문화재보호구역
  - 하천구역
  - 상수원보호구역
  - 군사시설보호
  - 지구단위계획
  - 도시계획시설 도로/공원/학교
  - 맹지
  - 접도 미달
  - 고저차 과다
  - 혼합용도지역
  - 다필지 면적 불일치
  - 공시지가 없음
  - 실거래 없음
  - 노후도 데이터 없음
  - 조례 API 실패
  - 조례 파싱 실패
  - VWorld 타일 실패
  - WFS geometry 실패
  - sessionStorage 차단
  - fullscreen 회귀
  - stale siteAnalysis

100% 게이트:

- redteam fixture 30개가 CI에서 매번 실행된다.

## 14. 100% 완성도 점수체계 v2

기존의 주관적 완성도 점수 대신, 제품 게이트를 가중치로 계산한다.

| 영역 | 가중치 | 100% 조건 |
|---|---:|---|
| 검증환경 | 10 | 백엔드/프론트/브라우저 테스트 재현 가능 |
| 공식원천 커넥터 | 15 | 원천별 readiness와 계약 테스트 통과 |
| 법령 SSOT | 15 | 중복 판정표 제거, fail-open 0건 |
| 조례/계획/특수조건 | 15 | blocking_unknown 체계와 특이 fixture 통과 |
| 지도 통합 | 15 | VWorld 기본, 레이어 query/compute 분리, fullscreen 안정 |
| 필지 핸드오프 | 10 | 다필지/삭제/스토리지/stale 무결성 통과 |
| 설계·CAD 파이프라인 | 10 | LegalVerdictEnvelope 기반 산출 차단/허용 |
| 증거 원장/반증 루프 | 10 | EvidenceLedger와 counter-check 전 산출물 연결 |

최종 판정:

- 100점: 배포 후보.
- 95~99점: 내부 QA 후보. P0은 없어야 하며 P1은 사용자 오판을 만들지 않아야 한다.
- 90~94점: 기능 검증 중. 통합자 배포 요청 금지.
- 90점 미만: 구현 미완료.

주의:

- P0가 1개라도 있으면 점수와 무관하게 100% 불가.
- 테스트 수집 실패가 있으면 최고점은 70점으로 제한.
- 공식 원천 readiness 미확정이면 최고점은 85점으로 제한.

## 15. 반복검증 루프 v2

각 Phase는 아래 루프를 통과해야 완료된다.

1. `Plan Attack`
   - 이 단계의 계획 자체가 실패할 수 있는 이유를 5개 이상 적는다.
2. `Implementation`
   - 목업 없는 실제 코드/커넥터/테스트 구현.
3. `Static Scan`
   - 금지 패턴, 중복 표, fail-open, mock fallback, stale bypass 검색.
4. `Unit Contract`
   - 입력/출력 스키마, 상태, evidence 계약 검증.
5. `Adversarial Fixture`
   - redteam fixture 실행.
6. `Integration Flow`
   - 지도 -> 필지 -> 법규 -> 설계 -> 산출물 핸드오프 검증.
7. `Browser E2E`
   - 전체화면, 레이어, 검색, 엑셀, 다필지, 산출 이동, stale 차단 검증.
8. `Evidence Audit`
   - 모든 산출물이 evidence ledger를 참조하는지 검사.
9. `Regression Lock`
   - 이번에 발견한 결함을 테스트로 고정.
10. `Completion Decision`
    - P0/P1/점수/미검증 항목 보고 후 다음 Phase 이동.

## 16. 구현 우선순위 v2

### Step A. 차단 게이트부터 구현

1. 백엔드 의존성/테스트 수집 복구.
2. `ComplianceStatus` 도입.
3. fail-open 반환 제거.
4. 미등록 용도지역 PASS 제거.
5. 조례 statutory-only 확정 산출 차단.

성공 기준:

- 사용자가 틀린 적합 판정을 볼 수 있는 경로 0건.

### Step B. 단일 판정 경로 완성

1. `LegalVerdictEnvelope` 추가.
2. `EvidenceLedger` 최소 스키마 추가.
3. 모든 산출 API가 verdict/evidence를 참조.
4. 중복 한도표 직접 참조 제거.

성공 기준:

- 같은 필지·같은 조건이면 모든 화면이 같은 법규 수치를 표시.

### Step C. 지도와 필지 입력 무결성

1. VWorld 기본 지도와 공식 오류 처리.
2. 레이어별 visual/queryable/computable 계약.
3. 필지 선택/삭제/다필지/엑셀/context/storage 테스트.
4. fullscreen 블랙아웃 회귀 테스트.

성공 기준:

- 지도에서 본 것과 산출물에 쓰인 데이터가 일치.

### Step D. 특수조건과 조례 확장

1. `LawScopeInventory`.
2. 산지/임목/경사/농지/도시계획/지구단위/문화재/상수원/군사/하천 트리거.
3. 공식 원천 미확보 항목 blocking_unknown.
4. counter evidence loop.

성공 기준:

- 특이사례 fixture가 PASS/FAIL/NEEDS_VERIFICATION을 정직하게 반환.

### Step E. 설계·CAD 통합

1. 설계 스튜디오 stale 차단.
2. 1~3순위 건축물 추천.
3. 1~3순위 건축개요 자동 생성.
4. CAD/BIM 도면 편집과 텍스트/음성 명령 재연결.
5. 확정/예비안 구분.

성공 기준:

- 법규 상태가 바뀌면 추천안, 건축개요, 도면 산출 권한이 즉시 바뀐다.

## 17. 추가 누락 방지 체크리스트

구현 전 매번 확인:

- [ ] 이 기능은 공식 원천 또는 사용자 입력 중 무엇을 근거로 하는가?
- [ ] 원천 실패 시 PASS가 되는 경로가 없는가?
- [ ] 수치가 법정상한, 조례 실효, 지구단위 상한, 가정값 중 무엇인지 구분되는가?
- [ ] 지도에 보이는 레이어와 계산에 쓰이는 데이터가 일치하는가?
- [ ] LLM이 만든 문장이 결정론 룰 결과를 덮어쓰지 않는가?
- [ ] 다필지에서 필지별 제한과 사업지 합산 제한을 분리했는가?
- [ ] 산지/농지/문화재/군사/상수원/하천/재해/도시계획시설 스캔이 실행됐는가?
- [ ] 조례 미확정 상태에서 확정 도면·확정 사업성·확정 인허가 판정을 차단했는가?
- [ ] 사용자가 "왜 이런 결론인지" 증거 원장에서 확인할 수 있는가?
- [ ] 이 결론을 뒤집을 수 있는 반증 질문을 실행했는가?
- [ ] 이번 결함이 회귀 테스트로 고정됐는가?

## 18. 2차 레드팀 결론

보강 후에도 100%는 문서 선언으로 달성되지 않는다.
다만 이 v2 계획은 기존 계획의 가장 큰 허점을 보완한다.

핵심 강화점:

1. 공식 원천을 단순 나열하지 않고 readiness/계약 테스트로 잠갔다.
2. 법규 목록 생성 에이전트의 LLM 누락 위험을 4중 합집합 구조로 낮췄다.
3. 법령엔진과 설계엔진 사이에 `LegalVerdictEnvelope` 차단막을 세웠다.
4. 지도 레이어를 visual/queryable/computable로 분리해 "보이는 지도"와 "계산 가능한 지도"의 혼동을 제거했다.
5. 다필지의 사업 단위와 법적 단위를 분리했다.
6. redteam fixture 30개와 반복검증 루프를 100% 게이트로 승격했다.

최종 구현은 반드시 Step A부터 진행해야 한다.
지도 UI나 설계 UI를 먼저 고도화하면 사용성은 좋아져도 법규 무결성은 여전히 100%가 될 수 없다.

## 19. 3차 계획 레드팀 감사: 실행·운영·증거 공백

3차 감사는 v2 계획 자체가 실제 구현 단계에서 다시 실패할 수 있는 지점을 대상으로 했다.
핵심 질문은 다음이다.

- 계획의 각 P0가 어느 코드, 어느 테스트, 어느 산출물에서 닫혔는가?
- 공식 원천이 끊기면 사용자는 무엇을 보게 되는가?
- 목업·fallback·가정값이 제품 판정으로 섞일 가능성은 없는가?
- 통합자에게 넘길 때 "믿어도 되는 증거 묶음"이 자동으로 남는가?
- 운영 중 법령/조례/지도 API/데이터가 바뀌면 기존 산출물이 stale 처리되는가?

### 19.1 Plan-P0-5. 추적성 매트릭스 부재

위험:

- P0를 문서에는 적었지만 어떤 커밋·테스트·API·화면에서 해소됐는지 추적하지 못하면 반복 검증이 사람 기억에 의존한다.
- 구현 완료 후에도 "이 P0가 정말 닫혔는가"를 통합자가 다시 조사해야 한다.

보강:

`CompletionTraceabilityMatrix`를 필수 산출물로 추가한다.

| 필드 | 설명 |
|---|---|
| `finding_id` | 예: P0-1, Plan-P0-5 |
| `risk` | 사용자 오판, 법규 누락, 산출 오류, 배포 차단 등 |
| `owner_module` | api, web, map, design, legal, ci |
| `code_paths` | 수정 대상 파일 |
| `tests` | 회귀 테스트 파일/명령 |
| `evidence_artifact` | 결과 JSON, screenshot, report path |
| `status` | open, in_progress, fixed, verified, blocked |
| `verified_by` | unit, e2e, redteam, integration, manual_review |
| `regression_lock` | 같은 결함 재발 시 실패하는 테스트 |

100% 게이트:

- 모든 P0/P1은 traceability matrix에 행이 있어야 한다.
- `status=verified`가 아닌 P0가 있으면 완료 판정 금지.
- 테스트 없는 P0 수정은 완료 판정 금지.

### 19.2 Plan-P0-6. 목업·fallback 경로가 제품 경로에 섞일 수 있다

현재 스캔에서 확인된 위험 유형:

- `apps/web/components/map/*` 일부가 `@/mocks/module-data` 타입 또는 목업 데이터 구조를 참조한다.
- `ParcelPickerMap`은 VWorld 타일 오류 시 OpenStreetMap fallback을 추가한다.
- `CadBimIntegrationPanel`에는 fallback spec 경로가 있다.
- 일부 통합 테스트는 dummy key 실패 시 mock fallback을 성공으로 본다.

위험:

- 목업은 테스트와 설계 보조에는 유용하지만, 사용자가 보는 법규/지도/설계 산출에서 실제 데이터처럼 섞이면 무결성이 무너진다.
- fallback이 "비권위 데이터"로 표시되지 않으면 사용자는 공식 원천 결과로 오해한다.

보강:

1. `NoMockProductionGate`를 추가한다.
2. 제품 런타임에서 허용되는 fallback은 세 종류만 둔다.
   - `display_unavailable`: 데이터를 표시하지 않고 재시도/수동확인 안내
   - `non_authoritative_preview`: 예비 미리보기, 확정 산출 차단
   - `test_only_mock`: 테스트 빌드에서만 허용
3. `useMock=false`만으로는 부족하다. 응답 envelope에 `data_authority`를 넣어야 한다.
4. OSM fallback은 공식 지도 대체가 아니라 "배경지도 임시 미리보기"로만 허용하고 법규/필지 계산에는 사용 금지한다.
5. 설계 fallback spec은 `assumption_registry`에 등록하고 확정 CAD 산출을 막는다.

100% 게이트:

- production build에서 mock import가 판정/산출 경로에 포함되면 실패.
- fallback 데이터로 PASS, 확정 도면, 확정 사업성, 확정 인허가가 생성되면 실패.
- fallback UI는 항상 "비권위/예비/확인 필요"를 표시한다.

### 19.3 Plan-P0-7. 공식 공간정보의 법적 효력 오해 가능성

공식 공간정보도 모두 같은 법적 효력을 갖지 않는다.
예를 들어 산지정보시스템은 산지구분도 면적이 GIS 공간분석상 참고 면적이며 지적공부상 면적과 다를 수 있음을 안내한다.
따라서 지도·공간 데이터는 정본 확인의 트리거이지, 모든 경우에 인허가 확정값이 아니다.

보강:

1. `legal_effect`를 필수 필드로 만든다.
   - `binding_record`
   - `official_reference`
   - `spatial_reference`
   - `derived_estimate`
   - `user_assertion`
2. 면적, 경사, 산지, 임상, 도로 폭은 정밀도와 법적 효력을 분리 표시한다.
3. 확정 인허가 판단에는 `binding_record` 또는 `official_reference + cross_checked`만 사용한다.
4. `spatial_reference`는 산출 차단까지는 아니어도 `requires_survey` 또는 `requires_official_document`를 만든다.

100% 게이트:

- GIS 면적/경사/산지 분석값이 지적공부·측량·허가도서 확정값처럼 표시되면 실패.
- 공식 공간정보와 지적공부/조례/고시가 충돌하면 `disputed` 상태로 차단.

### 19.4 Plan-P0-8. 운영 관측성과 stale 전파 계획 부족

위험:

- 법령, 조례, 지구단위계획, VWorld 레이어, 산림 데이터가 바뀌어도 기존 프로젝트 산출물이 stale 처리되지 않으면 과거 판정이 계속 살아남는다.
- API 장애가 늘어나도 사용자는 단순 오류 또는 빈 화면으로만 본다.

보강:

1. `SourceHealthMonitor`를 추가한다.
   - 원천별 성공률
   - 응답시간
   - 최근 실패 원인
   - 인증키/쿼터 상태
2. `EvidenceInvalidationPolicy`를 추가한다.
   - 법령/조례 시행일 변경
   - 지도 레이어 버전 변경
   - PNU/geometry 변경
   - 사용자가 필지 목록 변경
   - 설계 기준 변경
3. stale 전파 대상:
   - siteAnalysis
   - compliance
   - permit
   - designTopN
   - cad/bim
   - feasibility
   - decisionBrief

100% 게이트:

- 원천 변경 또는 필지 변경 후 하류 산출물이 자동 stale 처리된다.
- stale 산출물을 사용자가 확정 산출물로 다운로드할 수 없다.

### 19.5 Plan-P0-9. DB 마이그레이션·롤백·데이터 보존 계획 부족

위험:

- EvidenceLedger, LegalVerdictEnvelope, SourceReadiness 같은 핵심 스키마를 추가하면 기존 프로젝트 데이터 마이그레이션이 필요하다.
- 마이그레이션 실패 시 기존 프로젝트가 깨지거나 오래된 산출물이 새 엔진 기준으로 오해될 수 있다.

보강:

1. DB migration plan을 Phase 0에 포함한다.
2. 기존 프로젝트는 `legacy_unverified` 상태로 마이그레이션한다.
3. 기존 산출물은 새 evidence가 없으면 확정 배지를 제거한다.
4. rollback 시에도 기존 데이터가 손상되지 않도록 additive schema 우선 적용한다.

100% 게이트:

- 마이그레이션 전/후 프로젝트 로드 테스트 통과.
- evidence 없는 legacy 결과는 확정 상태로 표시되지 않는다.

### 19.6 Plan-P1-5. 보안·개인정보·키 관리 게이트 부족

위험:

- 주소, PNU, 소유/거래, 사업성, 설계 데이터는 민감할 수 있다.
- 공공 API 키와 지도 키가 클라이언트에 과도하게 노출되면 운영 리스크가 생긴다.

보강:

1. API 키는 서버 프록시 또는 도메인 제한 공개키 정책으로 분리한다.
2. 프로젝트별 evidence ledger 접근은 tenant/project 권한으로 제한한다.
3. redteam fixture는 실제 주소를 비식별화하거나 공개 샘플만 사용한다.
4. 로그에는 전체 주소/토큰/API 키/개인정보를 남기지 않는다.

100% 게이트:

- 브라우저 번들에 비공개 API 키 포함 0건.
- 로그에 토큰/키/민감주소 원문 출력 0건.

### 19.7 Plan-P1-6. 성능·비용·가용성 기준 부족

위험:

- 공식 원천을 모두 조회하면 분석 시간이 길어지고 API 비용/쿼터를 초과할 수 있다.
- 사용자는 100% 분석이 느려도 진행 상태와 원인을 알아야 한다.

보강:

1. `AnalysisRunBudget`을 둔다.
   - fast path: 필수 원천만, 30~60초
   - deep path: 특수조건 포함, 수분 가능
   - manual path: 자동확인 불가 원천
2. 원천별 캐시는 evidence hash 기반으로 재사용한다.
3. 진행 상태는 "수집/조례/특수조건/반증/산출" 단계로 보여준다.

100% 게이트:

- 장시간 분석 중 빈 화면 금지.
- 쿼터 초과 시 `NEEDS_VERIFICATION`으로 정직 반환.

## 20. Completion Evidence Pack

통합자에게 넘길 때는 말로 "완료"가 아니라 증거 묶음을 제공한다.

필수 파일:

1. `redteam-summary.json`
   - P0/P1 개수, 점수, 실패 시나리오, 검증 명령, 커밋 SHA
2. `traceability-matrix.json`
   - finding -> code -> test -> evidence 연결
3. `source-readiness.json`
   - 공식 원천별 readiness/권한/쿼터/fallback 정책
4. `redteam-fixture-results.json`
   - 30개 이상 특이사례 결과
5. `browser-e2e-report/`
   - 지도 레이어, fullscreen, 필지 선택, 설계 산출 차단 스크린샷
6. `legal-drift-scan.txt`
   - 중복 한도표, fail-open, mock production import 스캔 결과
7. `backend-test-report.txt`
   - pytest collection, 핵심 API 테스트 결과
8. `frontend-test-report.txt`
   - vitest, lint, build, Playwright 결과

100% 게이트:

- Evidence Pack이 없으면 통합자 배포 요청 금지.
- Evidence Pack 내부에 `blocked`, `unknown`, `not_run` P0가 있으면 배포 요청 금지.

## 21. 100% 완성도 점수체계 v3

v2 점수체계를 더 엄격하게 수정한다.

| 영역 | 가중치 | 100% 조건 |
|---|---:|---|
| 검증환경/CI 재현성 | 10 | 로컬·CI·컨테이너 중 2개 이상에서 수집/테스트 성공 |
| 공식원천 readiness | 10 | 모든 1차 원천 ready/limited/manual_only 분류, 권한 확인 |
| 법령/조례 SSOT | 15 | 중복 판정표 제거, statutory-only 차단, 조례 상태 분리 |
| 법규 scope/반증 | 15 | LawScopeInventory 4중 생성, counter-check, critical 누락 0 |
| 특수조건/공간정밀도 | 10 | 산지·농지·경사·임목·도시계획·지구단위 blocking rules |
| 지도 통합/레이어 계약 | 10 | VWorld 기본, visual/queryable/computable 분리, OSM 제품판정 배제 |
| 필지 핸드오프/상태관리 | 8 | 다필지/삭제/sessionStorage 차단/stale 전파 통과 |
| 설계·CAD 산출 차단 | 8 | LegalVerdictEnvelope 없으면 확정 산출 불가 |
| 무목업·fallback 통제 | 6 | production mock/fallback 판정 경로 0건 |
| 보안·운영·Evidence Pack | 8 | 키/로그/권한/관측성/traceability/evidence pack 완비 |

절대 차단 조건:

- P0 1건 이상
- 백엔드 테스트 수집 실패
- fail-open 1건 이상
- 확정 산출물에 evidence ledger 없음
- production 판정 경로 mock/fallback 사용
- 공식 원천 readiness 미분류
- 통합자 Evidence Pack 누락

## 22. 3차 반복검증 시나리오 추가

기존 R1~R20에 다음 시나리오를 추가한다.

| 번호 | 시나리오 | 기대 결과 |
|---|---|---|
| R21 | production build에 `@/mocks/module-data`가 판정 경로로 포함 | 빌드/스캔 실패 |
| R22 | VWorld tile 실패 후 OSM fallback 표시 | 법규/필지 계산에는 미사용, 비권위 표시 |
| R23 | 산지 GIS 면적과 지적공부 면적 불일치 | disputed 또는 requires_official_document |
| R24 | 법령 시행일 변경 후 기존 프로젝트 열람 | 하류 산출 stale |
| R25 | 조례 캐시와 법제처 원문 충돌 | disputed, 확정 산출 차단 |
| R26 | EvidenceLedger 없는 legacy 프로젝트 | legacy_unverified 배지, 확정 다운로드 차단 |
| R27 | API 키 누락/쿼터 초과 | UNKNOWN/NEEDS_VERIFICATION, PASS 금지 |
| R28 | 긴 분석 실행 중 일부 원천 지연 | 단계별 진행상태, timeout 원천만 미확인 처리 |
| R29 | LLM이 공식 원천과 다른 법규 제안 | 후보로만 보관, 공식 ID 없으면 판정 제외 |
| R30 | 다필지 합필 불가 조건 | 사업지 통합안과 필지별 법규 제한 분리 표시 |
| R31 | 지도 레이어는 보이나 WFS geometry 없음 | visual-only 경고, computable 분석 금지 |
| R32 | stale siteAnalysis로 CAD 편집 진입 | 편집은 가능해도 확정 산출/내보내기 차단 |

## 23. 구현 순서 v3

### Gate 0. 증거 기반 작업체계

1. `scripts/redteam-verify.sh` 작성.
2. `CompletionTraceabilityMatrix` 템플릿 작성.
3. `NoMockProductionGate` 스캔 작성.
4. pytest collection 복구.
5. Evidence Pack 출력 위치 고정.

완료 조건:

- 문서, 테스트, 스캔, 산출물 경로가 먼저 존재한다.

### Gate 1. 사용자 오판 가능성 제거

1. fail-open 제거.
2. 미등록 용도지역 PASS 제거.
3. statutory-only 확정 산출 차단.
4. fallback/mock 확정 산출 차단.

완료 조건:

- 틀린 "적합/확정"을 보여주는 경로 0건.

### Gate 2. 진실원천 통합

1. LegalZoneLimitsRegistry 통합.
2. OrdinanceResolution 상태화.
3. SourceReadiness/OfficialDataEnvelope 도입.
4. EvidenceLedger 최소 구현.

완료 조건:

- 모든 산출 수치가 evidence를 가진다.

### Gate 3. 지도 기반 통합 시스템

1. VWorld 기본 지도 고정.
2. 레이어 계약화.
3. 컴퓨터블 레이어만 분석 투입.
4. fullscreen/레이어/필지 선택 E2E.

완료 조건:

- 지도 화면에서 본 데이터와 산출 근거가 일치한다.

### Gate 4. 법규 scope와 특수조건

1. LawScopeAgent 4중 생성.
2. 산지/농지/경사/임목/도시계획/지구단위/문화재/하천/상수원/군사 스캔.
3. CounterEvidenceLoop.
4. redteam fixtures 30+.

완료 조건:

- critical 누락 0건.

### Gate 5. 설계·CAD 확정 산출

1. LegalVerdictEnvelope 기반 설계 산출.
2. 1~3순위 건축물/건축개요 추천.
3. CAD/BIM 도면과 텍스트/음성 명령 통합.
4. 확정/예비/보완안 출력 분리.

완료 조건:

- 미확인 법규가 있으면 확정 설계안이 나오지 않는다.

## 24. 3차 레드팀 결론

v3 보강 후에도 100% 완성은 구현과 검증을 통해서만 달성된다.
다만 이번 보강으로 "좋은 계획"에서 "검증 가능한 실행계획"으로 한 단계 더 잠겼다.

추가로 찾아낸 부족한 부분:

1. P0/P1 해소 추적 매트릭스가 없었다.
2. 목업·fallback 제품 유입 방지 게이트가 부족했다.
3. 공식 공간정보의 법적 효력 등급이 부족했다.
4. 운영 중 원천 변경/stale 전파 계획이 부족했다.
5. DB 마이그레이션·legacy 결과 처리 계획이 부족했다.
6. 보안·키·로그·권한 계획이 부족했다.
7. 성능·쿼터·장시간 분석 UX가 부족했다.
8. 통합자에게 넘길 Evidence Pack 정의가 부족했다.

따라서 다음 실제 구현은 반드시 `Gate 0`부터 시작해야 한다.
Gate 0 없이 기능 구현을 시작하면 테스트 미실행, 목업 혼입, 증거 누락이 반복될 가능성이 높다.
