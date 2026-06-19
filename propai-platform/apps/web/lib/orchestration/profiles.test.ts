// 워크플로우 프로필 SSOT 단위테스트 — Phase B B5
// 프리셋 4종의 폐포(상류 자동확장) 정합 + 헬퍼(allProfiles·findProfile) 검증.
// 무목업: 프리셋 nodes/order는 실제 NodeId만 사용. 폐포는 dependency-graph 엔진과 1:1.

import { describe, it, expect } from "vitest";

import {
  PRESET_PROFILES,
  allProfiles,
  findProfile,
  type WorkflowProfile,
} from "./profiles";
import { computeClosure } from "./dependency-graph";
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

/** id로 프리셋 조회(테스트 헬퍼). */
function preset(id: string): WorkflowProfile {
  const p = PRESET_PROFILES.find((x) => x.id === id);
  if (!p) throw new Error(`프리셋 없음: ${id}`);
  return p;
}

describe("PRESET_PROFILES — 4종 정합", () => {
  it("프리셋은 정확히 4개이며 모두 builtin·createdAt=0", () => {
    expect(PRESET_PROFILES).toHaveLength(4);
    expect(PRESET_PROFILES.every((p) => p.builtin)).toBe(true);
    expect(PRESET_PROFILES.every((p) => p.createdAt === 0)).toBe(true);
  });

  it("프리셋 id는 모두 preset:* 규약", () => {
    expect(PRESET_PROFILES.every((p) => p.id.startsWith("preset:"))).toBe(true);
  });

  it("프리셋 nodes/order는 모두 유효 NodeId", () => {
    const valid = new Set(ALL);
    for (const p of PRESET_PROFILES) {
      expect(p.nodes.every((n) => valid.has(n))).toBe(true);
      expect(p.order.every((n) => valid.has(n))).toBe(true);
    }
  });
});

describe("PRESET_PROFILES — 폐포(상류 자동확장) 검증", () => {
  it("developer-full: finance 시드 폐포 = 전 9노드 중 audit 제외 8노드(말단검증)이지만 order는 전 9노드 표기", () => {
    const p = preset("preset:developer-full");
    const closure = computeClosure(p.nodes); // ["finance"]
    // finance 폐포는 audit 제외 8노드(audit은 아무도 의존하지 않는 말단검증).
    expect(closure).not.toContain("audit");
    expect(closure).toHaveLength(8);
    // order는 디벨로퍼가 심의(audit)까지 보도록 전 9노드를 표기(표시 힌트).
    expect(new Set(p.order)).toEqual(new Set(ALL));
  });

  it("landowner-quick: 폐포에 finance·feasibility 미포함(수지·금융 제외)", () => {
    const p = preset("preset:landowner-quick");
    const closure = computeClosure(p.nodes);
    expect(closure).not.toContain("finance");
    expect(closure).not.toContain("feasibility");
    // 토지·법률·개발방식·분양성 + 분양성 상류(design)까지 자동확장.
    expect(closure).toContain("land");
    expect(closure).toContain("legal");
    expect(closure).toContain("recommend");
    expect(closure).toContain("sales");
  });

  it("pf-finance: 폐포에 land 포함(상류 자동충족)", () => {
    const p = preset("preset:pf-finance");
    const closure = computeClosure(p.nodes); // ["feasibility","finance"]
    expect(closure).toContain("land");
    expect(closure).toContain("feasibility");
    expect(closure).toContain("finance");
    // feasibility 상류(sales·qto·design)도 자동 포함.
    expect(closure).toContain("sales");
    expect(closure).toContain("qto");
    expect(closure).toContain("design");
  });

  it("architect: 폐포에 design·audit·qto 및 그 상류 포함", () => {
    const p = preset("preset:architect");
    const closure = computeClosure(p.nodes); // ["design","audit","qto"]
    expect(closure).toContain("design");
    expect(closure).toContain("audit");
    expect(closure).toContain("qto");
    // design/audit 상류(land·legal·recommend) 자동 포함.
    expect(closure).toContain("land");
    expect(closure).toContain("legal");
    expect(closure).toContain("recommend");
    // 수지·금융은 아님(설계 중심).
    expect(closure).not.toContain("feasibility");
    expect(closure).not.toContain("finance");
  });
});

describe("헬퍼 — allProfiles·findProfile", () => {
  it("allProfiles는 프리셋 먼저, 커스텀을 뒤에 합친다", () => {
    const custom: WorkflowProfile = {
      id: "uuid-1",
      label: "내 워크플로우",
      description: "",
      builtin: false,
      nodes: ["land"],
      order: ["land"],
      defaultMode: "selective",
      autoRunUpstream: true,
      createdAt: 1,
    };
    const all = allProfiles([custom]);
    expect(all).toHaveLength(PRESET_PROFILES.length + 1);
    expect(all[0].id).toBe(PRESET_PROFILES[0].id);
    expect(all.at(-1)!.id).toBe("uuid-1");
  });

  it("findProfile은 프리셋 ∪ 커스텀에서 찾는다(프리셋도 잡힘 — 갭 회귀 가드)", () => {
    expect(findProfile("preset:landowner-quick", [])?.label).toBe("지주 빠른검토");
    const custom: WorkflowProfile = {
      id: "uuid-2",
      label: "C",
      description: "",
      builtin: false,
      nodes: ["qto"],
      order: ["qto"],
      defaultMode: "selective",
      autoRunUpstream: true,
      createdAt: 2,
    };
    expect(findProfile("uuid-2", [custom])?.label).toBe("C");
  });

  it("findProfile은 null/미존재 id에 undefined", () => {
    expect(findProfile(null, [])).toBeUndefined();
    expect(findProfile("nope", [])).toBeUndefined();
  });
});
