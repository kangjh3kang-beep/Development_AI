# 81 — 온비드 공고목록 실연동 확정(getPbancList2 · resultType=json)

## 0. 조사
- `app/services/auction/onbid_client.py`: 기존엔 잘못된 베이스(`1611000/nadOpenApi`)+오퍼레이션(`getRealEstAuctnList`)+`type=json`. 라이브 검증으로 전부 틀린 것으로 확인.
- `app/services/auction/auction_service.py`: `AuctionStep1Service` — `_ensure` 멱등 DDL(`auction_items`/`auction_saved_filters`/`auction_watch`), `sync_region`/`_upsert_items`/`search`/`ranking`/`get_item`/`my_listings`/필터 CRUD. raw SQL+text() 패턴. **재사용**.
- `routers/auction.py`: `/search /ranking /my /filters /sync /items/{id}` + 키 해석 `_onbid_service_key()`(`ONBID_SERVICE_KEY` env→settings 폴백). 변경 불필요.
- `win_estimator.py`: 감정가 기반 추정. 감정가 None이면 정직 None 반환(가짜 금지) — 그대로 활용.
- 키는 런타임 env `ONBID_SERVICE_KEY`(루트 .env, NOT_TRACKED). 라우터가 이미 해석.

## 2. 변경 파일
- **재작성** `app/services/auction/onbid_client.py`
- **정합** `app/services/auction/auction_service.py` (`_upsert_items` fail None 보존, `search` price_note·est_win_max None 제외, `ranking` 빈 결과 note)
- **수정** `tests/test_auction_demock_court.py` (`_extract_items` 튜플 반환 반영)
- **신규** `tests/test_auction_onbid_pbanclist.py` (getPbancList2 픽스처 파싱)

## 3. getPbancList2 파라미터 / 날짜기본 / 정규화 / 취소필터
- BASE=`https://apis.data.go.kr/B010003`, OP=`OnbidPbancListSrvc2/getPbancList2`
- 파라미터: `serviceKey, pageNo, numOfRows, resultType=json, cltrTypeCd=0001(부동산), dspsMthodCd=0001(매각), bidDivCd=0001(전자입찰)` + 날짜범위. kind가 apt/officetel이면 `prptDivCd`(0007/0005), region은 `onbidPbancNm` 키워드. 그 외 kind는 정규화 결과 클라필터.
- **기본 날짜범위(datetime.now 실시간)**: 공고일 `pbancYmdStart`=오늘-90일/`End`=오늘, 개찰 `opbdDtStart`=오늘/`End`=+60일, 입찰기간 `bidPrdYmdStart`=오늘/`End`=+60일. (비우면 NO_MANDATORY_REQUEST_PARAMETERS_ERROR 회피)
- **정규화**: item_no=`pbancMngNo-pbctNo`, pbanc_mng_no, kind(prptDivNm→코드), kind_name, address=`onbidPbancNm`, status=`dspsMthodNm`, bid_start=`cltrBidBgngDt`, bid_end=`cltrBidEndDt`, opbd_dt=`cltrOpbdDt`, org=`orgNm`, pbanc_ymd=`pbancYmd`. 날짜 yyyyMMddHHmm/yyyyMMdd 파싱.
- **취소공고 필터**: `pbancKindNm`에 "취소" 포함 → `_normalize`가 None 반환 → fetch_items에서 제외.
- 성공=`data_source="onbid_live"`, 키없음/실패/무자료=빈결과+reason(무목업). resultCode!=00이면 error_reason로 unavailable.

## 4. 상세 메서드(보조)
- `get_pbanc_detail(pbanc_mng_no)` → `OnbidPbancDtlInfSrvc2/getPbancDtlInf2` (필수 pbancMngNo)
- `get_bid_result_detail(cltr_mng_no, pbct_cdtn_no)` → `OnbidCltrBidRsltDtlSrvc2/getCltrBidRsltDtl2`
- 둘 다 `_fetch_single` 경유, 실패/무자료 시 `{"item": None, "data_source":"unavailable", "reason":...}` 정직 반환.

## 5. 미연동 필드 정직처리
- 부동산 **물건목록 엔드포인트 미확정** → `appraisal_price/min_bid_price/fail_count = None`(가짜 금지).
- `_upsert_items`: fail을 `or 0` 제거 → None 영속(court 스크래핑은 실값).
- `search`: onbid 물건에 `price_note`("물건목록 연동 후 제공"). `est_win_max` 필터는 est_win_mid None이면 통과 안 시킴.
- `ranking`: `min_bid_price IS NOT NULL` 조건이라 onbid만 있으면 빈 결과 → `note`(연동 후 채워짐) 안내.
- `win_estimator`: 감정가 None → est_win 범위 None + basis "감정가 부재".

## 6. 단위검증(픽스처, 외부 실호출 0)
- `tests/test_auction_onbid_pbanclist.py` 8건 + `test_auction_demock_court.py` 갱신.
- 검증: 공고관리번호/주소/처분방식/입찰기간/개찰일시/기관/공고일 추출, 취소공고 필터, 단건 dict 방어, resultCode!=00 에러, 무자료, 기본 날짜범위 실시간 생성, 미연동 필드 None, 키없음 unavailable.
- 전체 auction 스위트 **33 passed**. py_compile OK. 앱부팅 OK(auction 라우트 10개).

## 7. 커밋
- (해시는 보고 본문 참조)

## 8. 라이브 검증방법(배포 후)
- 컨테이너에서: `GET /api/v1/auction/sync?source=onbid&rows=20` (write 권한) → `data_source:"onbid_live"`, `saved>0` 기대.
- `GET /api/v1/auction/search?kind=apt&page_size=10` → items[].address(onbidPbancNm), bid_start/bid_end/opbd_dt, status="매각", `price_note` 포함, appraisal_price=null 확인.
- 직접 API: `https://apis.data.go.kr/B010003/OnbidPbancListSrvc2/getPbancList2?serviceKey=$ONBID_SERVICE_KEY&resultType=json&pageNo=1&numOfRows=5&cltrTypeCd=0001&dspsMthodCd=0001&bidDivCd=0001&pbancYmdStart=...&pbancYmdEnd=...&opbdDtStart=...&opbdDtEnd=...&bidPrdYmdStart=...&bidPrdYmdEnd=...` → resultCode "00".
- 취소공고가 결과에서 제외되는지 onbidPbancNm/pbancKindNm 확인.

## 9. 부동산 물건목록 후속 연결지점
- 미확정: 감정가·최저입찰가·유찰횟수·낙찰가율 제공 엔드포인트명(부동산). 동산은 `OnbidMvastListSrvc2/getMvastCltrList2`(부동산 아님 — 사용 금지).
- 연결 시: `onbid_client`에 `fetch_cltr_list`(부동산 물건목록) 추가 → `_normalize`에 감정가/최저입찰가/유찰횟수 채움 → `_upsert_items` 그대로 영속 → ranking/win_estimator 자동 동작. 공고(pbancMngNo)↔물건(cltrMngNo) 조인키 확인 필요.
- `get_bid_result_detail`(cltrMngNo+pbctCdtnNo)로 낙찰가율/낙찰자 보강 가능.
