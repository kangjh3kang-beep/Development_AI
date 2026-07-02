# [HANDOFF → 다음 세션] 시장·시세 페이지 SSOT/다필지/좌표 — 라이브 검증 종결

**작성:** 2026-07-02 · 세션: 17970226 (Development_AI_market)
**상태:** ✅ **완료·머지·배포·라이브 검증 종결** — 이 스레드는 닫힘. 아래는 인계용 상태 요약 + 잔여 선택 항목.

---

## 1. 한 줄 요약
사용자 원본 버그(용인 다필지 업로드 → 지도/분석이 **강릉**·단일필지·PDF부실)를 근본 수정하고, **전역 전파방지 스윕 + 레이아웃 단순화 + 라이브 발견 갭(인테이크→보고서 store폴백)까지** 모두 origin/main 통합·배포·**라이브 검증 완료**.

## 2. 라이브 검증 결과 (4t8t.net, admin 로그인, 2026-07-02)
- ✅ **강릉 좌표 버그 수정**: repPnu 용인(4146510500)·feasibility 자연녹지·강릉/하시동/상시동 텍스트 0·1,161㎡ 없음.
- ✅ **백엔드 다필지 통합**: `/regulation/analyze`·`/building-compliance/check`·`/permits/compliance-check` 모두 통합면적·우세용도 반환(테스트 500+300→800㎡, 33필지→11,465㎡). 단일필지(parcels 미전달)=integrated 없음(무회귀).
- ✅ **시장보고서 feasibility**: 대지면적 **11,465㎡(통합 33필지)**·`IntegratedParcelsBadge "통합 N필지 기준"` 렌더·총사업비 1,032억.
- ✅ **레이아웃 단순화**: OrchestratorPanel "고급·분양성·분양가 ▶펼치기" 접기 격리(sw v375).

## 3. 머지·배포 현황
| 작업 | 브랜치 | 상태 |
|---|---|---|
| 시장 SSOT + 전파방지①② + MED2 + P1 | `fix/market-insights-ssot-unification` | PR#126 머지·배포 |
| 레이아웃 단순화(presentational) | `feat/market-page-layout-simplify` | PR#140로 내용 통합·배포 |
| 인테이크→보고서 store폴백 | `fix/market-report-store-parcels` | 내용 origin/main 통합·배포 |

★origin/main은 이후 타 세션이 계속 확장 중(`preferredEntryAddress`·`ContextHeader`·`SatongMultiMap` 등). **내 핵심 패턴은 보존됨**: NearbyTransactionsMap projectId 가드, `lib/parcel-rows.ts`(entriesToParcelRows/parcelDataToRows/shouldSendParcels), IntegratedParcelsBadge, ParcelData.zoneCode.

## 4. 핵심 아키텍처(다음 세션이 알아야 할 것)
- **다필지 계약 단일출처** = `apps/web/lib/parcel-rows.ts`. 다필지 통합이 필요한 요청은 전부 이걸 거쳐 `parcels[]`를 만든다. 백엔드 `ComprehensiveAnalysisService._integrated_context`(면적가중 `_aggregate_integrated_zoning`)가 소비 — **산식 복제 금지**.
- **두 입력 경로**: (a) 컴포넌트 자체 `ProjectAddressInput.onEntriesChange`→runEntries, (b) '지도 기반 필지 입력(인테이크)'→store(`siteAnalysis.parcels`). **소비처는 반드시 둘 다 커버**: `runEntries.length ? entriesToParcelRows(runEntries) : parcelDataToRows(siteAnalysis.parcels)`. (이걸 빠뜨려 라이브서 단일필지 갭이 났음 — 재발주의.)
- **좌표 누수 가드**: 지도 컴포넌트가 store pnu를 쓸 땐 `projectId ? siteAnalysis : null`로 가드(비프로젝트 stale 차단).

## 5. 검증 교훈(★재사용)
- **라이브 검증은 `grep` 금지**(㎡·한글에서 오탐/누락) → **python `json.load` 파싱이 권위**.
- `market/report`는 **인증 필요**(익명 curl 403). 무인증 검증은 regulation/building-compliance/permits로.
- 브라우저 자동화: `npx -y agent-browser@latest --session propai`(chromium 설치돼 있음). admin **admin@4t8t.net / admin1234** 로그인 됨. 세션 상태 `/tmp/propai_auth.json`.

## 6. 잔여 선택 항목(비차단·다음 세션이 원하면)
- **PDF 실물 내용 확인**: feasibility·평형MD 섹션·정직표기(빈 narrative/mock/공시지가0)를 로그인 상태로 다운로드해 육안 확인(코드·리뷰는 완료, 실물 육안만 미실시).
- 오탐/저영향 소비처(DesignChangePredict·ProjectFinance AVM)는 본질적 단일/주소기반 = 다필지 N/A.
- 상위 백로그(무관): [[project_self_healing_growth_agent_plan]] SHGA(P0 ROI), 성장루프 prod 미가동 등.

## 7. 배포 방법(참고)
프론트=158.179.174.207 A1 재빌드(수동)·백엔드=168.110.125.89 블루그린(`ssh ~/.oci.key 'deploy.sh' origin/main`). 둘 다 통합자 수동. sw 버전으로 프론트 배포 반영 확인.
