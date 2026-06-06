# 83 · 프론트엔드 경매·공매 3탭 UI

## 1. 조사
- 기존 `/auction` 라우트: `app/[locale]/(dashboard)/auction/page.tsx` 는 단건 AI analyze(useAIAnalyze, domain="auction") UI 였음. AuctionWorkspaceClient 와는 무관하게 동작.
- 기존 `components/auction/AuctionWorkspaceClient.tsx`: 구 계약(`/auction/opportunities`, `/auction/analyze`, `/chatbot/*`, `/contractors/active`) 기반. page 에서 미사용(고아 컴포넌트) + 테스트가 dashboard-route-shells 와 어긋나 이미 실패 중이었음.
- `apiClient`(lib/api-client.ts): `get/post/delete<T>(path, {body})`, `getRuntimeConfig()`(mode/hasAccessToken). 메인 인증. salesApi 아님.
- 81·82 계약 파일은 워크스페이스에 미존재 → 프롬프트 기재 계약(ranking/bid-results/my/filters)을 SSOT 로 사용.
- 토큰색·다크·모바일우선·한국어. WorkspaceQueryErrorCard·SkeletonLoader 재사용.

## 2. 신규/변경 파일
- 신규 `components/auction/AuctionWorkspace.tsx` — 3탭 워크스페이스.
- 변경 `app/[locale]/(dashboard)/auction/page.tsx` — useParams 로 locale 추출 후 AuctionWorkspace 렌더(단건 AI analyze 흡수·대체).
- 변경 `app/[locale]/(dashboard)/layout.tsx` — **메뉴 이동 보존**: 경매·공매→토지·자금 그룹, 공사비 분석→사업 검토 그룹(되돌리지 않음, 이번 커밋 포함).
- 변경 `app/[locale]/(dashboard)/__tests__/dashboard-route-shells.test.tsx` — auction mock 을 AuctionWorkspace 로 갱신, 신 page 구조에 맞춘 assertion.
- 삭제 `components/auction/AuctionWorkspaceClient.tsx` + 그 테스트 — 구 계약 고아 컴포넌트(page 미사용, 신 3탭으로 대체).

## 3. 3탭 구현
- 탭A 내 경공매: `GET /auction/my?group_by=project` → 통합 보드 + 프로젝트별 카드(테이블). 빈 결과 시 "관리 토지 중 경공매 진행 물건이 없습니다."
- 탭B 조건검색: 폼(시도·용도·물건명·유찰횟수·감정가·최저입찰가·면적·입찰결과[전체/유찰/낙찰]) → `GET /auction/bid-results?...`. 결과 테이블(주소·용도·감정가·최저입찰가·유찰·낙찰가율·낙찰가능가(추정)·상태). 저장조건 CRUD: `GET/POST /auction/filters`, `DELETE /auction/filters/{id}` (chip 클릭=적용, ✕=삭제). note 정직 노출.
- 탭C 전국 순위: `GET /auction/ranking?by=views|interest|min_bid|discount_rate&page=1&page_size=30` 토글 → 순위 리스트(순위·썸네일·주소·용도·상태·감정가·할인율·최저입찰가).
- 공통: 물건 클릭 → DetailModal(전 필드 정직 표기, 추정·가정 명시). 상세 단건 `GET /auction/{id}` 는 모달이 목록 페이로드 표시로 충분해 현재 미호출(잔여 참고).

## 4. 정직/무목업
- min_bid_price null → "비공개", 기타 null/빈값 → "-".
- est_win/win_rate/appraisal_price = 추정·가정. 헤더/모달에 "추정치이며 가정 포함" 명시.
- 백엔드 unavailable(401/403) → "로그인 필요", 그 외 → "온비드 데이터 없음/API 키 확인". 무목업(폴백 더미 없음).
- bid-results note(무자료 시 전국 폴백 안내) 그대로 렌더. 로딩(Skeleton)·빈상태·에러카드·권한 게이트 전부 처리.

## 5. tsc/eslint
- `pnpm type-check` → EXIT 0.
- eslint(변경 3파일) → EXIT 0. import 보존 확인(git diff·grep), 디버그 잔여 없음.

## 6. 커밋
- 메시지: `feat(auction): 경매·공매 3탭 UI(내경공매·조건검색·전국순위)+메뉴 재배치(경공매→토지/자금, 공사비→사업검토)`
- (해시는 커밋 후 기재)

## 7. 백엔드 정합·미진
- 계약 의존: items 배열(ranking=RankingResponse.items, bid-results=BidResultsResponse.items, my=projects/combined). filters = SavedFilter[]{filter_id,name,params}.
- 미진: (a) `/auction/{id}` 상세 미연동(목록 페이로드로 모달 구성). (b) 지도(NearbyTransactionsMap) 미사용 — 핵심 테이블 우선. (c) 페이지네이션 UI 미구현(page 고정 1, page_size 30). 백엔드 응답 키가 계약과 다르면(예: items 가 아닌 다른 래핑) 어댑팅 필요.
