# PropAI 프론트엔드 아키텍처 감사 보고서

작업 루트: `propai-platform/apps/web` (Next.js 16 App Router, React 19, Zustand, Tailwind v4)
감사 범위: 페이지/라우트 64개, 컴포넌트 216개(비테스트), 백엔드 라우터 ~90개
방식: 읽기 전용 정적 분석 (코드 미수정)

---

## 1. 종합 요약

- **구조 성숙도: 높음.** 64개 page.tsx 중 대부분이 "thin shell → client component 위임" 패턴으로 라이브 연동되어 있고, 정적 placeholder(`ModulePlaceholder`)는 일부 미구현 모듈에만 잔존.
- **FE↔BE 정합: 양호.** 표본 추출한 ~70개 API 경로가 백엔드 prefix와 일치. 404 위험은 거의 없으나 **api-client의 로컬/프록시 폴백 로직에 잠재 결함 1건**(아래 2.1).
- **데이터 흐름(모세혈관): 견고.** `useProjectContextStore`가 프로젝트별 스냅샷으로 영속·복원. 단, **전적으로 localStorage 의존**이라 기기간 동기화는 `/store/projects` 옵트인에만 의존.
- **혁신 공백: 시각화·여정 가시화 영역에 집중.** 라이프사이클 진행도·교차모듈 데이터 출처 추적·검증 배지 일관성에서 UX 기회 다수.

---

## 2. FE↔BE 정합 / 404 위험

### 2.1 [중] api-client 로컬 폴백 하드코딩 — `lib/api-client.ts:65-71`
- 프로덕션 base는 도메인 감지로 `https://api.4t8t.net/api/v1`, 그 외엔 `/api/proxy`.
- 그러나 `apiBaseUrl === "/api/proxy"`일 때 브라우저는 **무조건 `http://localhost:8000/api/v1`로 직타격**(line 71). 프로덕션이 아닌 임의 호스트(프리뷰 `*.pages.dev` 외 커스텀 도메인, 사내 스테이징)에서 열면 사용자 브라우저가 localhost를 때려 전량 실패.
- v1(`getRequestUrl`)과 v2(`getV2RequestUrl`)가 **호스트 화이트리스트를 각각 중복 유지**(line 12 vs 277) → 신규 도메인 추가 시 양쪽 누락 위험.
- 근거: 프로덕션 도메인 목록이 `4t8t.net / www / *.pages.dev / propai.kr`로 하드코딩. `propai.kr`은 v1·v2 양쪽에 있으나 신규 도메인은 누락되기 쉬운 구조.

### 2.2 정합 확인된 경로(표본, 일치)
| FE 호출 | api-client 변환 | BE prefix | 상태 |
|---|---|---|---|
| `/feasibility/auto-recommend` (postV2) | `/api/v2/feasibility/...` | `v2_feasibility_router` 자체 prefix `/api/v2/feasibility` | OK |
| `/cost/estimate-overview` | `/api/v1/cost/...` | `app/routers/cost.py` prefix `/api/v1/cost` | OK |
| `/g2b/bids` | `/api/v1/g2b/bids` | `g2b_bid` prefix `/g2b` + include `/api/v1` | OK |
| `/ai/llm` | `/api/v1/ai/llm` | `ai_analyze.py` 자체 prefix `/api/v1/ai` | OK |
| `/site-score/envelope` | `/api/v1/site-score/...` | site_score 자체 prefix | OK |
| `/expert-panel/analyze` | `/api/v1/expert-panel/...` | `expert_panel` + include `/api/v1` | OK |
| `/verify/analysis` | `/api/v1/verify/...` | `verification` + include `/api/v1` | OK |
| `/store/projects` | `/api/v1/store/projects` | `user_store` prefix `/store` + include `/api/v1` | OK |
| `/billing/charge` | `/api/v1/billing/charge` | `billing.py:99 @router.post("/charge")` | OK |
| `/reports/investor/generate` | `/api/v1/reports/...` | `reports` prefix `/api/v1/reports` | OK |

