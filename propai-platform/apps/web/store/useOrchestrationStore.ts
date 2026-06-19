// 분석 오케스트레이션 — 실행 슬라이스 store(L2)
// Phase B 블루프린트 §2-C 정합. 데이터 SSOT(useProjectContextStore)는 절대 미접촉(읽기 소비/액션 호출만).
// 이 store는 "무엇을·어떤 순서로·과금되는지"(실행 계획)와 노드별 실행 결과만 보관한다.
//
// 쉬운 설명: 사용자가 어떤 분석을 어떤 모드로 돌릴지(가이드/별도/선택/프로필) 고르면,
// 이 store가 (1) 필요한 상류까지 다 끌어모아 순서대로 줄세운 "실행계획"을 만들고,
// (2) 이미 최신이라 다시 안 돌려도 되는 건 건너뛰기로 표시하고,
// (3) 돈이 나가는 항목을 표시한다. 실제 백엔드 호출(5단계)은 useNodeRunner 훅이 담당한다.
//
// 무회귀: 별도 persist 키 "propai-orchestration"(version 1). 영속 대상은 customProfiles·byProject·
// activeProfileId만(partialize). 실행 휘발물(plan·nodeResult·picked·nodeOrder)은 새로고침 시 초기화.

import { create } from "zustand";
import { persist } from "zustand/middleware";

import {
  computeClosure,
  topoSort,
  moduleKeyOf,
  currentSignature,
  guidedOrder,
} from "@/lib/orchestration/dependency-graph";
import { NODES } from "@/lib/orchestration/node-registry";
import {
  PRESET_PROFILES,
  findProfile,
  type WorkflowProfile,
  type ProfileId,
} from "@/lib/orchestration/profiles";
import type {
  NodeId,
  AnalysisNode,
  SsotInputSpec,
} from "@/lib/orchestration/types";
import {
  useProjectContextStore,
  type ProjectContextState,
  type ModuleKey,
} from "@/store/useProjectContextStore";

// 기존 import 경로 호환 — WorkflowProfile은 이제 profiles.ts가 SSOT(여기서 재노출).
export type { WorkflowProfile, ProfileId };

/* ── 타입 ── */

/** 4실행모드. */
export type RunMode = "guided" | "standalone" | "selective" | "profile";

/** 단일 노드 실행 상태(5단계 캡슐 결과의 상위 상태). */
export type NodeRunState =
  | "idle"
  | "queued"
  | "running"
  | "done"
  | "skipped-fresh" // 신선분 — 이미 최신이라 재실행/재과금 생략
  | "skipped-unavailable" // 입력 미확보 또는 available:false(0 강제 금지·정직 고지)
  | "needs-input" // standalone에서 수동입력/업스트림 동의 대기
  | "error";

/** (d) 가드 결과 — /verify/analysis 판정. */
export type NodeVerifyStatus = "pass" | "warn" | "fail" | null;

/** 노드 실행 결과(휘발 — persist 제외). */
export interface NodeResult {
  state: NodeRunState;
  /** /verify/analysis 결과(미수행 시 null). */
  verifyStatus: NodeVerifyStatus;
  /** 슬롯별 그라운딩 정직표기(ok=실값 확보, unavailable=미확보·0강제 금지). */
  grounding: Record<string, "ok" | "unavailable">;
  /** charge_service 차감액(원). 무과금/미설정이면 0. */
  chargedKrw: number;
  /** moduleKey=null 노드 신선분 판정용 입력 시그니처(있을 때). */
  inputSignature: string | null;
  /** 결과 시각(epoch ms). 미실행이면 null. */
  at: number | null;
  /** 오류 메시지(state==="error"일 때). */
  error?: string | null;
}

