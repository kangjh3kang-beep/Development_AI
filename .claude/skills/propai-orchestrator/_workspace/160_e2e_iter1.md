# PropAI 전체 워크플로우 라이브 E2E 오류 전수 수집 — 무결점 검증 루프 1차 (160_e2e_iter1)

- 일시: 2026-06-07
- 환경: 라이브 https://www.4t8t.net (sw v87, 백엔드 version 62.0.0)
- 계정: test@4t8t.net (구독자)
- 도구: agent-browser 세션 qa (실제 로그인 → 라우트 순회 → console/network 캡처 + DOM 에러바운더리 텍스트 감지)
- 제외 규칙: 402(과금/코인 게이트)·401/403(인증)은 정상으로 제외. /auth·/login·favicon·sourcemap·font 노이즈 제외.
- **코드 수정 없음. 오류 목록·정상판정만.**

---

## 0. 선결 발견 — 환경/전제 불일치 (중요)

| # | 항목 | 발견 | 영향 |
|---|------|------|------|
| E0-1 | **지정 대상 프로젝트 부재** | 작업 지정 프로젝트 `8f07026a-2ac2-4489-94e2-b11a4c5faaba`(의정부/185㎡)는 이 계정에 **존재하지 않음**. `GET /api/v1/projects/8f07026a-…` → **404**, 화면은 "알 수 없는 프로젝트"로 렌더(크래시 아님). localStorage·store에도 미존재. | 지정 프로젝트로는 워크플로우 실행 불가. → 이 계정의 **실존 프로젝트로 대체 검증** 수행. |
| E0-2 | **로그인 경로** | `/login`은 404. 실제 경로는 로케일 프리픽스 필수 `/ko/login`·`/en/login`. 대시보드도 `/dashboard` 404 → 실제는 `/ko`(홈). | 라우트는 모두 `/ko/...` 또는 `/en/...` 프리픽스 필요. |
| E0-3 | **계정 코인 0원(코인 소진)** | 헤더 표시 "코인 698원 사용 / **0원**", "코인 소진 · 추가결제". | **모든 AI 분석 버튼이 402 또는 클라이언트단 차단**. 실제 분석 결과(물량·수지·LLM해석 등) 출력은 본 루프에서 검증 불가(과금 게이트=정상). 분석 산출물 무결점 판정은 코인 충전 후 재실행 필요. |

**대체 검증 프로젝트:** `1167cdda-9b1c-4698-b4f7-7c58526f28ac` (구독자검증PJ, 서울 강남구 역삼동, **일반상업지역, 용적률 1300%**, 층수 17, GFA 6500㎡). 작업이 기대한 "일반상업 1300% 정합" 검증 조건과 일치하여 적합한 테스트베드.

---

## 1. 오류 표 (심각도순)

| 심각도 | 라우트 | 증상 | 콘솔/네트워크 상세 | 재현스텝 |
|--------|--------|------|--------------------|----------|
| **HIGH** | `/ko/projects/{id}/feasibility` | 네트워크 5xx (백엔드 장애) | `GET https://api.4t8t.net/api/v2/feasibility/repos/{id}/log` → **503** (2회 연속 재현·일관). 분석원장(해시체인 ledger) 로그 조회 엔드포인트. redis unhealthy 의존 추정. 페이지 자체는 렌더됨(크래시 아님, "완성도 14%" 표시). | 수지분석 페이지 진입 즉시 자동 호출. |
| INFO | `/api/v1/projects/8f07026a-…` | 404 | 지정 대상 프로젝트가 백엔드/스토어에 미존재(E0-1). 환경 전제 오류. | 지정 프로젝트 ID로 진입. |
| INFO(정상) | site-analysis | 402 ×2 | `POST /api/v1/zoning/analyze` 402, `POST /api/v2/feasibility/auto-recommend` 402 | 코인 0원 과금 게이트. 제외 규칙 대상. |
| INFO(정상) | legal | 402 ×2 | `POST /api/v1/regulation/analyze` 402 | 과금 게이트. |
| INFO(정상) | feasibility | 402 | `POST /api/v2/feasibility/baseline` 402 | 과금 게이트. |
| INFO(정상) | permit | 402 | `POST /api/v1/permits/ai-analysis` 402 | 과금 게이트. |
| INFO(정상) | bim | 무반응(클라단 차단) | "BIM 물량 산출" 클릭 → **네트워크 호출 0건**, "코인 소진·추가결제" 표시. 콘솔 에러 없음, Failed to fetch/500 **없음**(이전 수정 유지). | 코인 0원으로 클라단 사전 차단. |

> **유일한 진성 결함은 feasibility의 503 1건.** 나머지 4xx는 전부 402 과금 게이트(정상). 어떤 페이지도 Next 에러바운더리("페이지 오류")·client-side exception·toLocaleString 크래시·Failed to fetch 미발생.

스크린샷(오류건): `.claude/skills/propai-orchestrator/_workspace/screenshots/160_feasibility_503.png`

---

## 2. 단계별 정상작동 판정 (무결점 ✓/✗)

대상 프로젝트: `1167cdda-…` (역삼동·일반상업·1300%). 판정 기준 = 진입 크래시 없음 + 콘솔에러 없음 + 과금외 네트워크 실패 없음. (분석 산출물은 코인 0원으로 미실행 → "게이트" 표기)

