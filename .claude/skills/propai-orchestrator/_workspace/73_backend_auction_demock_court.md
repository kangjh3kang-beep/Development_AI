# 73 — 경공매 1단계 무목업 전환 + 온비드 실연동 + 대법원 경매 스크래퍼

기준 커밋: `ae100cb` (경공매 1단계). 본 작업: 목업 제거(무목업) + 온비드 실연동 전용 + 법원경매 스크래퍼(지연·예의) 추가.
범위: 백엔드만. SSH배포·push·프로덕션DB 변경 없음. 구현+로컬검증+commit.

## 1. 조사 — ae100cb mock 위치 / 의존성

ae100cb 산출물:
- `app/services/auction/onbid_client.py` — ★mock 폴백 집중부.
  - `_mock_items()` (216~254행): `random` 기반 구조화 더미 30건 생성.
  - `fetch_items()` 키 없음(123) / 호출 실패(150~152) 시 `_mock_items` 호출, `data_source="mock"`.
- `app/services/auction/auction_service.py` — `data_source` 기본값 `"mock"` 다수(114/190/298행), `_mark_registry` 에러문구 "mock 폴백".
- `app/tasks/auction_sync_task.py` — 전국 시/도 배치, `data_source="mock"` 기본.
- `routers/auction.py` — `/sync` 등 docstring "키 없으면 mock".
- `win_estimator.py` — 순수 추정(mock 무관, 유지).

의존성: `httpx==0.27.2`(설치됨), `requests 2.33.1`(transitive 설치됨). **BeautifulSoup/lxml 미설치**(grep·import 확인). 기존 BeautifulSoup 사용처 없음.

## 2. 변경/신규 파일

| 파일 | 변경 |
|------|------|
| `app/services/auction/onbid_client.py` | ★재작성 — mock 전면 제거, 차세대 온비드 OpenAPI 실호출 전용, `_unavailable()` 도입 |
| `app/services/auction/court_scraper.py` | ★신규 — 법원경매 스크래퍼(requests+BS4, 지연·예의, 파서 분리) |
| `app/services/auction/auction_service.py` | `sync_region(source=...)` 분기, `_fetch_court()` 추가, `data_source` 기본값 `"mock"`→`"unavailable"`, `_mark_registry(source,reason)` 확장 |
| `app/tasks/auction_sync_task.py` | 온비드+법원 소스 분리 수집, 법원 시/도 배치 사이 지연(2s), `unavailable` 기본 |
| `routers/auction.py` | `/sync`에 `source=onbid\|court` 쿼리 추가, mock 문구 정직화 |
| `requirements.txt` | `beautifulsoup4==4.12.3`, `lxml==5.3.0` 추가 |
| `tests/test_auction_demock_court.py` | ★신규 — 파서 픽스처 + 키없음 unavailable 단위테스트 7건 |

## 3. 온비드 목업 제거 · 실연동

- `_mock_items` / `random` import 삭제. mock 분기 전부 제거.
- 키 미설정 → `{items:[], data_source:"unavailable", total:0, reason:"온비드 인증키 미설정(공공데이터포털 활용신청 필요)"}`.
- 호출 실패 → `reason:"온비드 호출 실패: ..."` (가짜 0건).
- 무자료(정상 응답이나 item 0건) → `reason:"온비드 응답 무자료(...)"`.
- 키 있고 성공 → 정규화 후 `data_source:"onbid_live"`.
- 엔드포인트를 차세대 온비드(data.go.kr `apis.data.go.kr/1611000/nadOpenApi`, 서비스 15157207 목록 / 15157251 상세)로 갱신. `type=json` 파라미터. 오퍼레이션명/필드명은 활용신청 승인 후 확정 — `_extract_items`/`_normalize` 방어적 파서가 스키마 차이를 흡수하며 미스매치 시에도 가짜 생성 없이 빈 결과.

## 4. court_scraper.py (지연·예의·파싱·한계 정직)

