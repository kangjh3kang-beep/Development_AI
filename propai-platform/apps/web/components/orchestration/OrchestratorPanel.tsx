"use client";

/**
 * OrchestratorPanel — 분석 오케스트레이션 컨테이너(L3 소비 UI).
 *
 * Phase B 블루프린트 §3-B 정합. 모드스위처 + 공용 AnalysisModuleSelector(레지스트리 구동) +
 * 실행 계획 미리보기 + 실행 진행 타임라인을 한 패널로 묶는다.
 *
 * 책무(B3 — 별도·선택 모드):
 *  - RunModeSwitcher: 가이드/별도/선택/프로필(B3는 별도·선택만 활성).
 *  - AnalysisModuleSelector: modules=nodesToOptions(scopeNodes), selected=picked,
 *      onChange=setPicked(→폐포 재계산→locked 재배지), onRun=선택분 실행, onSelectAll=전체 실행.
 *  - PlanPreview: buildPlan(폐포·신선스킵·과금합계 선표시·R8 동의 후 실행).
 *  - RunProgressTimeline: nodeResult+plan 실행 진행(NodeRunCard 정직고지).
 *  - 별도(standalone) 모드: 노드 클릭 → InputResolveModal(입력 자동해소·업스트림 동의·수동입력).
 *
 * 무회귀: AnalysisModuleSelector props 불변(래핑만). B2 store(buildPlan/resolveInputs/setPicked 등)와
 * useNodeRunner(runNode)만 소비. 데이터 SSOT(useProjectContextStore)는 useNodeRunner 내부에서만 환류.
 * runPlan은 store에 없으므로(설계상 useNodeRunner가 실행 담당) 이 컨테이너가 buildPlan→runNode로 코어를 구현한다.
 *
 * 과금: 미설정 0=무료, PlanPreview 선표시 → "분석 시작/전체 자동분석"이 동의·실행.
 * 색상 토큰만 사용(하드코딩 금지)·반응형.
 */

import { useCallback, useMemo, useState } from "react";

import {
  AnalysisModuleSelector,
} from "@/components/common/AnalysisModuleSelector";
import { RunModeSwitcher } from "./RunModeSwitcher";
import { PlanPreview } from "./PlanPreview";
import { RunProgressTimeline } from "./RunProgressTimeline";
import { InputResolveModal } from "./InputResolveModal";
import { ProfileManager } from "./ProfileManager";
import { PersonaPanel } from "./PersonaPanel";
import { SeniorConsultPanel } from "./SeniorConsultPanel";
import { nodesToOptions } from "@/lib/orchestration/selector-adapter";
import { computeClosure } from "@/lib/orchestration/dependency-graph";
import { buildRunAllSelection } from "@/lib/orchestration/run-all-selection";
import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId, SsotInputSpec } from "@/lib/orchestration/types";
import { useNodeRunner } from "@/hooks/useNodeRunner";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  useOrchestrationStore,
  type RunMode,
  type RunStep,
} from "@/store/useOrchestrationStore";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** 수동입력 슬롯 키 — InputResolveModal과 동일 규약("slot" 또는 "slot.field"). */
function manualKey(input: SsotInputSpec): string {
  return `${input.slot}${input.field ? "." + input.field : ""}`;
}

/**
 * 수동입력 값을 실제 데이터 SSOT에 주입(수정2). 입력 슬롯의 update 액션을 source:"user"로 호출해
 * 사용자값을 머지가드로 기록한다. 반환=실제 주입된 키 목록(정직 보고용).
 *
 * ★현 레지스트리에서 resolution에 "manual"이 포함된 슬롯은 land 노드의 siteAnalysis.address 하나뿐이다
 *   (다른 노드는 모두 "upstream-suggest"라 모달 수동입력 폼이 뜨지 않는다). siteAnalysis.address는
 *   updateSiteAnalysis({address}, {source:"user"})로 안전 주입 가능하다.
 *   값↔슬롯 매핑이 모호한(자유 텍스트→정형 필드 변환이 필요한) 슬롯은 조용히 버리지 않고 건너뛴다
 *   (InputResolveModal은 manual 슬롯만 폼을 그리므로 비-manual 슬롯은 애초에 값이 오지 않는다).
 */
