# 88 — 경매 3버그 백엔드 수정(무목업)

루트: `propai-platform/apps/api`. SSH배포·push·프로덕션DB 변경 없음. 로컬 검증 + 로컬 commit.

## 1. 변경 파일
- `app/services/auction/auction_service.py` — `_attach_est_win` 숫자화, search 필터 수정, `detail_live` 신규.
- `app/services/auction/onbid_client.py` — `get_cltr_bid_info`(getCltrBidInf2) + `_normalize_bid_info` 신규, `_fetch_single` 에 `raw_items` 추가.
- `routers/auction.py` — `GET /api/v1/auction/detail` 신규, `/monitor`·`/monitor/run` try-except graceful.
- `tests/test_auction_detail_fix.py` — 신규 단위테스트(est_win 숫자화·getCltrBidInf2 파싱·키없음 unavailable).

## 2. est_win 숫자화 (NaN 수정)
- 기존: `d["est_win"]` = win_estimator 반환 **객체**(`{est_win_low,est_win_mid,est_win_high,...}`) → 프론트 숫자 기대 → NaN.
- 수정: `_attach_est_win` 에서
  - `d["est_win"] = est["est_win_mid"]` (숫자[원] | None)
  - `d["est_win_low"] = est["est_win_low"]`, `d["est_win_high"] = est["est_win_high"]`
  - `d["est_win_detail"] = est` (신뢰도·가정·낙찰가율 원본 보존)
- search 의 `est_win_max` 필터를 `e["est_win"]`(숫자) 기준으로 일관 수정.
- ranking/ranking_live/search/monitor/monitor_run/get_item/search_bid_results 전부 `_attach_est_win` 단일 경유 → 일관.

## 3. /auction/detail (getCltrBidInf2)
- 라우트: `GET /api/v1/auction/detail?cltr_mng_no=&pbct_cdtn_no=` (둘 다 필수).
- onbid_client `get_cltr_bid_info(cltr_mng_no, pbct_cdtn_no)`:
  - `B010003/OnbidCltrBidDtlSrvc2/getCltrBidInf2`, `resultType=json`, 필수 cltrMngNo+pbctCdtnNo.
  - 응답 N행(회차별) → `_normalize_bid_info` 로 집계.
- 정규화 필드(`item`): `cltr_mng_no, pbct_cdtn_no, source, kind, kind_name, region_sido,`
  `fail_count`(usbdNcumNft/usbdNft 누적 **최대**), `land_area`(ldaQ/landSqms),
  `bld_area`(bldSqms), `appraisal_price`, `min_bid_price`, `win_rate`, `win_price`,
  `image_url`(cltrImgUrlAdr/thnlImgUrlAdr…), `usage`, `address`, `restriction`,
  `status`, `round_count`, `prev_bids[]`(round_no/min_bid_price/opbd_dt/status/win_price/win_rate),
  `raw`, + `est_win`/`est_win_low`/`est_win_high`/`est_win_detail`.
- 병합: getCltrBidInf2 성공 시 `getCltrBidRsltDtl2` 로 win_rate/win_price 빈값만 보강(실패 무시).
  getCltrBidInf2 무자료 시 getCltrBidRsltDtl2 단독 폴백.
- 이미지: `image_url` 키 후보에서 채워진 첫 값, **없으면 null**(가짜 금지).

## 4. monitor graceful (503 → 200)
- `/auction/monitor`·`/auction/monitor/run` 라우터를 try-except 로 감싸 예외 시 **200 + 빈결과 + note**.
  - monitor: `{group_by:"source", groups:{}, total_matched:0, targets:0, data_source:"unavailable", note:"관심대상을 등록하면…"}`
  - monitor/run: `{status:"ok", synced:0, data_source:"unavailable", total_matched:0, new_matches:0, groups_count:{}, note:…}`
- 관심대상 미등록(targets=0)은 기존 서비스가 이미 200+note 반환 → 일관. 절대 5xx 안 남.
- 라이브 검증: BoomService(예외 강제) 주입 시 두 엔드포인트 모두 200+note 확인.

## 5. 무목업
- 키 미설정/무자료/비공개/이미지없음 → null + reason/note. 가짜데이터 0.

## 6. 단위검증 (외부 실호출 0, 픽스처/직접호출만)
- `tests/test_auction_detail_fix.py`: est_win 숫자화(int·dict아님)·감정가없음 None·
  getCltrBidInf2 파싱(유찰누적 max2·면적84.93/59.82·이미지·kind=apt·서울·prev_bids2)·
  이미지없음 None·키없음/파라미터누락 unavailable.
- 전체 auction 스위트 **59 passed**. py_compile OK. 앱부팅 OK(/detail 라우트 등록 확인).

## 7. 커밋
- (해시는 보고 본문 참조)

## 8. 프론트 계약
- `est_win`: **숫자(원) | null** (중앙값). 범위는 `est_win_low`/`est_win_high`(숫자|null). 메타는 `est_win_detail`(신뢰도·가정·낙찰가율).
- `GET /api/v1/auction/detail?cltr_mng_no=&pbct_cdtn_no=` → `{item:{…정규화…}|null, data_source:"onbid_live"|"unavailable", reason?}`.
  순위 목록 아이템의 `cltr_mng_no`+`pbct_cdtn_no` 로 호출.
- `/auction/monitor`·`/monitor/run`: 항상 200. `groups:{}`+`note` 시 안내 표시.

## 9. 미진/주의
- getCltrBidInf2 실제 필드명(usbdNcumNft/cltrImgUrlAdr/rstrLmtCmptCont 등)은 방어적 매핑.
  실응답에서 다른 태그명이면 `_normalize_bid_info` 후보키 추가 필요(라이브 1회 확인 권장).
- 이미지 가용성은 온비드 응답 의존(없으면 null 정직).
- auction_service.py 의 기존 `row[0]`/`Result.rowcount` 린터경고는 본 작업 이전 코드(무관).
