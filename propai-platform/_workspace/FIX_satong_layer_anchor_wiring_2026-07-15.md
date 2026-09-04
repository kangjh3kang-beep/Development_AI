# FIX: 사통맵 레이어 좌표앵커 단선·경매401 삼킴 근본수정 (2026-07-15, PR#271)

## 증상 (사용자 보고)
- 사통팔땅 멀티지도(/precheck)에서 패널(레이어)마다 API 정보를 못 가져옴.
- 패널에서 켠 레이어 중 일부만 지도에 표시됨(침묵 빈지도).

## 진단 과정 (라이브 그라운드 트루스)
1. **로컬 stale 함정 재확인**: 로컬 공유 main = origin/main 대비 127커밋 뒤(공통조상 0123d90a, 7/7).
   로컬에서 보이던 "분양·경매가 market 이펙트에 종속(PR#197 회귀)"·"PR#221/268 가드 소실"은
   전부 stale 착시 — origin/main(=배포본)에는 모두 살아 있음. **진단은 반드시 origin/main 기준.**
2. **백엔드 계약 전수검증** (에이전트): 지도 관련 9개 엔드포인트 전부 실재·등록 확인.
   - ★`/auction/search`만 RBAC(`RequirePermission("auction","read")`) — 무인증 401.
   - ★`/zoning/parse-parcels`: PNU/법정동코드 보유 행은 `_enrich_fill` 경로라 **lat/lon 미세팅**
     (주소전용 행만 `_geocode_fill`로 좌표 확보).
   - `/zoning/parcel-boundaries`: per-feature 좌표 없음(geometry만).
   - `/presale/nearby`: 좌표 없이 address만 와도 서버 지오코딩 지원.
3. **프로드 실호출** (의정부동 224): POI·개발계획·분양·경계보강 정상 응답 / `/auction/search` HTTP 401 실측.
   → "API 미연동" 아님. **배선(앵커·노트) 문제.**

## 근본원인 3중
| # | 원인 | 결과 |
|---|---|---|
| ① | 조회 앵커 = `selectedParcels[0]의 lat/lon`만 참조(첫 필지 단선). 엑셀 PNU행·프로젝트 시드 필지는 좌표 없음 + 경계 역전파도 lat/lon 미매핑 → 영구 단선 | 분양·경매·개발계획 레이어 ON이어도 fetch 생략 |
| ② | `/auction/search` 401을 catch가 삼켜 `[]`("경매 무자료" 오표기) + api-client 전역 세션만료 처리(`handleSessionExpired`)가 발동 → **로그인 페이지로 강제 이동** | 비로그인 사용자가 경매 켜면 지도에서 튕김 |
| ③ | 앵커 미해소 시 payload null → 노트 없음 | 활성 배지 + 빈 지도 모순(정직원칙 역위반) |

## 수정 (공용화 — PR#271)
- `lib/satong-map-layers.ts`: **`resolveSelectionAnchor`** 신설 — ①좌표 보유 첫 필지 ②경계
  대표점(`geometryRepresentativePoint` — 경계상자 중심, 실측 기하 파생=무날조) ③무선택시 지도중심.
  선택 있는데 좌표 전무면 null(엉뚱한 지도중심 조회 역전 차단 — 기존 계약 보존).
- `SatongMapShell.tsx`: 분양·경매·개발계획·POI 공용앵커 전환. 정직 노트 3분류
  ("좌표 확인 중(경계보강 후 자동)"/"지도 이동 시 지도중심 조회"/"조회 실패"). 분양 address 폴백.
  경매: `hasAccessToken()` 사전 게이트 + 401/403 → "로그인/권한 필요" 구분 노트.
- `SatongMultiMap.tsx`: boundary 역전파(`boundaryFeatureToMapFeature`)에 대표점 좌표 파생 —
  **엑셀 필지도 경계보강 도착 즉시 앵커 자동 회복(자기치유 루프 폐합)**. presale/auction
  상태노트(marketLayer.presaleNote/auctionNote)가 건수 라벨보다 우선.
- `lib/api-client.ts`: `skipSessionExpiry` 옵트아웃(선택형 위젯 401이 전역 로그인 리다이렉트
  발동 금지 — refresh 재시도는 유지) + `hasAccessToken()` export.

## 의도적 보류 (판단 기록)
- 백엔드 `parse-parcels` PNU행 좌표 세팅(additive): 프론트 대표점 자기치유가 지도 경로를 완결.
  행별 지오코딩 추가는 대량 업로드(60행+) 지연 유발 → 후속 필요 시에만.

## 검증
- vitest 66/66 (신규: 앵커 3순위·대표점 파생·무날조 null) · tsc 0에러 · eslint 신규 경고 0(기준선 동일 13, stash 교차확인).

## 교훈(전파)
- ★좌표 기반 레이어의 앵커는 공용 계약(resolveSelectionAnchor)으로 — '첫 항목 좌표' 직참조 금지.
- ★공개 화면의 선택형 위젯이 RBAC 엔드포인트를 부를 땐 사전 토큰 게이트 + skipSessionExpiry —
  401을 "무자료"로 위장하지도, 전역 리다이렉트를 발동하지도 말 것.
- ★로컬 공유 main은 origin/main 대비 stale일 수 있음(이번 127커밋) — 라이브 버그 진단은 origin/main.
