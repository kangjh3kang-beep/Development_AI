# 99. 백엔드 — 대법원 법원경매(courtauction.go.kr) 실연동

작성: 2026-06-07 / 담당: Executor (백엔드)

## 결론
- **접근법 (A) JSON API 채택** — 라이브 실데이터 반환 **확인 완료**(전국 부동산 29,032건).
- 무목업 원칙 준수: 성공 시 `court_scrape`, 차단/무자료/오류 시 가짜 없이 `unavailable` + reason.
- **의존성 변경 0** (httpx 이미 설치). Oracle 배포 추가 작업 불필요.

## 1. 조사한 실엔드포인트 (라이브 확정)

신 courtauction.go.kr은 NELS(2023) WebSquare SPA. 정적 HTML에 물건 테이블 없음 →
**JSON POST 컨트롤러**로 동적 로드. WebSquare UI XML(`/pgj/ui/pgj100/PGJ151F01.xml`,
`PGJ151M01.xml`)의 submission 정의를 추적해 다음을 확정.

| 항목 | 값 |
|------|-----|
| 세션 취득 | `GET https://www.courtauction.go.kr/pgj/index.on` (JSESSIONID/WMONID 쿠키) |
| 검색 컨트롤러 | `POST https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on` |
| 요청 형식 | `application/json` body: `{"dma_pageInfo":{...}, "dma_srchGdsDtlSrchInfo":{...srchInfo}}` |
| 응답 형식 | JSON: `data.dma_pageInfo.totalCnt`(총건수) + `data.dlt_srchResult[]`(물건목록) |

### 요청 payload (부동산 전국/지역)
```json
{
  "dma_pageInfo": {"pageNo":1, "pageSize":40, "totalYn":"Y"},
  "dma_srchGdsDtlSrchInfo": {
    "menuNm":"물건상세검색", "lafjOrderBy":"", "pgmId":"PGJ151F01",
    "mvprpRletDvsCd":"00031R",       // 부동산(동산=00031M)
    "cortAuctnSrchCondCd":"0004601", // 부동산 검색구분(동산=0004604)
    "statNum":1,
    "rprsAdongSdCd":"11"             // (선택) 시/도 2자리: 서울11 경기41 ...
  }
}
```

### ★IP 보안정책(ipcheck) — 필수 헤더
세션쿠키만으로는 부족. 다음 헤더 **세트**가 있어야 통과(누락 시 `{"data":{"ipcheck":false},
"message":"...보안정책에 의하여 차단..."}`):
`X-Requested-With: XMLHttpRequest`, `SubmissionID: sbm_selectGdsDtlSrch`,
`Origin: https://www.courtauction.go.kr`, `Accept: application/json`, `Referer: .../pgj/index.on`.

### 검색구분/구분코드 출처
`PGJ151F01.xml` JS: `0004601`(부동산)/`0004604`(동산), `00031R`(부동산)/`00031M`(동산).
결과 필드(`dlt_srchResult` 컬럼)도 동일 XML에서 확인.

## 2. 라이브 호출 결과 (실데이터 샘플)

`POST searchControllerMain.on`(부동산 전국) → **HTTP 200, `ipcheck:true`,
`totalCnt:29032`**, `dlt_srchResult` 40건. 첫 물건:
```json
{
  "srnSaNo": "2021타경105850",           // 사건번호
  "printSt": "서울특별시 서초구 강남대로97길 49-20 3층304호",  // 소재지
  "gamevalAmt": "12887000000",           // 감정가 128.87억
  "minmaePrice": "4222812000",           // 최저매각가 42.2억
  "yuchalCnt": "5",                      // 유찰 5회
  "maeGiil": "20260618",                 // 매각기일
  "jiwonNm": "서울중앙지방법원",          // 법원
  "dspslUsgNm": "다세대"                 // 용도
}
```
정규화 파서(`parse_search_result`)를 이 실응답에 적용 → 40건 전부 정상 매핑 검증:
`case_no=2021타경105850, court_name=서울중앙지방법원, region_sido=서울특별시,
appraisal_price=12887000000, min_bid_price=4222812000, fail_count=5,
kind=building(다세대), status=open, bid_end=2026-06-18`.

