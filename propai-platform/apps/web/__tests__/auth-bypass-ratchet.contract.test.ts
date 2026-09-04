/**
 * **래칫**: 손수 `fetch` + 토큰을 조립하는 화면이 **늘어나지 않게** 잠근다.
 *
 * ## 왜 래칫인가 (한 번에 다 고칠 수 없다)
 *
 * `api-client` 에 **blob 경로가 없어서** 다운로드마다 손수 `fetch` 를 조립했고, 그래서
 * `api-client` 의 **401 → refresh → 1회 재시도**를 한 번도 받지 못했다. 액세스 토큰 TTL 은
 * **60분**이라, 그 뒤로는 «다운로드만» 실패한다(다른 조회는 갱신을 받아 살아 있다).
 *
 * 실측(2026-09-04): 그렇게 우회하는 파일이 **29개**. 한 PR 에서 전부 옮기면 리뷰가 불가능하고,
 * 옮기지 않고 두면 **새 화면이 같은 우회를 복사한다**(이미 그렇게 29개가 됐다).
 * → **지금 수를 못 박고, 줄어들기만 하게 한다.**
 *
 * ## ★이 락이 잠그는 두 방향
 *
 * | 방향 | 단언 |
 * |---|---|
 * | **늘지 않는다** | 실측 집합 ⊆ 고정 목록 (새 파일이 들어오면 빨강) |
 * | **줄면 목록도 준다** | 고정 목록 ⊆ 실측 집합 (고쳐 놓고 목록을 안 지우면 빨강 — 죽은 면제는 실패다) |
 *
 * ★한 방향만 걸면 반대쪽이 무제한이 된다(이 저장소 §회귀망 19).
 */
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = path.resolve(__dirname, "..");
const SKIP = /node_modules|[\\/]\.next[\\/]|__tests__|\.test\.|\.spec\.|[\\/]e2e[\\/]/;
/** 헤더 이름. **이것이 축이다** — 아래 주석 참조. */
const AUTH_HEADER = "Authorization";

/**
 * 축에서 제외하는 곳과 **그 사유**. 면제에는 반드시 사유를 적는다(사유 없는 면제는 부채다).
 *
 * - `lib/api-client.ts` — **공용 클라이언트 자신.** 여기가 유일한 정당 조립처다.
 * - `app/api/**` — Next.js **서버 라우트**. 브라우저가 아니라 서버에서 돌고, 들어온 헤더를
 *   **읽어서 전달**할 뿐이라 `localStorage` 토큰도 401 재시도도 무관하다(실측 2건).
 *   ★이 면제를 넓히지 마라 — `app/` 전체를 빼면 실제 화면이 통째로 빠진다.
 */
const EXEMPT = (rel: string) => rel === "lib/api-client.ts" || rel.startsWith("app/api/");

/**
 * **탐지기** — 이 소스가 **인증 헤더를 손수 조립하는 자리**를 몇 개 갖는가.
 *
 * ## ★축을 바꾼 이유 (적대 리뷰가 변이 3종으로 뚫었다)
 *
 * 초판은 «토큰 키 리터럴 ∧ `fetch(`» 를 봤다. **한 구문형만 덮은 것**이라 셋이 새어 나갔다:
 *
 * | 우회 형태 | 초판 | 지금 |
 * |---|---|---|
 * | 토큰 키를 **문자열 결합**(`"propai_access" + "_token"`) | 통과 | **잡힘** |
 * | `const F = globalThis.fetch; F(url, …)` | 통과 | **잡힘** |
 * | `XMLHttpRequest` + `setRequestHeader("Authorization", …)` | 통과 | **잡힘** |
 *
 * 셋 다 **`Authorization` 을 조립한다** — 그것 없이는 우회가 성립하지 않는다. 그래서 전송
 * 수단(`fetch`/XHR/axios/sendBeacon…)을 열거하는 대신 **모든 우회가 반드시 지나는 자리**를
 * 축으로 삼는다. *(열거는 곧 상한이 된다 — 이 저장소가 반복해 데인 형태다.)*
 *
 * ★**실측으로 상위집합임을 확인했다**: 새 축 31 ⊇ 옛 축 28, **잃는 것 0**.
 *   그리고 옛 축이 **놓치던 진짜 우회를 하나 찾았다** — `components/common/AIAssistant.tsx`
 *   (SSE 직호출). 토큰 키가 **주석에만** 있어 스트립 후 사라졌었다. **29 는 과소계수였다.**
 *
 * ## ★축의 단위가 「파일」이 아니라 「자리」다
 *
 * 리뷰 실측: 목록에 든 파일에 **두 번째 우회**를 더해도 초판은 말이 없었다(목록 28개 중
 * **20개가 `apiClient` 호출과 생 `fetch` 를 함께** 갖고 있어 사실상 영구 면제였다).
 * → **출현 수**를 세고 파일별로 못 박는다.
 */
