# 법령엔진 법규검토 시스템 완성도 분석 및 100% 워크플로우 구축안

작성일: 2026-07-01  
범위: 사통팔땅 법령엔진, 법규검토/인허가/설계검토, 필지 기반 법규 목록 생성 에이전트, 특이부지 반복검증 파이프라인

## 1. 결론

현재 법령엔진은 `LegalHub`, 법령 레지스트리, 용도지역 SSOT, 조례 조회, 특이부지 게이트, 법령 변경 모니터링이 구축되어 있어 "정적 숫자표만 있는 초기 엔진"은 아니다.
그러나 사용자가 기대하는 수준, 즉 필지 리스트별로 관련 법령·조례·도시군관리계획·고시·특이조건을 빠짐없이 스캔하고, 반복 반증까지 거쳐 산출물을 내는 법규검토 시스템으로 보면 아직 100%가 아니다.

현 완성도 추정: **64/100**

- 강점: 법령 단일 진실원천, 용도지역 한도 fail-closed, 조례 실효값 경로, 특이부지 감지, 법령 변경 모니터링, 근거 링크 UI의 기반이 있다.
- 핵심 미달: 필지별 "닫힌 법규 목록"을 생성하는 전용 스코프 엔진이 없고, 임야·산지·농지·도시계획시설·지구단위·개발행위허가 같은 특이조건의 공식 데이터 수집/검증이 아직 산발적이다.
- 100%의 정의: 법적 진실 자체를 무한 보장한다는 뜻이 아니라, **공식 원천 조회, 누락 스캔, 반증 루프, 증거 원장, 미확인 항목 차단**이 모두 통과된 상태를 뜻한다.

## 2. 공식 원천 및 사례 조사

### 2.1 법령·조례·고시 원천

| 원천 | 확인 내용 | 사통팔땅 반영 방향 |
|---|---|---|
| 국가법령정보센터 Open API | 법령 본문, 조항호목, 연혁, 자치법규 연계, 위임법령 등 API 제공 | 법률·시행령·시행규칙·행정규칙·별표를 버전/시행일 기준으로 수집 |
| 자치법규/ELIS/법제처 자치법규 | 도시계획조례, 건축조례, 산지전용허가기준 조례 등 지자체별 차이를 확인 | 주소 -> 관할 조례 정본 레벨 -> 조례 본문 -> 조항/별표 파싱 |
| 토지이음 | 토지이용계획, 지역·지구 지정현황, 행위제한내용, 도시계획도, 고시정보 | 필지별 규제 지정 목록과 도시·군관리계획/지구단위/고시를 법규 스코프의 1차 트리거로 사용 |
| VWorld | 국가 공간정보·지도·데이터 API | PNU, 경계, 용도지역/지구, 지적, 공간 레이어의 공통 좌표 기반 |
| 건축데이터/세움터 | 건축물대장, 건축·주택 인허가, 에너지, 유지점검 데이터 | 기존 건축물/노후도/인허가 이력/대지권/용도 변경 리스크 검토 |

### 2.2 산지·임야·경사·입목 원천

| 원천 | 확보해야 할 데이터 | 판정 역할 |
|---|---|---|
| 산림청 산지정보시스템 | 보전산지/준보전산지, 산지구분도, 고시도면, 산지 관련 법령 | 산지전용 가능성, 보전산지 포함 여부, 고시도면 확인 |
| 산림청 산림공간정보서비스 | 임상도, 산림입지토양도, 임도망도, 백두대간보호지역, 산림항공사진 | 입목축적/임상/수관밀도/영급/경급, 경사·표고·토양 예비 스크리닝 |
| 산림청 임상도 공공데이터 | 임종, 임상, 수종, 수관밀도, 영급, 경급 등 | 임목본수도/입목축적 추정의 보조 지표 |
| 산림기본통계 | 관할 시·군·구 ha당 평균 입목축적 등 | 산지전용 허가기준의 비교 기준 |
| 산e랑 | 산지전용허가·협의 절차, 제출서류, 산림조사서, 표고/평균경사도 조사서 | 인허가 준비물과 미확인 차단 게이트 |
| DEM/수치표고 | 표고, 평균경사도, 최대경사도, 레벨 차이, 절성토량 | 예비 설계/리스크 분석. 현재 SRTM 30m는 참고용이므로 공식 DEM/수치지형도 대체 필요 |

