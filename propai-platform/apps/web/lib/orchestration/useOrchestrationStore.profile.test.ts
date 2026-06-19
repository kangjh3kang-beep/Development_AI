// 분석 오케스트레이션 store — 프로필 모드 단위테스트(Phase B B5)
// 핵심 회귀 가드: applyProfile 후 seedNodes/computePlan(buildPlan·previewPlan)이
//   PRESET(프리셋)을 찾는지(갭 a·b 해소 검증) + 커스텀 라운드트립(save→delete→duplicate).
//
// 데이터 SSOT(useProjectContextStore)는 빈 상태로 시드해 결정성을 본다(무회귀: 데이터 store 미접촉).

import { describe, it, expect, beforeEach } from "vitest";

import { useOrchestrationStore } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { NodeId } from "@/lib/orchestration/types";

function resetData(): void {
  useProjectContextStore.setState({
    projectId: "p1",
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    updatedAt: {},
    snapshots: {},
    manualFields: {},
  });
}

function resetOrch(): void {
  useOrchestrationStore.setState({
    runMode: "guided",
    picked: {},
    activeProfileId: null,
    nodeOrder: [],
    plan: [],
    nodeResult: {},
    nodeUpdatedAt: {},
    currentProjectId: null,
    customProfiles: [],
    byProject: {},
  });
}

beforeEach(() => {
  resetData();
  resetOrch();
});

describe("applyProfile — 프리셋 적용(picked·순서·모드 세팅)", () => {
  it("프리셋(landowner-quick) 적용 시 picked/nodeOrder/activeProfileId/runMode 세팅", () => {
    useOrchestrationStore.getState().applyProfile("preset:landowner-quick");
    const st = useOrchestrationStore.getState();
    expect(st.activeProfileId).toBe("preset:landowner-quick");
    // 프로필 적용은 defaultMode와 무관하게 항상 'profile' 모드로 진입(guided 탭은 B4 미활성).
    expect(st.runMode).toBe("profile");
    expect(st.picked).toEqual({ land: true, legal: true, recommend: true, sales: true });
    expect(st.nodeOrder).toEqual(["land", "legal", "recommend", "sales"]);
  });

  it("디벨로퍼 풀패키지 적용 시 profile 모드 + finance 시드", () => {
    useOrchestrationStore.getState().applyProfile("preset:developer-full");
    const st = useOrchestrationStore.getState();
    // defaultMode:"guided"이지만 진입 모드는 'profile'로 통일(빈 화면 방지).
    expect(st.runMode).toBe("profile");
    expect(st.picked).toEqual({ finance: true });
  });

  it("없는 id면 무시(상태 불변)", () => {
    useOrchestrationStore.getState().applyProfile("preset:nope");
    expect(useOrchestrationStore.getState().activeProfileId).toBeNull();
  });
});

describe("★갭 회귀 가드 — buildPlan/seedNodes가 PRESET을 찾는다", () => {
  it("프리셋 적용 후 buildPlan(profile)이 프리셋 nodes를 시드로 폐포 산출(이전엔 custom만 봐서 빈 계획)", () => {
    useOrchestrationStore.getState().applyProfile("preset:landowner-quick");
    const steps = useOrchestrationStore.getState().buildPlan("profile");
    const ids = new Set(steps.map((s) => s.node));
    // landowner-quick = land·legal·recommend·sales. sales 상류로 design도 폐포 진입.
    expect(ids).toEqual(
      new Set<NodeId>(["land", "legal", "recommend", "design", "sales"]),
    );
    // 수지·금융은 미포함(빠른검토).
    expect(ids.has("feasibility")).toBe(false);
    expect(ids.has("finance")).toBe(false);
  });

  it("프리셋 적용 후 previewPlan(profile)도 동일 폐포(순수 미리보기, plan 미변경)", () => {
    useOrchestrationStore.getState().applyProfile("preset:pf-finance");
    const preview = useOrchestrationStore.getState().previewPlan("profile");
    const ids = new Set(preview.map((s) => s.node));
    expect(ids.has("land")).toBe(true); // 상류 자동충족
    expect(ids.has("feasibility")).toBe(true);
    expect(ids.has("finance")).toBe(true);
    // previewPlan은 plan을 변경하지 않는다.
    expect(useOrchestrationStore.getState().plan).toEqual([]);
  });

  it("프리셋 order가 computePlan 순서에 반영된다(갭 b — 이전엔 custom만 조회)", () => {
    // pf-finance order = [land, design, qto, sales, feasibility, finance].
    // nodeOrder를 비워 프로필 order가 힌트로 작동하게 한다.
    useOrchestrationStore.getState().applyProfile("preset:pf-finance");
    useOrchestrationStore.getState().setNodeOrder([]); // 사용자 재배열 없음 → 프로필 order 사용
    const steps = useOrchestrationStore.getState().buildPlan("profile");
    const order = steps.map((s) => s.node);
    const idx = (id: NodeId) => order.indexOf(id);
    // 프로필 order 힌트대로 land가 design보다 앞, design이 qto보다 앞.
    expect(idx("land")).toBeLessThan(idx("design"));
    expect(idx("design")).toBeLessThan(idx("qto"));
    // 의존성도 보존(feasibility가 finance보다 앞).
    expect(idx("feasibility")).toBeLessThan(idx("finance"));
  });

  it("사용자 재배열(nodeOrder)이 있으면 프로필 order보다 우선", () => {
    useOrchestrationStore.getState().applyProfile("preset:pf-finance");
    // sales를 맨 앞으로 끌어올리는 재배열(폐포 내 노드만 head로 반영).
    useOrchestrationStore.getState().setNodeOrder(["sales", "land", "design", "qto", "feasibility", "finance"]);
    const steps = useOrchestrationStore.getState().buildPlan("profile");
    const order = steps.map((s) => s.node);
    // sales가 land보다 앞으로 재배열됨(사용자 우선). 단 위상 자체는 head 순서를 그대로 쓴다.
    expect(order.indexOf("sales")).toBeLessThan(order.indexOf("land"));
  });
});

