# 85 · 백엔드 — 경·공매 모니터링 (토지조서 Excel업로드 + 지도구획 + 보유토지 매칭)

## 1. 변경/신규 파일·테이블
**신규**
- `apps/api/app/services/auction/monitor.py` — 매칭 엔진(Excel 파싱·컬럼감지·주소정규화·point-in-polygon).
- `apps/api/tests/test_auction_monitor.py` — 단위테스트 18건(외부 실호출 0, 픽스처/직접호출만).

**수정**
- `apps/api/app/services/auction/auction_service.py` — DDL 확장 + 모니터링 메서드 다수.
- `apps/api/routers/auction.py` — 모니터링 엔드포인트 6종 추가.
- `apps/api/app/tasks/auction_sync_task.py` — cron에 모니터링 매칭+신규알림 패스 추가.

**테이블**
- `auction_items` (기존) → 멱등 `ALTER TABLE ADD COLUMN IF NOT EXISTS`: `lat`, `lng`, `geocode_status`(폴리곤 매칭용 지오코딩 좌표 캐시).
- `auction_watch_target` (신규) — 관심대상 3입력 통합: `user_id, watch_source(landschedule/excel/region), pnu, address, region_geojson(JSONB), project_id, label, created_at`. 기존 `auction_watch`(물건↔관심 매칭결과)와 별도로 "사용자가 등록한 관심 자체"를 보관.

## 2. 3입력 처리 + 컬럼감지
- **(a) 토지조서 보유토지**: `sync_landschedule_targets` — 기존 `_my_pnus`(projects.pnu_codes + parcels.pnu) 재사용, `auction_watch_target(source=landschedule)` 멱등 등록(존재확인 후 INSERT). `/monitor`·`/watchlist` 호출 시 자동 최신화.
- **(b) Excel 업로드**: `POST /auction/watchlist/upload`(multipart `file`). pandas + openpyxl(xlsx)/xlrd(xls)/csv. **컬럼 자동감지**(`detect_columns`): 헤더 정규화(공백/특수문자 제거·소문자) 후 사전 매칭 — PNU계열(PNU/고유번호/토지고유번호/지번코드…), 주소계열(주소/소재지/지번주소/도로명주소/번지…), 라벨계열(비고/물건명/명칭…). 값 보조판별(19자리 숫자 → PNU). PNU 하이픈/공백 정규화. 미인식행(빈 PNU·주소) 스킵 카운트. 반환: `created/parsed_count/skipped_rows/total_rows/detected_columns/examples`. 빈 파일·미인식 헤더 → `ValueError` → 라우터 400.
- **(c) 지도 구획**: `POST /auction/regions {name, geojson}` — type=Polygon/MultiPolygon + coordinates 검증, `region_geojson` JSONB 저장. `GET /auction/regions`, `DELETE /auction/regions/{id}`.

## 3. 매칭(텍스트/PNU/폴리곤지오코딩) + 캐시
`AuctionStep1Service.monitor()`:
- **PNU 직접매칭**: `watch.pnu == auction_items.pnu`(정확).
- **주소 텍스트 부분매칭**: `normalize_address`(괄호 부가설명·공백·구분자 제거) 후 짧은쪽⊂긴쪽 포함관계, 짧은쪽 6자 미만은 매칭 제외(오탐 방지). 지오코딩 불필요(빠름).
- **폴리곤(region)**: 물건 주소 → `VWorldService.geocode_address` → 좌표 → shapely `point_in_polygon`. ★폭주 방지: region 관심대상이 있을 때만, 좌표 미캐시 물건에 한해 `max_geocode`(기본 60)건까지만 지오코딩. 성공좌표는 `auction_items.lat/lng` 캐시(멱등), 실패는 `geocode_status='failed'`로 기록해 재시도 회피(가짜좌표 금지).
- 매칭물건엔 `est_win`(낙찰가능가, 기존 `win_estimator` 재사용) + 감정가·최저입찰가·유찰 포함.

## 4. 엔드포인트
| 메서드 | 경로 | 용도 |
|---|---|---|
| POST | `/api/v1/auction/watchlist/upload` | Excel/CSV 업로드(multipart `file`) |
| POST | `/api/v1/auction/regions` | 지도 구획 저장 `{name, geojson}` |
| GET | `/api/v1/auction/regions` | 구획 목록 |
| DELETE | `/api/v1/auction/regions/{id}` | 구획 삭제 |
| GET | `/api/v1/auction/watchlist` | 관심대상 통합 목록(3입력) |
| GET | `/api/v1/auction/monitor?group_by=source` | 관심대상별 매칭 물건(landschedule/excel/region 그룹) |
| POST | `/api/v1/auction/monitor/run` | (관리/cron) 온비드 동기화+매칭+신규알림 |