중요: 산림청 임상도는 행정·연구 목적의 공간자료이며 산지전용허가 신청용 현장조사서를 대체할 수 없다. 따라서 엔진은 "공공데이터 예비판정"과 "인허가 제출용 확정조사 필요"를 분리해야 한다.

### 2.3 자동 법규검토 기술사례

| 사례 | 핵심 패턴 | 적용점 |
|---|---|---|
| buildingSMART IDS | 요구사항을 사람이 읽고 기계가 해석 가능한 형식으로 정의, IFC 모델 자동검토 | 법규 항목을 `RuleSpec/IDS-like` 스키마로 정형화 |
| Solibri rule-based checking | BIM 모델을 사전정의 규칙/룰셋으로 검증 | 도면/BIM 검증은 LLM이 아니라 결정론 룰셋으로 실행 |
| BIM 기반 자동 법규검토 연구 | rule interpretation -> model preparation -> rule execution -> reporting | 사통팔땅도 법령해석, 필지/모델 준비, 실행, 보고 4단계로 고정 |
| 국내 토지/AI설계 플랫폼 | 주소/필지 -> 법규/규모 -> 사업성/설계안 | 사통팔땅은 여기에 법규 증거 원장과 특이부지 반증 루프를 붙여 차별화 |

## 3. 현재 구현현황 대조

### 이미 있는 기반

- `LegalHub`: 법령 단일 진실원천 파사드.
- `legal_reference_registry`: 법률/조문/조례/고시 링크 레지스트리.
- `LegalDiscoveryService`: LLM 관련 법령 탐색 후 정본 레지스트리 교차검증.
- `OrdinanceService`: 관할 도시계획조례 실시간 조회 -> 캐시 -> 법정상한 폴백.
- `legal_zone_limits` / `zone_limit_contract`: 용도지역 한도 SSOT 및 fail-closed 계약.
- `RegulationAnalysisService`: 필지/다필지 기반 규제 분석과 근거/evidence 구성.
- `DESIGN_LAW_MAP`: 설계/토지/주차/환경/분양/세금 도메인별 법령 키 매핑.
- `special_parcel`: 학교용지, 도로, 농지, 임야, GB, 문화재 등 특이부지 게이트.
- `RegulationMonitorService`: 60개 법령 변경 모니터링 목록.
- `terrain_service`: 경사도/표고/토공량 예비 분석. 단, 현재 OpenTopoData SRTM 30m 참고용.

### 근본 미달

| 구분 | 현재 상태 | 문제 |
|---|---|---|
| 필지별 법규 목록 생성 | LLM 최대 15개 탐색 + 정적 도메인 매핑 | 특이부지, 도시계획시설, 지구단위, 산지/농지/환경/교육/문화재 누락 가능 |
| 조례 파싱 | 도시계획조례 중심, 일부 정규식/캐시 의존 | 별표, 예외, 용도별·지역별·인구감소지역 완화, 건축조례까지 완결 불가 |
| 산지/임야 | 특이부지 게이트 텍스트 경고 중심 | 입목축적, 평균경사도, 표고, 산지구분, 임도, 보전산지 포함 여부 수치화 부족 |
| DEM/경사 | SRTM 30m 참고용 | 인허가 판단용 정밀도 부족, 공식 수치지형도/지자체 기준 연결 필요 |
| Rule DSL | 일부 RASE 규칙 존재 | 법령별 조건/예외/위임/별표를 표현하는 공용 스키마 부족 |
| 반증 루프 | 없음 또는 약함 | "이 결론을 뒤집을 수 있는 법규"를 재검색하는 적대적 검증이 없음 |
| 증거 원장 | 일부 evidence 있음 | 법령명, 조문, 시행일, 수집일, 원문 hash, 적용/비적용 사유가 일관 저장되지 않음 |

## 4. 목표 아키텍처

핵심은 `LawScopeInventory`를 새 중심축으로 두는 것이다.

```
필지 리스트/PNU
  -> 공식 공부/공간/산림/도시계획 데이터 수집
  -> 법규검토 에이전트가 "확보·확인할 법규 목록" 생성
  -> 공식 원천 수집기에서 원문/조례/고시/별표 확보
  -> Rule DSL/IDS-like 스키마로 정규화
  -> 결정론 검토 실행
  -> LLM 해석/요약
  -> 적대적 누락검증
  -> 미확인 critical=0일 때만 산출물 확정
```

### 4.1 새 데이터 계약

`LawScopeInventory`

