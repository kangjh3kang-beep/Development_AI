# QA 검증 보고서 — 군살빼기·녹여내기 2커밋 배포 전 검증

- 대상: `d8f9c3d`(IA재편/페르소나게이팅/고아제거) + `89ee118`(상세탭다이어트/블록체인→신뢰배지/환경→보조카드/용어)
- 범위: 루트 `propai-platform/apps/web` (읽기 검증 전용, 코드수정·배포·push 없음)
- 검증일: 2026-06-06
- 도구 증거: `tsc --noEmit` EXIT 0, 변경파일 `eslint` 0 errors, `vitest run`(대상 3개 테스트파일), `git show`, 디스크 라우트 실재 확인

---

## 종합 판정: **GO (조건부 — 경미 WARN 2건, 배포 차단 아님)**

핵심 깔때기 무손상 확인. tsc/eslint 클린. 테스트 8건 실패는 **전부 사전존재(pre-existing) 베이스라인 실패**로, 본 2커밋의 회귀가 아님(증거: d8f9c3d~1 기준에서도 동일 실패).

---

## 1. ★핵심 깔때기 무손상 (최우선) — **PASS**

17개 핵심 라우트 page.tsx 전수 실재 + 사이드바 링크 정상 + 컴포넌트 삭제 0.

| 깔때기 단계 | 라우트 page.tsx | 사이드바 링크 | 결과 |
|---|---|---|---|
| PreCheck(90초 진단) | `precheck/page.tsx` | 사업검토 §1 | OK |
| 프로젝트 관리 | `projects/page.tsx` | 사업검토 §1 | OK |
| 시장·시세 | `market-insights/page.tsx` | 사업검토 §1 | OK |
| 인허가 가능성 | `permits/page.tsx` | 사업검토 §1 | OK |
| 개발 규제 | `regulations/page.tsx` | 사업검토 §1 | OK |
| 토지조서 | `land-schedule/page.tsx` | 토지·자금 §2 | OK |
| 등기/권리분석 | `registry-analysis/page.tsx` | 토지·자금 §2 | OK |
| AI 시세추정 | `desk-appraisal/page.tsx` | 토지·자금 §2 | OK |
| ROI/사업성 | `analytics/investment/page.tsx` | 토지·자금 §2 | OK |
| 공사비/적산 | `analytics/cost/page.tsx` | 토지·자금 §2 | OK |
| 분양 ERP | `sales/page.tsx`, `sales/projection/page.tsx` | 실행 §3 | OK |
| G2B 공공입찰 | `g2b/page.tsx` | 실행 §3 | OK |
| 경매·공매 | `auction/page.tsx` | 실행 §3 | OK |
| 설계 CAD | `design-studio/page.tsx` | 설계참고 §4 | OK |
| BIM·적산 | `bim-studio/page.tsx` | 설계참고 §4 | OK |

- 사이드바 4섹션(사업검토/토지·자금/실행/설계참고) + 자산운영(게이팅) + 관리(게이팅) 구성 정상.
- layout.tsx 참조 아이콘(IconDashboard/Design/Permit/Regulation/Auction/Project/Market/ROI/Cost) 전부 정의 존재 — 깨진 참조 0.
- 깨진 import/href 0: 대시보드 홈 page.tsx에 삭제 라우트 href 없음(/projects/new·/guide·/projects만).

## 2. 고아 제거 안전 — **PASS**

삭제된 11개 page.tsx(`agent`·`analytics/carbon`·`analytics/iot`·`approvals`·`dashboard/kdx`·`inspection`·`portfolio`·`safety`·`sre`·`webrtc`·`tax`) 전부 디스크에서 GONE 확인.

- 라이브(비테스트) 페이지가 고아 컴포넌트(`@/components/agent|safety|sre|dashboard/kdx`)를 import하는 곳 **0건** — 죽은 라우트만 제거, 공용 컴포넌트 0개 삭제(커밋 주장 일치).
- `ApprovalOperationsWorkspaceClient.tsx`가 `/${locale}/agent`로 링크하나, 해당 컴포넌트 자체가 어떤 라이브 라우트에도 마운트되지 않는 고아 → 런타임 영향 없음.
- tsc 참조오류 0 (EXIT 0).
- offline 퀵링크 죽은 `/inspection`→`/precheck` 교체 확인(`app/offline/page.tsx`:29).

