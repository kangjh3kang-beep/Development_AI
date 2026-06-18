// 분석 오케스트레이션 실행슬라이스 store 단위테스트 — Phase B B2
// buildPlan(폐포·topo·신선스킵)·resolveInputs(ready/missing)·syncProject(byProject 왕복)·nodeStale.
//
// 데이터 SSOT(useProjectContextStore)는 setState로 시드만 하고, 오케스트레이션 store의
// 순수 결정성(폐포·위상·스킵·과금표시)을 검증한다(무회귀: 데이터 store 정책 미접촉).

import { describe, it, expect, beforeEach } from "vitest";

import { useOrchestrationStore } from "@/store/useOrchestrationStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { currentSignature } from "@/lib/orchestration/dependency-graph";
import type { NodeId } from "@/lib/orchestration/types";

/** 데이터 SSOT 초기화(빈 상태 — 어떤 노드도 신선하지 않음). */
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

/** 오케스트레이션 store 초기화(휘발 실행상태). */
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

describe("buildPlan — 폐포 + 위상정렬 + 신선분 스킵 + 과금표시", () => {
  it("guided 모드: finance 시드 폐포 = 8노드(audit 제외), 전부 실행대상(빈 데이터)", () => {
    const steps = useOrchestrationStore.getState().buildPlan("guided");
    const ids = steps.map((s) => s.node);
    // audit은 말단 검증노드라 어떤 폐포에도 미포함(시드에 명시하지 않는 한).
    expect(ids).not.toContain("audit");
    expect(new Set(ids)).toEqual(
      new Set<NodeId>([
        "land",
        "legal",
        "recommend",
        "design",
        "sales",
        "qto",
        "feasibility",
        "finance",
      ]),
    );
    // 빈 데이터 → 신선분 없음 → 전부 실행(skipped=false).
    expect(steps.every((s) => !s.skipped)).toBe(true);
    // guided reason 일관.
    expect(steps.every((s) => s.reason === "guide")).toBe(true);
  });

  it("buildPlan은 위상순서를 보장한다(상류가 하류보다 앞)", () => {
    const steps = useOrchestrationStore.getState().buildPlan("guided");
    const order = steps.map((s) => s.node);
    const idx = (id: NodeId) => order.indexOf(id);
    expect(idx("land")).toBeLessThan(idx("legal"));
    expect(idx("legal")).toBeLessThan(idx("recommend"));
    expect(idx("recommend")).toBeLessThan(idx("design"));
    expect(idx("design")).toBeLessThan(idx("qto"));
    expect(idx("qto")).toBeLessThan(idx("feasibility"));
    expect(idx("sales")).toBeLessThan(idx("feasibility"));
    expect(idx("feasibility")).toBeLessThan(idx("finance"));
  });

  it("selective 모드: picked의 leaf 폐포 — qto 선택 시 land·recommend·legal·design·qto", () => {
    useOrchestrationStore.getState().setPicked({ qto: true });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    const ids = new Set(steps.map((s) => s.node));
    expect(ids).toEqual(
      new Set<NodeId>(["land", "legal", "recommend", "design", "qto"]),
    );
    // qto는 selected, 나머지는 closure.
    const reasonOf = (id: NodeId) => steps.find((s) => s.node === id)!.reason;
    expect(reasonOf("qto")).toBe("selected");
    expect(reasonOf("land")).toBe("closure");
  });

  it("신선분 스킵: moduleKey(siteAnalysis) 산출 후 land 노드는 skipped-fresh", () => {
    // 부지분석 실데이터 + stamp → moduleFresh(siteAnalysis)=true.
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 500, address: "서울시 중곡동 1-1" });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    // land만 선택하지 않았어도 selective seed가 비면 빈 계획 → land 직접 선택.
    useOrchestrationStore.getState().setPicked({ land: true });
    const steps2 = useOrchestrationStore.getState().buildPlan("selective");
    const land = steps2.find((s) => s.node === "land")!;
    expect(land.skipped).toBe(true);
    expect(land.skipReason).toBe("fresh");
    expect(land.chargeable).toBe(false);
    // 첫 호출(land 미선택)에서는 land가 계획에 없었음(seed 빈) — 결정성 확인.
    expect(steps.length).toBe(0);
  });

  it("available:false(audit) 노드는 시드해도 skipped-unavailable(0 강제 금지)", () => {
    useOrchestrationStore.getState().setPicked({ audit: true });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    const audit = steps.find((s) => s.node === "audit")!;
    expect(audit.skipped).toBe(true);
    expect(audit.skipReason).toBe("unavailable");
    expect(audit.chargeable).toBe(false);
  });

  it("과금표시: 실행 대상이고 billingKey 있으면 chargeable=true", () => {
    useOrchestrationStore.getState().setPicked({ land: true });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    const land = steps.find((s) => s.node === "land")!;
    expect(land.skipped).toBe(false);
    expect(land.chargeable).toBe(true); // stage:land billingKey
  });

  it("sales 실행 후 buildPlan 재호출 시 feasibility는 skipped-fresh가 아니라 실행대상에 포함(stamp 오염 회피)", () => {
    // 회귀 가드: sales가 feasibilityData를 stamp하면 moduleFresh(feasibility)=true가 되어
    // feasibility(ROI)가 영영 skipped-fresh로 건너뛰어졌다. sales ssotOutputs=[]로 데이터 미기록 →
    // feasibility는 stamp되지 않아 실행대상으로 남아야 한다.
    // 부지만 시드(폐포 진입). feasibility는 어떤 노드도 stamp하지 않는다.
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 500, address: "서울 강남구" });
    // sales 노드 실행 결과 환류(데이터 SSOT 비기록 — ssotOutputs=[]). orchestration nodeResult에만 done 기록.
    useOrchestrationStore.getState().recordNodeResult("sales", {
      state: "done",
      verifyStatus: "pass",
      grounding: {},
      chargedKrw: 0,
      inputSignature: null,
      at: Date.now(),
    });
    // feasibility 선택 → buildPlan.
    useOrchestrationStore.getState().setPicked({ feasibility: true });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    const feas = steps.find((s) => s.node === "feasibility")!;
    expect(feas).toBeDefined();
    // sales가 feasibility를 stamp하지 않았으므로 실행대상(skipped=false)이어야 한다.
    expect(feas.skipped).toBe(false);
    expect(feas.chargeable).toBe(true); // stage:feasibility
    // sales도 feasibility 상류(순서 의존)라 폐포에 포함된다.
    expect(steps.map((s) => s.node)).toContain("sales");
  });

  it("buildPlan은 state.plan과 runMode를 갱신한다", () => {
    useOrchestrationStore.getState().setPicked({ design: true });
    useOrchestrationStore.getState().buildPlan("selective");
    const st = useOrchestrationStore.getState();
    expect(st.runMode).toBe("selective");
    expect(st.plan.length).toBeGreaterThan(0);
    expect(st.plan).toContain("design");
  });
});

