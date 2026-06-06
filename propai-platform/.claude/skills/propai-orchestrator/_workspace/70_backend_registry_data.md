# 70. 백엔드 — 부지분석 대장(臺帳) 데이터 강화 (건축물대장 표제부·멸실·미준공·분묘 정직표기)

## 1. 조사 (건축HUB 오퍼레이션·필드)
- 엔드포인트: `http://apis.data.go.kr/1613000/BldRgstHubService/` (키: `MOLIT_API_KEY`, config.py:37)
- `getBrBasisOulnInfo` (총괄표제부): 면적·건폐율(bcRat)·용적률(vlRat)·층수 권위 소스. 이미 `get_building_info`/`get_building_by_pnu` 연결됨. 사용승인일(useAprDay)은 공란 빈번.
- `getBrTitleInfo` (표제부): 세대수(hhldCnt)·가구수(fmlyCnt)·호수(hoCnt)·동수(item 개수)·사용승인일(useAprDay)·주용도(mainPurpsCdNm)·구조(strctCdNm)가 충실. `get_title_by_pnu` 구현돼 있었으나 land_info_service에서 미호출 → 이번에 배선.
- 멸실 전용 무료 오퍼레이션 부재 → 표제부 상태텍스트(regstrKindCdNm/regstrGbCdNm/bldNm/etcPurps)의 '멸실' 포함 여부로 best-effort 추정(확인필요).
- 미준공 전용 오퍼레이션 키/스펙 불명확 → 표제부 사용승인일(useAprDay) 부재 = 미준공(공사중) 추정(확인필요).
- 분묘대장: 전국 단위 무료 공공API 부재 사실 확인 → 정직 표기(가짜 생성 금지).

## 2. 신규/변경 파일·함수
- `app/services/external_api/building_registry_service.py`
  - `get_title_by_pnu` 리팩토링 → 파싱을 순수함수 `_parse_title_items(items)`로 분리(단위테스트 가능, 외부호출 없음). 멸실/미준공 best-effort 필드 추가.
- `app/services/land_intelligence/land_info_service.py`
  - `_fetch_building_detail`: 총괄표제부 + 표제부 병합. 세대수·가구수·호수·동수, 멸실/미준공 필드를 building_detail에 추가. 표제부 우선(세대·동·호·사용승인일).
  - 결과 페이로드에 `grave_registry`(available:false 정직표기) 추가.
- `app/services/data_validation/public_data_registry.py`
  - `("molit_building_register", "api", "daily")` 신선도 소스 등록.

## 3. 표제부 배선·멸실·미준공·분묘
- 표제부 배선: get_title_by_pnu 호출 → household_count/family_count/ho_count/dong_count + 사용승인일/주용도/구조를 총괄표제부 위에 우선 병합. 표제부 무자료 시 총괄표제부 값 유지, `title_status: "표제부 미조회"`.
- 멸실: 표제부 상태텍스트 '멸실' 감지 → `is_demolished/demolition_date/demolition_basis`. 전용 필드 없어 best-effort "추정·확인필요" 명시.
- 미준공: 사용승인일 부재(멸실 아님) → `is_uncompleted/uncompleted_basis`="사용승인일 부재 → 미준공(공사중) 추정·확인필요".
- 분묘: `grave_registry:{available:false, reason:"전국 단위 무료 공공API 미제공", suggestion:"현장조사·항공/위성 판독(디지털트윈 항공레이어) 또는 지자체 개별 확인 권장", data_source:"unavailable"}`. 디지털트윈 항공 연계는 TODO 주석.

## 4. 무목업 보장
- 키 미설정/PNU<19/호출실패/무자료 → None 또는 빈값+사유. 가짜 세대수·멸실·분묘 절대 생성 안 함.
- `data_source: molit_live | unavailable` 표기. 멸실/미준공은 best-effort "추정·확인필요" 라벨.
- 키 강제 비움 검증: get_title_by_pnu → None (실호출 없이 가드).

## 5. 단위검증 (외부 실호출 금지)
- `_parse_title_items` 5케이스 PASS: 정상 단일동, 다동(최대연면적 동 선택+dong_count), 미준공(사용승인일 공란), 멸실(상태텍스트), 무자료→None.
- py_compile 3파일 OK. 앱부팅 OK(735 라우트). registry molit_building_register 등록 OK. 키없음 가드 OK.

## 6. 커밋
- (아래 커밋 단계에서 기재)

## 7. 프론트 표시 계약 (building_detail 신규필드 + grave_registry)
building_detail 추가 필드:
- `household_count` (int), `household_count_display` ("120세대" | "정보 미등록")
- `family_count` (int)
- `ho_count` (int), `ho_count_display` ("120호" | "정보 미등록")
- `dong_count` (int), `dong_count_display` ("3개동" | "정보 미등록")
- `title_status` ("정상" | "표제부 미조회")
- `is_demolished` (bool), `demolition_date` (str YYYYMMDD|""), `demolition_basis` (str)
- `is_uncompleted` (bool), `uncompleted_basis` (str)
- `data_source` ("molit_live" | "unavailable")

result.grave_registry:
- `{available:bool, reason:str, suggestion:str, data_source:str}` — available=false 시 "데이터 없음(사유)" UI 권장.

## 8. 미진 / 한계
- 멸실: 건축HUB 표제부에 멸실 전용 불리언/멸실일 필드가 없어 텍스트 기반 추정. 정확 멸실대장은 별도(지자체/세움터) 필요.
- 미준공: 착공신고 전용 API 미연동. 사용승인일 부재 기반 추정만(공란 사유가 데이터 누락일 수도 있어 "확인필요").
- 분묘: 무료 전국 API 부재 → 디지털트윈 항공레이어 판독 연계가 후속 과제(TODO 주석).
- 키 신청: MOLIT_API_KEY(data.go.kr 건축HUB BldRgstHubService) 활용신청 필요. 미승인 시 unavailable.
