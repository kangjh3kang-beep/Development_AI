/**
 * 「선택 필지」 라벨 토글 — 기본 ON · 끌 수 있음 (2026-09-03)
 *
 * ★이 파일이 잠그는 것과 잠그지 못하는 것을 먼저 적는다.
 *   jsdom 은 Leaflet CDN 을 로드하지 않아 `mapReady` 가 영영 false 다 — 라벨 이펙트는
 *   **아예 실행되지 않는다**. 그래서 "라벨이 실제로 사라지는가"를 렌더로 태울 수 없다.
 *   대신 세 축을 각각 잠근다:
 *     ① 판정        — satongSelectionLabelsVisible 이 두 모집단을 가르는가
 *     ② 호출부 선언 — 실제 호출부 6곳이 그 판정에서 어떻게 갈리는가(파생형)
 *     ③ 배선        — 이펙트가 그 판정을 실제로 소비하는가(주석 제거 경유)
 *   ★미측정: 브라우저에서 라벨이 눈으로 사라지는 것(라이브 검증에서 잰다).
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  SATONG_SELECTION_LABEL_CONTROL_IDS,
  satongSelectionLabelsVisible,
  type SatongMapLayerState,
} from "@/lib/satong-map-layers";
import { __stripCommentsForScan, assertWiredThrough } from "@/lib/source-invariant";

const st = (controls: SatongMapLayerState["controlsByLayer"]): SatongMapLayerState => ({
  enabledLayerIds: [],
  controlsByLayer: controls,
});

describe("① 판정 — 두 모집단이 실제로 갈린다", () => {
  it("컨트롤이 켜져 있으면 표시한다", () => {
    expect(satongSelectionLabelsVisible(st({ cadastre: ["boundary", "selected"] }))).toBe(true);
  });

  it("★컨트롤을 끄면 숨긴다 — 이 케이스가 사용자의 요구 그 자체다", () => {
    // 「선택 필지」만 뺀다. 다른 컨트롤은 그대로 있다 = 「cadastre 를 통째로 지웠다」가 아니다.
    expect(satongSelectionLabelsVisible(st({ cadastre: ["boundary"] }))).toBe(false);
  });

  it("★컨트롤을 선언하지 않으면 표시한다 — 끄는 UI 가 없는 화면에서 사라지면 안 된다", () => {
    expect(satongSelectionLabelsVisible(undefined)).toBe(true);
    expect(satongSelectionLabelsVisible(st({}))).toBe(true);
    expect(satongSelectionLabelsVisible(st({ zoning: ["land-use"] }))).toBe(true);
  });

  it("★닫힌 집합의 **내용**을 못 박는다 — 자기지시 루프만으로는 못 잡는다", () => {
    // 실측 2026-09-03: 집합에서 "selected-parcel" 을 지우는 변이를 ①만으로 판정하니
    // **SURVIVED** 였다 — 아래 `for (const id of SATONG_...)` 루프가 집합과 **함께 깎여**
    // 단언이 조용히 사라지기 때문이다(전체 실행에서는 ②가 잡았다 = 형제 락의 공).
    // 기대값을 집합에서 파생시키지 않고 **리터럴로** 적어야 그 축이 실제로 잠긴다.
    expect([...SATONG_SELECTION_LABEL_CONTROL_IDS].sort()).toEqual(["selected", "selected-parcel"]);
  });

  it("두 어휘를 모두 인정한다(selected · selected-parcel)", () => {
    for (const id of SATONG_SELECTION_LABEL_CONTROL_IDS) {
      expect(satongSelectionLabelsVisible(st({ cadastre: [id] }))).toBe(true);
    }
    // ★음성 대조군 — 아무 문자열이나 통과하지 않는다(위 단언이 공허하지 않음을 증명).
    expect(satongSelectionLabelsVisible(st({ cadastre: ["selected-something-else"] }))).toBe(false);
  });
});

// ── ② 호출부 선언 — 손 목록이 아니라 소스에서 **파생**한다 ─────────────────────
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

/** 프로덕션(테스트 제외) `<SatongMultiMap` 호출부 파일 — 파생형. */
function callerFiles(): string[] {
  return walk(join(WEB, "components"))
    .filter((p) => !p.includes("__tests__"))
    .filter((p) => /(?<![A-Za-z0-9_$])<SatongMultiMap/.test(__stripCommentsForScan(readFileSync(p, "utf8"), p)));
}