### 2.3 [관찰] 백엔드 라우터 이중 위치
- `apps/api/routers/*.py`(v1 다수)와 `apps/api/app/routers/*.py`(cost/g2b/pipeline/v2 등)가 공존. 런타임 진입점은 `apps/api/main.py`(이것이 `apps.api.app.routers.*`를 선택적 import). FE 영향은 없으나, 신규 라우터 등록 위치 혼동 시 누락 위험. (FE 감사 범위 밖이지만 정합성 관점에서 기록)

---

## 3. 페이지별 상태 매트릭스 (근거 파일:라인)

상태 정의: **라이브**=client 컴포넌트가 apiClient/Context 실호출 / **부분**=일부 placeholder 혼재 / **목업**=ModulePlaceholder 단독 / **정적**=연동 없는 안내성.

### 핵심 워크플로우 (사이드바 "프로젝트 분석")
| 라우트 | 상태 | 근거 |
|---|---|---|
| `/[locale]` (대시보드) | 라이브 | dashboard/overview·stats 호출 |
| `/projects` | 부분 | `projects/page.tsx`에 ModulePlaceholder import 잔존 |
| `/projects/new` | 라이브 | `projects/new/page.tsx:62,70,81,86,93` POST /projects→billing/charge→setProject→updateSiteAnalysis→push |
| `/projects/[id]` (라이프사이클) | 라이브 | useProjectContextStore + dynamic ssr:false |
| `/market-insights` | 부분 | ModulePlaceholder import 존재(MarketInsightsWorkspaceClient와 혼재) |
| `/permits` | 라이브 | PermitAiWorkspaceClient + VerificationBadge |
| `/regulations` | 라이브 | RegulationsWorkspaceClient + VerificationBadge |

### 프로젝트 상세 탭
| 라우트 | 상태 | 근거 |
|---|---|---|
| `site-analysis` | 라이브 | SiteAnalysisDetail + VerificationBadge |
| `feasibility` | 라이브 | FeasibilityEditorV2 (`feasibility/page.tsx:2`) |
| `cost` | 라이브 | BimCostDashboard (`cost/page.tsx`) |
| `design` | 라이브 | DesignStudio (`design/page.tsx:4`) |
| `esg` | 부분 | ProjectEsgWorkspaceClient + ModulePlaceholder 혼재 + VerificationBadge |
| `report` | 라이브 | `report/page.tsx:2` ProjectReportWorkspaceClient → reports/investor/generate, ReportPdfDownload, BankReadyReportBuilder |
| `legal` / `construction` / `finance` / `bim` / `contracts` / `operations` / `drone` / `blockchain` | 목업/부분 | 해당 page.tsx들이 ModulePlaceholder import (§목업 목록) |
| `cad` / `multi-parcel` / `supervision` / `agent` / `permit` | 라이브 | client 컴포넌트 위임 |

### 독립 메뉴
| 라우트 | 상태 | 근거 |
|---|---|---|
| `auction` | 라이브 | `auction/page.tsx:5` useAIAnalyze, 177줄 자체구현 |
| `g2b` | 라이브 | G2BBidDashboard + G2bEstimateSimPanel |
| `sales`, `sales/[siteId]`, `sales/projection` | 라이브 | SalesSiteList 등 |
| `analytics/investment`·`cost`·`esg` | 라이브 | 전부 VerificationBadge 결합 |
| `analytics/carbon`·`iot` | 목업 | ModulePlaceholder 단독 |
| `land-schedule`·`registry-analysis`·`desk-appraisal` | 라이브 | DeskAppraisalReportClient 등 |
| `design-studio`·`bim-studio` | 라이브 | useProjectContextStore + dynamic ssr:false |
| `settings/*`(4종) | 라이브 | admin secrets/users/billing/lists |
| `guide` | 정적 | 안내성 |

### 사이드바 IA에서 제거된 라우트(고아 페이지)
다음 page.tsx는 **존재하나 사이드바 어디에서도 링크되지 않음** (layout.tsx:142-153 주석에서 의도적 제거):
`agent`, `analytics/iot`, `analytics/carbon`, `digital-twin`, `inspection`, `maintenance`, `safety`, `tenant`, `tax`, `approvals`, `portfolio`, `sre`, `webrtc`, `dashboard/kdx`.
→ URL 직접 접근은 되나 UX상 도달 불가. 일부는 미작동(Cloudflare 1102/k.map 오류)으로 의도적 격리. **죽은 코드 vs 미래 복원 후보 구분 표식 부재.**

