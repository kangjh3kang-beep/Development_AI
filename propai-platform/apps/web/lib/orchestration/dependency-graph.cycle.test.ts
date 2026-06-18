// 순수 그래프 엔진 — 사이클 throw 검증(별도 파일: node-registry를 cyclic으로 mock)
// 실제 레지스트리는 무사이클이라 throw 경로를 직접 못 타므로, 합성 cyclic 그래프를 주입해 검증.
import { describe, it, expect, vi } from "vitest";

// a→b→a 순환 합성 레지스트리(최소 필드만; topoSort/topoLevels는 id·upstream·storyOrder만 사용).
vi.mock("./node-registry", () => ({
  NODES: [
    { id: "a", storyOrder: 1, upstream: ["b"], moduleKey: null },
    { id: "b", storyOrder: 2, upstream: ["a"], moduleKey: null },
  ],
}));

describe("topoSort / topoLevels — 사이클 throw", () => {
  it("a↔b 순환이면 topoSort가 throw", async () => {
    const { topoSort } = await import("./dependency-graph");
    expect(() => topoSort(["a", "b"] as never)).toThrowError(/사이클/);
  });

  it("a↔b 순환이면 topoLevels도 throw(내부 topoSort 경유)", async () => {
    const { topoLevels } = await import("./dependency-graph");
    expect(() => topoLevels(["a", "b"] as never)).toThrowError(/사이클/);
  });
});
