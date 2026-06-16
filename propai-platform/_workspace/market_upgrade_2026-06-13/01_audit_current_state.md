# 초정밀 시장·인구·소득 분석(MarketInsights) 모듈 현황 정밀 실사 (2026-06-13)

> 읽기전용 실사 에이전트 산출. 모든 항목 파일:라인 근거 인용. 가짜 추정 금지.

## ① 요약표 (계획 항목 × 상태 × 근거)

| Phase | 계획 항목 | 상태 | 근거 (파일:라인) |
|---|---|---|---|
| §5-1 | SGIS/KOSIS 키 환경변수(`config.py`) 추가 | **구현됨** | `apps/api/app/core/config.py:62-67` (`SGIS_CONSUMER_KEY/SECRET`, `KOSIS_API_KEY` 빈 문자열 기본값) |
| §5-1 | SGIS OAuth 토큰 발급/캐싱(Redis) | **구현됨** | `sgis_client.py:31-73` (`/OpenAPI3/auth/authentication.json`, `_set_cache(ttl=3*3600)`) |
| Phase2.5 | 토큰 재발급 `asyncio.Lock`(동시성) | **구현됨** | `sgis_client.py:22` (`_auth_lock`), `:43-47` (락 획득 후 재확인 double-check) |
| Phase2.5 | Hard Timeout(`asyncio.wait_for`) | **부분** | 토큰·통계 호출엔 적용. 단 `_fetch_with_auth_retry`(`sgis_client.py:84`)에는 미적용(데드코드) |
| Phase2.5 | Pydantic Validation Guard | **구현됨** | `sgis_client.py:155,220`, `kosis_client.py:96` |
| §5-2 | SGIS 인구통계 실연동 | **부분(스텁성)** | `sgis_client.py:161-224` — 호출은 실제지만 0건이면 하드코딩 폴백값(`base=125430`)·고정분포 주입(`:197-217`) |
| §5-2 | SGIS **인구이동** 실연동 | **스텁/오연동** | `sgis_client.py:103-159` — 인구이동 전용이 아닌 인구통계와 **동일** `searchpopulation.json` 호출(`:119`). `top_inflow_regions` 하드코딩(`:149-152`) |
| §5-3 | KOSIS 소득 통계표ID/파라미터 확정 | **스텁(예시값)** | `kosis_client.py:62-67` — `tblId="DT_1EW0010" #일자리행정통계(예시)`. 미확정 |
| Phase2.5 | KOSIS 지역코드 변환(행정동8/법정동10/시군구5) | **없음** | `kosis_client.py:65` `objL1=sigungu_cd` 직접 사용. 호출부 단순 `lawd_cd[:5]`(`market_report_service.py:191`) |
| Phase2.5 | KOSIS HTML 에러응답 방어 | **부분** | `kosis_client.py:75-80`(`errMsg`·非list 체크). HTML은 `resp.json()` 예외→except 폴백 흡수(`:99-101`), 명시 HTML 가드 없음 |
| §4 | 선택형 분석 체크박스 UI(`selectedModules`) | **구현됨** | `MarketInsightsWorkspaceClient.tsx:218-222`(`analysisOptions{sgis,kosis,katlas}`), 패널 `:340-382` |
| §4 | 선택 항목 수 기반 **예상 코인 동적 계산** | **없음** | 선택수→코인 계산 부재. 잔액 표시(`:392-396`)만. 차감은 백엔드 LLM 호출 시 자동(`:246`) |
| §4 | 백엔드 선택 모듈만 비동기 호출 | **구현됨** | `market_report_service.py:184-198`(`use_sgis/use_kosis` 분기, 미선택 시 빈 dict) |
| Phase3-1 | Feasibility 엔진(AutoZoning+시세→규모/비용/수익/ROI) | **구현됨(개략)** | `feasibility_service.py:72-140`(`analyze_feasibility`). AutoZoning 폴백 `market_report_service.py:226-234` |
| Phase3-1 | `/market/report` 응답에 `feasibility_analysis` 포함 | **구현됨** | `market_report_service.py:250-255,292` |
| Phase3-1 | NPV 산출 | **없음(개략 한정)** | `feasibility_service.py`는 ROI만(`:110-112`). NPV는 V2 엔진 별도, market 보고서 미연결 |
| Phase3-2 | `FeasibilityDashboard.tsx` 신규 + Recharts | **구현됨** | `FeasibilityDashboard.tsx:1-194`(Recharts). 연결 `MarketInsightsWorkspaceClient.tsx:26,639-644` |
| Phase3-2 | 인구피라미드/가구 파이차트(Recharts) | **없음** | demographics는 텍스트/타일만(`:647-723`). `age_distribution`·`household_types` 화면 미사용. 메인에 Recharts import 없음 |
| §1.2 | 인구 이동 히트맵(Migration Map) | **없음** | 유입 Top3 텍스트만(`:679-691`). 히트맵/지도 없음 |
| §1.2 | AI 내러티브(target_persona 등) | **구현됨** | `market_report_service.py:133-156`(LLM JSON, `target_persona`), 렌더 `:485-490` |
| Phase3-3 | 코드 스플릿(DemographicPanel/FinancialPanel/AiSummaryPanel) | **없음** | `MarketInsightsWorkspaceClient.tsx` 단일 **772줄/40KB**, 전 패널 인라인 |
| §5-4 | 실데이터 통합/Fallback | **부분** | `gather(return_exceptions=True)`(`:193-198`). 단 **`use_mock=True` 하드코딩**으로 실데이터 경로 차단(G1) |
| 과금 | 시장분석 LLM 게이트 | **구현됨** | `market_report.py:44,53,68`(`Depends(enforce_llm_quota)`), `billing_deps.py:15-35`(402) |
| Phase2 | K-Atlas 어댑터(`DemographicProfile`/`MicroFinancialData`) | **구현됨(스키마만)** | `market_models.py:40-88`. 프론트 잠금 UI `:725-769`(데이터 하드코딩 더미 `:735-747`) |