/** buildPlan 미리보기 항목 — 실행 전 화면 표시(과금·스킵 사유). */
export interface RunStep {
  node: NodeId;
  /** 왜 계획에 들어왔는가. */
  reason: "selected" | "closure" | "guide";
  /** 신선분/미가용으로 건너뛰는가. */
  skipped: boolean;
  /** 스킵 사유(skipped일 때). */
  skipReason?: "fresh" | "unavailable";
  /** 과금 대상인가(스킵 아니고 billingKey 있을 때만 true). */
  chargeable: boolean;
  /** 예상 차감액(원). preview-charge 합산용(관리자 미설정=0). */
  estimatedKrw: number;
}

/** resolveInputs 결과 — 입력 자동해소 진단. */
export interface ResolveInputsResult {
  /** SSOT에서 바로 확보된 입력. */
  ready: SsotInputSpec[];
  /** 미확보 입력(수동입력/업스트림 자동실행 후보 대상). */
  missing: SsotInputSpec[];
  /** 미확보를 채워줄 수 있는 상류 노드(자동실행 "제안" 대상 — 자동실행 금지). */
  autoCandidates: NodeId[];
}

/** 프로젝트별 복원 스냅샷([graft C] — store migrate 미접촉). */
interface ProjectOrchestrationSnapshot {
  runMode: RunMode;
  picked: Record<string, boolean>;
  activeProfileId: string | null;
  nodeOrder: NodeId[];
}

interface OrchestrationState {
  /* ── 휘발 실행상태(persist 제외) ── */
  runMode: RunMode;
  picked: Record<string, boolean>; // selective 선택집합(controlled)
  activeProfileId: string | null; // profile 모드
  nodeOrder: NodeId[]; // [graft C] 가이드/프로필 순서 재배열
  plan: NodeId[]; // computeClosure → topoSort 결과(미리보기·실행)
  nodeResult: Record<string, NodeResult>;
  nodeUpdatedAt: Partial<Record<NodeId, number>>; // moduleKey=null 노드 staleness 파생
  currentProjectId: string | null;

  /* ── 영속 대상(partialize) ── */
  customProfiles: WorkflowProfile[];
  byProject: Record<string, ProjectOrchestrationSnapshot>;

  /* ── 모드/선택 설정 액션 ── */
  setRunMode: (mode: RunMode) => void;
  setPicked: (picked: Record<string, boolean>) => void;
  togglePicked: (id: NodeId) => void;
  setActiveProfile: (profileId: string | null) => void;
  setNodeOrder: (order: NodeId[]) => void;

  /* ── 프로필 액션(B5) ── */
  /** 프로필 적용 — picked·nodeOrder·activeProfileId·runMode 세팅(실행은 사용자가 별도). */
  applyProfile: (id: ProfileId) => void;
  /** 현재 picked(고른 leaf)를 커스텀 워크플로우로 저장. 반환=새 id(label 빈 문자열이면 ""). */
  saveCustomProfile: (label: string, description?: string) => string;
  /** 커스텀 프로필 삭제(프리셋은 무시). 활성 프로필이면 해제. */
  deleteCustomProfile: (id: ProfileId) => void;
  /** 프로필 복제(프리셋·커스텀 모두) → 새 커스텀. 반환=새 id. */
  duplicateProfile: (id: ProfileId, newLabel?: string) => string;

  /* ── 핵심 메서드 ── */
  /** 폐포+topo+신선스킵+과금표시 → 실행 미리보기. plan(state)도 갱신한다(실행 확정 시에만 호출). */
  buildPlan: (mode: RunMode, seed?: NodeId[]) => RunStep[];
  /**
   * buildPlan과 동일 계산이되 store(plan/runMode)를 변경하지 않는 순수 미리보기.
   * React 렌더(useMemo)에서 안전하게 호출 가능(렌더 중 set 금지 위반 회피 — 수정3).
   */
  previewPlan: (mode: RunMode, seed?: NodeId[]) => RunStep[];
  /** 입력 자동해소 — SSOT read → 미확보 시 업스트림 제안/수동입력 후보. */
  resolveInputs: (id: NodeId) => ResolveInputsResult;
  /** moduleKey=null 노드의 staleness 파생(입력 시그니처 변화 감지). */
  nodeStale: (id: NodeId) => boolean;
  /** 노드 결과 환류(useNodeRunner가 호출). */
  recordNodeResult: (id: NodeId, result: NodeResult) => void;
  /** 노드 상태만 갱신(queued/running 등 진행표시). */
  setNodeState: (id: NodeId, state: NodeRunState) => void;
  /** [graft C] byProject ↔ 현재 상태 왕복(전환 시 복원·진입 시 저장). */
  syncProject: (projectId: string) => void;
}

