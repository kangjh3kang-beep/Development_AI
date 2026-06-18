// 순수 그래프 엔진 단위테스트 — Phase B B1
// 폐포(finance→9전노드)·topoSort(순서·사이클 throw)·topoLevels(레벨)·currentSignature(안정성)·guidedOrder.
import { describe, it, expect } from "vitest";
import {
  computeClosure,
  topoSort,
  topoLevels,
  moduleKeyOf,
  currentSignature,
  guidedOrder,
} from "./dependency-graph";
import { NODES } from "./node-registry";
import type { NodeId, ProjectContextState } from "./types";

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

// finance 폐포에서 audit은 제외된다 — audit은 design·legal을 소비하는 "말단 검증 노드"라
// 다른 노드가 audit을 upstream으로 갖지 않는다(§1-C: 아무도 audit을 의존하지 않음). 따라서
// 어떤 시드의 폐포에도 audit은 명시적으로 audit을 시드/포함했을 때만 들어간다.
const ALL_BUT_AUDIT: NodeId[] = ALL.filter((id) => id !== "audit");

describe("computeClosure — 의존성 폐포(상류 전이 포함)", () => {
  it("finance 폐포 = audit 제외 8노드(finance→feasibility,qto→sales,land,design→recommend→legal→land). audit은 말단 검증노드라 미포함", () => {
    const closure = computeClosure(["finance"]);
    expect(new Set(closure)).toEqual(new Set(ALL_BUT_AUDIT));
    expect(closure).toHaveLength(8);
    expect(closure).not.toContain("audit");
  });

  it("audit를 시드에 명시하면 전 9노드 폐포(finance+audit)", () => {
    const closure = computeClosure(["finance", "audit"]);
    expect(new Set(closure)).toEqual(new Set(ALL));
    expect(closure).toHaveLength(9);
  });

  it("land 폐포 = [land] (상류 없음)", () => {
    expect(computeClosure(["land"])).toEqual(["land"]);
  });

  it("design 폐포 = land, legal, recommend, design (recommend→legal→land 전이)", () => {
    expect(new Set(computeClosure(["design"]))).toEqual(
      new Set<NodeId>(["land", "legal", "recommend", "design"]),
    );
  });

  it("qto 폐포 = land, legal, recommend, design, qto", () => {
    expect(new Set(computeClosure(["qto"]))).toEqual(
      new Set<NodeId>(["land", "legal", "recommend", "design", "qto"]),
    );
  });

  it("feasibility 폐포는 finance를 포함하지 않음(상류만, 하류 제외)", () => {
    const closure = computeClosure(["feasibility"]);
    expect(closure).not.toContain("finance");
    expect(closure).toContain("sales");
    expect(closure).toContain("qto");
  });

  it("반환은 storyOrder 오름차순 안정 정렬", () => {
    const closure = computeClosure(["finance"]);
    const orders = closure.map((id) => NODES.find((n) => n.id === id)!.storyOrder);
    expect(orders).toEqual([...orders].sort((a, b) => a - b));
  });

  it("중복 시드는 한 번만(사이클가드 방문집합)", () => {
    expect(computeClosure(["land", "land", "legal"]).sort()).toEqual(["land", "legal"]);
  });
});

describe("topoSort — 위상정렬(Kahn, storyOrder tie-break)", () => {
  it("전노드 정렬: 모든 upstream이 자기보다 앞", () => {
    const order = topoSort(ALL);
    const pos = new Map(order.map((id, i) => [id, i]));
    for (const node of NODES) {
      for (const up of node.upstream) {
        expect(pos.get(up)!).toBeLessThan(pos.get(node.id)!);
      }
    }
  });

  it("land가 항상 첫 노드(상류 없음·storyOrder 1)", () => {
    expect(topoSort(ALL)[0]).toBe("land");
  });

  it("finance가 항상 마지막(최하류)", () => {
    expect(topoSort(ALL).at(-1)).toBe("finance");
  });

  it("부분집합 정렬 가능(집합 밖 의존은 완료로 가정)", () => {
    const order = topoSort(["finance", "feasibility"]);
    expect(order).toEqual(["feasibility", "finance"]);
  });

  it("동일 in-degree는 storyOrder로 결정적 tie-break", () => {
    // legal(2)·design 분기에서 storyOrder 작은 쪽 우선.
    const order = topoSort(["legal", "qto", "sales"]);
    // 셋 다 집합 내부 상류가 없으므로 storyOrder순: legal(2)<sales(6)<qto(7)
    expect(order).toEqual(["legal", "sales", "qto"]);
  });
});

