# 101 · 프론트엔드 부지분석 UX 폴리시 3건

담당 범위: ModulePlaceholder / LandIntelligencePanel / site-analysis page / DigitalTwinScene
(EnvironmentAnalysisPanel·environment_service는 타 executor 담당이라 미접촉)

## 변경 파일
- `components/layout/ModulePlaceholder.tsx` — 타이틀 사이즈 축소
- `app/[locale]/(dashboard)/projects/[id]/site-analysis/page.tsx` — 주변 실거래 지도 패널 마운트 + 디지털트윈 자동연결/안내 props
- `components/projects/LandIntelligencePanel.tsx` — 실거래 텍스트탭 → "지도에서 보기" CTA 대체
- `components/digital-twin/DigitalTwinScene.tsx` — designHref prop + 건물 없음 안내 블록
- (신규 컴포넌트 없음. `components/map/NearbyTransactionsMap.tsx`는 Read만·재사용)

## 1. 타이틀 과대 축소 (ModulePlaceholder.tsx:42)
- 전: `text-4xl font-[900] ... tracking-tighter sm:text-5xl lg:text-6xl leading-[1.1]`
- 후: `max-w-2xl text-3xl font-[900] ... tracking-tighter sm:text-4xl lg:text-[40px] leading-[1.15]`
- 한 단계씩 축소(base 4xl→3xl, sm 5xl→4xl, lg 6xl→40px) + max-w-2xl 폭 제약 + leading 1.1→1.15(가독성).
- 공용 컴포넌트라 전 페이지 일관 적용.

## 2. 인근 실거래가 → 지도기반 별도 패널 승격
- site-analysis page에 `NearbyTransactionsMap`을 dynamic(ssr:false, window.L 동적로드) 임포트로 추가.
- result stage에서 `<L3EnhancedCards>` 다음에 마운트:
  `<div id="nearby-transactions-map" className="scroll-mt-24"><NearbyTransactionsMap address={siteData.address} pnu={siteData.pnu} /></div>`
- **NearbyTransactionsMap 실제 props 시그니처(Read 확인)**: `{ onPayload?, onLoading?, address?, pnu? }` (전부 optional, 미전달 시 활성 프로젝트 store 사용). 본 패널은 `address`/`pnu`만 직접 주입.
  - 컴포넌트 자체가 `<section>`(제목 "주변 실거래 지도" + 매매/전월세·유형필터 + 반경원 + 마커 팝업 + 데이터 없음 정직처리)를 렌더 → 별도 래핑 최소화.
- LandIntelligencePanel의 `transaction` 탭: 5건 텍스트표 제거 → 안내문구 + "지도에서 보기" CTA(클릭 시 `#nearby-transactions-map`로 smooth scroll). PNU/공시지가/GIS 탭은 유지.
  - 기존 tx fetch effect/state(txData·txLoading)는 그대로 두되 미사용(상태표시용 txError만 잔존 사용). tsconfig에 noUnusedLocals 없음 → tsc 무영향.
- 무목업: 데이터 없을 때 NearbyTransactionsMap 자체 "해당 유형 최근 거래 없음" 배지에 위임.

## 3. 디지털트윈 건물 안내 + 최신 설계 자동연결
### (a) 안내 (DigitalTwinScene.tsx)
- `designHref?: string` optional prop 추가.
- `hasBuildingGlb === false`일 때 정직성 배지 아래 amber 안내 블록 표시:
  - 문구: "설계가 아직 없어 지형·필지만 표시됩니다." + "설계를 생성/업로드하면 건물이 합성된 가상준공(준공 전 미리보기)을 볼 수 있습니다." + "AI 자동설계로 매스를 즉시 만들거나, 보유한 CAD 도면을 업로드해 연동할 수 있습니다."
  - CTA: `<a href={designHref}>건축 설계로 이동</a>` (designHref 있을 때만).

### (b) 자동연결 (site-analysis page)
- **latest design_version 조회 경로(Read 확인)**: `GET /api/v1/design/{project_id}/drawings/load` → `{ saved: bool, version, data, updated_at }` (design_versions 테이블 최신 cad_2d 행 조회).
- result stage 진입 시 effect로 호출, `res.saved === true`면 `designVersionId = id`(프로젝트 id) 세팅, 아니면 null.
- **백엔드 배선 근거**: `routers/digital_twin.py` /scene이 design_version_id 수용 → `scene_service._resolve_building_glb(design_version_id, None)`가 glb URL을 `/api/v1/design/{design_version_id}/bim/model.glb`로 구성. 해당 glb POST 라우트(`design_v61.py:470`)는 path 세그먼트를 project_id로 사용하므로 **프로젝트 id 전달이 정합**.
- 전달: `<DigitalTwinScene address pnu designVersionId={designVersionId} designHref={`/${locale}/projects/${id}/design`} />`
- 설계 없음/조회 실패 → designVersionId=null → 건물 미합성 + (a) 안내만(가짜 건물 금지).

## tsc 결과
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- git diff 확인: 4개 파일 모두 import 제거 0건. 디버그 코드(console/TODO/debugger) 0건.

## 미진사항 / 후속 검토
- **glb 로드 GET/POST 불일치(기존 이슈, 본 범위 밖)**: `DigitalTwinScene > BuildingGlb`는 `GLTFLoader.loadAsync(glb_url)`로 **GET** 호출하나, `/api/v1/design/{id}/bim/model.glb` 라우트는 **POST(매스 페이로드 동봉)** 전용. scene_service 주석도 "프론트가 POST 로드"라고 명시. 따라서 설계가 존재(designVersionId 전달)해도 GET 405로 건물이 안 보일 수 있음. 이는 디지털트윈 3D 파이프라인의 기존 백엔드/로더 설계 문제로, 4파일 범위를 넘는 별도 작업 필요(BuildingGlb를 POST+arraybuffer→GLTFLoader.parse로 전환하거나, glb 라우트에 GET 추가). 자동연결 의도(designVersionId 배선)는 사양대로 완료.
- LandIntelligencePanel의 죽은 tx fetch(txData/txLoading)는 정리하지 않고 보존(스코프 최소화). 추후 제거 가능.