## ② 갭 목록 (우선순위)

**[P0 — 치명: 실데이터가 절대 안 나옴]**
- **G1.** `market_report_service.py:187/189/191` SGIS·KOSIS 호출 `use_mock=True` 하드코딩 → 키 세팅돼도 항상 Mock. §5 전체 무력화.

**[P1 — 핵심 기능 스텁/오연동]**
- **G2.** SGIS 인구이동이 인구통계 엔드포인트 재사용 + Top3 하드코딩(`sgis_client.py:119,149-152`). (행안부/KOSIS OD로 실연동 필요 — SGIS stats엔 OD 없음)
- **G3.** KOSIS 소득 통계표ID 미확정(예시값 `DT_1EW0010`)(`kosis_client.py:62`).
- **G4.** KOSIS 지역코드 변환(행정동/법정동→시군구5) 부재(`kosis_client.py:65`).
- **G5.** PDF/PPTX가 `options` 미전달로 인구·소득 섹션 누락(`market_report.py:60,75`).

**[P2 — UI/시각화 갭]**
- **G6.** 인구피라미드·가구 파이차트 미구현(데이터 수신하나 화면 미사용). 인구이동 히트맵 없음.
- **G7.** 마이크로 타겟팅 패널 수치 하드코딩 더미(`MarketInsightsWorkspaceClient.tsx:735-747`).
- **G8.** "예상 코인 동적 계산"(§4.2) 미구현.

**[P3 — 견고화/유지보수]**
- **G9.** `_fetch_with_auth_retry` 데드코드(미사용) — -401 재시도 실경로 미적용(`sgis_client.py:75`).
- **G10.** SGIS 인구통계 0건 시 합성 폴백값 주입(`:197`) → 실데이터/폴백 구분 불명확.
- **G11.** 코드 스플릿 미적용(772줄 단일), market 전용 TS 타입 부재.
- **G12.** KOSIS HTML(비-JSON) 명시 가드 없이 예외 흡수(`kosis_client.py:99`).

**근거 무결성**: 모든 항목 위 인용 파일:라인에서 직접 확인. 커밋 c05265a는 import/캐싱/모델-dict 키 불일치 등 크래시·유실급 7건 수정했으나 실데이터 진입(G1)·인구이동 실연동(G2)·KOSIS 통계표 확정(G3)은 미해결.
