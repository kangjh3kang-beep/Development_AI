/**
 * LLM 과금 `service` 라벨 — **단일 SSOT**.
 *
 * 왜(라이브 실측 2026-08-26, 관리자 계정 `GET /billing/token-usage?days=365`):
 * 같은 엔드포인트를 쓰는 두 화면이 라벨표를 **각자 인라인 선언**하고 있었고 키 집합이
 * 거의 겹치지 않았다(교집합 3). 그래서 **마이페이지 사용량(일반 사용자 화면)** 이
 * LLM 서비스명을 **영문 raw 로** 보여 주고 있었다.
 *
 *   라이브 service 값 11종 — avm · cost · expert_panel · feasibility · market ·
 *                            market_report · registry · regulation · scenario ·
 *                            site_analysis · verifier
 *   UsageClient 표(5키)      → 그중 **market 하나만** 덮음 → **10/11 종이 raw**
 *                              토큰 가중 **1,092,114 / 1,726,051 = 63.3%** 가 raw 렌더
 *   AiTokenUsageDashboard(12키) → 6/11 raw
 *
 * 양쪽 다 **죽은 키**를 갖고 있었다(`land` `assistant` `design` `report` `tax` `esg`
 * `permit` `digital_twin` `llm`) — 실제로 기록되는 값이 아니라 **상상한 어휘**로 쓴 표다.
 * 표를 각자 두면 각자 표류한다. 그래서 한 곳에 모은다.
 *
 * ★**이 표의 완전성은 보장할 수 없다 — 백엔드에 `service` enum 이 없다.**
 *   호출부는 `service="..."` 리터럴(25종)과 **변수 전달**이 섞여 있고,
 *   라이브의 `avm` · `cost` · `site_analysis` 는 **리터럴에 없다.**
 *   따라서 소스 파생은 **하한**이고 정본은 **런타임**이다.
 *   → 짝 테스트가 ①소스 리터럴 파생 ②아래 관측 집합 둘 다를 덮는지 본다.
 *   → 관측 집합은 **휘발성**이므로 값이 아니라 **재측정 명령**을 같이 적는다(아래).
 */

/**
 * 2026-08-26 라이브에서 **실제로 관측된** `service` 값 전수(플랫폼 전체·365일).
 *
 * ★재측정(값이 아니라 방법을 남긴다 — 이 목록은 시간이 지나면 늘어난다):
 * ```
 * TOK=$(curl -s -X POST https://api.4t8t.net/api/v1/auth/login \
 *        -H 'Content-Type: application/json' \
 *        -d '{"email":"<관리자>","password":"<비밀번호>"}' | jq -r .access_token)
 * curl -s -H "Authorization: Bearer $TOK" \
 *   'https://api.4t8t.net/api/v1/billing/token-usage?days=365' | jq -r '.by_service[].service'
 * ```
 * ★플랫폼 전체뷰는 `tier=super_admin` 만 본다(일반 계정은 본인 것만 나와 **부분집합**이다).
 */
export const OBSERVED_LLM_SERVICES = [
  "avm",
  "cost",
  "expert_panel",
  "feasibility",
  "market",
  "market_report",
  "registry",
  "regulation",
  "scenario",
  "site_analysis",
  "verifier",
] as const;

/**
 * 표시 라벨. **관측값 + 백엔드 호출부 리터럴**을 모두 덮는다.
 *
 * ★문구는 *사용자가 읽는 기능 이름*으로 통일한다. 종전 관리자 화면은 전부 " AI" 접미를
 *   붙였는데(`시장·시세 AI`), 일반 사용자 화면은 안 붙였다(`시장 분석`). 한 표를 쓰므로
 *   접미를 **떼고** 기능명만 남긴다 — 이 화면들은 이미 "AI 사용량" 문맥 안에 있어
 *   모든 항목에 AI 를 반복하면 정보가 아니라 소음이다.
 */
export const LLM_SERVICE_LABELS: Record<string, string> = {
  // ── 라이브 관측값(11종) ──────────────────────────────────────────────
  avm: "자동감정평가",
  cost: "공사비 적산",
  expert_panel: "전문가 패널",
  feasibility: "수지 분석",
  market: "시장 분석",
  market_report: "시장 보고서",
  registry: "등기 권리분석",
  regulation: "법규 자문",
  scenario: "시나리오 생성",
  site_analysis: "부지 분석",
  verifier: "자가 검증",
  // ── 백엔드 호출부 리터럴 중 아직 관측 안 된 것 ───────────────────────
  //    ★"관측 0" 은 부재가 아니라 **아직 안 쓰였을 뿐**이다. 미리 덮어 둔다.
  ai_assistant: "AI 비서",
  alris: "토지행정(ALRIS)",
  bid: "입찰 분석",
  design_ai: "설계 지원",
  design_ingest: "도면 인식",
  growth_analyze: "성장루프 분석",
  growth_improve: "성장루프 개선",
  legal_discovery: "법령 탐색",
  market_ai: "시장 AI",
  parcel_excel_row_reverify: "토지조서 행 재검증",
  parcel_excel_structure_detect: "토지조서 구조 인식",
  permit: "인허가 검토",
  precheck: "사전 진단",
};

/**
 * 라벨을 찾는다. **없으면 raw 를 그대로 돌려주지 않고 최소한 읽을 수 있게 만든다.**
 *
 * ★종전 두 화면은 `LABELS[k] ?? k` 로 **snake_case 영문**을 그대로 노출했다.
 *   미지의 값이 올 때 화면이 깨지면 안 되지만, `site_analysis` 를 그대로 보여 주는 것과
 *   `Site Analysis` 로 보여 주는 것은 다르다 — 후자는 **모르는 값임이 드러나면서도** 읽힌다.
 *   ★이것은 결함을 **가리는 것이 아니다**: 라벨 누락은 짝 테스트가 잡는다(초록 안에서).
 */
export function llmServiceLabel(service: string): string {
  const known = LLM_SERVICE_LABELS[service];
  if (known) return known;
  const trimmed = service.trim();
  if (!trimmed) return "미분류";
  return trimmed
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