(기존 `/search /ranking /bid-results /my /filters /sync /items` 무파괴 유지)

## 5. 알림·cron
- `monitor_run`: 온비드 `fetch_ranking`(getInqRnkClg 실데이터)로 캐시 적재 → before/after 매칭 스냅샷 비교 → 신규 매칭만 `_notify_match`(기존 알림훅, 키 없으면 로깅). 반환 `synced/data_source/total_matched/new_matches/groups_count`.
- cron: `auction_sync_task._sync_all_regions`에 ③ 모니터링 패스 추가 — `auction_watch_target`의 DISTINCT user_id 별로 `monitor_run` 실행. 기존 Celery beat `sync-onbid-auctions-daily`(매일 04:00) 진입점 그대로 사용(별도 스케줄 추가 불필요).

## 6. 무목업 정직성
- Excel: 실제 파싱값만 등록, 미인식행 스킵+카운트, 빈/미인식 헤더 정직 400.
- 지오코딩: 실패/무자료 스킵 + `geocode_status='failed'`(가짜좌표 금지).
- 캐시 물건 없으면 `data_source=unavailable` + note(동기화 안내).
- 키 없음 → `fetch_ranking`이 unavailable 반환(가짜 없음).
- 모든 쿼리 `user_id` 격리.

## 7. 단위검증(픽스처)
`tests/test_auction_monitor.py` — **18 passed**. 외부 실호출 0(온비드·VWorld 미호출).
- detect_columns: PNU/소재지/지번주소/도로명주소/토지고유번호 감지, 미인식.
- parse_watchlist_excel: xlsx(PNU/라벨)·csv(주소, 빈행 스킵)·PNU 하이픈 정규화·주소값 PNU 보조인식·미인식헤더 ValueError·빈파일 ValueError.
- normalize_address/address_matches: 정규화·부분일치·불일치·짧은주소·빈값.
- point_in_polygon: 내부/외부/잘못된 geojson.

기타 검증: `py_compile` 4파일 OK · 앱부팅 OK · auction 라우트 17개(신규 6 포함) 등록 확인 · 기존 auction 테스트 회귀 0(test_auction_onbid_ranking/pbanclist/demock_court/router_auction 31 passed).
※ `test_celery_tasks`의 beat/task count 단언 2건 실패는 **사전존재**(celery_app.py 미수정, sync-onbid 태스크는 이전 커밋분).

## 8. 커밋해시
(아래 커밋 출력 참조)

## 9. 프론트 계약
- **업로드**: `POST /api/v1/auction/watchlist/upload` `multipart/form-data`, field `file`(xlsx/xls/csv). 응답 `{created, parsed_count, skipped_rows, total_rows, detected_columns:{pnu,address,label}, examples:[{pnu,address,label}]}`. 실패 400 `{detail}`.
- **구획**: `POST /api/v1/auction/regions` JSON `{name:string, geojson:{type:"Polygon"|"MultiPolygon", coordinates:[...]}}`. 응답 `{id,user_id,watch_source,label,geojson,created_at}`. `GET /regions`→`{items:[{id,label,geojson,created_at}],total}`. `DELETE /regions/{id}`→`{status:"deleted",id}`.
- **모니터**: `GET /api/v1/auction/monitor?group_by=source` → `{group_by:"source", groups:{landschedule:[],excel:[],region:[]}, total_matched, targets, data_source, note?}`. 각 물건: `{id,source,item_no,kind,region_sido,region_sigungu,pnu,address,appraisal_price,min_bid_price,fail_count,status,bid_start,bid_end,data_source,watch_target_id,watch_label,project_id,est_win:{...}}`.
- **통합목록**: `GET /watchlist`→`{items:[{id,watch_source,pnu,address,geojson,project_id,label,created_at}],total}`.
- **run**: `POST /monitor/run`→`{status,synced,data_source,total_matched,new_matches,groups_count}`.

## 10. 미진
- 의존성 `openpyxl==3.1.5`가 로컬 `.venv`에 미설치 상태였어 검증 위해 설치(requirements.txt/pyproject에 이미 선언된 정식 의존성). 프로덕션 이미지엔 포함됨.
- cron 모니터링은 `tenant_id=None`으로 호출 → landschedule 자동최신화는 스킵(이미 등록된 excel/region 대상만 매칭). 보유토지 신규 PNU 반영은 사용자의 `/monitor`·`/watchlist` 진입 시 최신화됨. cron에서 user→tenant 역매핑은 후속.
- `monitor_run` 캐시 적재는 전국 조회수 순위(getInqRnkClg) 기반(빠른 매칭용). 시/도 전수 적재는 기존 일배치(`sync_region`)가 담당.
- 폴리곤 지오코딩 상한(max_geocode=60/실행)은 보수치 — 물건 급증 시 다회 실행으로 점증 캐싱(failed 재시도 안 함).
