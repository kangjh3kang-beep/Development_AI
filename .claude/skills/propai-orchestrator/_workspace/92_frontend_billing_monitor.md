# 92 · Frontend — LLM 사용량 모니터링 실데이터화 + 코인 잔액 미터 + 시장분석 명시실행

## 목표
LLM 사용량 대시보드 목업 제거 → 실 API 바인딩, 사이드바 코인 잔액 미터 실데이터화, 시장·시세 분석 자동실행 제거 + 명시실행 + 코인 차감 안내. ★무목업.

## 백엔드 계약(라이브, dae5b47) — apiClient(메인 인증)
- `GET /api/v1/billing/token-usage?days=30`
  → `{ days, total_tokens, total_cost_krw, by_service:[{service,tokens,cost_krw}], daily:[{date(YYYY-MM-DD),tokens,cost_krw}] }`
- `GET /api/v1/billing/balance`
  → `{ tier, tier_label, monthly_base_krw, monthly_base_remaining, topup_krw, topup_remaining, used_this_cycle_krw, markup_pct, cycle_start }`
- 비용은 등급별 마진(낮은등급 +50% / 중위 +40% / 최상위 +30%) 포함. 차감은 BaseInterpreter가 LLM 호출 시 자동.
- 인터프리터 service 식별자(실제 로깅값): `site_analysis, market, feasibility, esg, permit, cost, design, tax, avm, report, digital_twin, llm`.

## 변경 파일
1. `apps/web/components/settings/AiTokenUsageDashboard.tsx` — 목업 전면 제거, 실 API 바인딩.
2. `apps/web/components/billing/BillingMeter.tsx` — `/billing/balance` 병합, 코인 잔액(월기본+충전)·마진율 배지·소진 임박 경고.
3. `apps/web/components/operations/MarketInsightsWorkspaceClient.tsx` — 자동실행 제거 + 「분석 실행」 명시버튼 + 코인 차감 안내 + 잔액부족 충전 유도.

## 1) 사용량 대시보드 실데이터(AiTokenUsageDashboard)
- `MOCK_USAGE` 전체 삭제. `Promise.all([token-usage?days=30, balance])` 동시 조회.
- 401/403 → "로그인 후 확인" 안내. 기타 오류 → 정직 안내. 사용 0건 → "사용 내역 없음" 정직 안내.
- 요약 카드 3종: ① 최근 N일 총 토큰(AnimatedCounter) ② 비용(마진 포함, 원화 + 등급/마진율) ③ 코인 잔여(월기본 잔여 / 충전 잔여 / 이번 주기 사용 분해).
- 서비스별: by_service를 라벨/색상 매핑(부지분석·시장·수지·ESG·인허가·공사비 등) + 토큰·원화(마진포함) 바.
- 일별: daily 막대 + 호버 시 날짜·토큰·원화. 비용 단위 USD→원화(원) 전환(백엔드 cost_krw 사용).

## 2) 코인 잔액 미터(BillingMeter, 레이아웃 상단 sidebar)
- 기존 `/billing/status` 유지 + `/billing/balance` 병행 조회(실패 시 null 폴백 → 기존 동작 무손상).
- 구독자 메터에 추가: 마진율 배지(`마진 +N%`), 코인 잔여=월기본 잔여+충전 잔여(balance 기준, 없으면 status.remaining_krw 폴백), 월기본/충전 잔여 분해 라인.
- 소진 임박(usage_pct ≥ 85%, 미차단) → 앰버 경고 "코인 소진 임박 · 충전 권장". 충전(topup) 성공 후 balance 재조회.
- 일반회원(무료등급)·비구독 분기 로직은 무변경.

## 3) 시장분석 명시실행(MarketInsightsWorkspaceClient)
- 기존: `address`(검색/프로젝트주소)가 NearbyTransactionsMap에 즉시 전달 → 자동 fetch.
- 변경: `searchAddr`(입력 후보) ↔ `runAddress`(실행 확정) 분리. `address = runAddress`로 지도/`deriveResults`/모든 결과 카드 게이팅.
- 「분석 실행」 버튼: `inputAddress`(searchAddr || 프로젝트주소) 확정 → runAddress 세팅 → 지도 1회 fetch. 실행 후 1.5s 뒤 balance 재조회(차감 반영).
- 안내: "분석 시 사용한 LLM 사용량만큼 코인이 자동 차감됩니다 · 코인 잔여 N · 마진 +N%". 잔액 0 이하 → 버튼 disabled + "좌측 코인 미터 추가결제로 충전" 유도.
- 보고서(`/market/report` use_llm) 성공 후에도 balance 재조회. 빈 상태 문구를 "주소 입력 후 「분석 실행」" 으로 갱신.

## 무목업 정합
- 목업 데이터/배너 0. 실 API만. 데이터 없음/미인증/오류는 정직 문구. 마진율·잔액 실표시.

## 검증
- `tsc --noEmit --incremental false` → EXIT 0 (변경 파일 무오류).
- `eslint` (3개 파일) → EXIT 0 (errors 0). MarketInsights 13:1 `no-explicit-any` unused-directive 경고는 HEAD 기준 기존 존재(스코프 외, 무수정).
- import 보존 확인: useEffect/ApiClientError/apiClient 등 git diff로 유지 확인.

## 미진/후속
- 다른 분석 페이지 자동실행 점검: site-analysis/feasibility 등은 기존에 명시버튼 구조로 추정(이번 스코프=market만 확인·전환). 자동실행 잔여 페이지 발견 시 동일 패턴(runAddress 분리 + 코인 안내) 적용 권장.
- "이번 분석 약 N코인 차감" 정확 수치는 백엔드가 호출당 증분을 별도 반환하지 않아, 실행 전후 balance 재조회(잔액 변화)와 설정>AI사용량 집계로 반영. 단건 증분 표시는 백엔드 응답 확장 시 추가 가능.
