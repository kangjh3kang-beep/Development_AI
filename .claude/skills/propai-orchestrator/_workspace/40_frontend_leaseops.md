# 40 — 프론트엔드: 운영서비스 1탄 (임대·임차인 관리)

## 1. 신규/변경 파일·라우트·사이드바
**신규**
- `apps/web/components/lease-ops/types.ts` — 백엔드 정합 타입(LeaseSummaryResponse, Tenant, LeaseContract, Create 입력, MutationResponse, LeaseAnalyze/Nps). `LEASE_STATUSES` 화이트리스트.
- `apps/web/components/lease-ops/LeaseOpsWorkspace.tsx` — "use client" 워크스페이스(대시보드+임차인 CRUD+계약 CRUD+상태변경+결합 AI/NPS).
- `apps/web/app/[locale]/(dashboard)/operations/lease/page.tsx` — thin shell. `isValidLocale` 가드 후 `<LeaseOpsWorkspace locale=.../>`만 렌더.

**변경(무파괴)**
- `apps/web/app/[locale]/(dashboard)/layout.tsx` — 신규 그룹 **"자산 운영"** 추가(+6줄). `assetOpsNavigation = [{ /operations/lease, "임대·임차인 관리", IconProject }]`, sections 배열에 "공공입찰·경공매" 다음 위치 삽입. 기존 그룹/순서/아이콘 무파괴.

**라우트**: `/{locale}/operations/lease`
**사이드바 위치**: 그룹 "자산 운영" (공공입찰·경공매 ↔ 지원 사이)

★ 기존 `components/operations/TenantWorkspaceClient.tsx`(/projects 데모)는 **건드리지 않음**. 신규 페이지로 분리해 혼란 방지.

## 2. 대시보드/CRUD/AI결합 구현
- **대시보드(GET /lease-ops/summary)**: KPI 6종 — 총세대·임대중·공실·**공실률(accent 강조)**·월임대료합·연환산수익. `by_status`는 recharts `BarChart`(상태별 분포, Cell 색상). summary.ok=false/빈데이터 시 안내문.
- **임차인 관리**: 목록(GET /tenants 테이블) + 등록 폼(POST /tenants: name필수/contact/business_type). 성공 시 invalidate tenants.
- **임대계약 관리**: 등록 폼(POST /contracts: unit_label·lessee(임차인 select)·deposit·monthly_rent·start/end_date·area_sqm·status). 목록(GET /contracts, status 쿼리 필터) 테이블. 행별 상태변경 select(PATCH /contracts/{id}/status) → 성공 시 contracts+summary invalidate(대시보드 자동갱신).
- **(결합) 계약서 AI분석**(POST /leases/analyze): textarea 입력→분석 결과 표시. 응답 summary/analysis/result/message 관용 파싱.
- **(결합) 임차인 만족도 NPS**(POST /tenant/satisfaction/nps): 버튼→nps/score 표시.
- 결합 섹션은 **404 시 자동 숨김**(analyzeAvailable/npsAvailable state) — 백엔드 미가용해도 무파괴.

## 3. 403/빈데이터/로딩/에러 처리
- **canUseLiveApi**(live 모드 또는 토큰 보유) 게이트 — 미충족 시 "로그인 필요" 안내, 쿼리 disabled.
- **403(권한 없음)**: `extractErrorMessage`가 403을 별도 분기 → `forbidden` 플래그. 어느 쿼리든 403이면 Hero에 운영 권한 안내 배너(구독자 viewer는 leases:read 미보유 가능성 명시). 403 시 일반 에러카드는 숨김(중복 방지).
- **401**: "로그인 필요" 메시지(api-client 자동 refresh 후에도 실패 시).
- **빈데이터**: summary 없음/임차인0/계약0/필터결과0 각각 전용 안내문(추정·하드코딩 없이 0 그대로 노출하는 백엔드 정직성과 일관).
- **로딩**: `SkeletonLoader`. **에러**: `WorkspaceQueryErrorCard`(재시도 → 3쿼리 refetch).

## 4. tsc/eslint
- `npx tsc --noEmit` → **EXIT 0**.
- `npx eslint`(신규 3파일) → **EXIT 0, 0 warning**(초기 _locale 미사용·tenants useMemo 경고 2건 정리: `void locale` + `useMemo(tenants)`).
- layout.tsx의 eslint 경고 4건(headers·AuthGuard·IconSiteAnalysis·IconDesign)은 **본 변경과 무관한 기존 경고**(diff는 +6줄 추가뿐).
- git diff 확인: layout +6줄만, apiClient import 보존(린터 되돌림 없음). TenantWorkspaceClient 무변경.

## 5. 커밋
`feat(lease-ops): 임대·임차인 관리 화면 — 공실률·임대수익 대시보드·임차인/계약 CRUD + 사이드바`
add 명시경로: components/lease-ops/, app/.../operations/, layout.tsx (해시는 보고 본문 참조)

## 6. 백엔드 정합
- 경로: 전부 `/lease-ops/*` (apiClient v1, get/post/patch). summary·tenants·contracts(+status 쿼리)·status PATCH 6엔드포인트 매핑.
- 응답 스키마 정합(39 보고 6항):
  - summary `{ ok,total_units,leased,vacant,vacancy_rate_pct,monthly_rent_total,annual_income_est,by_status }`
  - tenants `{ ok,tenants:[{id,name,contact,business_type}] }`
  - contracts `{ ok,contracts:[{id,unit_label,lessee_name,deposit,monthly_rent,start_date,end_date,status,area_sqm}] }`
  - POST `{ ok,id }` / PATCH `{ ok,id,status }`
- status 화이트리스트(active/occupied/leased/expired/vacant/pending) = 백엔드 VALID_STATUSES 정합. 폼 select·필터·행별 변경 모두 동일 목록.
- POST /contracts의 `lessee`는 tenant id(select value=tenant.id)로 전송 — 백엔드 lessee(uuid→tenants.id) 정합.
- 결합: /leases/analyze, /tenant/satisfaction/nps 기존 엔드포인트 무파괴 재사용(404 graceful).
