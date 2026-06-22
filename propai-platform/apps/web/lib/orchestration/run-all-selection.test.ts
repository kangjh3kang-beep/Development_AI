import { describe, it, expect } from "vitest";
import { buildRunAllSelection } from "@/lib/orchestration/run-all-selection";
import { NODES } from "@/lib/orchestration/node-registry";
import type { NodeId } from "@/lib/orchestration/types";

describe("buildRunAllSelection — 전체분석 선택맵", () => {
  it("scope 내 레지스트리 유효 노드를 모두 true로", () => {
    expect(buildRunAllSelection(["land", "legal"])).toEqual({
      land: true,
      legal: true,
    });
  });

  it("레지스트리에 없는 id는 무시(가짜 노드 선택 금지)", () => {
    expect(buildRunAllSelection(["land", "bogus" as NodeId])).toEqual({
      land: true,
    });
  });

  it("중복 id는 한 번만", () => {
    expect(buildRunAllSelection(["land", "land"])).toEqual({ land: true });
  });

  it("빈 scope면 빈 맵", () => {
    expect(buildRunAllSelection([])).toEqual({});
  });

  it("전체 노드 scope면 NODES 수만큼 true", () => {
    const all = NODES.map((n) => n.id);
    const sel = buildRunAllSelection(all);
    expect(Object.keys(sel)).toHaveLength(NODES.length);
    expect(Object.values(sel).every((v) => v === true)).toBe(true);
  });
});