function injectManualValues(
  node: AnalysisNode,
  values: Record<string, string>,
  store: ReturnType<typeof useProjectContextStore.getState>,
): string[] {
  const injected: string[] = [];
  for (const input of node.ssotInputs) {
    // manual 해소가 가능한 슬롯만 대상(폼이 그려진 슬롯).
    if (!input.resolution.includes("manual")) continue;
    const raw = (values[manualKey(input)] ?? "").trim();
    if (!raw) continue;

    if (input.slot === "siteAnalysis" && input.field === "address") {
      // 주소/PNU 자유 텍스트 → siteAnalysis.address 직접 주입(머지가드 source:user).
      store.updateSiteAnalysis({ address: raw }, { source: "user" });
      injected.push(manualKey(input));
    }
    // 그 외 manual 슬롯은 현재 없음. 추가 시 여기서 slot/field별 update 액션 매핑을 늘린다
    // (가짜 주입 금지 — 매핑 불가 슬롯은 건너뛰고, 그 노드 폼은 모달에서 비활성화한다).
  }
  return injected;
}

/** 과금 잔액(MarketInsights Balance와 동일 계약 — module_fees·unlimited 재사용). */
export interface OrchestratorBalance {
  unlimited?: boolean;
  /** 관리자 설정 분석 모듈 사용료 맵(미설정 빈dict=전부 무료). */
  module_fees?: Record<string, number>;
}

export interface OrchestratorPanelProps {
  /** 이 패널이 다룰 노드(scope). 보통 워크스페이스가 책임지는 NodeId[]. */
  scopeNodes: NodeId[];
  /** 과금 잔액/요율(미전달 시 전부 무료로 표시). */
  balance?: OrchestratorBalance | null;
  /** 실행 비활성(주소 미입력·코인 부족 등 — 상위가 판단). */
  runDisabled?: boolean;
  /** 패널 제목. */
  title?: string;
  /** 패널 부제. */
  subtitle?: string;
  /**
   * 프로젝트 ID(있을 때만 '전문가 페르소나' 뷰 탭 노출). 미전달 시 페르소나 탭 미표시
   * (MarketInsights 등 projectId 없는 소비처는 기존 4모드만 그대로 — 무회귀).
   */
  projectId?: string;
  /**
   * (U5) 단순화 뷰: 첫 화면에 「전체 분석 한 번에」 큰 버튼 1개를 보이고, 4모드·페르소나·항목 선택은
   * 「고급 옵션」 접기로 이동(무삭제·무회귀). 미전달(기본 false) 소비처는 기존 레이아웃 그대로.
   */
  simplified?: boolean;
}

