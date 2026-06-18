// 레지스트리 lint 강제 — CI 게이트(vitest). 실제 레지스트리가 계약 5단계·사이클·중복·일관성을 만족하는지 단언.
// 단독 CLI(scripts/lint-node-registry.ts)와 동일 lintNodeRegistry()를 호출 → errors=0이어야 통과.
import { describe, it, expect } from "vitest";
import { lintNodeRegistry } from "@/scripts/lint-node-registry";
import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId } from "@/lib/orchestration/types";

// 실 노드를 얕은 복사로 변형(함수 필드 readyCheck는 참조 보존 — structuredClone 불가).
function withNode(id: NodeId, patch: Partial<AnalysisNode>): AnalysisNode[] {
  return NODES.map((n) => (n.id === id ? { ...n, ...patch } : n));
}

describe("lint-node-registry — 노드 불변계약 CI 게이트", () => {
  it("현재 9노드 레지스트리는 위반(errors) 0", () => {
    const { errors } = lintNodeRegistry();
    expect(errors).toEqual([]);
  });

  // W1 드리프트는 fail이 아니라 warn(블루프린트 §6). 알려진 1건만 허용(legal/compliance vs design):
  // store MODULE_UPSTREAM[compliance]=["siteAnalysis","design"]이나, legal 노드는 부지(land)만 소비하고
  // design 이전에 실행되는 게 도메인상 정상이다(법규검토는 설계 산출이 없어도 가능). 의도된 차이라 warn 유지.
  it("MODULE_UPSTREAM 드리프트는 알려진 legal/compliance 1건만(의도된 차이, fail 아님)", () => {
    const { warnings } = lintNodeRegistry();
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain("legal");
    expect(warnings[0]).toContain("design");
  });
});

// 네거티브 — lint 자체가 위반을 실제로 잡는지(깨진 레지스트리 주입). lint가 조용히 통과하는 회귀 차단.
describe("lint-node-registry — 네거티브(깨진 레지스트리 감지)", () => {
  it("[E3] 중복 billingKey 주입 → errors 발생", () => {
    const dup = NODES.find((n) => n.id === "land")!.billingKey!;
    const { errors } = lintNodeRegistry(withNode("legal", { billingKey: dup }));
    expect(errors.some((e) => e.includes("E3"))).toBe(true);
  });

  it("[E4] reportContract.unavailableLabel 빈 문자열 → errors 발생", () => {
    const land = NODES.find((n) => n.id === "land")!;
    const { errors } = lintNodeRegistry(
      withNode("land", { reportContract: { ...land.reportContract, unavailableLabel: "" } }),
    );
    expect(errors.some((e) => e.includes("E4") && e.includes("unavailableLabel"))).toBe(true);
  });

  it("[E4] verify.crossValidate=false → errors 발생(true 강제·우회 차단)", () => {
    const land = NODES.find((n) => n.id === "land")!;
    const { errors } = lintNodeRegistry(
      withNode("land", { verify: { ...land.verify, crossValidate: false } }),
    );
    expect(errors.some((e) => e.includes("E4") && e.includes("crossValidate"))).toBe(true);
  });

  it("[E4] 판단분기 노드 expertPanel=false → errors 발생", () => {
    const { errors } = lintNodeRegistry(withNode("legal", { expertPanel: false }));
    expect(errors.some((e) => e.includes("E4") && e.includes("expertPanel"))).toBe(true);
  });

  it("[E1] upstream 자기참조 → 사이클 errors 발생", () => {
    const legal = NODES.find((n) => n.id === "legal")!;
    const { errors } = lintNodeRegistry(
      withNode("legal", { upstream: [...legal.upstream, "legal"] }),
    );
    expect(errors.some((e) => e.includes("E1"))).toBe(true);
  });
});
