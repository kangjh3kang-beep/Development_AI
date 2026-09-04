/**
 * 간략 수지 원장 — **백엔드가 싣는 곳 ↔ 프론트가 그리는 곳** 대조(2026-08-26).
 *
 * ## 왜 필요한가 (적대 리뷰 중1)
 *
 * 패널에서 `<LegacyLedgerTable …/>` **한 줄을 지워도 프론트 49건이 전부 초록**이었다.
 * 컴포넌트 자체 테스트는 컴포넌트만 태우고, **패널이 그것을 부르는지**는 아무도 안 봤다.
 * 이 저장소가 반복해 데인 형태 — *"부른다 ≠ 그래서 그렇게 됐다"* 의 한 칸 위.
 *
 * 정답 패턴이 바로 옆에 있었다: `components/ui/__tests__/IntegrityWarnings.surfaces.contract.test.ts`
 * (백엔드 emit 표면 수 ↔ 프론트 render 표면 수 대조). 같은 형태로 잠근다.
 *
 * ★소스 검사이지만 주석에 뚫리지 않는다 — `__stripCommentsForScan` 을 경유하고
 *   **그 면역을 대조군으로 실측**한다(주장하지 않는다).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..", "..");
const API_ROOT = join(WEB_ROOT, "..", "api");

/** 백엔드에서 `legacy_ledger` 를 **응답에 싣는** 파일(실측). */
const API_EMITTERS = ["app/routers/v2_feasibility.py"] as const;

/** 그 응답을 받아 **화면에 그리는** 프론트 표면. */
const WEB_RENDERERS = ["components/feasibility/RoughScenarioPanel.tsx"] as const;

const readApi = (rel: string) => readFileSync(join(API_ROOT, rel), "utf8");
const readWeb = (rel: string) =>
  __stripCommentsForScan(readFileSync(join(WEB_ROOT, rel), "utf8"), rel);

describe("원장 배선 계약", () => {
  it("★전제 — 대상 파일을 실제로 읽었다(공허한 초록 방지)", () => {
    for (const f of API_EMITTERS) expect(readApi(f).length).toBeGreaterThan(1000);
    for (const f of WEB_RENDERERS) expect(readWeb(f).length).toBeGreaterThan(1000);
  });

  it("★주석 스트립 면역이 **실제로 작동한다**(주장하지 않고 잰다)", () => {
    const stripped = __stripCommentsForScan(
      "const a = 1;\n// <LegacyLedgerTable ledger={x} />\n/* <LegacyLedgerTable /> */\n",
      "probe.tsx",
    );
    expect(stripped).not.toContain("LegacyLedgerTable");
    // 대조군 — 실행 줄은 살아남아야 한다(전부 지우는 구현이 통과하지 않게).
    expect(stripped).toContain("const a = 1;");
  });

  it("★백엔드가 legacy_ledger 를 응답에 싣는다", () => {
    const emitters = API_EMITTERS.filter((f) => /scenario\["legacy_ledger"\]\s*=/.test(readApi(f)));
    expect(emitters, "응답에 원장을 싣는 백엔드 표면이 없다").toEqual([...API_EMITTERS]);
  });

  it("★★프론트가 그것을 **렌더한다** — 컴포넌트 존재가 아니라 **패널의 호출**을 본다", () => {
    const missing = WEB_RENDERERS.filter((f) => {
      const src = readWeb(f);
      return !(/<LegacyLedgerTable\b/.test(src) && /legacy_ledger/.test(src));
    });
    expect(
      missing,
      "백엔드는 원장을 싣는데 화면이 그리지 않는 표면:\n" + missing.join("\n"),
    ).toEqual([]);
  });

  it("★emit 표면 수와 render 표면 수가 어긋나지 않는다(새 표면이 조용히 빠지지 않게)", () => {
    expect(API_EMITTERS.length).toBeGreaterThan(0);
    expect(WEB_RENDERERS.length).toBe(API_EMITTERS.length);
  });
});