describe("② 호출부 선언 — 파생형", () => {
  it("★호출부를 실제로 모았다(공허진리 방지)", () => {
    // 하한만 걸면 「너무 많이 잡음」이 안 잡히므로 상한도 함께 건다(양방향).
    const n = callerFiles().length;
    expect(n).toBeGreaterThanOrEqual(4);
    expect(n).toBeLessThanOrEqual(12);
  });

  it("★cadastre 컨트롤을 선언한 호출부는 반드시 알려진 어휘를 쓴다 — 세 번째 어휘를 막는다", () => {
    // 이 결함이 생긴 이유가 바로 「선언만 있고 소비처 0」이라 어휘가 두 벌로 갈린 것이다.
    // 소비처가 생긴 지금, 새 어휘가 조용히 들어오면 그 화면 라벨이 사라진다.
    const KNOWN = new Set<string>([
      ...SATONG_SELECTION_LABEL_CONTROL_IDS,
      "boundary",
      "parcel-boundary",
      "neighbors",
    ]);
    const offenders: string[] = [];
    let declared = 0;
    for (const p of callerFiles()) {
      const src = __stripCommentsForScan(readFileSync(p, "utf8"), p);
      const m = src.match(/cadastre:\s*\[([^\]]*)\]/);
      if (!m) continue;
      declared += 1;
      for (const raw of m[1].split(",")) {
        const id = raw.trim().replace(/^["']|["']$/g, "");
        if (id && !KNOWN.has(id)) offenders.push(`${p}: ${id}`);
      }
    }
    // ★대조군: 선언한 호출부가 하나도 없으면 위 루프가 공허하다.
    expect(declared).toBeGreaterThanOrEqual(1);
    expect(offenders).toEqual([]);
  });
});

// ── ③ 배선 — 이펙트가 그 판정을 실제로 소비하는가 ────────────────────────────
describe("③ 배선", () => {
  it("★라벨 이펙트가 판정 함수를 거치고 deps 에도 실린다", () => {
    for (const inv of [
      {
        file: "components/map/SatongMultiMap.tsx",
        // 대입줄이 아니라 **사용줄**만 보면 별칭 우회를 놓친다 → 대입줄을 본다.
        scope: /const\s+selectionLabelsOn\s*=/,
        mustContain: "satongSelectionLabelsVisible(layerState)",
        minMatches: 1,
      },
      {
        file: "components/map/SatongMultiMap.tsx",
        // deps 에 없으면 토글해도 이펙트가 재실행되지 않아 화면이 안 바뀐다.
        scope: /\}, \[mapReady, overlayFeatures, selectionRollup/,
        mustContain: "selectionLabelsOn",
        minMatches: 1,
      },
      {
        file: "components/map/SatongMultiMap.tsx",
        // 게이트 자체.
        scope: /if \(!selectionLabelsOn\) return;/,
        mustContain: "return",
        minMatches: 1,
      },
    ] as const) assertWiredThrough(inv);
  });

  it("★기본은 켜져 있다 — 툴바가 selected 를 기본값으로 준다", () => {
    const shell = __stripCommentsForScan(
      readFileSync(join(WEB, "components/precheck/SatongMapShell.tsx"), "utf8"),
      "SatongMapShell.tsx",
    );
    const m = shell.match(/function defaultControlsByLayer\(\)[\s\S]*?\n\}/);
    expect(m).toBeTruthy();
    const cad = m![0].match(/cadastre:\s*\[([^\]]*)\]/);
    expect(cad).toBeTruthy();
    const ids = cad![1].split(",").map((s) => s.trim().replace(/^["']|["']$/g, ""));
    expect(ids).toContain("selected");
  });
});
