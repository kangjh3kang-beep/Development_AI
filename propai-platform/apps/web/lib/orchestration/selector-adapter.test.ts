// selector-adapter 단위테스트 — Phase B B3
// nodesToOptions: storylineStage 그룹핑, coinCost=feeOf(미설정 0), locked(폐포강제),
// description(신선·미가용·의존 정직표기), required=land.
// ★audit은 심의엔진 BFF 풀통합으로 available:true(unlock) — 폐포강제일 때만 '의존 항목' locked.
import { describe, it, expect } from "vitest";
import { nodesToOptions } from "./selector-adapter";
import type { SelectorAdapterCtx } from "./selector-adapter";
import type { NodeId } from "./types";

const ALL: NodeId[] = [
  "land",
  "legal",
  "recommend",
  "design",
  "audit",
  "sales",
  "qto",
  "feasibility",
  "finance",
];

/** 기본 ctx — 신선 없음, 폐포 강제 없음. */
const baseCtx: SelectorAdapterCtx = {
  isFresh: () => false,
  isClosureForced: () => false,
};

/** 모든 요율 미설정(0=무료) feeOf. */
const zeroFee = () => 0;

/** 평탄화: 모든 자식 옵션을 key로 찾는다(그룹은 부모, 노드는 자식). */
function flatten(opts: ReturnType<typeof nodesToOptions>) {
  const map = new Map<string, (typeof opts)[number]>();
  for (const g of opts) {
    map.set(g.key, g);
    for (const c of g.children ?? []) map.set(c.key, c);
  }
  return map;
}

describe("nodesToOptions — 그룹핑·키", () => {
  it("storylineStage로 그룹핑(부모=group:*, 자식 key=NodeId)", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    // 모든 부모는 group: 접두사, children 보유.
    for (const g of opts) {
      expect(g.key.startsWith("group:")).toBe(true);
      expect((g.children?.length ?? 0)).toBeGreaterThan(0);
    }
    // 9노드 전부 자식으로 등장(누락 없음).
    const flat = flatten(opts);
    for (const id of ALL) expect(flat.has(id)).toBe(true);
  });

  it("feasibility 그룹에 sales·feasibility가 함께(같은 storylineStage)", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const feasGroup = opts.find((g) => g.key === "group:feasibility");
    const childKeys = (feasGroup?.children ?? []).map((c) => c.key);
    expect(childKeys).toContain("sales");
    expect(childKeys).toContain("feasibility");
  });

  it("design 그룹에 design·audit(같은 storylineStage), storyOrder 오름차순", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const designGroup = opts.find((g) => g.key === "group:design");
    const childKeys = (designGroup?.children ?? []).map((c) => c.key);
    expect(childKeys).toEqual(["design", "audit"]); // storyOrder 4 < 5
  });

  it("scope 밖 노드는 제외(scoped만 변환)", () => {
    const opts = nodesToOptions(["land", "qto"], zeroFee, baseCtx);
    const flat = flatten(opts);
    expect(flat.has("land")).toBe(true);
    expect(flat.has("qto")).toBe(true);
    expect(flat.has("finance")).toBe(false);
  });
});

describe("nodesToOptions — coinCost(관리자 요율, 하드코딩 금지)", () => {
  it("feeOf(billingKey) 값을 coinCost로 주입", () => {
    const fee = (k: string) => (k === "stage:land" ? 5000 : k === "stage:finance" ? 12000 : 0);
    const opts = nodesToOptions(ALL, fee, baseCtx);
    const flat = flatten(opts);
    expect(flat.get("land")?.coinCost).toBe(5000);
    expect(flat.get("finance")?.coinCost).toBe(12000);
    // 미설정 키는 0(무료).
    expect(flat.get("legal")?.coinCost).toBe(0);
  });

  it("요율 전부 미설정이면 coinCost=0(무료)", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const flat = flatten(opts);
    for (const id of ALL) expect(flat.get(id)?.coinCost).toBe(0);
  });
});

describe("nodesToOptions — locked(정직 표기)", () => {
  it("audit(available:true·심의엔진 BFF 풀통합)는 unlock — 평시 근거 표기", () => {
    // ★새 계약: audit은 심의분석엔진 BFF 풀통합으로 available:true가 됐다.
    // 더는 unavailableLocked가 아니므로(폐포 강제도 없음) locked:false·lockedCtaLabel 미표기.
    // description은 평시 그라운딩 출처(근거:)를 표기한다(미가용 라벨이 아님).
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const audit = flatten(opts).get("audit");
    expect(audit?.locked).toBe(false);
    expect(audit?.lockedCtaLabel).toBeUndefined();
    expect(audit?.description?.startsWith("근거:")).toBe(true);
  });

  it("폐포 강제 노드는 locked + '의존 항목(자동 포함)'", () => {
    const ctx: SelectorAdapterCtx = {
      isFresh: () => false,
      isClosureForced: (id) => id === "legal", // legal이 상류 의존으로 강제 포함됐다고 가정
    };
    const opts = nodesToOptions(ALL, zeroFee, ctx);
    const legal = flatten(opts).get("legal");
    expect(legal?.locked).toBe(true);
    expect(legal?.lockedCtaLabel).toBe("의존 항목(자동 포함)");
  });

  it("audit(available:true)도 폐포강제면 '의존 항목(자동 포함)' locked(미가용 우선 분기 제거)", () => {
    // ★새 계약: audit이 available:true가 되어 unavailableLocked 분기를 더는 타지 않는다.
    // 따라서 폐포 강제(상류 의존)면 다른 노드와 동일하게 closure-forced locked('의존 항목')로 표기된다.
    const ctx: SelectorAdapterCtx = {
      isFresh: () => false,
      isClosureForced: () => true, // 전부 강제로 가정
    };
    const opts = nodesToOptions(ALL, zeroFee, ctx);
    const audit = flatten(opts).get("audit");
    expect(audit?.locked).toBe(true);
    expect(audit?.lockedCtaLabel).toBe("의존 항목(자동 포함)");
  });
});

describe("nodesToOptions — description(신선/근거 정직)", () => {
  it("신선분은 '최신(스킵)' 표기", () => {
    const ctx: SelectorAdapterCtx = {
      isFresh: (id) => id === "land",
      isClosureForced: () => false,
    };
    const opts = nodesToOptions(ALL, zeroFee, ctx);
    const land = flatten(opts).get("land");
    expect(land?.description).toContain("최신(스킵)");
  });

  it("평시는 그라운딩 출처를 근거로 표기", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const land = flatten(opts).get("land");
    expect(land?.description?.startsWith("근거:")).toBe(true);
  });
});

describe("nodesToOptions — required(land 루트)", () => {
  it("land는 required(부지=사실근거 루트), locked 아닐 때만", () => {
    const opts = nodesToOptions(ALL, zeroFee, baseCtx);
    const land = flatten(opts).get("land");
    expect(land?.required).toBe(true);
  });

  it("land가 폐포강제로 locked면 required 아님(중복 표기 방지)", () => {
    const ctx: SelectorAdapterCtx = {
      isFresh: () => false,
      isClosureForced: (id) => id === "land",
    };
    const opts = nodesToOptions(ALL, zeroFee, ctx);
    const land = flatten(opts).get("land");
    expect(land?.required).toBe(false);
    expect(land?.locked).toBe(true);
  });
});