### 목업(ModulePlaceholder) 단독/혼재 페이지 (근거)
`agent`, `analytics/carbon`, `analytics/iot`, `inspection`, `maintenance`, `market-insights`, `tax`, `tenant`, `projects/page`, 그리고 프로젝트 탭 `bim/blockchain/construction/contracts/drone/esg/finance/legal/operations/report`. (report/esg/market는 라이브 컴포넌트와 혼재 = 부분)

---

## 4. 상태관리 / 데이터흐름

- **이중 스토어 구조:** `store/use-project-store.ts`(경량 currentProjectId/recent, 비영속) + `store/useProjectContextStore.ts`(모세혈관, persist). `lib/stores/index.ts`는 프록시 재내보내기.
- **모세혈관(useProjectContextStore.ts):** 10단계 LIFECYCLE_STAGES(line 125), 6종 교차모듈 데이터(site/design/feasibility/cost/esg/compliance), `withSnap`(line 227)으로 모든 mutation을 **프로젝트별 snapshot에 동시 영속** → 전환/재선택 복원. 이전 "전환 시 분석 전멸" 버그 구조적 해결 확인(line 264-300).
- **영속 범위:** `persist` name `propai-project-context` = **localStorage 단독**(line 383). 기기간 동기화는 `lib/projectSync.ts`가 `/store/projects` GET/PUT으로 옵트인 제공(로그인 시에만, line 22 토큰 체크). **비로그인/오프라인은 localStorage만**.
- **취약점:** 교차모듈 데이터의 출처/신선도(`fetchedAt`, `dataSource`)가 타입에는 있으나(line 77), 화면 렌더에서 일관 노출 안 됨 → 사용자가 "이 숫자가 언제·어디서 온 값"인지 추적 불가. **§6 혁신기회 #2.**

---

## 5. AI 해석 / 검증 배지 노출

### VerificationBadge 렌더 화면 (12곳, 근거)
analytics/esg, CostEstimationClient, InvestmentFeasibilityClient, TaxOperationsWorkspaceClient, DeskAppraisalReportClient, MarketInsightsWorkspaceClient, PermitAiWorkspaceClient, RegulationsWorkspaceClient, PipelineResultDetail, SiteAnalysisDetail, ProjectEsgWorkspaceClient, ProjectReportWorkspaceClient.

### AI 해석 카드(인터프리터) 렌더 (제한적)
ComprehensiveAnalysisPanel, AutoRecommendPanel, G2BBidAnalysisModal **3곳만** 명시적 해석 카드.
- **불일치:** CLAUDE.md 메모리는 "10개 interpreter 전부 화면 연결(설계/CAD/BIM 포함)"이라고 기록하나, 정적 검색상 해석 카드 컴포넌트의 직접 사용처는 위 3곳에 집중. 설계/CAD/BIM·시장·부지의 LLM 해석은 각 WorkspaceClient 내부 인라인 렌더일 가능성(별도 명명 컴포넌트 부재) → **해석 카드의 명명·재사용 표준화 부재**. 검증 배지(12곳)와 해석 카드(3곳) 사이 **노출 비대칭** = 일부 화면은 검증만 있고 해석 없음, 또는 그 반대.

---

## 6. 3D/CAD/BIM · 지도 · 성능 게이팅