describe("topoLevels — 레벨(rank)별 병렬 그룹", () => {
  it("레벨 0은 land만(상류 없음)", () => {
    const levels = topoLevels(ALL);
    expect(levels[0]).toEqual(["land"]);
  });

  it("각 노드의 레벨 > 모든 집합내 upstream의 레벨", () => {
    const levels = topoLevels(ALL);
    const rankOf = new Map<NodeId, number>();
    levels.forEach((lv, r) => lv.forEach((id) => rankOf.set(id, r)));
    for (const node of NODES) {
      for (const up of node.upstream) {
        expect(rankOf.get(node.id)!).toBeGreaterThan(rankOf.get(up)!);
      }
    }
  });

  it("모든 노드가 정확히 한 레벨에 한 번 등장(누락·중복 없음)", () => {
    const levels = topoLevels(ALL);
    const flat = levels.flat();
    expect(flat).toHaveLength(9);
    expect(new Set(flat)).toEqual(new Set(ALL));
  });

  it("finance는 최상위 레벨(feasibility 다음)", () => {
    const levels = topoLevels(ALL);
    const last = levels.at(-1)!;
    expect(last).toContain("finance");
  });
});

describe("moduleKeyOf — 노드→ModuleKey", () => {
  it("moduleKey 보유 노드", () => {
    expect(moduleKeyOf("land")).toBe("siteAnalysis");
    expect(moduleKeyOf("legal")).toBe("compliance");
    expect(moduleKeyOf("design")).toBe("design");
    expect(moduleKeyOf("qto")).toBe("cost");
    expect(moduleKeyOf("feasibility")).toBe("feasibility");
    expect(moduleKeyOf("finance")).toBe("finance");
  });

  it("파생/검증/피드 노드는 null", () => {
    expect(moduleKeyOf("recommend")).toBeNull();
    expect(moduleKeyOf("audit")).toBeNull();
    expect(moduleKeyOf("sales")).toBeNull();
  });
});

describe("currentSignature — 입력 시그니처 안정성", () => {
  // 최소 store 모양(필요 슬롯만). 타입 안전을 위해 캐스팅.
  const mkState = (over: Partial<ProjectContextState>): ProjectContextState =>
    ({
      siteAnalysis: null,
      designData: null,
      costData: null,
      feasibilityData: null,
      esgData: null,
      complianceData: null,
      ...over,
    }) as unknown as ProjectContextState;

  it("동일 입력 → 동일 시그니처(결정적)", () => {
    const s = mkState({
      siteAnalysis: { address: "서울 강남", landAreaSqm: 1000, pnu: "1168010100" } as never,
      complianceData: { violations: [] } as never,
    });
    expect(currentSignature("recommend", s)).toBe(currentSignature("recommend", s));
  });

  it("입력 변경 → 시그니처 변경", () => {
    const a = mkState({ siteAnalysis: { address: "A", landAreaSqm: 1000, pnu: "1" } as never });
    const b = mkState({ siteAnalysis: { address: "B", landAreaSqm: 1000, pnu: "1" } as never });
    expect(currentSignature("recommend", a)).not.toBe(currentSignature("recommend", b));
  });

  it("객체 키 순서가 달라도 동일 시그니처(안정 직렬화)", () => {
    const a = mkState({ siteAnalysis: { address: "A", landAreaSqm: 1, pnu: "1" } as never });
    const b = mkState({ siteAnalysis: { pnu: "1", landAreaSqm: 1, address: "A" } as never });
    expect(currentSignature("recommend", a)).toBe(currentSignature("recommend", b));
  });

  it("빈 store는 결정적 빈 슬롯 시그니처", () => {
    const empty = mkState({});
    expect(typeof currentSignature("sales", empty)).toBe("string");
    expect(currentSignature("sales", empty)).toBe(currentSignature("sales", mkState({})));
  });
});

describe("guidedOrder — 가이드 모드 전노드 위상순", () => {
  it("9개 전노드를 위상순으로 반환", () => {
    const order = guidedOrder();
    expect(order).toHaveLength(9);
    expect(new Set(order)).toEqual(new Set(ALL));
  });

  it("의존성 보존(upstream이 항상 앞)", () => {
    const order = guidedOrder();
    const pos = new Map(order.map((id, i) => [id, i]));
    for (const node of NODES) {
      for (const up of node.upstream) {
        expect(pos.get(up)!).toBeLessThan(pos.get(node.id)!);
      }
    }
  });

  it("land 시작·finance 종료", () => {
    const order = guidedOrder();
    expect(order[0]).toBe("land");
    expect(order.at(-1)).toBe("finance");
  });
});
