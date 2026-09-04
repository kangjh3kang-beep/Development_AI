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

import {
  scanRenderClocks,
  staleRatchetEntries,
  unlistedFiles,
  type ClockHit,
} from "@/lib/render-clock-scan";

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
    "141행 `today.current` → 385행 `작성일 {today.current}` 로 **화면에 표시**된다. " +
    "판단: 감정 보고서의 **작성일 기준**이 사용자 로컬 날짜인가 서버/발행 기준일인가",
  "components/sales/DeveloperProjection.tsx":
    "401행 `thisMonth`(YYYY-MM) → 급여 조회 월 `useState` **초깃값**. " +
    "판단: 기본 조회월이 **달력월**인가 회계 기준월인가",
  "components/sales/TaxPanel.tsx":
    "17행 `period`(YYYY-MM) → 세금계산서 **조회 기간 기본값**(과세 산식이 아니다). " +
    "판단: 기본 기간이 **이번 달**인가 직전 신고기간인가",
  "components/sales-app/SocialPanel.tsx":
    "986행 `hour >= 21 || hour < 8` → 야간 안내 분기. **사용자 로컬 시각 기준이 맞다** — " +
    "판단은 거의 없고 **마운트 후 판정**으로 옮기면 된다(서버는 서버 시간대라 갈린다)",
  "components/sre/SreDashboardClient.tsx":
    "★**제품 판단이 아니라 결함이다.** `logs` 는 `string[]` 로 **시각을 담지 않는데**(58행) " +
    "137행이 줄마다 `new Date().toLocaleTimeString()` 를 찍는다 → 모든 로그가 **같은 현재 시각**을 " +
    "보이고 리렌더마다 **과거 로그의 시각이 바뀐다**. 그 값은 로그가 난 시각이 아니다(거짓 정보). " +
    "판단: **로그에 시각을 실을 것인가**(데이터 형태 변경) 아니면 **시각 표시를 뺄 것인가**",
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

  it("★`useMemo` 는 **렌더 중**이라 잡는다 — `useEffect` 와 갈려야 DEFERRED 목록이 장식이 아니다", () => {
    // 변이 검증에서 DEFERRED 를 무력화해도 통과했다 — 폴백("그 밖의 콜백")이 같은 답을 줬기 때문.
    // 두 훅이 **다른 답**을 내야 그 목록이 실제로 판정에 쓰인다.
    const memo = scanRenderClocks("m.tsx", 'export function C(){ const t = useMemo(() => new Date(), []); return (<p>{String(t)}</p>); }');
    const eff = scanRenderClocks("e.tsx", 'export function C(){ useEffect(() => { const t = new Date(); }, []); return (<p>x</p>); }');
    expect(memo, "useMemo 는 렌더 중이므로 잡아야 한다").toHaveLength(1);
    expect(memo[0].phase).toBe("component-body");
    expect(eff, "useEffect 는 렌더 이후라 잡으면 위양성").toHaveLength(0);
  });

  it("★★판정 자체를 태운다 — 합성 입력으로 갈린다(실제 미등재가 0건이라 공허한 참이 된다)", () => {
    // 변이 검증에서 이 단언이 **생존**했다: 실제 미등재가 0건이라 무엇을 넣어도 [] 였다.
    const listed = Object.keys(RATCHET)[0];
    expect(unlistedFiles([{ file: listed }], RATCHET), "등재된 파일을 미등재로 신고했다").toEqual([]);
    expect(
      unlistedFiles([{ file: "components/새로운/Thing.tsx" }], RATCHET),
      "미등재 파일을 못 잡는다 — 래칫이 무의미하다",
    ).toEqual(["components/새로운/Thing.tsx"]);
    // 죽은 항목 판정도 같은 방식으로 갈라 둔다.
    expect(staleRatchetEntries([{ file: listed }], RATCHET).length).toBeGreaterThan(0);
    expect(staleRatchetEntries(Object.keys(RATCHET).map((f) => ({ file: f })), RATCHET)).toEqual([]);
  });

  it("★새 자리가 생기면 실패한다 — 래칫은 늘어나지 않는다", () => {
    expect(
      unlistedFiles(hits, RATCHET),
      "렌더 중 new Date()/Date.now() 를 새로 만들었다.\n" +
        "→ 값을 **데이터에서 파생**하거나(라벨이 약속하는 그 시각), 마운트 후로 옮겨라.\n" +
        "  그대로 두면 ①라벨이 거짓을 말하고 ②하이드레이션 불일치(React #418)가 난다.",
    ).toEqual([]);
  });

  it("★죽은 래칫 항목도 실패시킨다 — 고친 자리가 목록에 남으면 목록이 낡는다", () => {
    const stale = staleRatchetEntries(hits, RATCHET);
    expect(stale, `래칫에 있는데 소스에서 사라졌다(고쳤으면 목록에서 지워라): ${stale.join(", ")}`).toEqual([]);
  });

  it("★확정 사례는 **고쳐졌다** — ProjectsOverviewClient 는 래칫에 없다", () => {
    // 변이로 확정한 그 자리. 되돌리면 이 단언이 실패한다.
    expect(hits.map((h) => h.file)).not.toContain("components/projects/ProjectsOverviewClient.tsx");
    expect(RATCHET).not.toHaveProperty("components/projects/ProjectsOverviewClient.tsx");
  });

  /**
   * ★부채를 **초록 안에 드러낸다**(커밋 메시지에만 적으면 안 드러난다 · 회귀망 규율 D13).
   *
   * `SreDashboardClient` 는 제품 판단이 아니라 **결함**이다 — 로그가 시각을 담지 않는데
   * 화면이 렌더 시각을 찍어, 모든 줄이 같은 시각을 보이고 리렌더마다 과거 로그의 시각이 바뀐다.
   * 고치려면 `logs` 가 `string[]` → `{at, message}[]` 가 돼야 한다(데이터 형태 변경).
   */
  it.todo("SRE 로그가 **자기 발생 시각**을 표시한다(현재는 렌더 시각을 찍는다 — logs 에 시각을 실어야 한다)");

  it("★'마지막 업데이트'는 데이터에서 파생한다 — 렌더 시각이 아니다", () => {
    const src = readFileSync(join(WEB_ROOT, "components/projects/ProjectsOverviewClient.tsx"), "utf8");
    expect(src, "렌더 시각을 다시 넣었다").not.toMatch(/updatedAt:\s*new Date\(\)/);
    expect(src, "데이터 파생이 사라졌다").toContain("latestUpdatedAt");
  });
});