export function countBypassSites(raw: string, fileName: string): number {
  // ★프리필터 — 이 한 줄이 TS 파싱을 714파일 → 수십으로 줄인다(전수 파싱은 30초 타임아웃을
  //   건드렸다). 원문에 낱말이 없으면 주석에도 코드에도 없다.
  if (!raw.includes(AUTH_HEADER)) return 0;
  // 주석·JSDoc 을 걷어내고 본다. 손 정규식은 이 저장소에서 다섯 번 관통됐으므로
  // `lib/source-invariant.ts` 의 **간극 전수 주사**를 쓴다(줄 주석·URL 의 `//` 포함).
  const src = __stripCommentsForScan(raw, fileName);
  return src.split(AUTH_HEADER).length - 1;
}

/**
 * ★파생형 수집 — 손으로 나열하지 않는다. 목록은 곧 상한이 된다.
 *
 * ★결과를 **한 번만 계산**한다: 호출당 트리를 훑으므로 테스트마다 다시 걸면 이 한 파일이
 *   CI 를 수십 초 잡아먹는다(첫 실행 실측 40초).
 */
let _cache: Record<string, number> | null = null;
function collectBypassSites(): Record<string, number> {
  return (_cache ??= collectBypassSitesUncached());
}

function collectBypassSitesUncached(): Record<string, number> {
  const out: Record<string, number> = {};
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, e.name);
      if (SKIP.test(full)) continue;
      if (e.isDirectory()) { walk(full); continue; }
      // ★확장자를 넓힌다 — `.tsx?` 만 보면 `.js/.jsx/.mjs` 우회가 안 세어진다(현재 0건 · 잠재).
      if (!/\.(tsx?|jsx?|mjs)$/.test(e.name)) continue;
      const rel = path.relative(WEB_ROOT, full).split(path.sep).join("/");
      if (EXEMPT(rel)) continue;
      const n = countBypassSites(fs.readFileSync(full, "utf8"), full);
      if (n > 0) out[rel] = n;
    }
  };
  walk(WEB_ROOT);
  return out;
}

/**
 * 2026-09-04 실측으로 못 박은 잔여 우회 — **29파일 · 35자리**.
 *
 * ★값은 **자리 수**(`Authorization` 조립 지점)다. 파일 축으로 세면 같은 파일에 우회를
 *   더해도 안 보인다 — 실측으로 **6자리가 숨어 있었다**(`LandScheduleClient` 혼자 4).
 * ★이 표는 **줄어들기만 한다.** 항목을 더하거나 수를 올려 초록을 만들지 마라 —
 *   그 순간 이 파일은 래칫이 아니라 **면제 발급기**가 된다.
 *   `components/operations/RegistryRightsReportButton.tsx` 는 이 PR 에서 **옮겨서 빠졌다**.
 */