export function OrchestratorPanel({
  scopeNodes,
  balance,
  runDisabled = false,
  title = "분석 항목 선택",
  subtitle = "필요한 분석만 선택하세요. 선택한 항목만 실행·과금됩니다.",
  projectId,
  simplified = false,
}: OrchestratorPanelProps) {
  const runMode = useOrchestrationStore((s) => s.runMode);
  const picked = useOrchestrationStore((s) => s.picked);
  const plan = useOrchestrationStore((s) => s.plan);
  const nodeResult = useOrchestrationStore((s) => s.nodeResult);
  const nodeOrder = useOrchestrationStore((s) => s.nodeOrder);
  const activeProfileId = useOrchestrationStore((s) => s.activeProfileId);
  const setRunMode = useOrchestrationStore((s) => s.setRunMode);
  const setPicked = useOrchestrationStore((s) => s.setPicked);
  const setActiveProfile = useOrchestrationStore((s) => s.setActiveProfile);
  const buildPlan = useOrchestrationStore((s) => s.buildPlan);
  const previewPlan = useOrchestrationStore((s) => s.previewPlan);
  const resolveInputs = useOrchestrationStore((s) => s.resolveInputs);
  const nodeStale = useOrchestrationStore((s) => s.nodeStale);
  const setNodeState = useOrchestrationStore((s) => s.setNodeState);

  const { runNode } = useNodeRunner();

  // 표면(view) — DAG 4모드(dag) ↔ 전문가 페르소나(persona) ↔ 시니어 자문(senior). ★RunMode 미확장(plan 엔진 무영향).
  // 로컬 state라 새로고침 시 dag로 초기화(휘발 정책 — 결과는 서버 재산출 가능).
  const [view, setView] = useState<"dag" | "persona" | "senior">("dag");

  // 별도(standalone) 모드 입력해소 모달 대상.
  const [resolveTarget, setResolveTarget] = useState<NodeId | null>(null);
  // 선택 모드 force(전체 자동분석) 미리보기 토글 — onSelectAll이 force 계획·과금합계를 선표시(수정5).
  const [forcePreview, setForcePreview] = useState(false);

  // 관리자 요율(미설정 0=무료 — ★하드코딩 금지). MarketInsights fee() 패턴 재사용.
  const feeOf = useCallback(
    (billingKey: string) => balance?.module_fees?.[billingKey] ?? 0,
    [balance],
  );

  // 현재 picked의 leaf(선택집합) → 폐포. 폐포에만 있고 직접 선택 안 된 노드 = "폐포 강제"(locked).
  const closureForced = useMemo(() => {
    const leaves = scopeNodes.filter((id) => picked[id]);
    const closure = new Set(computeClosure(leaves));
    const forced = new Set<NodeId>();
    for (const id of closure) {
      if (!picked[id]) forced.add(id); // 폐포에 끌려왔지만 사용자가 직접 고르지 않은 상류
    }
    return forced;
  }, [scopeNodes, picked]);

  // 레지스트리 → 셀렉터 옵션(어댑터). 신선/폐포강제를 정직 표기.
  const modules = useMemo(
    () =>
      nodesToOptions(scopeNodes, feeOf, {
        isFresh: (id) => !nodeStale(id),
        isClosureForced: (id) => closureForced.has(id),
      }),
    [scopeNodes, feeOf, nodeStale, closureForced],
  );

  // 실행 계획 미리보기(선택 모드 기준) — ★순수 계산(previewPlan)이라 렌더 중 store 변경 없음(수정3).
  // (이전 buildPlan은 set({runMode,plan})으로 store를 변경 → useMemo에서 React 순수성 위반이었음.)
  const previewSteps: RunStep[] = useMemo(() => {
    // 선택·프로필 모드 모두 picked(프로필은 applyProfile로 시드) 기반 계획 미리보기.
    if (runMode === "selective" || runMode === "profile") return previewPlan(runMode);
    // 별도 모드는 노드 클릭 시 단건 계획. 미리보기는 빈 계획(클릭 전).
    return [];
    // previewPlan은 store 상태(picked·nodeResult·nodeOrder·activeProfileId·데이터 SSOT)를 읽으므로
    // picked/runMode/nodeResult/nodeOrder/activeProfileId 변화에 의존.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runMode, picked, nodeResult, nodeOrder, activeProfileId, previewPlan]);

  // force(전체 자동분석) 미리보기 — 신선분도 실행 대상으로 보이게 변환(과금합계 선표시·수정5).
  // PlanPreview는 skipped 행을 합계에서 제외하므로, force일 땐 fresh 스킵을 실행 대상으로 풀어 보여준다.
  const previewStepsForView: RunStep[] = useMemo(() => {
    if (!forcePreview) return previewSteps;
    return previewSteps.map((step) =>
      step.skipped && step.skipReason === "fresh"
        ? {
            ...step,
            skipped: false,
            skipReason: undefined,
            chargeable: !!BY_ID[step.node]?.billingKey,
          }
        : step,
    );
  }, [forcePreview, previewSteps]);

  // 모드 전환 — 별도 모드면 선택 초기화하지 않음(노드 클릭으로 단건 실행).
  const onModeChange = useCallback(
    (mode: RunMode) => {
      setRunMode(mode);
    },
    [setRunMode],
  );

  // 선택 변경(controlled). 그룹(group:*) 키는 셀렉터가 자식으로 펼쳐 전달하므로 노드 키만 남긴다.
  const onSelectorChange = useCallback(
    (next: Record<string, boolean>) => {
      const cleaned: Record<string, boolean> = {};
      for (const [k, v] of Object.entries(next)) {
        if (BY_ID[k as NodeId]) cleaned[k] = v; // NodeId만 picked에 보관(group:* 제외)
      }
      setPicked(cleaned);
      setForcePreview(false); // 선택이 바뀌면 force 미리보기 단계 초기화(계획 재산정).
      // 사용자가 셀렉터로 선택을 직접 바꾸면 더 이상 '적용된 프로필 그대로'가 아니다.
      // activeProfileId를 해제해 ProfileManager의 '적용됨' 배지가 picked와 어긋나지 않게 한다
      // (이 콜백은 사용자 토글 시에만 호출 — applyProfile의 controlled 주입은 onChange를 트리거하지 않음).
      if (activeProfileId) setActiveProfile(null);
    },
    [setPicked, setActiveProfile, activeProfileId],
  );

  /**
   * 이미 만들어진 계획(steps)을 순서대로 실행(수정1 — 내부 buildPlan 재호출 금지).
   * @param steps 호출부가 buildPlan(mode, seed)로 만든 RunStep[](store.plan 확정 포함).
   * @param force true면 신선분(skipReason:"fresh")도 강제 실행. 미가용은 항상 스킵.
   *
   * 수정4(실패-하류 스킵): 어떤 노드가 error/needs-input/skipped-unavailable로 끝나면 failed에 기록하고,
   * 그 노드를 상류로 두는 하류 노드는 빈입력 백엔드호출·과금을 막기 위해 실행하지 않고 blocked 표기한다.
   */
  const executePlan = useCallback(
    async (steps: RunStep[], force: boolean) => {
      const failed = new Set<NodeId>();
      for (const step of steps) {
        // 미가용은 항상 스킵(0 강제 금지). 신선분은 force일 때만 실행.
        if (step.skipped && step.skipReason === "unavailable") continue;
        if (step.skipped && step.skipReason === "fresh" && !force) continue;

        // 상류(전이 폐포)에 실패 노드가 있으면 실행하지 않고 차단(빈입력 호출·과금 방지·수정4).
        // computeClosure([node])는 node+전이상류를 반환하므로 자기 자신은 제외하고 검사.
        const upstreamClosure = computeClosure([step.node]).filter((u) => u !== step.node);
        if (upstreamClosure.some((u) => failed.has(u))) {
          setNodeState(step.node, "skipped-unavailable"); // 타임라인 표면화(미가용=차단 정직 표기)
          failed.add(step.node); // 차단 노드의 하류도 연쇄 차단
          continue;
        }

        const res = await runNode(step.node); // useNodeRunner가 5단계·환류·과금 단일 처리
        // 실패/입력미확보/미가용은 하류 차단 대상으로 기록(done만 통과로 인정).
        if (res.state !== "done") failed.add(step.node);
      }
    },
    [runNode, setNodeState],
  );

  // "분석 시작" — 선택분만(신선분 스킵). buildPlan으로 계획 확정 후 동일 steps로 실행(수정1).
  // 프로필 모드도 picked/closure 기반이라 현재 runMode를 그대로 넘긴다(프로필 시드·순서 반영).
  const onRun = useCallback(() => {
    setForcePreview(false);
    const mode = runMode === "profile" ? "profile" : "selective";
    const steps = buildPlan(mode);
    void executePlan(steps, false);
  }, [runMode, buildPlan, executePlan]);

  // "전체 자동분석" — 먼저 force 계획·과금합계를 PlanPreview에 선표시(1클릭째), 다시 누르면 실행(2클릭째·수정5).
  // (과한 모달 대신 미리보기 확인 단계. forcePreview=true면 PlanPreview가 신선분 포함 합계를 보여준다.)
  const onSelectAll = useCallback(() => {
    if (!forcePreview) {
      setForcePreview(true); // 1클릭: force 합계 선표시(즉시 실행 금지·R8 동의)
      return;
    }
    setForcePreview(false);
    const mode = runMode === "profile" ? "profile" : "selective";
    const steps = buildPlan(mode);
    void executePlan(steps, true); // 2클릭: 신선분 포함 강제 실행
  }, [runMode, forcePreview, buildPlan, executePlan]);

  // (U5) 「전체 분석 한 번에」 — 단순화 뷰의 1클릭 기본 실행. scope 전체 노드를 선택(상류 의존은
  // buildPlan 폐포가 자동 포함)하고 selective로 실행한다. force=false라 이미 신선한 항목은 스킵(재과금 회피),
  // 처음 실행 땐 전부 대상. 비용 동의는 runDisabled(코인 게이트)·모듈요율(기본 0=무료)로 상위가 이미 통제.
  const onRunAll = useCallback(() => {
    setForcePreview(false);
    if (runMode !== "selective") setRunMode("selective");
    setPicked(buildRunAllSelection(scopeNodes));
    const steps = buildPlan("selective");
    void executePlan(steps, false);
  }, [runMode, scopeNodes, setRunMode, setPicked, buildPlan, executePlan]);

  // 별도 모드: 노드 단건 실행 요청 → 입력 해소 모달.
  const requestStandalone = useCallback((id: NodeId) => {
    setResolveTarget(id);
  }, []);

  // 모달: 입력 확보됨 → 단건 계획 확정 후 동일 steps로 실행(수정1).
  // standalone은 사용자가 그 노드를 "지금 실행"하겠다는 명시 의도 → force=true(신선분 스킵 미적용).
  // (신선분 스킵은 선택/가이드 모드의 효율 기능. 사용자가 직접 고른 단건은 항상 실행.)
  const onModalRun = useCallback(
    (id: NodeId) => {
      setResolveTarget(null);
      const steps = buildPlan("standalone", [id]); // store.plan 반영 + 반환 steps 재사용
      void executePlan(steps, true);
    },
    [buildPlan, executePlan],
  );

  // 모달: 업스트림 자동실행 동의 → 단건 시드 standalone 계획(폐포가 상류 포함) 빌드 후 동일 steps 실행(수정1·2).
  // _upstream은 표시용(폐포가 이미 상류를 포함하므로 별도 사용 안 함). 사용자 명시 실행 → force=true.
  const onAutoRunUpstream = useCallback(
    (id: NodeId, _upstream: NodeId[]) => {
      setResolveTarget(null);
      const steps = buildPlan("standalone", [id]); // 단건 시드 → 폐포가 상류 포함
      void executePlan(steps, true);
    },
    [buildPlan, executePlan],
  );

  // 모달: 수동입력 제출 → 입력값을 실제 데이터 SSOT에 주입(source:"user") 후 단건 실행(수정2).
  // 주입 후 buildPlan으로 계획 확정(주입된 ready가 폐포에 반영) → 동일 steps 실행(수정1). 명시 실행 → force=true.
  const onManualSubmit = useCallback(
    (id: NodeId, values: Record<string, string>) => {
      setResolveTarget(null);
      const node = BY_ID[id];
      if (node) {
        // 입력값을 데이터 SSOT에 머지가드로 주입(가짜주입 금지 — 매핑 가능한 슬롯만).
        injectManualValues(node, values, useProjectContextStore.getState());
      }
      const steps = buildPlan("standalone", [id]);
      void executePlan(steps, true);
    },
    [buildPlan, executePlan],
  );

  const unlimited = !!balance?.unlimited;
  const isStandalone = runMode === "standalone";

  // 페르소나 뷰는 projectId가 있을 때만(통합 분석 워크스페이스). 미전달 소비처는 기존과 동일.
  const personaEnabled = !!projectId;
  const showPersona = personaEnabled && view === "persona";
  // 시니어 자문 패널 자체는 무컨텍스트(projectId 불필요)이나, v1 진입점은 워크스페이스(projectId)
  // 한정으로 의도 — projectId 없는 소비처(예: MarketInsights)에 탭 바를 신설하는 회귀를 피한다.
  // (무컨텍스트 노출이 필요해지면 탭 컨테이너를 personaEnabled에서 분리하는 후속 작업.)
  const showSenior = personaEnabled && view === "senior";

  return (
    <section className="grid gap-4">
      {/* (U5) 단순화 뷰: 「전체 분석 한 번에」 큰 버튼 1개 — 상류 의존 포함 단계순 자동 실행. */}
      {simplified && (
        <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
          <p className="text-sm font-bold text-[var(--text-primary)]">{title}</p>
          {subtitle && (
            <p className="mt-1 mb-3 text-xs text-[var(--text-secondary)]">{subtitle}</p>
          )}
          <button
            type="button"
            onClick={onRunAll}
            disabled={runDisabled}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent-strong)] px-6 py-4 text-base font-black text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            전체 분석 한 번에
          </button>
          <p className="mt-2 text-[10px] text-[var(--text-hint)]">
            상류 의존을 포함해 단계 순서로 자동 실행합니다. 세부 조정은 아래 「고급 옵션」에서.
          </p>
        </div>
      )}

      {/* (U5) 고급 옵션 접기 — 단순화 뷰에서만 접힘. 비단순화 소비처는 display:contents+open으로
          기존 레이아웃 byte-identical(무회귀). summary는 단순화 뷰에서만 노출. */}
      <details
        {...(simplified ? {} : { open: true })}
        className={
          simplified
            ? "rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)]"
            : "contents"
        }
      >
        <summary
          className={
            simplified
              ? "cursor-pointer select-none px-4 py-3 text-sm font-bold text-[var(--text-secondary)]"
              : "hidden"
          }
        >
          고급 옵션 — 단계별·전문가별·분석 항목 선택
        </summary>
        <div className={simplified ? "grid gap-4 p-4 pt-0" : "contents"}>
      {/* 5번째 표면 전환 — DAG 분석 ↔ 전문가 페르소나(projectId 있을 때만 노출). RunModeSwitcher는 불변. */}
      {personaEnabled && (
        <div
          role="tablist"
          aria-label="분석 표면"
          className="flex flex-wrap gap-2 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-1.5"
        >
          {(
            [
              { id: "dag", label: "통합 분석", hint: "항목 기반 가이드/별도/선택/프로필" },
              { id: "persona", label: "실무 전문가 분석", hint: "분양대행·도시계획 실무 전문가" },
              { id: "senior", label: "시니어 자문", hint: "7분야 시니어 판단·근거·정량판정" },
            ] as const
          ).map((t) => {
            const active = view === t.id;
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setView(t.id)}
                className={`flex flex-col items-start gap-0.5 rounded-xl px-3.5 py-2 text-left transition-colors ${
                  active
                    ? "bg-[var(--accent-strong)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-strong)]"
                }`}
              >
                <span className="text-sm font-bold">{t.label}</span>
                <span
                  className={`text-[10px] font-normal ${active ? "text-white/80" : "text-[var(--text-tertiary)]"}`}
                >
                  {t.hint}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* 페르소나 뷰: DAG 셀렉터/계획/타임라인을 전부 건너뛰고 PersonaPanel만 렌더(plan 엔진 무영향). */}
      {showPersona && projectId && (
        <PersonaPanel projectId={projectId} runDisabled={runDisabled} />
      )}

      {/* 시니어 자문 뷰: SeniorConsultPanel만 렌더(서버 오라클·plan 엔진 무영향·자족). */}
      {showSenior && <SeniorConsultPanel />}

      {/* 이하 DAG 4모드 블록 — 페르소나 뷰가 아닐 때만 렌더(기존 동작 byte-identical). */}
      {!showPersona && !showSenior && (
        <>
      <RunModeSwitcher value={runMode} onChange={onModeChange} />

      {/* 프로필 모드: 워크플로우 관리(프리셋·커스텀·순서). 셀렉터 위에 렌더 */}
      {runMode === "profile" && <ProfileManager />}

      {/* 선택·프로필 모드: 공용 셀렉터(레지스트리 구동) + 계획 미리보기 */}
      {!isStandalone && (
        <>
          <AnalysisModuleSelector
            modules={modules}
            selected={picked}
            onChange={onSelectorChange}
            onRun={onRun}
            onSelectAll={onSelectAll}
            runDisabled={runDisabled}
            unlimited={unlimited}
            title={title}
            subtitle={subtitle}
          />
          {forcePreview && (
            <p className="-mt-1 rounded-lg border border-[color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[color-mix(in_srgb,var(--accent-strong)_6%,transparent)] px-3 py-2 text-[11px] text-[var(--accent-strong)]">
              전체 자동분석: 최신 항목까지 포함한 아래 계획·예상 과금을 확인하세요. &quot;전체 자동분석&quot;을 한 번 더 누르면 실행됩니다.
            </p>
          )}
          <PlanPreview steps={previewStepsForView} unlimited={unlimited} />
        </>
      )}

      {/* 별도 모드: 노드 카드 그리드(클릭 → 입력 해소 모달). 셀렉터 대신 단건 진입. */}
      {isStandalone && (
        <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
          <p className="mb-2.5 text-sm font-bold text-[var(--text-primary)]">분석 단독 실행</p>
          <p className="mb-3 text-[11px] text-[var(--text-secondary)]">
            원하는 분석 하나를 선택하면 필요한 상류 입력을 자동 확인하고, 부족하면 동의 후 함께 실행합니다.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {scopeNodes.map((id) => {
              const node = BY_ID[id];
              if (!node) return null;
              return (
                <button
                  key={id}
                  type="button"
                  disabled={!node.available || runDisabled}
                  onClick={() => requestStandalone(id)}
                  className="flex items-center justify-between gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3.5 py-2.5 text-left transition-colors hover:border-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-bold text-[var(--text-primary)]">
                      {node.label}
                    </span>
                    <span className="block truncate text-[10px] text-[var(--text-tertiary)]">
                      {node.available
                        ? node.groundingSources.slice(0, 2).join("·")
                        : node.reportContract.unavailableLabel}
                    </span>
                  </span>
                  <span className="shrink-0 text-[var(--accent-strong)]">›</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

        </>
      )}
        </div>
      </details>

      {/* 실행 진행 — 모든 모드 공통(plan + nodeResult). 단건 재실행은 별도 모달 경유.
          (U5) 고급 접기 밖에 두어 단순화 뷰에서도 「전체 분석 한 번에」 진행이 항상 보이게 한다.
          페르소나 뷰에서는 기존과 동일하게 숨김(!showPersona 게이트 유지·무회귀). */}
      {!showPersona && !showSenior && (
        <RunProgressTimeline
          plan={plan}
          nodeResult={nodeResult}
          onRunNode={requestStandalone}
          runDisabled={runDisabled}
        />
      )}

      {/* 별도 모드 입력 해소 모달 */}
      {resolveTarget && (
        <InputResolveModal
          nodeId={resolveTarget}
          resolution={resolveInputs(resolveTarget)}
          onClose={() => setResolveTarget(null)}
          onRun={onModalRun}
          onAutoRunUpstream={onAutoRunUpstream}
          onManualSubmit={onManualSubmit}
        />
      )}
    </section>
  );
}
