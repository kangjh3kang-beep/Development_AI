# 86. 경·공매 모니터링 UI (프론트엔드)

## 1. 조사 (Leaflet / leaflet-draw / 기존 지도)
- **leaflet / react-leaflet / leaflet-draw 모두 npm 미설치** (package.json·node_modules 없음).
- 기존 지도 패턴: `components/map/NearbyTransactionsMap.tsx`, `ParcelBoundaryMap.tsx` 등이
  **Leaflet을 CDN(unpkg 1.9.4)으로 동적 로드**(`loadLeaflet()` + `window.L`, `declare global`).
- 동일 패턴을 재사용 → **새 npm 의존성 0**. leaflet-draw 미설치이므로 폴리곤은 네이티브 클릭으로 직접 구현.
- apiClient는 `body`에 FormData 전달 시 Content-Type 자동 생략(브라우저가 multipart boundary 설정) → 업로드 호환.

## 2. 변경 / 신규 파일 (의존성 변경 없음)
- **신규** `apps/web/components/auction/AuctionMonitorPanel.tsx` — 모니터링 센터 본체.
- **수정** `apps/web/components/auction/AuctionWorkspace.tsx` — "내 경공매" 탭 상단에 패널 마운트,
  기존 프로젝트 연동 보드(my)는 하단에 "프로젝트 연동 물건" 섹션으로 유지·흡수. import 1줄 추가.
- **package.json 변경 없음** (CDN 동적로드).

## 3. 3입력 + 매칭결과 + 수동실행
- **ⓐ 보유토지(토지조서)**: 자동연동 안내 카드 + 현재 모니터링 건수(GET /watchlist 중 watch_source=landschedule 카운트).
- **ⓑ Excel 업로드**: 파일선택(.xlsx/.xls/.csv) → `POST /auction/watchlist/upload` (multipart, field `file`).
  결과 표시 = created/parsed_count/skipped_rows/total_rows + detected_columns(PNU/주소/명칭) + examples 2건 + note.
  업로드 후 watchlist·monitor 쿼리 무효화 갱신.
- **ⓒ 지도 구획**: Leaflet 지도 + 네이티브 클릭 폴리곤 → 이름 입력 후 `POST /auction/regions {name, geojson}`.
  저장 구역 목록(GET /regions → `{items}`)·삭제(DELETE /regions/{id}, id=정수). 저장구역은 지도에 청록 폴리곤 렌더.
- **매칭 결과**: `GET /auction/monitor?group_by=source` → groups(landschedule/excel/region)별 카드+표
  (관심대상·주소·용도(usage??kind)·감정가·최저입찰가·유찰·낙찰가능가(est_win.est_win_mid)·상태). total_matched 배지·data_source 출처표기.
- **수동실행**: "지금 모니터링 실행"(POST /monitor/run, timeout 120s) → monitor·watchlist 무효화.

## 4. 폴리곤 그리기 구현방식 (leaflet-draw 미사용)
- "구역 그리기 시작" → `drawing=true`. 지도 `click` 핸들러가 활성 시 정점 추가:
  각 클릭마다 circleMarker(빨강) + 정점들을 잇는 dashed polyline 갱신, 정점 수 표시.
- "구역 완료"(≥3정점) → drawing 종료, draft 라인을 닫힌 주황 폴리곤으로 시각화.
- "구역 저장" → leaflet `[lat,lng]` → GeoJSON `[lng,lat]`로 변환 + 시작점으로 ring 닫기 → POST.
- "지우기" → draft 마커·라인·정점 초기화. drawingRef로 click 핸들러 내 최신 상태 참조(closure 안전).

## 5. 무목업 / 빈상태
- 모든 데이터는 실 API(apiClient)만. 가짜 물건/좌표 없음.
- 매칭 0건 그룹: "해당 조건 매칭 물건 없음 (자동 모니터링 중)" 안내.
- 업로드 실패/미인식행: skipped_rows·note·에러메시지 정직 표기.
- monitor note(캐시없음/동기화안내), data_source 출처, watchlist note 그대로 노출.
- 지도 로드 실패 시 정직 표기. 지오코딩/키없음은 백엔드 note로 전달되어 표시.

## 6. tsc / eslint / import 보존
- `tsc --noEmit --incremental false` → **EXIT 0** (오류 0).
- `eslint AuctionMonitorPanel.tsx AuctionWorkspace.tsx --no-cache` → **EXIT 0** (경고·오류 0).
- import 보존 확인: AuctionWorkspace에 `AuctionMonitorPanel`·`apiClient`·`ApiClientError` 유지,
  패널에 `apiClient`·`@tanstack/react-query`·`ChangeEvent` 유지(린터 삭제 없음).

## 7. 커밋 해시
- (아래 커밋 단계 결과 기재)

## 8. 백엔드 정합 / 미진
- **정합 교정(계약서 vs 실제 라우터)**:
  - GET /watchlist → 실제 `{items, total}` (계약서의 "targets" 아님). 타깃 source 필드명은 `watch_source`.
  - GET /regions → 실제 `{items, total}` (bare array 아님). region id = **정수**(int).
  - monitor 매칭행 `est_win` = **객체** `{est_win_low, est_win_mid, est_win_high, ...}` (flat number 아님) → mid 사용.
  - 매칭행은 `usage`가 없고 `kind` 사용 → `usage ?? kind` 표기.
  - monitor.targets = 관심대상 **수(number)**.
- 위 항목을 백엔드 실제 응답에 맞춰 프론트 타입·접근자 보정 완료. (계약서 문구보다 라우터/서비스 실제 응답 우선)
- 미진: 매칭행 상세 모달은 미구현(표만). 필요 시 후속.
