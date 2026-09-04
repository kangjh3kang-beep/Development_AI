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
const TOKEN_KEY = "propai_access_token";

/**
 * **탐지기** — 이 소스가 «공용 클라이언트를 우회해 토큰을 손수 싣는가».
 *
 * ★따로 꺼낸 이유: 트리 순회 안에 인라인으로 두면 **합성 입력으로 태울 수 없다.**
 *   그러면 탐지기를 «항상 false» 로 바꾸는 변이가 «위반 0» 을 내며 **초록으로 생존**한다
 *   (이 저장소가 반복해 데인 형태 — «전부 통과시키는 가드» 가 만점을 받는다).
 *   아래 `탐지기` describe 가 **두 모집단**(우회 ↔ 정상)으로 이것을 직접 태운다.
 */
export function isBypassSource(raw: string, fileName: string): boolean {
  // ★주석·JSDoc 을 걷어내고 본다. 손 정규식은 이 저장소에서 다섯 번 관통됐으므로
  //   `lib/source-invariant.ts` 의 **간극 전수 주사**를 쓴다(줄 주석·URL 의 `//` 포함).
  const src = __stripCommentsForScan(raw, fileName);
  return src.includes(TOKEN_KEY) && /\bfetch\s*\(/.test(src);
}

/**
 * ★파생형 수집 — 손으로 나열하지 않는다. 목록은 곧 상한이 된다.
 *
 * ★결과를 **한 번만 계산**한다: 트리 전수를 TS 로 파싱하므로 호출당 약 10초가 든다.
 *   테스트마다 다시 걸면 이 한 파일이 CI 를 40초 잡아먹는다(첫 실행 실측).
 */
let _cache: string[] | null = null;
function collectBypassFiles(): string[] {
  return (_cache ??= collectBypassFilesUncached());
}

function collectBypassFilesUncached(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, e.name);
      if (SKIP.test(full)) continue;
      if (e.isDirectory()) { walk(full); continue; }
      if (!/\.tsx?$/.test(e.name)) continue;
      const rel = path.relative(WEB_ROOT, full).split(path.sep).join("/");
      if (rel === "lib/api-client.ts") continue; // 공용 클라이언트 자신 — 여기가 유일한 정당 소비처
      // ★주석·문자열 설명에 속지 않게 주석을 걷어내고 본다(소스 검사가 반복해 뚫린 자리).
      // ★`fileName` 은 필수다 — 빼면 TS 가 경로 정규화에서 터진다(첫 실행 실측).
      //   확장자로 ScriptKind 를 고르므로 `.tsx` 의 JSX 도 올바로 파싱된다.
      if (isBypassSource(fs.readFileSync(full, "utf8"), full)) out.push(rel);
    }
  };
  walk(WEB_ROOT);
  return out.sort();
}

/**
 * 2026-09-04 실측으로 못 박은 잔여 우회 **28개**.
 * ★이 목록은 **줄어들기만 한다.** 새 항목을 여기 더해 초록을 만들지 마라 —
 *   그 순간 이 파일은 래칫이 아니라 **면제 발급기**가 된다.
 *   `components/operations/RegistryRightsReportButton.tsx` 는 이 PR 에서 **옮겨서 빠졌다**.
 */
const KNOWN_BYPASS = [
  "components/analytics/CashflowDcfPanel.tsx",
  "components/analytics/CostEstimationClient.tsx",
  "components/common/GlobalAddressSearch.tsx",
  "components/cost/BoqAutoWorkspace.tsx",
  "components/cost/BoqDetailTable.tsx",
  "components/dashboard/RealtxReportPanel.tsx",
  "components/design-audit/AuditReportView.tsx",
  "components/design/CadBimIntegrationPanel.tsx",
  "components/design/DesignGenPanel.tsx",
  "components/feasibility/FeasibilityExportButton.tsx",
  "components/feasibility/RoughScenarioPanel.tsx",
  "components/mypage/CoinsClient.tsx",
  "components/operations/DeskAppraisalModal.tsx",
  "components/operations/DeskAppraisalReportClient.tsx",
  "components/operations/LandScheduleClient.tsx",
  "components/operations/LandShareModal.tsx",
  "components/operations/MarketInsightsWorkspaceClient.tsx",
  "components/operations/PermitAiWorkspaceClient.tsx",
  "components/operations/RegulationsWorkspaceClient.tsx",
  "components/orchestration/PersonaPanel.tsx",
  "components/pipeline/PipelineResultDetail.tsx",
  "components/projects/DecisionBriefPanel.tsx",
  "components/projects/ParcelExportButton.tsx",
  "components/projects/ReportPdfDownload.tsx",
  "components/report/BankReadyReportBuilder.tsx",
  "components/report/ReportDownloadMenu.tsx",
  "components/sales-app/TerminationCertPanel.tsx",
  "lib/land/desk-appraisal.ts",
].sort();