### 라이브 재검증 시 제약 (정직 기록)
조사 단계의 반복 호출로 해당 IP가 **일시 throttle**됨
(`HTTP 400 "사용에 불편을 드려서 죄송합니다. 잠시 후 다시 이용해 주십시오."`).
이는 **코드 결함이 아니라 서버측 rate-limit**이며, 동일 엔드포인트/payload/헤더의
최초 호출(res5)은 위 실데이터를 정상 반환했다. 코드는 throttle 구간에서 가짜 없이
`unavailable` + reason을 정직 반환함을 확인(무목업 준수). 운영(cron, 저빈도·지연)
환경에서는 정상 동작 예상.

## 3. 수정 파일
- `propai-platform/apps/api/app/services/auction/court_scraper.py` (전면 재구현, +257/-158)
  - 기존: BeautifulSoup HTML 추측 셀렉터(실사이트 미검증) + `requests`(pyproject 미설치=실패).
  - 변경: **httpx 동기 클라이언트 기반 JSON 실연동**.
    - `CourtAuctionScraper.fetch_items()`: index.on 세션취득 → searchControllerMain.on
      POST(필수 헤더) → `parse_search_result()` 정규화. 지연·예의·페이지제한 유지.
    - `parse_search_result()`/`_normalize_row()`: 네트워크 분리, 실응답/픽스처 단위테스트 가능.
      `ipcheck:false`→`blocked` 정직 처리.
    - `sido_to_code()`: 시/도 키워드→2자리 행정구역 코드(서울11 …).
  - 반환 스키마는 기존 `auction_service._upsert_items()` 키와 **그대로 호환**
    (source/item_no/kind/region_*/address/appraisal_price/min_bid_price/fail_count/
    status/bid_start/bid_end/raw) → 서비스·라우터 변경 불필요.

## 4. 정합성 / 미변경
- `auction_service.py` **변경 없음**: `_fetch_court()`가 `asyncio.to_thread(scraper.fetch_items, …)`로
  동기 호출하므로 fetch_items를 동기(httpx.Client) 유지. data_source `court_scrape`/`unavailable`
  분기, `_mark_registry(source="court")` 모두 그대로 동작.
- 라우터 `routers/auction.py` 변경 없음.

## 5. 의존성 / Oracle 배포
- **변경 0**. `httpx`는 이미 `pyproject.toml`(>=0.27.0) 및 `requirements.oracle.txt`(==0.27.2,
  Oracle 빌드가 실제 사용하는 파일)에 존재.
- bs4/lxml/requests는 court_scraper에서 제거됨. 코드베이스 전체에서 더 이상 사용처 없음
  (`grep` 확인). `requirements.txt`(Oracle 미사용)의 bs4/lxml 라인은 잔존하나 무해 →
  스코프 최소화 위해 미수정.
- Oracle 재배포 시 추가 pip 설치 불필요. 코드만 반영하면 동작.

## 6. 검증 로그
- `py_compile` court_scraper.py / auction_service.py: PASS.
- 패키지 경로 import 스모크(.venv): `from app.services.auction.court_scraper import …` OK.
- 오프라인 파서 테스트(실응답 res5.json): blocked=False, total=29032, 40건 정상 매핑.
- 라이브 클래스 호출: 코드 정상(throttle 구간에선 unavailable+reason 정직 반환).
- `git diff`: court_scraper.py만 변경, import 보존, auction_service.py 무변경.

## 7. 미진사항 / 후속
- **상세(parse_detail)**: 목록(searchControllerMain)만 연동. 물건 개별 상세(등기·감정평가서·
  현황조사 등)는 별도 컨트롤러(예: `selectGdsDtlInfo` 류) 추가 조사·연동 가능(미구현).
- **지역 필터**: 시/도(rprsAdongSdCd)만 매핑. 시군구/읍면동(rprsAdongSggCd/EmdCd)은
  코드 조회(adong 서비스) 추가 시 정밀 필터 가능.
- **PNU/지오코딩**: 응답에 PNU 직접 없음(주소·법정동코드 `srchHjguDongCd`만). 내토지 매칭은
  주소 텍스트 또는 후속 지오코딩 의존.
- 운영 cron에서 저빈도·충분한 지연으로 호출 권장(IP throttle 회피).