describe("커스텀 프로필 라운드트립 — save→delete→duplicate", () => {
  it("saveCustomProfile: 현재 picked를 커스텀으로 저장(leaf 기준)", () => {
    useOrchestrationStore.getState().setRunMode("selective");
    useOrchestrationStore.getState().setPicked({ qto: true, design: true });
    const id = useOrchestrationStore.getState().saveCustomProfile("내 적산 워크플로우", "설계+적산");
    expect(id).not.toBe("");
    const st = useOrchestrationStore.getState();
    expect(st.customProfiles).toHaveLength(1);
    const p = st.customProfiles[0];
    expect(p.id).toBe(id);
    expect(p.label).toBe("내 적산 워크플로우");
    expect(p.description).toBe("설계+적산");
    expect(p.builtin).toBe(false);
    expect(new Set(p.nodes)).toEqual(new Set<NodeId>(["qto", "design"]));
    expect(p.defaultMode).toBe("selective");
    expect(p.autoRunUpstream).toBe(true);
  });

  it("saveCustomProfile: 빈 라벨은 무시(저장 안 함, 반환 \"\")", () => {
    useOrchestrationStore.getState().setPicked({ land: true });
    const id = useOrchestrationStore.getState().saveCustomProfile("   ");
    expect(id).toBe("");
    expect(useOrchestrationStore.getState().customProfiles).toHaveLength(0);
  });

  it("저장한 커스텀을 applyProfile로 적용 가능(findProfile 잡힘)", () => {
    useOrchestrationStore.getState().setPicked({ design: true });
    const id = useOrchestrationStore.getState().saveCustomProfile("설계만");
    useOrchestrationStore.getState().setPicked({}); // 초기화 후 재적용
    useOrchestrationStore.getState().applyProfile(id);
    expect(useOrchestrationStore.getState().picked).toEqual({ design: true });
    expect(useOrchestrationStore.getState().activeProfileId).toBe(id);
  });

  it("deleteCustomProfile: 커스텀 삭제 + 활성이면 해제", () => {
    useOrchestrationStore.getState().setPicked({ land: true });
    const id = useOrchestrationStore.getState().saveCustomProfile("토지만");
    useOrchestrationStore.getState().applyProfile(id);
    expect(useOrchestrationStore.getState().activeProfileId).toBe(id);
    useOrchestrationStore.getState().deleteCustomProfile(id);
    const st = useOrchestrationStore.getState();
    expect(st.customProfiles).toHaveLength(0);
    expect(st.activeProfileId).toBeNull(); // 활성이었으므로 해제
  });

  it("deleteCustomProfile: 프리셋은 삭제 불가(무시)", () => {
    useOrchestrationStore.getState().deleteCustomProfile("preset:landowner-quick");
    // 프리셋은 customProfiles에 없으므로 변화 없음(에러 없이 무시).
    expect(useOrchestrationStore.getState().customProfiles).toHaveLength(0);
  });

  it("duplicateProfile: 프리셋 복제 → 새 커스텀(새 id·builtin:false·(복제) 라벨)", () => {
    const newId = useOrchestrationStore.getState().duplicateProfile("preset:architect");
    expect(newId).not.toBe("");
    const st = useOrchestrationStore.getState();
    expect(st.customProfiles).toHaveLength(1);
    const copy = st.customProfiles[0];
    expect(copy.id).toBe(newId);
    expect(copy.id).not.toBe("preset:architect");
    expect(copy.builtin).toBe(false);
    expect(copy.label).toBe("(복제) 설계사");
    // 원본 nodes/order 보존.
    expect(new Set(copy.nodes)).toEqual(new Set<NodeId>(["design", "audit", "qto"]));
  });

  it("duplicateProfile: newLabel 지정 시 그 라벨 사용", () => {
    const newId = useOrchestrationStore
      .getState()
      .duplicateProfile("preset:landowner-quick", "지주 검토 v2");
    const copy = useOrchestrationStore.getState().customProfiles.find((p) => p.id === newId)!;
    expect(copy.label).toBe("지주 검토 v2");
  });

  it("duplicateProfile: 커스텀도 복제 가능", () => {
    useOrchestrationStore.getState().setPicked({ qto: true });
    const id = useOrchestrationStore.getState().saveCustomProfile("원본");
    const dupId = useOrchestrationStore.getState().duplicateProfile(id);
    expect(dupId).not.toBe(id);
    expect(useOrchestrationStore.getState().customProfiles).toHaveLength(2);
  });

  it("duplicateProfile: 없는 id면 무시(반환 \"\")", () => {
    expect(useOrchestrationStore.getState().duplicateProfile("nope")).toBe("");
    expect(useOrchestrationStore.getState().customProfiles).toHaveLength(0);
  });
});
