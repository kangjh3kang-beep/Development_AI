/**
 * 렌더 중 **비결정 시각 호출** 비성장 래칫.
 *
 * ## 무엇이 있었나(변이로 확정 · 2026-08-25)
 *
 * `ProjectsOverviewClient` 가 렌더 중 `new Date().toISOString()` 을 만들어
 * *"마지막 업데이트"* 라벨 옆에 그렸다. 그 값은 **화면을 그린 순간**이지 데이터의 시각이 아니다.
 * 그리고 서버 렌더 시각 ≠ 클라이언트 하이드레이트 시각이라 **React #418** 을 냈다.
 *
 * 로컬 프로덕션 빌드에서 **그 한 줄만** 상수로 고정하니 `/ko/projects` 의 #418 이 **1 → 0**,
 * 같은 배치의 양성 대조군(`/ko/regulations`·`/ko/permits`)은 **1 유지**, 음성 대조군은 0 유지.
 *
 * ## ★왜 래칫인가 — 지금 있는 것을 한 번에 고칠 수 없다
 *
 * 남은 자리들은 각각 *"무엇을 대신 보여 줄 것인가"* 라는 **제품 판단**이 필요하다
 * (예: 야간 배너 분기 · 이번 달 집계 기준). 근거 없이 일괄로 바꾸면 화면이 거짓을 말하거나
 * 기능이 죽는다. 그래서 **새 것은 막고 기존은 초록 안에서 보이게** 둔다.
 *
 * ★이 목록은 **줄어드는 방향으로만** 움직인다. 늘면 실패한다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { scanRenderClocks, type ClockHit } from "@/lib/render-clock-scan";

const WEB_ROOT = join(__dirname, "..", "..");
const SKIP = new Set(["node_modules", ".next", "dist", "coverage", "e2e", "__tests__"]);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (SKIP.has(entry)) continue;
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(p);
  }
  return out;
}

function scanAll(): ClockHit[] {
  const hits: ClockHit[] = [];
  for (const f of walk(WEB_ROOT)) {
    hits.push(...scanRenderClocks(relative(WEB_ROOT, f), readFileSync(f, "utf8")));
  }
  return hits;
}

/**
 * ★기존 부채 — 각각 **제품 판단**이 필요해 이번에 못 고친 자리들.
 * 고칠 때마다 여기서 지운다. **추가는 실패**한다.
 */
const RATCHET: Record<string, string> = {
  "components/operations/DeskAppraisalReportClient.tsx":
    "감정 보고서의 발행 시각 — '언제 발행됐는가'를 서버가 실어 보내야 정확하다(스키마 판단 필요)",
  "components/sales/DeveloperProjection.tsx":
    "급여 광고 섹션의 '이번 달' 기준 — 회계 기준월이 달력월과 같은지 확인이 필요하다",
  "components/sales/TaxPanel.tsx":
    "세금 계산의 기준 연도 — 과세 기준일을 무엇으로 볼지는 세무 판단이다",
  "components/sales-app/SocialPanel.tsx":
    "방송 화면의 주야 분기 — 사용자 로컬 시각으로 갈라야 하므로 마운트 후 판정이 맞다(UX 판단)",
  "components/sre/SreDashboardClient.tsx":
    "SRE 대시보드의 상대시간 표시 — 실시간 갱신이 의도라 마운트 후 타이머로 옮겨야 한다",
};

describe("렌더 중 비결정 시각 호출 — 비성장 래칫", () => {
  const hits = scanAll();

  it("★스캐너가 살아 있다 — 알려진 형태를 실제로 잡는다(공허한 초록 방지)", () => {
    // 대조군: 확정 사례와 동형인 합성 소스를 넣으면 반드시 잡혀야 한다.
    const probe = scanRenderClocks(
      "probe.tsx",
      'export function C(){ const t = new Date().toISOString(); return (<p>{t}</p>); }',
    );
    expect(probe, "스캐너가 죽었다 — 아래 '0건'은 근거가 되지 않는다").toHaveLength(1);
    expect(probe[0].phase).toBe("component-body");
  });

  it("[양성 대조군] 이벤트 핸들러·effect 안의 시각 호출은 잡지 않는다 — 정상 코드를 막으면 그것도 결함", () => {
    const ok = scanRenderClocks(
      "ok.tsx",
      'export function C(){ useEffect(() => { const a = Date.now(); }, []);' +
        ' return (<button onClick={() => { const b = new Date(); }}>x</button>); }',
    );
    expect(ok).toHaveLength(0);
  });

  it("★새 자리가 생기면 실패한다 — 래칫은 늘어나지 않는다", () => {
    const unlisted = hits.map((h) => h.file).filter((f) => !(f in RATCHET));
    expect(
      [...new Set(unlisted)].sort(),
      "렌더 중 new Date()/Date.now() 를 새로 만들었다.\n" +
        "→ 값을 **데이터에서 파생**하거나(라벨이 약속하는 그 시각), 마운트 후로 옮겨라.\n" +
        "  그대로 두면 ①라벨이 거짓을 말하고 ②하이드레이션 불일치(React #418)가 난다.",
    ).toEqual([]);
  });

  it("★죽은 래칫 항목도 실패시킨다 — 고친 자리가 목록에 남으면 목록이 낡는다", () => {
    const present = new Set(hits.map((h) => h.file));
    const stale = Object.keys(RATCHET).filter((f) => !present.has(f));
    expect(stale, `래칫에 있는데 소스에서 사라졌다(고쳤으면 목록에서 지워라): ${stale.join(", ")}`).toEqual([]);
  });

  it("★확정 사례는 **고쳐졌다** — ProjectsOverviewClient 는 래칫에 없다", () => {
    // 변이로 확정한 그 자리. 되돌리면 이 단언이 실패한다.
    expect(hits.map((h) => h.file)).not.toContain("components/projects/ProjectsOverviewClient.tsx");
    expect(RATCHET).not.toHaveProperty("components/projects/ProjectsOverviewClient.tsx");
  });

  it("★'마지막 업데이트'는 데이터에서 파생한다 — 렌더 시각이 아니다", () => {
    const src = readFileSync(join(WEB_ROOT, "components/projects/ProjectsOverviewClient.tsx"), "utf8");
    expect(src, "렌더 시각을 다시 넣었다").not.toMatch(/updatedAt:\s*new Date\(\)/);
    expect(src, "데이터 파생이 사라졌다").toContain("latestUpdatedAt");
  });
});
