# 82. 백엔드 — 온비드 순위·물건입찰결과목록·낙찰가능가 엔진 확장 (무목업)

직전 커밋 `395f230`(getPbancList2 공고목록) 위에 이어, 라이브 검증된 신규 엔진
3종(조회수순위·관심순위·물건입찰결과목록)을 실데이터로 연동하고 낙찰가능가 추정을
실데이터(감정가+유찰횟수)에 연결했다. SSH배포·push·프로덕션DB 변경 없음.

## 1. 변경 파일 · 신규 메서드
- `apps/api/app/services/auction/onbid_client.py`
  - 신규 엔드포인트 상수: `ONBID_INQ_RANK_OP`(getInqRnkClg), `ONBID_ITRS_RANK_OP`
    (getItrsCltrRnkClg), `ONBID_BID_RESULT_LIST_OP`(getCltrBidRsltList2),
    `ONBID_BID_INF_OP`(getCltrBidInf2 보조), 코드(`BID_DIV_GENERAL`, `PBCT_STAT_WIN/FAIL`).
  - 신규 파서 헬퍼: `_parse_amount`(금액·"비공개"→None·콤마/통화 제거),
    `_parse_int`, `_parse_rate`(%·실수), `_sido_from_address`(주소 선두 시도 정규화).
  - 신규 메서드 `fetch_ranking(kind="부동산", interest=False)` — getInqRnkClg/
    getItrsCltrRnkClg(`cltrDivNm=부동산`만, 날짜 불필요), 실패/무자료→unavailable.
  - 신규 메서드 `fetch_bid_result_list(filters)` — getCltrBidRsltList2, 지역/용도/
    유찰/감정가/최저입찰가/면적/개찰일/상태 필터→파라미터 매핑, mandatory 충족용
    기본조합(cltrTypeCd=0001+dspsMthodCd=0001+bidDivCd=0001+opbdDt 최근범위).
  - 신규 정규화 `_normalize_ranking`, `_normalize_bid_result`.
- `apps/api/app/services/auction/auction_service.py`
  - 신규 `ranking_live(service_key, by="views"|"interest", limit)` — 실 API 직접 조회+est_win 부착.
  - 신규 `search_bid_results(service_key, filters, page, page_size)` — getCltrBidRsltList2
    조건검색, 무자료 시 getInqRnkClg 전국 폴백(정직 표기)+est_win 부착.
- `apps/api/routers/auction.py`
  - `/auction/ranking` 확장: `by=views`(기본, getInqRnkClg 실데이터)/`interest`/
    `min_bid`/`discount_rate`(캐시). views·interest는 ranking_live로 라우팅.
  - 신규 `/auction/bid-results`: 소재지·용도·유찰횟수·감정가·최저입찰가·면적·개찰일·
    낙찰/유찰상태 필터 → getCltrBidRsltList2.
- `apps/api/tests/test_auction_onbid_ranking.py` (신규, 11 케이스).

## 2. getInqRnkClg 순위 / 정규화
`_normalize_ranking`이 추출: `rank`(sn), `appraisal_price`(apslEvlAmt 실값),
`min_bid_price`(lowstBidPrcIndctCont, "비공개"→None), `usage`(소>중>대 우선),
`kind`(용도명→내부코드), `region_sido`(onbidCltrNm 선두 정규화), `address`,
`status`(pbctStatNm), `discount_rate`(feeRate), `thumbnail`(thnlImgUrlAdr).
item_no=`cltrMngNo-pbctCdtnNo`. 감정가 있으면 est_win 부착.

## 3. getCltrBidRsltList2 조건검색 · 유찰 · 낙찰가율
`_normalize_bid_result`가 추출: `fail_count`(usbdNft), `appraisal_price`(apslEvlAmt),
`min_bid_price`(lowstBidPrc, "비공개"→None), `win_rate`(scsbidRate %), `win_price`
(scsbidAmt), `valid_bidder_count`(vldBidrCnt), `land_area`/`bld_area`, `round_no`,
`status`(pbctStatNm: 낙찰/유찰), `opbd_dt`. 필터→파라미터: lctnSdnm/Sggnm/EmdNm,
cltrUsg{L/M/S}clsCtgrId, prptDivCd, pbctStatCd(0010낙찰/0011유찰), usbdNftStart/End,
apslEvlAmtStart/End, lowstBidPrcStart/End, landSqmsStart/End, bldSqmsStart/End,
opbdDtStart/End, onbidCltrNm, orgNm. 무자료→getInqRnkClg 폴백(engine 표기).

## 4. win_estimator 실데이터
기존 `estimate_win_price`(감정가×종류·지역 낙찰가율×유찰보정(유찰 1회당 -10%))를
순위/입찰결과 정규화 dict에 `_attach_est_win`으로 연결. 감정가 실값(apslEvlAmt)과
유찰횟수(usbdNft) 실데이터로 추정. 최저입찰가 있으면 하한 보정. 감정가 없으면 추정불가.

## 5. 무목업
- 키없음/실패/무자료 → `{"items":[], "data_source":"unavailable", "reason":...}`.
- 최저입찰가 "비공개" → None(가짜 0 금지).
- 순위 응답엔 유찰횟수 없음 → fail_count=None(가짜 금지).
- data_source 정직(onbid_live/unavailable), 폴백 시 engine·note 명시.

## 6. 단위검증 (픽스처·외부 실호출 없음)
`tests/test_auction_onbid_ranking.py` 11 케이스 PASS:
순위 실필드 추출/"비공개"min_bid None/입찰결과 유찰·낙찰가율 파싱/win_estimator
범위·하한보정·감정가부재/금액·정수·실수 파서/키없음 unavailable(ranking·bid-result)/
시도 정규화. 전체 auction 스위트(5파일) 42 passed.

## 7. 커밋 해시
`88d84f4` (main)

## 8. 라이브 검증방법 (배포 후 — 별도 SSH배포 필요)
ONBID_SERVICE_KEY 설정된 백엔드에서:
- `GET /api/v1/auction/ranking?by=views&limit=20` → 조회수순위 실데이터(감정가·할인율·순위·상태·est_win).
- `GET /api/v1/auction/ranking?by=interest` → 관심순위.
- `GET /api/v1/auction/bid-results?pbct_stat=fail&fail_min=1` → 유찰물건(낙찰가율·감정가).
- `GET /api/v1/auction/bid-results?sido=경기&apsl_max=500000000` → 지역·감정가 조건검색.
data_source=onbid_live 여야 함. 무자료면 engine=getInqRnkClg(fallback)+note.

## 9. 미진
- getCltrBidRsltList2 응답 item 필드명(scsbidRate/scsbidAmt/ldaQ 등)은 문서 기반 추정 —
  라이브 응답으로 정확한 키 1회 확정 필요(대안 키도 normalize에서 방어적 fallback).
- /auction/search(기존 캐시 기반)는 그대로 — bid-results를 캐시 upsert에 연결하면
  감정가·유찰·낙찰가율이 auction_items에 영속화되어 min_bid/discount_rate 순위도 채워짐(후속).
- 용도 대/중/소 분류 ID(cltrUsgLclsCtgrId 등) 매핑 테이블 미구축 — 현재 명칭 텍스트만.
