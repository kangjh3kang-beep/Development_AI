# 79. 인근 토지 실거래 오분류 교정 (land 버킷이 아파트 API 호출 버그)

## 1. 조사
- `MOLITService.get_apt_transactions` → `MolitClient.get_transactions(prop_type="apt")` → operation `getRTMSDataSvcAptTradeDev`, 경로 `/1613000/RTMSDataSvcAptTradeDev/...`, `_type=json`, 영문필드 정규화(`_parse_trade_items`).
- `MolitClient`는 이미 `land` 매핑 보유: `_TRADE_ENDPOINTS["land"] = "getRTMSDataSvcLandTrade"` → 토지 매매 신고 자료, 별개 오퍼레이션/경로.
- `_parse_trade_items`는 토지 거래면적(`dealArea`/`plottageAr`)까지 area 폴백 처리 중. 단, MOLITService에 **land 진입점(get_land_transactions) 부재**가 근본 원인.
- 버그 위치: `land_info_service.py` `_fetch_nearby_transactions` — apt·land 두 라벨 모두 `get_apt_transactions` 호출 → land 버킷에 아파트 거래 복제.

## 2. 변경 파일
- `app/services/external_api/molit_service.py`: `get_land_transactions(region_code, year_month)` 신규 — `_client.get_transactions(..., prop_type="land")` 호출. 키미승인/무자료/오류 시 빈 list(아파트 대체 금지).
- `integrations/molit_client.py`: `_parse_trade_items`에 토지 전용 필드 `jimok`(지목)·`land_use`(용도지역) 추가(영문 `jimok`/`landUse` 우선·한글 폴백, 없으면 빈값).
- `app/services/land_intelligence/land_info_service.py`: `_fetch_nearby_transactions` 재작성 — label별 fetcher 매핑 dict, 예외 정직 로깅, `data_source`(molit_apt_live/molit_land_live/unavailable) 표기, 토지 item에 jimok/land_use·표시명(지목) 추가.

## 3. label별 올바른 매핑
- `apt`  → `MOLITService.get_apt_transactions`  → `getRTMSDataSvcAptTradeDev`
- `land` → `MOLITService.get_land_transactions` → `getRTMSDataSvcLandTrade`
- 엔드포인트 distinct 검증 PASS (apt path ≠ land path).

## 4. 무목업(키미승인 빈값)
- land 조회가 예외(403 키미승인 포함)/무자료면 `count=0`, `items=[]`, `data_source="unavailable"`, `avg=0`. 아파트 데이터로 복제하지 않음(검증 PASS).
- 성공 시 `data_source="molit_land_live"`.

## 5. 단위검증(호출분기·무복제) — 모킹, 외부 실호출 없음
- apt 3회/land 3회 각각 올바른 메서드 호출.
- land avg(30000) ≠ apt avg(50000): 복제 없음.
- land 예외 시 빈값·unavailable, avg=0(아파트 미복제).
- MOLITService.get_land_transactions가 `prop_type="land"`로 라우팅.
- py_compile OK, app import OK.

## 6. 커밋
- (아래 본문 참조)

## 7. 토지 API 키 활용신청 안내
- 메모리상 MOLIT 키는 AptTradeDev만 승인. 토지 매매(getRTMSDataSvcLandTrade)는 별도 활용신청 필요 가능성.
- 미승인 시 라이브에서 land = `data_source:"unavailable"`로 정직 표기됨(가짜·아파트복제 없음). 공공데이터포털 1613000 서비스에서 "국토교통부_토지 매매 신고 자료" 활용신청 승인 후 자동으로 molit_land_live 전환.

## 8. 미진
- 토지 API 라이브 응답 실필드명(jimok/landUse) 확정은 키 승인 후 실호출로 최종 검증 필요(현재는 영문 우선·한글 폴백 방어).
- nearby_transactions는 apt/land 범위만 사용 → officetel/villa/commercial은 영향 없음(범위 그대로).