- `parcel_basis`: PNU, 주소, 면적, 지목, 소유/공부 기준, 다필지 그룹.
- `spatial_facts`: 용도지역/지구/구역, 도시계획시설, 지구단위, 접도, 도로폭, 고저차, 경사도, 표고.
- `forest_facts`: 산지구분, 보전산지 포함, 임상도 속성, 입목축적 추정, 관할 평균 입목축적, 평균경사도, 표고비율, 임도/대체임도.
- `required_law_items`: 확인해야 할 법령·조례·고시·계획 문서 목록.
- `evidence_items`: 공식 원문/URL/시행일/수집일/hash/조항/별표.
- `rule_specs`: 기계검토용 조건식.
- `missing_facts`: 미확보 데이터와 그 영향.
- `adversarial_findings`: 결론을 뒤집을 수 있는 반례 후보.
- `gate_status`: `PASS | CONDITIONAL | BLOCKED | NEEDS_OFFICIAL_SURVEY`.

## 5. 법규검토 에이전트 구축안

### 5.1 법규 목록 생성 프롬프트

목적: 해당 필지 리스트에서 검토해야 할 법규·조례·고시·계획문서를 빠짐없이 확보하기 위한 스코프 목록을 만든다.

```text
당신은 대한민국 개발사업 법규검토 에이전트입니다.
주어진 필지 리스트와 공식 공부/공간정보를 기준으로, 검토해야 할 법령·시행령·시행규칙·조례·행정규칙·고시·도시군관리계획·지구단위계획·인허가 제출서류를 빠짐없이 식별하세요.

원칙:
1. 공식 원천으로 확인 가능한 항목만 verified 후보로 둡니다.
2. 수치나 조문을 모르면 생성하지 말고 missing_facts에 넣습니다.
3. 용도지역 일반규정만 보지 말고 특이조건을 반드시 스캔합니다.
4. 산지/임야는 보전산지, 준보전산지, 입목축적, 임목본수도/수관밀도, 평균경사도, 표고, 임도, 대체산림자원조성비, 산지전용허가 조례를 별도 스캔합니다.
5. 도시계획시설, 지구단위계획, 개발행위허가, 환경/재해/문화재/교육환경/군사/하천/도로/철도/공항/상수원 규제를 누락하지 않습니다.
6. 최종 결론을 내지 말고 "확보해야 할 법규 목록"과 "왜 필요한지"만 반환합니다.

출력 JSON:
{
  "required_law_items": [
    {
      "category": "법률|시행령|시행규칙|조례|행정규칙|고시|도시군관리계획|지구단위계획|제출서류",
      "name": "정식 명칭",
      "article_or_section": "조문/별표/고시번호/계획명 또는 null",
      "trigger": "이 필지에서 이 법규가 필요한 이유",
      "official_source": "law.go.kr|eum.go.kr|elis.go.kr|forest.go.kr|fcis.forest.go.kr|vworld.kr|open.eais.go.kr|other_official",
      "priority": "critical|high|normal",
      "verification_query": "공식 원천 조회 키워드",
      "expected_facts": ["확보할 수치/문서"],
      "status": "needs_fetch"
    }
  ],
  "special_case_scan": [
    {"case": "산지/임야", "needed": true, "why": "..."},
    {"case": "도시계획시설", "needed": false, "why": "..."}
  ],
  "missing_facts": [
    {"fact": "평균경사도 조사서", "impact": "산지전용 가능성 확정 불가", "required_for_gate": true}
  ]
}
```

### 5.2 반증 프롬프트

```text
아래 법규검토 결론을 무효화하거나 보류시킬 수 있는 누락 법령·조례·고시·도시계획·특이조건을 찾아라.
결론을 지지하는 법규를 반복하지 말고, 반대근거/예외/위임조례/별표/공고/현장조사 필요 항목만 반환한다.
critical 누락 가능성이 있으면 PASS를 금지하고 NEEDS_VERIFICATION으로 표시한다.
```

## 6. 세밀 조건분석 필수 체크리스트

### 6.1 모든 필지 공통

- PNU/주소/지목/면적/합필 가능성/다필지 접합성.
- 용도지역, 용도지구, 용도구역.
- 도시계획시설 결정 여부: 도로, 학교, 공원, 녹지, 철도, 하천, 공공청사 등.
- 지구단위계획구역, 특별계획구역, 개발행위허가 제한지역.
- 도로 접면, 도로폭, 건축선, 도로법 접도구역.
- 일조, 높이, 사선, 대지안 공지, 주차, 피난, 소방, BF.
- 문화재/매장유산/역사문화환경.
- 환경영향/소규모환경영향/재해영향/교통영향.
- 교육환경보호구역, 군사시설보호구역, 공항/철도/하천/상수원 규제.