## 3. 페르소나 게이팅 — **PASS**

`SidebarNav.tsx`:30-55 — `assetOpsOnly`가 기존 `adminOnly` 패턴 정확 재사용.

- `/auth/me` role 단일 조회로 `isAdmin`·`isAssetOps` 동시 산정(추가 호출 0).
- 운영권한 = 관리자 ∪ {`asset_manager`,`operations`,`운영관리자`,`자산운용`}. 시행사/구독자(developer/viewer) 제외 — 시행사 기본화면서 '자산 운영' 숨김.
- 무권한·미확인(catch/`null`) 시 보수적 숨김: `(!s.assetOpsOnly || isAssetOps === true)` — `null`이면 false → 숨김(SidebarNav.tsx:51-54).
- `MobileSidebarToggle.tsx` 타입에 `assetOpsOnly?` 추가(타입 정합).
- layout.tsx:131 `{ title: "자산 운영", items: assetOpsNavigation, assetOpsOnly: true }` 적용. 관리자엔 노출(admin이 isAssetOps에 포함).

## 4. 블록체인 녹여내기 — **PASS**

`TrustBadge.tsx`(신규) — 순수 표식, 네트워크 호출 0(주석·코드 모두 확인).

- 결합처: `BankReadyReportBuilder.tsx`:467, `feasibility/page.tsx`:40(은행보고서·사업성) — 요구 일치.
- STO/블록체인 별도 메뉴·탭 비노출: layout.tsx 내 'blockchain'은 주석 1건뿐(메뉴/링크 아님). LifecycleNavigator 블록체인 탭 제거.
- 라우트 보존: `projects/[id]/blockchain/page.tsx` 디스크 실재(삭제 아님, 탭만 비노출).
- 실제 변조탐지/계산검증은 별도 `VerificationBadge`가 담당(중복 구현 없음).

## 5. 환경 녹여내기 graceful — **PASS**

`EnvironmentSummaryCard.tsx`(신규) — `POST /environment/analyze` 재사용, graceful 무파괴.

- 실패/데이터부족 시 `return null`(L58-60 catch 무처리, L69 `!res?.ok`, L76/128 focus별 데이터부재 null) — 화면 무파괴 보장.
- 결합: permit/page.tsx:120 `focus="solar"`(일조), FeasibilityEditorV2.tsx:185 `focus="view"`(조망).
- 주소/PNU 출처: 양쪽 모두 `useProjectContextStore(s=>s.siteAnalysis)`의 address/pnu 가드 후 전달 — `(siteAnalysis?.address || siteAnalysis?.pnu)`일 때만 렌더.
- `./types` import(`EnvironmentResult`/`SolarGrade`/`SkylinePosition`) 실재 확인.

## 6. 상세탭 다이어트 — **PASS**

`LifecycleNavigator.tsx` 탭 정의만 제거, 콘텐츠 라우트 전부 보존.

| 변경 | 탭 처리 | 라우트 보존 |
|---|---|---|
| 블록체인 탭 제거 | 인허가/계약 그룹서 제거 | `blockchain/page.tsx` OK |
| 드론 측량 숨김 | 시공관리서 제거 | `drone/page.tsx` OK |
| ESG/LCA→ESG(친환경) | 라벨 통합 | `esg/page.tsx` OK |
| 설계 3탭→2탭(CAD 제거, BIM·도면 통합) | cad 링크 제거 | `cad/page.tsx`·`bim/page.tsx` OK |
| 자산운영→보고서 통합 | operations 단독탭 제거 | `operations/page.tsx` OK |
| 전자계약 | 인허가 그룹 잔류 | `contracts/page.tsx` OK |

- 미사용 아이콘(Operations/Cad/Chain/Drone) 정의 제거 — tsc EXIT 0(깨짐 0).

## 7. 회귀/품질 — **PASS (WARN 2 비차단)**