- `requests.Session` + `BeautifulSoup(html.parser)`. **순차(동시성 없음)**.
- ★지연: `CourtAuctionScraper(delay_sec=1.5, delay_jitter=0.8)` — 페이지 간 `_sleep()`으로 1.5~2.3초 sleep(지터로 패턴화 완화). 동기화 태스크는 시/도 배치 사이에 추가 2초 sleep.
- 예의: 전용 User-Agent(`PropAI-AuctionBot`), `max_pages=3` 소량, 200 외 응답/예외 시 graceful 중단+로그.
- 파서 분리: `parse_list_html()` / `parse_detail_html()` 는 네트워크 비의존(픽스처 단위테스트 대상). `source="court"` 정규화.
- 무목업: requests 미설치 / 차단·실패 / JS-only / 무자료 → `data_source:"unavailable"` + reason(가짜 없음).
- ★한계 정직(코드 상단 docstring + 본 보고 §9): 법원경매정보는 세션/JS(폼 POST·동적렌더) 의존이 많아 순수 requests+BS로 일부 화면을 못 가져올 수 있음 → 빈 결과+reason로 노출. **Selenium/chromium 미도입**(Micro 1GB OOM 위험). HTML 변경 시 파서 유지보수 필요, 과도요청 시 차단 위험.

## 5. 무목업 보장

- `grep -rni "mock|더미|가짜|dummy|random.rand|fake"` 결과: 잔존은 전부 "가짜 없음/무목업" 설명 문구뿐. 데이터 생성 mock 0건.
- `data_source` 값 도메인: `onbid_live` | `court_scrape` | `unavailable` (mock 제거).
- 서비스/태스크 기본값 `"mock"`→`"unavailable"`.

## 6. 단위 검증 (외부 실호출 없음)

- 파서 픽스처: 저장 샘플 HTML(목록 2행/JS-only/상세)로 `parse_list_html`·`parse_detail_html` 검증.
- 키없음 unavailable: `OnbidClient("").fetch_items()` → unavailable·items=[]·total=0.
- `_extract_items` 무자료/오류 → 빈 리스트.
- 지연 로직: `_sleep` monkeypatch로 sleep 호출·범위(1.5~2.3) 검증.
- 차단 시(`_fetch=None`) unavailable.
- **결과: `tests/test_auction_demock_court.py` 7 passed. 회귀: 기존 `tests/test_auction_service.py` 17건 포함 24 passed.**
- `ast.parse` 전 파일 OK. 앱 부팅 OK, `/api/v1/auction/*` 10개 라우트 등록(`/sync` 포함).
- ★멱등 upsert는 ae100cb의 `_upsert_items` ON CONFLICT(source,item_no) 유지 — source별 UNIQUE라 onbid/court 분리. (DB 통합 검증은 프로덕션DB 금지로 코드 경로·기존 패턴으로 보증.)

## 7. 커밋 해시

`2718fb4` — fix(auction): 목업 제거(무목업)+온비드 실연동 전용+대법원 경매 스크래퍼(지연·예의, 향후 API 대체)

## 8. requirements 변경

추가: `beautifulsoup4==4.12.3`, `lxml==5.3.0` (requirements.txt). venv 설치 완료(+soupsieve 의존). Oracle requirements는 별도(미변경) — 배포 시 추가 필요.

## 9. 미진/후속

- **법원경매 JS/세션 한계**: 현재 파서는 표준 테이블(`tr.court-auction-item` / `data-*`) 구조 가정. 실 courtauction.go.kr는 폼 POST·동적렌더라 실 셀렉터는 실측 후 보정 필요. 실호출은 본 작업 범위 외(금지)라 픽스처 검증까지만.
- **Selenium 후속**: 자원(Micro 1GB) 여유 호스트에서 플래그 기반 도입 검토(현재 미도입).
- **온비드 활용신청**: 차세대 온비드 부동산(15157207/15157251) 키 승인 + 오퍼레이션명/필드명 실측 확정 필요(키 미승인 시 unavailable 정상 동작).
- **Oracle 배포**: requirements.oracle.txt에 bs4/lxml 미반영 — 배포 시 추가.
