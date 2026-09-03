/**
 * 「선택 필지」 라벨 토글 — 기본 ON · 끌 수 있음 (2026-09-03 · #954)
 *
 * ★이 파일의 전신은 **소스 문자열 락**이었고, 적대 리뷰가 넣은 변이 6종 중 **5종이 SURVIVED**
 *   했다. 가장 아픈 것:
 *
 *       const selectionLabelsOn = satongSelectionLabelsVisible(layerState) || true;
 *
 *   토글을 **아무 일도 안 하게** 만드는 변이인데(= 이 PR 이 고치려던 결함의 부활)
 *   `line.includes("satongSelectionLabelsVisible(layerState)")` 는 통과한다.
 *   **이름은 보고 값은 안 봤다.**
 *
 * ★그래서 축을 전부 **값·행위**로 옮겼다:
 *     A 계획(순수)   — 판정이 두 모집단을 실제로 가르는가
 *     B 배선(행위)   — 컴포넌트가 그 판정값을 **위임 인자로 싣는가** (`|| true` 를 죽인다)
 *     C 기본값(값)   — defaultControlsByLayer() 를 **실행해서** 판정에 먹인다
 *     D 호출부(판정) — 어휘 소속이 아니라 **판정 결과**를 파생시킨다
 *     E 시간축       — **토글을 바꾸고**(rerender) **언마운트**한다
 *   (계획·그리기 자체는 `lib/__tests__/satong-selection-labels.test.ts` 가 태운다 —
 *    이 파일이 여섯 축을 다 덮는 것처럼 읽히지 않게 여기 적는다.)
 *
 * ★2차 적대 리뷰(REVISE)가 지적한 근본:
 *   *"1차는 락이 **이름**을 봤고, 2차는 **값**을 보지만 **마운트 시점에만** 본다.
 *    토글과 정리는 본질적으로 **시간축**인데 정적으로 잠갔다."*
 *   실측: `selectionLabelsOn` 을 deps 에서 빼도 **27건 전부 초록**이었다(린트 래칫이
 *   우연히 잡았을 뿐이고, 그 여유는 **0**이라 무관한 경고 하나만 고쳐도 침묵한다).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SATONG_MAP_SHELL_LAYERS, defaultControlsByLayer } from "@/components/precheck/SatongMapShell";
import {
  SATONG_SELECTION_LABEL_CONTROL_IDS,
  satongSelectionLabelsVisible,
  type SatongMapLayerState,
} from "@/lib/satong-map-layers";
import { __stripCommentsForScan } from "@/lib/source-invariant";

// ── B 축을 위한 스파이. 실제 모듈의 계획 로직은 A 에서 직접 태운다. ──────────────
const planSpy = vi.hoisted(() => vi.fn(() => ({ kind: "empty" as const })));
const removeSpy = vi.hoisted(() => vi.fn());
const renderSpy = vi.hoisted(() => vi.fn(() => ({ remove: removeSpy })));
vi.mock("@/lib/satong-selection-labels", () => ({
  planSelectionLabels: planSpy,
  renderSelectionLabels: renderSpy,
}));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: {
      ...actual.apiClient,
      request: vi.fn(pending), get: vi.fn(pending), post: vi.fn(pending),
      put: vi.fn(pending), patch: vi.fn(pending), delete: vi.fn(pending),
      getV2: vi.fn(pending), postV2: vi.fn(pending), putV2: vi.fn(pending),
      deleteV2: vi.fn(pending),
    },
  };
});

const st = (controls: SatongMapLayerState["controlsByLayer"]): SatongMapLayerState => ({
  enabledLayerIds: [],
  controlsByLayer: controls,
});

// ─────────────────────────────────────────────────────────────────────────────
describe("A 판정(순수) — 두 모집단이 실제로 갈린다", () => {
  it("컨트롤이 켜져 있으면 표시한다", () => {
    expect(satongSelectionLabelsVisible(st({ cadastre: ["boundary", "selected"] }))).toBe(true);
  });

  it("★컨트롤을 끄면 숨긴다 — 사용자의 요구 그 자체", () => {
    expect(satongSelectionLabelsVisible(st({ cadastre: ["boundary"] }))).toBe(false);
  });

  it("★둘 다 끄면(cadastre: []) 숨긴다 — 라이브에서 도달 가능한 상태다", () => {
    // handleLayerControlClick 은 키를 지우지 않고 빈 배열을 남긴다 → 이 모집단은 실재한다.
    expect(satongSelectionLabelsVisible(st({ cadastre: [] }))).toBe(false);
  });

  it("★컨트롤을 선언하지 않으면 표시한다 — 끄는 UI 가 없는 화면에서 사라지면 안 된다", () => {
    expect(satongSelectionLabelsVisible(undefined)).toBe(true);
    expect(satongSelectionLabelsVisible(st({}))).toBe(true);
    expect(satongSelectionLabelsVisible(st({ zoning: ["land-use"] }))).toBe(true);
  });

  it("★닫힌 집합의 **내용**을 리터럴로 못 박는다 — 자기지시 루프는 집합과 함께 깎인다", () => {
    // 실측: 집합에서 한 원소를 지우는 변이를 이 축 **단독**으로 판정하니 SURVIVED 였다.
    expect([...SATONG_SELECTION_LABEL_CONTROL_IDS].sort()).toEqual(["selected", "selected-parcel"]);
  });

  it("아무 문자열이나 통과하지 않는다(음성 대조군)", () => {
    expect(satongSelectionLabelsVisible(st({ cadastre: ["selected-something-else"] }))).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("B 배선(행위) — 컴포넌트가 판정**값**을 위임 인자로 싣는다", () => {
  const visibleArgs = () =>
    (planSpy.mock.calls as unknown as [{ visible: boolean }][]).map((c) => c[0].visible);

  it("★토글 ON → visible:true 로 위임한다", async () => {
    planSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    render(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    expect(planSpy).toHaveBeenCalled();
    expect(visibleArgs()).toContain(true);
    expect(visibleArgs()).not.toContain(false);
  });

  it("★★토글 OFF → visible:false 로 위임한다 — `|| true` 변이를 죽이는 단언", async () => {
    planSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    render(<SatongMultiMap layerState={st({ cadastre: ["boundary"] })} />);
    expect(planSpy).toHaveBeenCalled();
    // 이 단언이 없으면 «항상 true» 인 구현도 초록이다.
    expect(visibleArgs()).toContain(false);
    expect(visibleArgs()).not.toContain(true);
  });

  it("★렌더 위임도 실제로 일어난다 — 계획만 세우고 안 그리면 화면이 안 바뀐다", async () => {
    renderSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    render(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    expect(renderSpy).toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("E 시간축 — 토글은 **바뀌는 것**이고, 정리는 **끝나는 것**이다", () => {
  const visibleArgs = () =>
    (planSpy.mock.calls as unknown as [{ visible: boolean }][]).map((c) => c[0].visible);

  it("★★ON → OFF 로 바꾸면 위임이 다시 일어나고 visible 이 뒤집힌다", async () => {
    planSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    const { rerender } = render(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    expect(visibleArgs()).toEqual([true]);

    rerender(<SatongMultiMap layerState={st({ cadastre: ["boundary"] })} />);
    // ★deps 에서 selectionLabelsOn 을 빼면 여기서 재실행이 안 일어나 [true] 로 남는다.
    expect(visibleArgs()).toEqual([true, false]);
  });

  it("★OFF → ON 도 대칭으로 동작한다(한쪽만 걸면 반대쪽이 무제한)", async () => {
    planSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    const { rerender } = render(<SatongMultiMap layerState={st({ cadastre: ["boundary"] })} />);
    rerender(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    expect(visibleArgs()).toEqual([false, true]);
  });

  it("★★언마운트하면 레이어를 제거한다 — **낡은 라벨이 화면에 남는** 결함의 유일한 락", async () => {
    // 2차 리뷰 실측: 이 줄(`group?.remove?.()`)을 지워도 27건 전부 초록이었고,
    // 형제 `SatongMultiMap.layoutOverlay.test.tsx` 는 같은 형태를 **잡고 있었다**.
    // 추출 선례는 따랐는데 **락 선례는 안 따랐다.**
    removeSpy.mockClear();
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    const { unmount } = render(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    expect(removeSpy).not.toHaveBeenCalled(); // 음성 대조군 — 마운트만으로는 안 지운다
    unmount();
    expect(removeSpy).toHaveBeenCalledTimes(1);
  });

  it("★계획을 세우고 **그 계획을** 그리기에 넘긴다(중간에서 바꿔치기 방지)", async () => {
    planSpy.mockClear();
    renderSpy.mockClear();
    const sentinel = { kind: "empty" as const };
    planSpy.mockReturnValueOnce(sentinel);
    const { SatongMultiMap } = await import("@/components/map/SatongMultiMap");
    render(<SatongMultiMap layerState={st({ cadastre: ["boundary", "selected"] })} />);
    const arg = (renderSpy.mock.calls as unknown as [{ plan: unknown }][])[0][0];
    expect(arg.plan).toBe(sentinel);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("C 기본값(값) — 함수를 **실행해서** 판정에 먹인다", () => {
  it("★기본 상태는 표시다 — 사용자 요구 「기본은 나타나도록」", () => {
    // 텍스트가 아니라 값이다. `useState(() => ({...defaultControlsByLayer(), cadastre: []}))`
    // 같은 초기값 뒤집기가 이 단언에 걸린다.
    expect(satongSelectionLabelsVisible(st(defaultControlsByLayer()))).toBe(true);
  });

  it("★그 기본값이 실제로 useState 초기화자로 쓰인다(배선)", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(process.cwd(), "components/precheck/SatongMapShell.tsx"), "utf8"),
      "SatongMapShell.tsx",
    );
    expect(src).toMatch(/useState<SatongMapLayerState\["controlsByLayer"\]>\(\(\) => defaultControlsByLayer\(\)\)/);
    // 그리고 그 상태가 layerState 로 흘러간다.
    expect(src).toMatch(/controlsByLayer:\s*layerControls/);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// D 호출부 — 어휘 소속이 아니라 **판정 결과**를 파생시킨다
const WEB = process.cwd();

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    if (e === "node_modules" || e === ".next" || e.startsWith(".")) continue;
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".tsx")) out.push(p);
  }
  return out;
}

function callerFiles(): string[] {
  return walk(join(WEB, "components"))
    .filter((p) => !p.includes("__tests__"))
    .filter((p) => /(?<![A-Za-z0-9_$])<SatongMultiMap/.test(__stripCommentsForScan(readFileSync(p, "utf8"), p)));
}

/** 툴바(레이어 설정 패널)를 가진 화면 = 사용자가 라벨을 **다시 켤 수 있는** 유일한 화면. */
const HAS_TOOLBAR = new Set(["SatongMapShell.tsx"]);

