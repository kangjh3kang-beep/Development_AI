# [통합자 인계 — 배포 요청] 시장·시세 SSOT 일원화 + 전역 전파방지

**작성:** 2026-06-28 · 작성 세션: Development_AI_market
**브랜치:** `fix/market-insights-ssot-unification` (origin/main 기반 · 무발산 · 5커밋)
**상태:** 코드 완료 · 전 검증 통과 · 독립 리뷰 4회 APPROVE(8.5~9) · **PR/머지·배포 대기**

---

## 1. 배포 요청 (통합자 작업)
1. **PR 생성 → 머지** (`fix/market-insights-ssot-unification` → main). 무발산이라 충돌 없음.
2. **A1 프론트 재빌드** (158.179.174.207 · Cloudflare 자동 무효화). next build 로컬 exit 0 확인됨.
3. **백엔드 블루그린 배포** (168.110.125.89 · `ssh ~/.oci.key 'deploy.sh' origin/main`). 백엔드 변경:
   regulation/building_compliance/permits 라우터 + regulation_analysis_service + market_report_service.
4. (선택·권장) **공공 API 키 점검** — 시장보고서 실데이터화: SGIS_CONSUMER_KEY·KOSIS_API_KEY·VWORLD 키.
   미설정 시 코드가 "데이터 없음(공공 API 키 미설정)"으로 **정직 표기**(무목업) — 크래시 없음.

## 2. 커밋 (5)
| 순서 | 내용 |
|---|---|
| 1 | 시장 SSOT 일원화 P0~P3: 좌표누수(강릉) · 단일필지 고착 · 분석시작 1클릭 일괄 · PDF 재구성(feasibility/평형MD·정직표기) |
| 2 `f0a6d2f5` | 전파방지① 좌표누수 공용가드(NearbyTransactionsMap projectId)+LandSchedule pnu |
| 3 `98c7fa6c` | 전파방지② 다필지 전파(공용 lib/parcel-rows.ts + 규제·인허가·법규 3엔드포인트 _integrated_context 재사용) |
| 4 `29fe248c` | MED2 통합 메타 뱃지(IntegratedParcelsBadge — 통합 N필지·통합면적·우세용도 가시화) |
| 5 `90838ded` | P1+enabler: store ParcelData.zoneCode(프로젝트 스코프 폴백 zone 통합)+ProjectPermit/ProjectLegal 배선 |

## 3. 라이브 검증 시나리오 (배포 후)
**용인시 수지구 신봉동 56-1 외 12필지(12,079㎡) 엑셀 업로드 → 시장·시세 분석 실행:**
- [ ] 주변 실거래 지도 마커·필지 구획도가 **용인**(강릉 오표시 0).
- [ ] 통합 종합분석·Feasibility 대지면적이 **12,079㎡**(단일 1,161㎡ 아님).
- [ ] 「분석 시작」 1클릭으로 지도+시장보고서 동시 생성.
- [ ] 결과/보고서에 "통합 12필지 기준 · 통합면적 12,079㎡ · 우세용도 …" **뱃지** 표시.
- [ ] PDF에 Feasibility·평형MD 섹션 포함, 빈 narrative/소득/공시지가가 "데이터 없음"/"-"로 정직 표기(mock·0만 0).
- [ ] 규제·인허가·법규(Regulations/Approvals/Permits/ProjectPermit/ProjectLegal)도 다필지 업로드 시 통합면적·우세용도 기준 + 뱃지.

## 4. 검증 근거
- tsc 0 · eslint 0 errors(선재 경고만) · next build exit 0 · py_compile OK · ruff 무신규(8파일 base==now).
- 독립 코드리뷰 4회: 시장 8.5 · ② 8.5 · Item3/P1 9.0 — critical/high 0, MED+ 전건 반영.

## 5. 후속(비차단·선택)
- store ParcelData에 farPct/bcrPct 추가(피커 경로 패리티) — 현재 백엔드 재계산으로 정확, 불요.
- 오탐/저영향(DesignChangePredict·ProjectFinance AVM)은 본질적 단일·주소기반이라 다필지 N/A.