/* ── 헬퍼 ── */

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** 데이터 SSOT(store) 현재 스냅샷을 읽는다(구독 아님 — 액션 시점 1회 read). */
function ctx(): ProjectContextState {
  return useProjectContextStore.getState();
}

/** 모드별 시드 노드(§2-C seedNodes). */
function seedNodes(
  mode: RunMode,
  picked: Record<string, boolean>,
  activeProfileId: string | null,
  profiles: WorkflowProfile[],
  explicitSeed?: NodeId[],
): NodeId[] {
  if (explicitSeed && explicitSeed.length) return explicitSeed;
  switch (mode) {
    case "guided":
      // 최종 출구(finance) 시드 → 폐포 = 전 분석노드(audit은 말단검증이라 미포함).
      return ["finance"];
    case "standalone":
      // 별도 모드는 명시 seed가 필수(클릭한 단일 노드). 없으면 빈 계획.
      return [];
    case "selective":
      // 선택집합의 노드들(leaf) — computeClosure가 상류를 끌어온다.
      return (Object.keys(picked) as NodeId[]).filter((id) => picked[id] && BY_ID[id]);
    case "profile": {
      // 갭(a) 해소: PRESET ∪ custom 조회(이전엔 custom만 봐서 프리셋이 안 잡혔음).
      const p = findProfile(activeProfileId, profiles);
      return p ? p.nodes.filter((id) => BY_ID[id]) : [];
    }
    default:
      return [];
  }
}

/** moduleKey 보유 노드 신선분 판정 — 기존 store 셀렉터 위임(무회귀). */
function moduleFresh(mk: ModuleKey, s: ProjectContextState): boolean {
  // 결과가 있고(stamp 존재) 업스트림보다 최신이면 신선(재실행 불필요).
  // isStale=false && 이미 산출됨(updatedAt) → 신선. isReadyForFirstCompute=true면 최초산출 필요(미신선).
  const stamped = s.updatedAt[mk] != null;
  if (!stamped) return false; // 한 번도 산출 안 됨 → 신선 아님(실행 필요)
  if (s.isStale(mk)) return false; // 업스트림이 더 최신 → 신선 아님(재실행 필요)
  return true;
}

/** moduleKey=null 노드 신선분 판정 — 입력 시그니처 변화 감지(useStageAutoRecalc 동일 패턴 R4). */
function derivedFresh(id: NodeId, state: OrchestrationState, s: ProjectContextState): boolean {
  const last = state.nodeResult[id];
  if (!last || last.at == null) return false; // 미실행 → 신선 아님
  if (last.state === "error") return false; // 오류 노드는 신선 아님 — 동일입력 재시도 허용
  return last.inputSignature === currentSignature(id, s);
}

/**
 * 실행계획 순수 계산(set 미수행) — buildPlan/previewPlan 공용 코어.
 * 폐포 → 위상정렬 → 모드별 순서 재배열 → 신선/미가용 스킵·과금 표시까지 산출하되
 * store 상태는 절대 변경하지 않는다. ordered(plan 후보)와 steps를 함께 반환한다.
 */