### 6.2 산지·임야·녹지 필수

- 산지 여부, 산지구분: 보전산지/준보전산지, 임업용/공익용.
- 산지전용허가/협의/신고 대상 여부.
- 지자체 산지전용허가기준 조례 적용 여부.
- 평균경사도, 25도/30도/지자체 기준 및 면적분포.
- 표고비율, 해발고, 산자락하단부 대비 위치.
- 입목축적: 대상지 ha당 입목축적 vs 관할 시·군·구 평균 입목축적.
- 임목본수도/수관밀도/영급/경급/수종: 산림조사 보조 지표.
- 660㎡ 미만 예외, 분할회피 의심, 2만㎡ 이상 집단화 보전산지 기준.
- 임도 단절, 대체임도, 산사태위험, 백두대간/보호구역.
- 대체산림자원조성비, 복구비, 재해방지·복구계획.
- 산림조사서, 표고조사서, 평균경사도조사서의 제출 필요 여부와 작성 자격.

## 7. 100% 게이트 정의

법규검토 완료로 인정하려면 아래가 모두 통과되어야 한다.

1. 필지별 PNU/면적/지목/용도지역/지구/구역 식별률 100%.
2. `required_law_items` critical 항목 공식 원천 fetch 성공률 100%.
3. critical 조례/고시/도시군관리계획 미확인 0건.
4. 특이부지 스캔 미확인 0건. 단, 공공데이터로 확정 불가한 항목은 `NEEDS_OFFICIAL_SURVEY`로 차단.
5. 법령·조례·별표·고시 원문에 시행일, 수집일, hash, URL 저장.
6. Rule DSL로 변환된 항목은 결정론 검토 통과.
7. LLM 산출 숫자 0건. LLM은 목록 생성, 해석, 누락 탐지에만 사용.
8. 적대적 반증 루프에서 신규 critical 누락 0건.
9. 같은 필지 재분석 시 동일 입력/동일 원천 버전이면 동일 결과.
10. UI에서 `확정`, `예비`, `공식조사 필요`, `불가/조건부`가 분리 표시.

## 8. 구현 단계

### Phase 1. 법규 스코프 인벤토리

- `legal_scope_inventory` 서비스와 DB 테이블 추가.
- `/api/v1/legal/scope-inventory` 엔드포인트 추가.
- 기존 `LegalDiscoveryService`는 최대 15개 요약 탐색으로 유지하지 말고, 새 스코프 인벤토리의 보조 모듈로 강등.
- `ALRISService`의 하드코딩 문서/40개 표현은 폐기 또는 LegalHub 경유로 재배선.

### Phase 2. 공식 원천 수집기

- 법제처: 법률/시행령/시행규칙/행정규칙/별표/연혁.
- 자치법규: 도시계획조례, 건축조례, 산지전용허가기준 조례.
- 토지이음: 토지이용계획, 행위제한, 도시계획도, 고시정보.
- VWorld: PNU/경계/공간레이어.
- 산림청: 산지구분도, 임상도, 산림입지토양도, 산림기본통계.
- 세움터/건축데이터: 건축물대장, 인허가 이력, 기존건축물 조건.

### Phase 3. 산지·경사·입목 심층 엔진

- 현재 SRTM 30m 지형분석은 "참고용"으로 유지.
- 공식 수치지형도/DEM 또는 지자체 제출기준 기반 평균경사도 계산 모듈을 별도 추가.
- 임상도/산림기본통계로 입목축적 예비값 산정.
- 산지전용 제출용 조사서가 필요한 경우 확정 PASS 금지.

### Phase 4. Rule DSL / IDS-like 규칙화

- 법령 조항을 `Applicability`, `Requirement`, `Selection`, `Exception`, `Evidence`로 분해.
- BIM/도면 검토 항목은 buildingSMART IDS 개념처럼 기계검토 가능한 요구사항으로 저장.
- 모든 규칙은 출처 조문/별표와 연결.

### Phase 5. 적대적 누락검증

- `law_scope_agent` 결과를 `counter_law_agent`가 반증.
- "이 결론을 뒤집는 조례/고시/특이조건은?" 질문을 최소 2회 반복.
- 신규 critical 발견 시 원래 결론을 무효화하고 스코프 인벤토리 재실행.