describe("D 호출부 — 판정 결과를 파생시킨다", () => {
  it("★호출부를 실제로 모았다(개수를 실측에 결속 · 양방향)", () => {
    const n = callerFiles().length;
    // 실측 6. 상·하한을 실제 값에 붙인다 — 느슨하면 «2곳이 사라져도 통과» 한다.
    expect(n).toBeGreaterThanOrEqual(6);
    expect(n).toBeLessThanOrEqual(8);
  });

  it("★★판정이 false 로 떨어지는 호출부는 반드시 툴바가 있어야 한다", () => {
    // 툴바가 없는 화면에서 false 면 라벨을 **조작 수단 없이 영구 상실**한다.
    // 어휘 소속(대리변수)이 아니라 **판정 함수에 실제로 먹여** 본다.
    const offenders: string[] = [];
    let declared = 0;
    for (const p of callerFiles()) {
      const src = __stripCommentsForScan(readFileSync(p, "utf8"), p);
      const m = src.match(/cadastre:\s*\[([^\]]*)\]/);
      if (!m) continue;
      declared += 1;
      const ids = m[1]
        .split(",")
        .map((r) => r.trim().replace(/^["']|["']$/g, ""))
        .filter(Boolean);
      if (!satongSelectionLabelsVisible(st({ cadastre: ids }))) {
        const base = p.split("/").pop()!;
        if (!HAS_TOOLBAR.has(base)) offenders.push(`${base}: [${ids.join(", ")}]`);
      }
    }
    expect(declared).toBeGreaterThanOrEqual(3); // 대조군 — 선언한 호출부가 실제로 있다
    expect(offenders).toEqual([]);
  });

  it("★HAS_TOOLBAR 면제가 **죽어 있지 않다** — 합성 위반 1건으로 루프를 태운다", () => {
    // 리뷰 minor-2 실측: 면제 집합을 세 파일로 넓혀도 SURVIVED 였다 — 현재 false 로
    // 떨어지는 호출부가 없어 **면제가 한 번도 참조되지 않기** 때문이다(§36 죽은 면제).
    const judge = (base: string, ids: string[]) =>
      !satongSelectionLabelsVisible(st({ cadastre: ids })) && !HAS_TOOLBAR.has(base);
    // 툴바 없는 화면이 false → 위반
    expect(judge("ZoningSignalMap.tsx", ["parcel-boundary"])).toBe(true);
    // 툴바 있는 화면이 false → 위반 아님(사용자가 스스로 껐다)
    expect(judge("SatongMapShell.tsx", ["boundary"])).toBe(false);
  });

  it("★양성 대조군 — 판정 함수가 실제로 false 를 낼 수 있다", () => {
    // 위 단언이 «판정이 늘 true 라서» 초록인 것이 아님을 증명한다.
    expect(satongSelectionLabelsVisible(st({ cadastre: ["parcel-boundary"] }))).toBe(false);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ★계획서 §5 가 선언하고도 **존재하지 않던** 4번째 락(2차 리뷰 MAJOR-3).
//   *"선언됐지만 안 읽히는 컨트롤을 세어, 늘면 실패"* — 이 결함(선언만 있고 소비처 0)이
//   **또 생기는 것**을 막는다. 이 PR 자신이 그 형태였다.
describe("F 미배선 감지 — 선언만 하고 안 읽히는 컨트롤을 센다", () => {
  /** 실제로 «컨트롤로서» 읽히는 id — 부분문자열이 아니라 **소비 형태**로 판정한다. */
  function readControlIds(): Set<string> {
    const read = new Set<string>();
    for (const f of walk(join(WEB, "components")).concat(walk(join(WEB, "lib")))) {
      if (f.includes("__tests__")) continue;
      const src = __stripCommentsForScan(readFileSync(f, "utf8"), f);
      // ★`hasSatongLayerControl(state, layer, "<id>")` 의 3번째 인자만 센다.
      //   `feature.source === "boundary"` 같은 **동명의 다른 것**을 세지 않기 위해서다
      //   (초판에서 실제로 그 부분문자열에 속아 "boundary 는 읽힌다"고 오독했다).
      for (const m of src.matchAll(/hasSatongLayerControl\(\s*[^,]+,\s*"[^"]+",\s*"([^"]+)"/g)) {
        read.add(m[1]);
      }
    }
    // 닫힌 집합으로 소비되는 것도 «읽힘» 이다.
    for (const id of SATONG_SELECTION_LABEL_CONTROL_IDS) read.add(id);
    return read;
  }

  it("★조회기가 살아 있다(대조군) — 다른 레이어의 컨트롤은 읽힌다", () => {
    const read = readControlIds();
    // 이 단언이 없으면 «전부 미배선» 이라는 결과가 «조회기 사망» 과 구별되지 않는다.
    expect(read.has("land-use")).toBe(true);
    expect(read.size).toBeGreaterThanOrEqual(5);
  });

  it("★★cadastre 의 미배선 컨트롤은 정확히 boundary·neighbors 뿐이다(래칫)", () => {
    const cadastre = SATONG_MAP_SHELL_LAYERS.find((l) => l.id === "cadastre");
    expect(cadastre).toBeTruthy();
    const declared = cadastre!.controls!.map((c) => c.id);
    expect(declared).toContain("selected"); // 모집단이 실제로 있다

    const read = readControlIds();
    const unread = declared.filter((id) => !read.has(id)).sort();
    // ★부채를 **이름으로** 못 박는다. 늘면(새 컨트롤을 선언만 하면) 실패하고,
    //   줄면(boundary 를 배선하면) 역시 실패해서 **래칫을 내리도록 강제**한다(§36 죽은 면제).
    expect(unread).toEqual(["boundary", "neighbors"]);
  });
});