- **dynamic ssr:false 게이팅(7곳):** bim-studio/page, projects/[id]/page, CadEditor, ParcelMapWrapper, PipelinePanelClient, LifecycleStageViews, sales/UnitGrid. → WebGL/무거운 위젯 SSR 회피 적용됨(이전 "설계패널 자동마운트 메인스레드 점유" 버그 대응 흔적).
- **glTF/Three:** CadBimIntegrationPanel(GLTFLoader), sales/Grid3D. BIM glb 로딩은 client 전용.
- **Leaflet 지도 결함 [중]:** `NearbyTransactionsMap.tsx:67-87`, `ParcelBoundaryMap.tsx` 모두 **unpkg CDN에서 leaflet.css/js를 런타임 `<script>` 주입**으로 로드. 
  - 리스크: (a) 외부 CDN 의존 → CSP 강화 시 차단, (b) `app/offline/page.tsx`(PWA 오프라인)에서 지도 무동작, (c) unpkg 장애 시 지도 전멸, (d) 번들러 트리셰이킹/버전 고정 우회. npm 의존성+dynamic import가 정석.

---

## 7. UX / 디자인 일관성 · 접근성 · i18n

- **토큰 디스크립린: 대체로 양호하나 누수 존재.** 컴포넌트에서 하드코딩 hex 다수: `#3b82f6`×15, `#f59e0b`×13, `#ffffff`×11, `#ef4444`×11, `#0a0f14`×10 등. accent/surface 토큰이 있음에도 차트·배지·그래디언트에서 직접 hex 사용 → 다크/라이트 테마 회귀 위험. (메모리상 토큰 통일 작업했으나 신규 컴포넌트에서 재발).
- **i18n 적용률 ~64%:** 대시보드 page.tsx 58개 중 37개만 dictionary 사용. 나머지 21개는 한국어 하드코딩(예: layout.tsx 사이드바 라벨 전부 한국어 문자열 `"대시보드"` 등 line 112-167, dictionary 미경유). 한/영/중 3로케일 선언(`i18n/config.ts:1`)이나 **사이드바·다수 클라이언트 컴포넌트는 ko 고정** → en/zh 전환 시 메뉴가 한국어로 남음.
- **접근성:** SidebarNav에 `aria-hidden`/`sr-only` 일부 적용(SidebarNav.tsx:50, layout.tsx:190). 단 아이콘 버튼·차트 alt/aria-label 체계적 검증 필요(표본 범위 밖, 후속 권고).
- **관리자 게이팅:** SidebarNav.tsx:29-43이 `/auth/me`로 role 확인 후 adminOnly 섹션 노출. 확인 전엔 숨김(안전 기본값) — 양호.

---

## 8. 사용자 여정 데이터흐름 단절 Top

1. **[중] 임의 호스트에서 전량 실패** — `api-client.ts:71` localhost 폴백. 프로덕션 화이트리스트(4t8t/pages.dev/propai.kr) 밖 도메인 접속 시 모든 API가 사용자 브라우저의 localhost:8000로 향함. 신규/스테이징 도메인 추가 시 v1·v2 양쪽 화이트리스트 동시 수정 필요(2.1).
2. **[중] 비로그인 작업물 기기 이동 불가** — Context는 localStorage 단독 영속. 로그인 후 `/store/projects` 동기화 옵트인 전까지 다른 기기/브라우저에서 분석 0건으로 보임(projectSync.ts:22).
3. **[중] 프로젝트 상세 핵심 탭 일부 목업** — legal/construction/finance/bim 등이 ModulePlaceholder. 라이프사이클 10단계 중 일부 탭 진입 시 "준비중" 표시 → 여정 중단 체감.
4. **[하] 교차모듈 값 출처 미표시** — site-analysis→feasibility/cost/esg로 흐른 숫자의 출처·시점이 화면에 비일관 노출. 사용자가 "왜 이 값?" 추적 불가.
5. **[하] 사이드바 도달 불가 고아 페이지 14개** — URL은 살아있으나 메뉴 미링크. 일부 미작동. 사용자가 검색/북마크로 진입 시 깨진 경험.
6. **[하] AI 해석 카드 비대칭** — 검증 배지 12곳 vs 명시 해석 카드 3곳. 검증만 있고 해석 없는 화면에서 "왜 통과/실패인지" 설명 공백.

---

## 9. 혁신 기회 — 프론트 UX/시각화 공백 (우선순위)