### Phase 6. UI/보고서

- 필지별 법규 추적표: 적용, 비적용, 미확인, 공식조사 필요.
- 산지/임야는 입목·경사·표고·산지구분 패널을 별도 표시.
- 결과는 "사업 가능" 단정 대신 `가능`, `조건부`, `공식조사 필요`, `불가`, `도시계획변경 선행`으로 표시.

## 9. 즉시 보강 우선순위

1. `LawScopeInventory` 서비스/스키마 추가.
2. 임야/산지 스코프 항목을 critical로 승격.
3. `terrain_service`의 SRTM 결과가 법규판정 확정값으로 쓰이지 않도록 게이트 추가.
4. 산림청 임상도/산지구분도/산림기본통계 수집기 설계.
5. 조례 파서 개선: 별표/표/예외/인구감소지역 완화/산지전용허가기준 조례 파싱.
6. ALRIS 하드코딩 RAG 제거 또는 격리.
7. 법규검토 에이전트 프롬프트와 반증 프롬프트를 테스트 픽스처화.
8. 100% 게이트 테스트: 자연녹지, 계획관리, 임야, 학교용지, 도로, GB, 문화재, 지구단위, 다필지 혼합용도.

## 10. 참고 원천

- 국가법령정보센터 Open API: https://open.law.go.kr/LSO/openApi/guideList.do
- 법제처 국가법령정보 공유서비스: https://www.data.go.kr/data/15000115/openapi.do
- 토지이음 토지이용계획 열람: https://www.eum.go.kr/web/ar/lu/luLandDet.jsp
- 토지이음 서비스안내: https://www.eum.go.kr/web/lc/bi/biServiceIntro.jsp
- 토지이음 데이터개방 목록: https://www.eum.go.kr/web/op/sv/svItemList.jsp
- VWorld: https://www.vworld.kr/
- VWorld 데이터 API 안내: https://www.vworld.kr/dtna/dtna_guide_s001.do
- 세움터: https://www.eais.go.kr/
- 건축데이터 민간개방 안내: https://www.data.go.kr/bbs/ntc/selectNotice.do?originId=NOTICE_0000000003704
- 산림청 산지정보조회: https://www.forest.go.kr/newkfsweb/html/HtmlPage.do?mn=KFS_02_05_01_02&orgId=fli&pg=%2Ffli%2FUI_KFS_7006_010100.html
- 산지정보시스템: https://www.forest.go.kr/newkfsweb/kfs/idx/SubIndex.do?mn=KFS_03_08_02&orgId=fli
- 산e랑 산지전용통합정보시스템: https://fcis.forest.go.kr/
- 산림공간정보서비스: https://map.forest.go.kr/
- 산림청 산지구분도: https://www.forest.go.kr/newkfsweb/html/HtmlPage.do?mn=KFS_02_04_03_04_03&orgId=fgis&pg=%2Ffgis%2FUI_KFS_5002_020300.html
- 산림청 임상도: https://www.forest.go.kr/newkfsweb/html/HtmlPage.do?mn=KFS_02_04_03_04_01&orgId=fgis&pg=%2Ffgis%2FUI_KFS_5002_020100.html
- 산림청 공공데이터 개방목록: https://www.forest.go.kr/kfsweb/opda/dataMng/selectPblicDataList.do?mn=NKFS_06_08_02&tabs=1
- 산림청 임상도 공공데이터: https://www.data.go.kr/data/15093362/fileData.do
- 산림기본통계: https://www.data.go.kr/data/15067764/fileData.do
- 산지전용허가기준 세부 검토기준: https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2000000011143
- 산지관리법 시행령 별표4: https://law.go.kr/LSW/lsLawLinkInfo.do?lsJoLnkSeq=1001104030
- 산지전용허가 절차 가이드: https://fcis.forest.go.kr/portal/cnprm-porcs/001002/dtl
- buildingSMART IDS: https://www.buildingsmart.org/standards/bsi-standards/information-delivery-specification-ids/
- Solibri Rule-based Checking: https://help.solibri.com/hc/en-us/articles/1500005009042-Understanding-Checking
- Eastman et al., Automatic rule-based checking of building designs: https://yonsei.elsevierpure.com/en/publications/automatic-rule-based-checking-of-building-designs/
- BIM automated code compliance checking review: https://ieeexplore.ieee.org/document/8002486/