describe("previewPlan — 순수 미리보기(store 미변경·수정3)", () => {
  it("previewPlan은 buildPlan과 동일한 steps를 반환하되 plan/runMode를 변경하지 않는다", () => {
    useOrchestrationStore.getState().setPicked({ qto: true });
    // 초기 휘발 상태(runMode=guided, plan=[]).
    const before = useOrchestrationStore.getState();
    expect(before.runMode).toBe("guided");
    expect(before.plan).toEqual([]);

    const preview = useOrchestrationStore.getState().previewPlan("selective");
    const after = useOrchestrationStore.getState();
    // ★store 미변경(렌더 안전): runMode·plan 그대로.
    expect(after.runMode).toBe("guided");
    expect(after.plan).toEqual([]);
    // 그러나 계획 자체는 buildPlan과 동일(폐포·스킵·과금표시 일치).
    const built = useOrchestrationStore.getState().buildPlan("selective");
    expect(preview.map((s) => s.node)).toEqual(built.map((s) => s.node));
    expect(preview.map((s) => s.skipped)).toEqual(built.map((s) => s.skipped));
    expect(preview.map((s) => s.chargeable)).toEqual(built.map((s) => s.chargeable));
  });

  it("standalone seed 미리보기도 store를 변경하지 않는다", () => {
    const preview = useOrchestrationStore.getState().previewPlan("standalone", ["design"]);
    expect(preview.map((s) => s.node)).toContain("design");
    expect(useOrchestrationStore.getState().plan).toEqual([]); // set 미수행
  });
});

describe("resolveInputs — SSOT read → ready/missing", () => {
  it("부지 미확보 시 land 입력은 missing, 상류 후보는 빈배열(land는 upstream 없음)", () => {
    const r = useOrchestrationStore.getState().resolveInputs("land");
    expect(r.ready.length).toBe(0);
    expect(r.missing.length).toBe(1); // siteAnalysis.address
    expect(r.autoCandidates).toEqual([]); // land.upstream = []
  });

  it("부지 확보 시 land 입력은 ready", () => {
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    const r = useOrchestrationStore.getState().resolveInputs("land");
    expect(r.ready.length).toBe(1);
    expect(r.missing.length).toBe(0);
    expect(r.autoCandidates).toEqual([]);
  });

  it("design 입력 일부 미확보 시 missing + 상류 후보 = design.upstream(land,recommend)", () => {
    // 부지만 확보, compliance 미확보 → siteAnalysis ready, complianceData missing.
    useProjectContextStore.getState().updateSiteAnalysis({ address: "서울 강남구" });
    const r = useOrchestrationStore.getState().resolveInputs("design");
    expect(r.ready.map((x) => x.slot)).toContain("siteAnalysis");
    expect(r.missing.map((x) => x.slot)).toContain("complianceData");
    expect(new Set(r.autoCandidates)).toEqual(new Set<NodeId>(["land", "recommend"]));
  });
});