function computePlan(
  mode: RunMode,
  seed: NodeId[] | undefined,
  state: OrchestrationState,
  s: ProjectContextState,
): { ordered: NodeId[]; steps: RunStep[] } {
  const seeds = seedNodes(
    mode,
    state.picked,
    state.activeProfileId,
    state.customProfiles,
    seed,
  );
  // 폐포(상류 전이 포함) → 위상정렬 실행순서.
  const closure = computeClosure(seeds);
  let ordered = topoSort(closure);

  // [graft C] 가이드/프로필 순서 재배열 주입.
  if (mode === "guided") {
    // 가이드는 스토리라인 위상순으로 안내(전노드 정렬). 폐포 노드만 남긴다.
    const guideSet = new Set(closure);
    ordered = guidedOrder().filter((id) => guideSet.has(id));
  } else if (mode === "profile") {
    // 갭(b) 해소: PRESET ∪ custom 조회(이전엔 custom만 봐서 프리셋 order가 안 잡혔음).
    // 사용자가 NodeOrderEditor로 재배열한 nodeOrder가 있으면 그것을 우선(프로필 order는 기본 힌트).
    const p = findProfile(state.activeProfileId, state.customProfiles);
    const orderHint = state.nodeOrder.length ? state.nodeOrder : p?.order ?? [];
    if (orderHint.length) {
      const orderSet = new Set(closure);
      const head = orderHint.filter((id) => orderSet.has(id));
      const tail = ordered.filter((id) => !head.includes(id));
      ordered = [...head, ...tail];
    }
  } else if (state.nodeOrder.length) {
    // 사용자 재배열이 있으면 그 순서를 우선(폐포에 속한 것만).
    const orderSet = new Set(closure);
    const head = state.nodeOrder.filter((id) => orderSet.has(id));
    const tail = ordered.filter((id) => !head.includes(id));
    ordered = [...head, ...tail];
  }

  const seedSet = new Set(seeds);
  const steps: RunStep[] = ordered.map((id) => {
    const node = BY_ID[id];
    const reason: RunStep["reason"] =
      mode === "guided"
        ? "guide"
        : seedSet.has(id)
          ? "selected"
          : "closure";

    // (2) available 가드 — 미가용(audit 등)은 unavailable 스킵(0 강제 금지).
    if (!node.available) {
      return {
        node: id,
        reason,
        skipped: true,
        skipReason: "unavailable",
        chargeable: false,
        estimatedKrw: 0,
      };
    }

    // (1) 신선분 스킵 — moduleKey 위임 또는 시그니처 파생.
    const mk = moduleKeyOf(id);
    const fresh = mk ? moduleFresh(mk, s) : derivedFresh(id, state, s);
    if (fresh) {
      return {
        node: id,
        reason,
        skipped: true,
        skipReason: "fresh",
        chargeable: false,
        estimatedKrw: 0,
      };
    }

    // 실행 대상 — 과금 표시(billingKey 있을 때만). 예상액은 관리자 미설정 0(프론트 추정 금지).
    const chargeable = !!node.billingKey;
    return {
      node: id,
      reason,
      skipped: false,
      chargeable,
      estimatedKrw: 0,
    };
  });

  return { ordered, steps };
}

/* ── store ── */