describe("공용 클라이언트 우회 래칫", () => {
  it("★수집기가 살아 있다(공허진리 방지 — 0건이면 무엇이든 통과한다)", () => {
    const found = collectBypassFiles();
    expect(found.length).toBeGreaterThanOrEqual(20);
    // 양성 대조군: 우회가 실재하는 파일을 실제로 집는가
    expect(found).toContain("components/report/ReportDownloadMenu.tsx");
    // 음성 대조군: 주석 스트립이 동작하는가 — 주석뿐인 소스는 안 집힌다
    const commentOnly = __stripCommentsForScan(
      `const x = 1; // ${TOKEN_KEY} 를 fetch( 로 쓰면 안 된다\n`,
      "probe.ts",
    );
    expect(commentOnly.includes(TOKEN_KEY)).toBe(false);
  });

  it("새 우회가 늘지 않는다(실측 ⊆ 고정 목록)", () => {
    const added = collectBypassFiles().filter((f) => !KNOWN_BYPASS.includes(f));
    expect(added, `공용 클라이언트를 우회하는 새 파일: ${added.join(", ")}\n` +
      "→ 손수 fetch + Authorization 대신 apiClient.download / apiClient.post 를 쓰세요. " +
      "우회하면 401→refresh 재시도가 붙지 않아 토큰 만료 60분 뒤부터 그 기능만 실패합니다.").toEqual([]);
  });

  it("고친 파일은 목록에서 지운다(고정 목록 ⊆ 실측 — 죽은 면제는 실패다)", () => {
    const found = collectBypassFiles();
    const stale = KNOWN_BYPASS.filter((f) => !found.includes(f));
    expect(stale, `이미 고쳐졌는데 목록에 남은 항목: ${stale.join(", ")}`).toEqual([]);
  });

  it("★신고된 화면은 **우회 집합 밖**이다 — 결함이 살던 자리", () => {
    // 이 단언이 없으면 «컴포넌트를 되돌리는 변이» 가 나머지 락을 전부 통과한다
    // (되돌리면 목록에 없는 새 우회가 되어 두 번째 테스트가 잡긴 하지만,
    //  그 테스트의 메시지는 «새 파일» 이라 원인을 오도한다).
    expect(collectBypassFiles()).not.toContain(
      "components/operations/RegistryRightsReportButton.tsx",
    );
  });

  it("목록은 줄기만 한다(상한 못 박기)", () => {
    expect(KNOWN_BYPASS.length).toBeLessThanOrEqual(28);
    expect(new Set(KNOWN_BYPASS).size).toBe(KNOWN_BYPASS.length); // 중복으로 수를 부풀리지 않는다
  });
});

describe("탐지기 자체 — 합성 입력 두 모집단", () => {
  // ★이 describe 가 없으면 탐지기를 «항상 false» 로 바꾸는 변이가 위 네 테스트를
  //   **전부 통과**한다(위반 0 = 초록). 탐지와 특이도는 다른 축이다.
  it("우회 소스를 **집는다**(탐지 축)", () => {
    const bypass = [
      'const t = localStorage.getItem("propai_access_token");',
      'await fetch("/x", { headers: { Authorization: `Bearer ${t}` } });',
    ].join("\n");
    expect(isBypassSource(bypass, "probe.ts")).toBe(true);
  });

  it("공용 클라이언트를 쓰는 소스는 **안 집는다**(특이도 축)", () => {
    const clean = 'import { apiClient } from "@/lib/api-client";\nawait apiClient.download("/x");';
    expect(isBypassSource(clean, "probe.ts")).toBe(false);
  });

  it("주석에만 나오는 언급은 **안 집는다**(위양성 축)", () => {
    // ★위양성도 결함이다 — 정상 코드를 막으면 가드가 꺼진다.
    const commented = [
      'const x = 1; // propai_access_token 을 fetch( 로 직접 쓰지 마세요',
      "/* propai_access_token + fetch( 조합은 금지 */",
      'await apiClient.post("/x", {});',
    ].join("\n");
    expect(isBypassSource(commented, "probe.ts")).toBe(false);
  });

  it("★한쪽만 있으면 안 집는다 — 두 조건이 **둘 다** 필요하다", () => {
    expect(isBypassSource('await fetch("/public");', "probe.ts")).toBe(false);
    expect(isBypassSource('localStorage.getItem("propai_access_token");', "probe.ts")).toBe(false);
  });
});