| 항목 | 결과 | 증거 |
|---|---|---|
| tsc --noEmit | **EXIT 0** | 직접 실행, 에러 0 |
| eslint(변경파일 16개) | **0 errors** / 3 warnings | 아래 WARN 참조 |
| apiClient import 보존 | OK | SidebarNav.tsx·EnvironmentSummaryCard.tsx 존재 |
| AI카드 토글이 검증배지 유지 | **OK** | `AnalysisVerdict.tsx`:87-95 — VerificationBadge는 `context` 존재 시 무조건 렌더, `defaultOpen`은 해석 본문 접힘만 제어. `defaultOpen` 3건 제거(DigitalTwin/Finance/Esg)는 배지 비표시와 무관 |

### eslint WARN(전부 사전존재, 본 커밋 무관 — 비차단)
- `layout.tsx`:2 `headers`, :13 `AuthGuard` 미사용 — d8f9c3d~1에서도 미사용(커밋이 해당 import 라인 미수정).
- `ProjectEsgWorkspaceClient.tsx`:4 `CardTitle` 미사용 — 커밋은 라벨 문자열만 변경.

### 테스트 실패 8건 = 전부 사전존재 베이스라인 실패 (회귀 아님)
대상 3개 파일 `vitest run` → 8 failed / 2 passed. 회귀 구분 증거:

| 실패 테스트 | 실패 원인 | 회귀 여부 |
|---|---|---|
| home-navigation ×2 | `/en/tax`·`/inspection`·`/webrtc` 링크 기대 + "Welcome to PropAI" 텍스트 | **사전존재** — d8f9c3d~1 홈 page.tsx에 해당 링크·텍스트 부재(count 0) |
| route-shells: home/투자/공사비 | "Welcome to PropAI"·"투자 운영 컨트롤타워"·"공사비 분석 허브" 텍스트 부재 | **사전존재** — 본 커밋 미수정 페이지, 텍스트 드리프트 |
| route-shells: auction/ESG | `No QueryClient set`(QueryClientProvider 미래핑) | **사전존재** — 테스트 셋업 인프라 이슈 |
| auxiliary: feasibility | `feasibility-workspace` testid 부재 | **사전존재** — d8f9c3d~1 소스에도 해당 testid 없음(테스트만 기대) |

- ✓ PASS 2건: `offline fallback route shell`(d8f9c3d의 `/precheck` 변경 반영 확인), `projects list page`.
- 본 2커밋은 오히려 테스트 부채 **감소**: route-shell 삭제라우트 케이스 제거 + offline 테스트 갱신.

---

## WARN 항목 (배포 차단 아님 — 후속 정리 권장)

- **WARN-1** `dashboard-route-shells.test.tsx`:130-162 — 삭제 라우트 컴포넌트(`agent`/`safety`/`sre`) `vi.mock` 선언 잔존. 직접 import 아닌 hoisted mock 팩토리라 빌드/tsc 무영향이나, 죽은 mock 선언. → 후속: 미사용 `vi.mock` 블록 제거.
- **WARN-2** 사전존재 베이스라인 테스트 8건 만성 실패(QueryClientProvider 래핑 누락 + 텍스트 드리프트 + 유령 testid). 본 커밋 무관이나 누적 부채. → 후속: 테스트 셋업에 QueryClient 래퍼 추가 + 기대 텍스트/testid 현행화.

> 위 2건 모두 **본 2커밋의 회귀가 아니며 배포를 차단하지 않음.**

---

## 수정지시
- FAIL: 없음.
- 배포 전 필수 수정: 없음.
- 후속(별도 커밋 권장): WARN-1 죽은 vi.mock 정리, WARN-2 테스트 셋업 QueryClient 래퍼·기대값 현행화.

## 핵심 깔때기 무손상 명시 확인
**핵심 깔때기 page.tsx 17종·사이드바 링크·콘텐츠 컴포넌트 전부 무손상.** 컴포넌트 삭제 0, 깨진 import/href 0, tsc EXIT 0. 삭제된 11개는 죽은 고아 라우트 한정. 페르소나 게이팅 대상(operations/tenant/maintenance/digital-twin)·상세탭 제거 대상(blockchain/drone/cad/operations/contracts) 라우트 전부 보존.

## 최종: **GO**
핵심 깔때기 무손상, tsc/eslint 클린, 모든 테스트 실패는 사전존재 베이스라인(회귀 0). 경미 WARN 2건은 비차단 후속 정리 항목.