export const useOrchestrationStore = create<OrchestrationState>()(
  persist(
    (set, get) => ({
      // 휘발
      runMode: "guided",
      picked: {},
      activeProfileId: null,
      nodeOrder: [],
      plan: [],
      nodeResult: {},
      nodeUpdatedAt: {},
      currentProjectId: null,

      // 영속
      customProfiles: [],
      byProject: {},

      /* ── 설정 액션 ── */
      setRunMode: (mode) => set({ runMode: mode }),
      setPicked: (picked) => set({ picked }),
      togglePicked: (id) =>
        set((state) => ({ picked: { ...state.picked, [id]: !state.picked[id] } })),
      setActiveProfile: (profileId) => set({ activeProfileId: profileId }),
      setNodeOrder: (order) => set({ nodeOrder: order }),

      /* ── 프로필 액션(B5) ── */

      // 프로필 적용 — 프리셋∪커스텀에서 찾아 선택/순서/모드를 세팅한다.
      // buildPlan은 호출하지 않는다(UI가 picked 반영 후 미리보기는 previewPlan, 실행은 사용자 동작).
      applyProfile: (id) => {
        const profile = findProfile(id, get().customProfiles);
        if (!profile) return; // 없는 id면 무시(가짜 적용 금지)
        const picked: Record<string, boolean> = {};
        for (const n of profile.nodes) {
          if (BY_ID[n]) picked[n] = true; // 유효 NodeId만
        }
        set({
          picked,
          nodeOrder: [...profile.order], // 표시·실행 순서 힌트(사용자가 NodeOrderEditor로 재배열 가능)
          activeProfileId: id,
          // ★프로필 적용은 항상 'profile' 모드로 진입한다. profile.defaultMode가 'guided'여도
          //   guided 탭(B4)이 아직 비활성이고 OrchestratorPanel에 guided 전용 미리보기 UI가 없어
          //   guided로 바꾸면 프리셋(디벨로퍼·PF금융)이 빈 화면이 된다. profile 모드는 셀렉터+
          //   미리보기 기반이라 전 프리셋이 정상 동작한다(폐포는 동일·실행 정확). defaultMode는
          //   B4 guided 활성 시 진입 모드 힌트로 사용하도록 데이터만 보존한다(블루프린트 §4 정합).
          runMode: "profile",
        });
      },

      // 현재 picked(사용자가 고른 leaf — 폐포 확장 전)를 커스텀 워크플로우로 저장.
      saveCustomProfile: (label, description) => {
        const trimmed = (label ?? "").trim();
        if (!trimmed) return ""; // 빈 라벨은 무시(정직 — 저장 안 함)
        const state = get();
        // 고른 노드(leaf) — picked가 true인 유효 NodeId만.
        const nodes = (Object.keys(state.picked) as NodeId[]).filter(
          (n) => state.picked[n] && BY_ID[n],
        );
        if (nodes.length === 0) return ""; // 빈 워크플로우 저장 방지(정직 — 고른 노드 없음)
        // 순서: 사용자 재배열(nodeOrder)이 있으면 그것의 picked 부분, 없으면 nodes 순서.
        const order = state.nodeOrder.length
          ? state.nodeOrder.filter((n) => nodes.includes(n))
          : [...nodes];
        const id = crypto.randomUUID();
        const profile: WorkflowProfile = {
          id,
          label: trimmed,
          description: (description ?? "").trim(),
          builtin: false,
          nodes,
          order,
          // 현재 모드가 가이드면 가이드, 아니면 선택(커스텀은 selective 기본).
          defaultMode: state.runMode === "guided" ? "guided" : "selective",
          autoRunUpstream: true,
          createdAt: Date.now(), // 클라이언트 런타임이라 실시각 사용 OK(resume 제약 없음)
        };
        set({ customProfiles: [...state.customProfiles, profile] });
        return id;
      },

      // 커스텀 프로필 삭제 — 프리셋(builtin)은 삭제 불가(무시). 활성이면 해제.
      deleteCustomProfile: (id) => {
        const state = get();
        // 프리셋은 PRESET_PROFILES에 있으므로 보호(커스텀 목록에만 삭제 적용).
        if (PRESET_PROFILES.some((p) => p.id === id)) return;
        const next = state.customProfiles.filter((p) => p.id !== id);
        if (next.length === state.customProfiles.length) return; // 없던 id면 변경 없음
        set({
          customProfiles: next,
          activeProfileId: state.activeProfileId === id ? null : state.activeProfileId,
        });
      },

      // 프로필 복제 — 프리셋·커스텀 모두 새 커스텀으로 복제(새 uuid·builtin:false).
      duplicateProfile: (id, newLabel) => {
        const state = get();
        const src = findProfile(id, state.customProfiles);
        if (!src) return ""; // 없는 id면 무시
        const newId = crypto.randomUUID();
        const copy: WorkflowProfile = {
          ...src,
          id: newId,
          label: (newLabel ?? "").trim() || `(복제) ${src.label}`,
          builtin: false,
          nodes: [...src.nodes],
          order: [...src.order],
          createdAt: Date.now(),
        };
        set({ customProfiles: [...state.customProfiles, copy] });
        return newId;
      },

      /* ── buildPlan(실행 확정 — set 수행) ── */
      buildPlan: (mode, seed) => {
        const { ordered, steps } = computePlan(mode, seed, get(), ctx());
        set({ runMode: mode, plan: ordered });
        return steps;
      },

      /* ── previewPlan(순수 미리보기 — set 미수행, 렌더 안전) ── */
      previewPlan: (mode, seed) => {
        return computePlan(mode, seed, get(), ctx()).steps;
      },

      /* ── resolveInputs ── */
      resolveInputs: (id) => {
        const node = BY_ID[id];
        const s = ctx();
        const ready: SsotInputSpec[] = [];
        const missing: SsotInputSpec[] = [];
        if (!node) return { ready, missing, autoCandidates: [] };
        for (const input of node.ssotInputs) {
          if (input.readyCheck(s)) ready.push(input);
          else missing.push(input);
        }
        // 미확보 입력을 채워줄 상류 노드 후보 = 노드의 직접 업스트림(자동실행 "제안"만).
        const autoCandidates = missing.length ? [...node.upstream] : [];
        return { ready, missing, autoCandidates };
      },

      /* ── nodeStale (moduleKey=null 노드 파생) ── */
      nodeStale: (id) => {
        const node = BY_ID[id];
        if (!node) return false;
        const s = ctx();
        const mk = moduleKeyOf(id);
        if (mk) return !moduleFresh(mk, s);
        return !derivedFresh(id, get(), s);
      },

      /* ── 결과 환류 ── */
      recordNodeResult: (id, result) =>
        set((state) => ({
          nodeResult: { ...state.nodeResult, [id]: result },
          nodeUpdatedAt:
            result.at != null
              ? { ...state.nodeUpdatedAt, [id]: result.at }
              : state.nodeUpdatedAt,
        })),

      setNodeState: (id, runState) =>
        set((state) => {
          const prev: NodeResult = state.nodeResult[id] ?? {
            state: "idle",
            verifyStatus: null,
            grounding: {},
            chargedKrw: 0,
            inputSignature: null,
            at: null,
          };
          return {
            nodeResult: { ...state.nodeResult, [id]: { ...prev, state: runState } },
          };
        }),

      /* ── syncProject ([graft C]) ── */
      syncProject: (projectId) => {
        const state = get();
        // 직전 프로젝트 상태를 byProject에 저장(전환 손실 방지).
        const prevId = state.currentProjectId;
        const byProject = { ...state.byProject };
        if (prevId && prevId !== projectId) {
          byProject[prevId] = {
            runMode: state.runMode,
            picked: state.picked,
            activeProfileId: state.activeProfileId,
            nodeOrder: state.nodeOrder,
          };
        }
        // 대상 프로젝트의 이전 스냅샷이 있으면 복원, 없으면 모드 기본값으로 초기화.
        const snap = byProject[projectId];
        if (snap) {
          set({
            currentProjectId: projectId,
            byProject,
            runMode: snap.runMode,
            picked: snap.picked ?? {},
            activeProfileId: snap.activeProfileId ?? null,
            nodeOrder: snap.nodeOrder ?? [],
            // 실행 휘발물은 프로젝트 전환 시 초기화(과금/결과 혼선 방지).
            plan: [],
            nodeResult: {},
            nodeUpdatedAt: {},
          });
        } else {
          set({
            currentProjectId: projectId,
            byProject,
            runMode: "guided",
            picked: {},
            activeProfileId: null,
            nodeOrder: [],
            plan: [],
            nodeResult: {},
            nodeUpdatedAt: {},
          });
        }
      },
    }),
    {
      name: "propai-orchestration",
      version: 1,
      // 영속 대상 = customProfiles·byProject·activeProfileId만(§2-D).
      // 실행 휘발물(plan·nodeResult·picked·nodeOrder·runMode)은 persist 제외 → 새로고침 시 초기화.
      partialize: (state) => ({
        customProfiles: state.customProfiles,
        byProject: state.byProject,
        activeProfileId: state.activeProfileId,
      }),
    },
  ),
);
