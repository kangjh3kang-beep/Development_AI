# 89 · 경매 UI 2종 개선 (프론트엔드)

대상: `apps/web/components/auction/`

## 1) 물건 상세 모달 실조회 — AuctionWorkspace.tsx
- `AuctionItem`에 상세조회 키 `cltr_mng_no`·`pbct_cdtn_no` 추가. 신규 타입 `AuctionPrevBid`/`AuctionDetail`/`AuctionDetailResponse`.
- `DetailModal`에 `useQuery(["auction","detail",cltr,pbct])` 추가. 두 키가 모두 있을 때만 `enabled`(`/auction/detail?cltr_mng_no=&pbct_cdtn_no=`).
- 표시값 = 목록값 우선 + 상세 보강(`pick(detailVal, listVal)`): 물건관리번호·주소·용도·감정가·최저입찰가·유찰횟수·낙찰가율·낙찰가격·토지/건물면적·상태.
- 이미지: `image_url`(공백 트림) 있으면 `<img>`, 없으면 정직 플레이스홀더 "이미지 없음 (온비드 미제공)" / 로딩 중 "이미지 불러오는 중…". 가짜 금지.
- est_win: `safeNumber()`(유한 숫자만 통과, NaN/Infinity/문자→null) 가드. null이면 "추정 불가", `est_win_low/high` 있으면 범위 병기. NaN 절대 미노출.
- 회차별 입찰내역(`prev_bids`) 표: 회차·개찰일·최저입찰가·결과·낙찰가·낙찰가율(각 숫자 `safeNumber` 가드, `formatBidPrice`).
- 상세 상태 정직 안내: 로딩 "상세 정보를 불러오는 중…", 실패 "상세 불러오기 실패 — 목록 기준만 표시", `data_source==="unavailable"` → "온비드 상세 미제공(+reason)".

## 2) 지도 관심구역 UX — AuctionMonitorPanel.tsx
- Ctrl+Z / ⌘+Z: `undoLastVertex()`로 그리는 중 마지막 정점 1개 pop + 마커/폴리라인 재구성. keydown 리스너는 `drawing===true`일 때만 등록, cleanup으로 `removeEventListener` 필수.
- 저장 구역 클릭 → 확대: 폴리곤 `click` 핸들러 + 칩의 라벨 버튼 → `zoomToRegion()`(`map.fitBounds`, maxZoom 16). 그리기/편집 중에는 무시.
- 점 드래그 수정: 칩의 "편집" → `enterEdit()` 진입. 정점마다 `L.marker({draggable:true})` divIcon, `drag` 이벤트로 `editPointsRef` 갱신 + `refreshEditPolygon()` 실시간 재그리기. "수정 저장" → `editSaveMutation`(PUT 없음 → `DELETE /auction/regions/{id}` 후 `POST /auction/regions` 같은 이름). "편집 취소" 가능.
- 편집 중에는 저장 레이어 재렌더 생략(`if (editing) return`), 종료 시 effect dep `editing` 변화로 재렌더.
- 상태 안내: 헤더에 그리기/편집 모드 + 현재 정점수 표시, Ctrl+Z 힌트.

## cleanup / 릭 방지
- 지도 init effect return: `clearTimeout`, `map.off()`, `map.remove()`, 모든 ref null/[] 초기화(언마운트).
- keydown 리스너 cleanup. 편집/그리기 전환 시 `clearDraft`/`clearEdit`로 레이어 제거.
- 신규 의존성 0(CDN window.L 재사용). React Compiler 규약 위해 useCallback dep에 setState 세터 포함.

## 검증
- `tsc --noEmit` EXIT 0.
- `eslint`(두 파일) EXIT 0.
- import 보존 확인(apiClient·useQuery·useCallback 등 무삭제).
- 무목업: 실 API(`/auction/detail`, `/auction/regions`)·실데이터만, 가짜 이미지/좌표 없음.

## push/배포
- 금지(요청대로). git commit만 수행.