describe("nodeStale — moduleKey 위임 / 파생 시그니처", () => {
  it("moduleKey 노드(land): 미산출이면 stale=true, 산출 후 stale=false", () => {
    expect(useOrchestrationStore.getState().nodeStale("land")).toBe(true);
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 500, address: "서울" });
    expect(useOrchestrationStore.getState().nodeStale("land")).toBe(false);
  });

  it("파생 노드(recommend, moduleKey=null): 실행결과 없으면 stale=true", () => {
    expect(useOrchestrationStore.getState().nodeStale("recommend")).toBe(true);
  });

  it("error 기록된 파생 노드(recommend)는 동일입력에서도 신선 아님 → buildPlan 재실행대상 포함", () => {
    // 회귀 가드: derivedFresh가 state="error"를 신선판정하면 동일입력 재시도가 막혔다.
    // recommend 입력 시드(siteAnalysis + complianceData) → resolveInputs ready, available:true.
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 500, address: "서울 강남구" });
    useProjectContextStore.getState().updateComplianceData({
      bcrCompliant: true,
      farCompliant: true,
      heightCompliant: true,
      violations: [],
    });
    // 직전 실행이 error로 끝났고 동일입력 시그니처를 기록한 상태(서명 일치 → error 클로즈만 분리 검증).
    const sig = currentSignature("recommend", useProjectContextStore.getState());
    useOrchestrationStore.getState().recordNodeResult("recommend", {
      state: "error",
      verifyStatus: null,
      grounding: {},
      chargedKrw: 0,
      inputSignature: sig,
      at: Date.now(),
      error: "500",
    });
    // nodeStale=true(error는 신선 아님), buildPlan에 실행대상(skipped=false)으로 재포함.
    expect(useOrchestrationStore.getState().nodeStale("recommend")).toBe(true);
    useOrchestrationStore.getState().setPicked({ recommend: true });
    const steps = useOrchestrationStore.getState().buildPlan("selective");
    const rec = steps.find((s) => s.node === "recommend")!;
    expect(rec.skipped).toBe(false);
    expect(rec.skipReason).toBeUndefined();
  });
});

describe("syncProject — byProject 왕복 복원([graft C])", () => {
  it("프로젝트A 설정 → B 전환 → A 재진입 시 모드/선택 복원", () => {
    const st = useOrchestrationStore.getState();
    // 프로젝트 A 진입 + selective + qto 선택.
    st.syncProject("A");
    useOrchestrationStore.getState().setRunMode("selective");
    useOrchestrationStore.getState().setPicked({ qto: true });
    // 프로젝트 B 전환 — A 상태가 byProject에 저장돼야 한다.
    useOrchestrationStore.getState().syncProject("B");
    const afterB = useOrchestrationStore.getState();
    expect(afterB.currentProjectId).toBe("B");
    expect(afterB.runMode).toBe("guided"); // B는 신규 → 기본값
    expect(afterB.picked).toEqual({}); // B는 선택 없음
    expect(afterB.byProject.A?.runMode).toBe("selective"); // A 저장 확인
    expect(afterB.byProject.A?.picked).toEqual({ qto: true });
    // 프로젝트 A 재진입 — 복원.
    useOrchestrationStore.getState().syncProject("A");
    const backA = useOrchestrationStore.getState();
    expect(backA.currentProjectId).toBe("A");
    expect(backA.runMode).toBe("selective");
    expect(backA.picked).toEqual({ qto: true });
  });

  it("프로젝트 전환 시 실행 휘발물(plan·nodeResult)은 초기화된다", () => {
    const st = useOrchestrationStore.getState();
    st.syncProject("A");
    useOrchestrationStore.getState().setPicked({ land: true });
    useOrchestrationStore.getState().buildPlan("selective");
    expect(useOrchestrationStore.getState().plan.length).toBeGreaterThan(0);
    useOrchestrationStore.getState().syncProject("B");
    expect(useOrchestrationStore.getState().plan).toEqual([]);
    expect(useOrchestrationStore.getState().nodeResult).toEqual({});
  });
});