| # | 단계 | 라우트 | 진입(크래시/콘솔) | 네트워크 | 판정 | 비고 |
|---|------|--------|-------------------|----------|------|------|
| 1 | 입지/부지분석 | `/projects/{id}/site-analysis` | ✓ 무크래시 | 402(게이트) | **✓** | **toLocaleString 크래시 재발 없음(수정 유지)**. 용도지역=일반상업지역, 건폐율80%/용적률1300% 정합 표시. |
| 2 | 법규검토 | `/projects/{id}/legal` | ✓ | 402(게이트) | **✓** | regulation/analyze 자동호출=과금게이트. |
| 3 | 건축설계 | `/projects/{id}/design` | ✓ | 없음 | **✓** | **용적률 1300% 정합(일반상업), 400% 환각 재발 없음**. 적용1300%/한도1300%, 예상전용연면적 ≈5,070㎡. |
| 4 | BIM 물량 | `/projects/{id}/bim` | ✓ | 클릭 시 0건(코인차단) | **✓(게이트)** | **Failed to fetch/500 재발 없음**(이전 수정 유지). 메타데이터(층수17) 라이브 로드 정상. 산출 실행은 코인 필요. |
| 5 | 공사비/시공 | `/projects/{id}/construction` | ✓ | 없음 | **✓** | 진입 정상. |
| 6 | 수지분석 | `/projects/{id}/feasibility` | ✓ 무크래시 | **503**(ledger log) + 402(baseline) | **✗** | **유일 진성결함: repos/{id}/log 503**. 페이지는 "완성도14%"로 렌더. |
| 7 | 개발금융 | `/projects/{id}/finance` | ✓ | 없음 | **✓** | 진입 정상(PF/DSCR 자동산출은 미실행). |
| 8 | ESG | `/projects/{id}/esg` | ✓ | 없음 | **✓** | 진입 정상. |
| 9 | 인허가 | `/projects/{id}/permit` | ✓ | 402(게이트) | **✓** | ai-analysis 자동호출=과금게이트. |
| 10 | 통합보고서 | `/projects/{id}/report` | ✓ | 없음 | **✓** | 진입 정상(은행보고서 생성은 미실행). |

### 글로벌/부가 라우트 (전부 진입 무크래시·무에러)

| 라우트 | 판정 | 비고 |
|--------|------|------|
| `/ko` (대시보드) | ✓ | store/projects·auth/me·billing 200. |
| `/ko/precheck` (90초 진단) | ✓ | |
| `/ko/projects` (목록) | ✓ | |
| `/ko/projects/new` (생성) | ✓ | |
| `/ko/market-insights` (시장분석) | ✓ | |
| `/ko/permits` (인허가) | ✓ | |
| `/ko/regulations` (개발규제) | ✓ | |
| `/ko/analytics/cost` (공사비) | ✓ | |
| `/ko/land-schedule` (토지조서) | ✓ | |
| `/ko/registry-analysis` (등기열람) | ✓ | |
| `/ko/desk-appraisal` (AI시세보고서) | ✓ | |
| `/ko/analytics/investment` (ROI) | ✓ | |
| `/ko/auction` (경매·공매) | ✓ | |
| `/ko/g2b` (나라장터) | ✓ | |
| `/ko/sales` (분양관리) | ✓ | |
| `/ko/sales/sites` (현장앱) | ✓ | |
| `/ko/sales/projection` (분양요약) | ✓ | |
| `/ko/design-studio` (CAD) | ✓ | |
| `/ko/bim-studio` (BIM·적산) | ✓ | |
| `/projects/{id}` (개요) | ✓ | 실존 프로젝트는 정상. 지정 8f07026a는 "알 수 없는 프로젝트"(E0-1). |

---

## 3. 무결점 판정 요약

- **프론트엔드 안정성: 무결점.** 전 라우트(프로젝트 10단계 + 부가 20여 페이지) 진입 시 Next 에러바운더리·client-side exception·toLocaleString·Failed to fetch **0건**. 이전 수정(site-analysis toLocaleString, BIM 500, design 400%환각)이 **모두 회귀 없이 유지**됨.
- **진성 백엔드 결함 1건(HIGH):** `GET /api/v2/feasibility/repos/{id}/log → 503` (수지분석 페이지, 일관 재현). 분석원장 로그 엔드포인트, redis unhealthy 의존 추정. → **다음 수정 루프 P0 후보.**
- **검증 한계(2건, 환경):**
  1. 지정 프로젝트(8f07026a/의정부)는 미존재 → 실존 프로젝트(1167cdda/역삼동·일반상업1300%)로 대체.
  2. 계정 코인 0원 → 모든 AI 분석 버튼이 402/클라단 차단되어 **실제 분석 산출물(물량·수지·금융·ESG·인허가·보고서 결과값)은 본 루프에서 미검증**. 산출물 무결점 판정은 **코인 충전 후 2차 루프** 필요.
- **redis·qdrant unhealthy**: /health "degraded"(기존 정상 범주). 단, redis 의존 엔드포인트(feasibility ledger log)가 503을 유발하는 점은 사용자 영향 있음.

## 4. 다음 루프 권고
1. (P0) feasibility `/repos/{id}/log` 503 원인 규명·수정(redis 미가용 시 graceful fallback).
2. (P1) 코인 충전 후 10단계 분석 버튼 실제 실행 → 산출물 정합/환각 전수 검증(2차 루프).
3. (P2) 지정 대상 프로젝트 ID 정합(8f07026a 의정부 시드 생성 또는 올바른 계정/ID 확인).