1. **라이프사이클 진행 레일(Lifecycle Progress Rail)** — 10단계(LIFECYCLE_STAGES) 완료/현재/추천(`getNextRecommendedStage` 이미 존재, line 372)을 상시 가시화하는 좌측/상단 스테퍼. 현재 store에 데이터는 있으나 전역 시각화 컴포넌트 부재. 효과: 여정 단절 #3 체감 완화.
2. **데이터 계보(Data Lineage) 툴팁** — 모든 교차모듈 숫자에 `dataSource`/`fetchedAt`(타입에 이미 존재, line 77) hover 출처·신선도 배지. 할루시네이션 방지 서사 강화 + 신뢰도 시각화.
3. **단일 검증·해석 통합 카드 표준화** — VerificationBadge(12곳)와 해석 카드(3곳)를 `<AnalysisVerdict>` 단일 컴포넌트로 통합, 전 분석 화면 일관 배치. 비대칭 해소(#6).
4. **오프라인-퍼스트 지도** — Leaflet CDN 주입(map:67-87)을 npm+dynamic import로 전환하고 PWA(offline/page) 타일 캐시. CSP/장애 내성 + 오프라인 답사 UX.
5. **프로젝트 비교 보드** — recentProjectIds(use-project-store:5) + snapshots 활용해 2~3개 프로젝트 ROI/수지/ESG 나란히 비교. 데이터는 이미 영속, 뷰만 부재.
6. **i18n 커버리지 자동 게이지 + 사이드바 라벨 dictionary화** — 적용률 64%→100%. 특히 layout.tsx 메뉴 라벨(112-167) dictionary 경유. en/zh 시장 진입 전제.
7. **고아 라우트 정리/복원 대시보드** — 미링크 14개 페이지를 "베타/관리자/폐기" 태그로 분류하는 내부 라우트 인벤토리 화면. 죽은 코드 가시화.
8. **AI 해석 스트리밍 UX** — `/ai/llm`(timeoutMs 90s, ai-analyze-client.ts:50) 응답을 토큰 스트리밍으로 점진 렌더. 현재는 최대 120s 블로킹 대기("분석중..." 정적).
9. **토큰 가드 린트 + 차트 팔레트 토큰화** — 하드코딩 hex(상위 #3b82f6 등)를 CSS 변수 차트 팔레트로 치환, eslint 규칙으로 신규 hex 차단. 다크/라이트 회귀 근절.
10. **새 프로젝트 → 첫 분석 원스텝 마법사** — new/page.tsx가 이미 생성+billing+컨텍스트 시드+push까지 연결(62-93). 그 직후 site-analysis 자동 트리거 + 진행 토스트로 "빈 화면 도착" 제거.

---

## 10. 참조 (근거 파일:라인)

- `lib/api-client.ts:65-72, 270-288` — 로컬 폴백 하드코딩, v1/v2 호스트 화이트리스트 이중 유지
- `store/useProjectContextStore.ts:125-138, 227-237, 264-300, 383` — 라이프사이클·withSnap 영속·전환 복원·localStorage persist
- `store/use-project-store.ts:1-27` — 경량 비영속 프로젝트 스토어
- `lib/projectSync.ts:22, 31, 79` — 기기간 동기화(/store/projects) 옵트인
- `app/[locale]/(dashboard)/layout.tsx:111-178` — 사이드바 IA 8섹션, 고아 라우트 제거 주석(142-153), 한국어 라벨 하드코딩
- `components/layout/SidebarNav.tsx:29-43, 57` — /auth/me 관리자 게이팅, active 매칭
- `app/[locale]/(dashboard)/projects/new/page.tsx:62-93` — 생성→과금→컨텍스트 시드→push 여정
- `components/feasibility/AutoRecommendPanel.tsx:258` — postV2 /feasibility/auto-recommend
- `components/projects/ProjectReportWorkspaceClient.tsx:225,265` — /projects/{id}, /reports/investor/generate
- `components/map/NearbyTransactionsMap.tsx:67-87` — Leaflet CDN 런타임 주입
- `i18n/config.ts:1-11` — ko/en/zh-CN 로케일 선언
- BE 검증: `apps/api/main.py`(런타임 진입점) + 등록 prefix 60여종, `apps/api/app/routers/{cost,g2b_bid,ai_analyze,pipeline}.py` 자체 prefix