const KNOWN_BYPASS: Record<string, number> = {
  "components/analytics/CashflowDcfPanel.tsx": 1,
  "components/analytics/CostEstimationClient.tsx": 1,
  "components/common/AIAssistant.tsx": 1,
  "components/common/GlobalAddressSearch.tsx": 1,
  "components/cost/BoqAutoWorkspace.tsx": 1,
  "components/cost/BoqDetailTable.tsx": 1,
  "components/dashboard/RealtxReportPanel.tsx": 1,
  "components/design-audit/AuditReportView.tsx": 2,
  "components/design/CadBimIntegrationPanel.tsx": 1,
  "components/design/DesignGenPanel.tsx": 1,
  "components/feasibility/FeasibilityExportButton.tsx": 1,
  "components/feasibility/RoughScenarioPanel.tsx": 1,
  "components/mypage/CoinsClient.tsx": 1,
  "components/operations/DeskAppraisalModal.tsx": 2,
  "components/operations/DeskAppraisalReportClient.tsx": 2,
  "components/operations/LandScheduleClient.tsx": 4,
  "components/operations/LandShareModal.tsx": 1,
  "components/operations/MarketInsightsWorkspaceClient.tsx": 1,
  "components/operations/PermitAiWorkspaceClient.tsx": 1,
  "components/operations/RegulationsWorkspaceClient.tsx": 1,
  "components/orchestration/PersonaPanel.tsx": 1,
  "components/pipeline/PipelineResultDetail.tsx": 1,
  "components/projects/DecisionBriefPanel.tsx": 1,
  "components/projects/ParcelExportButton.tsx": 1,
  "components/projects/ReportPdfDownload.tsx": 1,
  "components/report/BankReadyReportBuilder.tsx": 1,
  "components/report/ReportDownloadMenu.tsx": 1,
  "components/sales-app/TerminationCertPanel.tsx": 1,
  "lib/land/desk-appraisal.ts": 1,
};
const KNOWN_TOTAL = Object.values(KNOWN_BYPASS).reduce((a, b) => a + b, 0);

describe("공용 클라이언트 우회 래칫", () => {
  it("★수집기가 살아 있다(공허진리 방지 — 0건이면 무엇이든 통과한다)", () => {
    const found = collectBypassSites();
    // ★하한을 **손으로 고르지 않는다.** 고정값을 쓰면 정상적인 이관이 진행될수록
    //   «수집기가 죽었다» 라는 **오도하는 메시지로 빨개진다**(위양성도 결함이다).
    //   목록에서 파생시키면 목록이 줄 때 하한도 같이 준다.
    expect(Object.keys(found).length).toBeGreaterThanOrEqual(
      Math.min(5, Object.keys(KNOWN_BYPASS).length),
    );
    // 양성 대조군: 우회가 실재하는 파일을 실제로 집는가
    expect(found["components/report/ReportDownloadMenu.tsx"]).toBeGreaterThan(0);
  });

  it("새 우회가 늘지 않는다(파일도, **자리 수**도)", () => {
    const found = collectBypassSites();
    const added = Object.keys(found).filter((f) => !(f in KNOWN_BYPASS));
    expect(added, `공용 클라이언트를 우회하는 새 파일: ${added.join(", ")}\n` +
      "→ 손수 fetch + Authorization 대신 apiClient.download / apiClient.post 를 쓰세요. " +
      "우회하면 401→refresh 재시도가 붙지 않아 토큰 만료 60분 뒤부터 그 기능만 실패합니다.").toEqual([]);

    // ★**같은 파일 안에서** 늘어나는 것도 잡는다. 축이 「파일」이면 목록에 든 28개가
    //   사실상 영구 면제가 된다(그중 20개는 apiClient 호출과 생 fetch 를 함께 갖고 있다).
    const grew = Object.entries(found)
      .filter(([f, n]) => f in KNOWN_BYPASS && n > KNOWN_BYPASS[f])
      .map(([f, n]) => `${f}: ${KNOWN_BYPASS[f]} → ${n}`);
    expect(grew, `기존 파일에 우회가 늘었다:\n${grew.join("\n")}`).toEqual([]);
  });

  it("고친 파일은 목록에서 지운다(죽은 면제는 실패다)", () => {
    const found = collectBypassSites();
    const stale = Object.keys(KNOWN_BYPASS).filter((f) => !(f in found));
    expect(stale, `이미 고쳐졌는데 목록에 남은 항목: ${stale.join(", ")}`).toEqual([]);
    const shrunk = Object.entries(KNOWN_BYPASS)
      .filter(([f, n]) => f in found && found[f] < n)
      .map(([f, n]) => `${f}: ${n} → ${found[f]}`);
    expect(shrunk, `자리가 줄었는데 표를 안 고쳤다(진전을 기록하라):\n${shrunk.join("\n")}`).toEqual([]);
  });

  it("★신고된 화면은 **우회 집합 밖**이다 — 결함이 살던 자리", () => {
    expect(collectBypassSites()).not.toHaveProperty(
      "components/operations/RegistryRightsReportButton.tsx",
    );
  });

  it("총 자리 수는 줄기만 한다(상한 못 박기)", () => {
    const total = Object.values(collectBypassSites()).reduce((a, b) => a + b, 0);
    expect(total).toBeLessThanOrEqual(KNOWN_TOTAL);
    expect(KNOWN_TOTAL).toBe(35); // 2026-09-04 실측
  });
});

describe("탐지기 자체 — 합성 입력", () => {
  // ★이 describe 가 없으면 탐지기를 «항상 0» 으로 바꾸는 변이가 위 다섯을 **전부 통과**한다
  //   (위반 0 = 초록). 탐지와 특이도는 다른 축이다.
  const P = "probe.ts";

  it("표준형 우회를 **집는다**(탐지 축)", () => {
    expect(countBypassSites(
      'const t = localStorage.getItem("propai_access_token");\n' +
      "await fetch(u, { headers: { Authorization: `Bearer ${t}` } });", P)).toBe(1);
  });

  it("★리뷰가 뚫은 **세 형태**를 전부 집는다(축을 넓힌 이유)", () => {
    // ① 토큰 키를 문자열 결합 — 키 리터럴로는 안 잡히지만 헤더는 조립해야 한다
    expect(countBypassSites(
      'const t = localStorage.getItem("propai_access" + "_token");\n' +
      "await fetch(u, { headers: { Authorization: `Bearer ${t}` } });", P)).toBe(1);
    // ② fetch 별칭 호출
    expect(countBypassSites(
      "const F = globalThis.fetch;\nawait F(u, { headers: { Authorization: b } });", P)).toBe(1);
    // ③ XMLHttpRequest
    expect(countBypassSites(
      'const x = new XMLHttpRequest();\nx.setRequestHeader("Authorization", b);', P)).toBe(1);
  });

  it("공용 클라이언트를 쓰는 소스는 **안 집는다**(특이도 축)", () => {
    expect(countBypassSites(
      'import { apiClient } from "@/lib/api-client";\nawait apiClient.download("/x");', P)).toBe(0);
  });

  it("주석에만 나오는 언급은 **안 집는다**(위양성 축)", () => {
    // ★위양성도 결함이다 — 정상 코드를 막으면 가드가 꺼진다.
    expect(countBypassSites(
      "const x = 1; // Authorization 을 손수 붙이지 마세요\n" +
      "/* Authorization 조립은 api-client 만 */\n" +
      'await apiClient.post("/x", {});', P)).toBe(0);
  });

  it("★**자리 수**를 센다 — 같은 파일의 두 번째 우회가 보인다", () => {
    expect(countBypassSites(
      "await fetch(a, { headers: { Authorization: b } });\n" +
      "await fetch(c, { headers: { Authorization: d } });", P)).toBe(2);
  });

  it("프리필터가 **정답을 바꾸지 않는다**(성능 최적화가 탐지를 죽이지 않았는가)", () => {
    // 낱말이 없으면 0 — 그런데 있는데 0 을 주면 그것이 위음성이다.
    expect(countBypassSites("const x = 1;", P)).toBe(0);
    expect(countBypassSites("headers: { Authorization: b }", P)).toBe(1);
  });
});
