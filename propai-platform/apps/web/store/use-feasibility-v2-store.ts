/**
 * 수지분석 v2 Zustand 스토어 — 상태 관리 + API 호출
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient, ApiClientError } from "@/lib/api-client";

// ── 타입 ──

export interface FeasibilityInput {
  development_type: string;
  project_name: string;
  total_land_area_sqm: number;
  land_category: string;
  official_price_per_sqm: number;
  price_multiplier: number;
  total_gfa_sqm: number;
  building_type: string;
  total_households: number;
  avg_sale_price_per_pyeong: number;
  avg_area_pyeong: number;
  sale_ratio: number;
  bridge_amount_won: number;
  pf_amount_won: number;
  midpay_amount_won: number;
  sido_name: string;
  sigungu_name: string;
  project_months: number;
  discount_rate: number;
  equity_won: number;
  params: Record<string, unknown>;
}

export interface FeasibilityResult {
  development_type: string;
  module_name: string;
  total_revenue_won: number;
  total_cost_won: number;
  net_profit_won: number;
  profit_rate_pct: number;
  roi_pct: number;
  npv_won: number;
  grade: string;
  cost_breakdown_won: Record<string, number>;
  tax_detail: Record<string, unknown>;
  special_detail: Record<string, unknown>;
  // ★P4②: 시니어 회계사(K-IFRS) 자문 — with_senior opt-in 시에만 채워짐(기본 {}).
  //   구조는 공용 evidence 계약(SeniorVerdictCard의 SeniorConsultation과 동일).
  //   타입은 소비처(에디터)에서 SeniorConsultation으로 단언 — store가 컴포넌트 타입에
  //   역의존하지 않도록 unknown 유지.
  senior_accountant_review?: unknown;
  // baseline(추정) 응답에만 존재 — /calculate 결과는 미포함.
  is_baseline?: boolean;
  confidence?: string;
  sources?: Record<string, unknown>;
  assumptions?: Record<string, unknown>;
}

/** baseline(추정 수지) 요청 — 부지 데이터만으로 1차 산출 */
export interface FeasibilityBaselineInput {
  address?: string;
  zone_type?: string;
  zone_code?: string;
  land_area_sqm?: number;
  pnu?: string;
  region?: string;
  official_price_per_sqm?: number;
}

export interface MonteCarloResult {
  mean: number;
  std: number;
  p5: number;
  p50: number;
  p95: number;
  probability_positive: number;
  convergence_ratio: number;
  n_simulations: number;
  histogram: Array<{ bin_start: number; bin_end: number; count: number }>;
}

export interface Recommendation {
  rule_code: string;
  rule_name: string;
  severity: string;
  message: string;
  suggestion: string;
}

export interface VCSCommit {
  sha: string;
  message: string;
  parent_sha: string | null;
  timestamp: string;
}

export interface ModuleInfo {
  code: string;
  name: string;
}

interface FeasibilityV2State {
  // 입력
  input: Partial<FeasibilityInput>;
  // 이 input 이 어느 프로젝트에 속하는지(프로젝트 스코핑) — 이 스토어는 전역 단일이라
  //   프로젝트를 전환해도 이전 프로젝트의 input 이 남는다. 투자분석 등 다른 화면이 이 input 을
  //   리스크 시뮬 base 로 재사용할 때, boundProjectId 와 현재 projectId 가 다르면 '남의 프로젝트
  //   데이터'이므로 신뢰하지 않도록 하는 표식(무목업: 다른 프로젝트 실데이터 오표시 방지).
  boundProjectId: string | null;
  // 결과
  result: FeasibilityResult | null;
  comparisonResults: FeasibilityResult[];
  monteCarloResult: MonteCarloResult | null;
  recommendations: Recommendation[];
  commits: VCSCommit[];
  modules: ModuleInfo[];
  // UI
  selectedModule: string;
  isCalculating: boolean;
  error: string | null;
  // baseline 추정 산출에 필요한 입력(부지면적/주소)이 부족(422)할 때 true.
  // 빈 0 결과 대신 입력 유도 게이트를 띄우기 위한 신호(무목업).
  baselineNeedsInput: boolean;
  activeTab: "input" | "result" | "montecarlo" | "version" | "tax";
  // 액션
  setInput: (patch: Partial<FeasibilityInput>) => void;
  // 현재 input 을 특정 프로젝트에 바인딩(수지 에디터가 프로젝트 로드 시 호출).
  bindProject: (projectId: string) => void;
  setSelectedModule: (code: string) => void;
  setActiveTab: (tab: FeasibilityV2State["activeTab"]) => void;
  // ★P4②: 시니어 회계 자문(K-IFRS) opt-in — LLM 비용이 발생하므로 기본 false(과금 정책).
  withSenior: boolean;
  setWithSenior: (v: boolean) => void;
  // opts.constructionCostOverrideWon: 공사비 정밀분석 결과를 엔진에 주입(3자 수치 정합).
  calculate: (opts?: { constructionCostOverrideWon?: number | null }) => Promise<void>;
  // 부지 데이터만으로 시장표준 추정(baseline) 수지를 1회 산출해 즉시 표시.
  runBaseline: (input: FeasibilityBaselineInput) => Promise<void>;
  compareMulti: (inputs: FeasibilityInput[]) => Promise<void>;
  runMonteCarlo: (variables: Array<{ name: string; mean: number; std: number }>, n?: number) => Promise<void>;
  fetchRecommendations: () => Promise<void>;
  fetchModules: () => Promise<void>;
  commitVersion: (message: string, projectId?: string) => Promise<void>;
  fetchCommitLog: (projectId: string) => Promise<void>;
  reset: () => void;
}

const DEFAULT_INPUT: Partial<FeasibilityInput> = {
  development_type: "M06",
  project_name: "",
  total_land_area_sqm: 0,
  land_category: "land",
  official_price_per_sqm: 0,
  price_multiplier: 1.0,
  total_gfa_sqm: 0,
  building_type: "apartment",
  total_households: 0,
  avg_sale_price_per_pyeong: 0,
  avg_area_pyeong: 0,
  sale_ratio: 1.0,
  bridge_amount_won: 0,
  pf_amount_won: 0,
  midpay_amount_won: 0,
  sido_name: "",
  sigungu_name: "",
  project_months: 48,
  discount_rate: 0.08,
  equity_won: 0,
  params: {},
};

export const useFeasibilityV2Store = create<FeasibilityV2State>()(
  immer((set, get) => ({
    input: { ...DEFAULT_INPUT },
    boundProjectId: null,
    result: null,
    comparisonResults: [],
    monteCarloResult: null,
    recommendations: [],
    commits: [],
    modules: [],
    selectedModule: "M06",
    isCalculating: false,
    error: null,
    withSenior: false,
    setWithSenior: (v) =>
      set((s) => {
        s.withSenior = v;
      }),
    baselineNeedsInput: false,
    activeTab: "input",

    setInput: (patch) =>
      set((s) => {
        Object.assign(s.input, patch);
      }),

    // 다른 프로젝트로 바뀌면 이전 프로젝트 input 이 남지 않도록 초기화 후 바인딩(오염 방지).
    bindProject: (projectId) =>
      set((s) => {
        if (s.boundProjectId !== projectId) {
          s.input = { ...DEFAULT_INPUT };
          s.result = null;
          s.monteCarloResult = null;
          s.baselineNeedsInput = false;
        }
        s.boundProjectId = projectId;
      }),

    setSelectedModule: (code) =>
      set((s) => {
        s.selectedModule = code;
        s.input.development_type = code;
      }),

    setActiveTab: (tab) =>
      set((s) => {
        s.activeTab = tab;
      }),

    calculate: async (opts) => {
      set((s) => {
        s.isCalculating = true;
        s.error = null;
        s.baselineNeedsInput = false;
      });
      try {
        // 공사비 정밀분석 결과가 있으면 params.construction_cost_override_won로 주입.
        const base = get().input;
        const override = opts?.constructionCostOverrideWon;
        const params = {
          ...(base.params ?? {}),
          ...(override != null && override > 0
            ? { construction_cost_override_won: override }
            : {}),
        };
        const res = await apiClient.postV2<FeasibilityResult>("/feasibility/calculate", {
          // with_senior: K-IFRS 자문 opt-in(스토어 토글) — 백엔드가 LLM 계측·과금 훅 경유로 처리.
          body: { ...base, params, with_senior: get().withSenior } as Record<string, unknown>,
        });
        set((s) => {
          s.result = res;
          s.isCalculating = false;
          s.activeTab = "result";
        });
      } catch (e: unknown) {
        set((s) => {
          s.error = e instanceof Error ? e.message : "계산 실패";
          s.isCalculating = false;
        });
      }
    },

    runBaseline: async (input) => {
      set((s) => {
        s.isCalculating = true;
        s.error = null;
        s.baselineNeedsInput = false;
      });
      try {
        const res = await apiClient.postV2<FeasibilityResult>("/feasibility/baseline", {
          body: input as unknown as Record<string, unknown>,
          timeoutMs: 90000,
        });
        set((s) => {
          s.result = res;
          s.isCalculating = false;
          s.baselineNeedsInput = false;
        });
      } catch (e: unknown) {
        // 422 = 부지면적/주소 등 산출 입력 부족 → 사일런트 금지, 입력 유도 게이트 노출.
        // 그 외 실패는 치명적이지 않음(사용자 직접 계산 경로 유지)하되 에러는 표시.
        const status = e instanceof ApiClientError ? e.status : null;
        set((s) => {
          s.isCalculating = false;
          if (status === 422) {
            s.baselineNeedsInput = true;
            s.error = null;
          } else {
            s.error = e instanceof Error ? e.message : null;
          }
        });
      }
    },

    compareMulti: async (inputs) => {
      set((s) => {
        s.isCalculating = true;
      });
      try {
        const res = await apiClient.postV2<{ results: FeasibilityResult[] }>("/feasibility/compare", {
          body: { projects: inputs } as unknown as Record<string, unknown>,
        });
        set((s) => {
          s.comparisonResults = res.results;
          s.isCalculating = false;
        });
      } catch {
        set((s) => {
          s.isCalculating = false;
        });
      }
    },

    runMonteCarlo: async (variables, n = 10000) => {
      set((s) => {
        s.isCalculating = true;
      });
      try {
        const res = await apiClient.postV2<MonteCarloResult>("/feasibility/monte-carlo", {
          body: { variables, n_simulations: n, seed: 42 } as unknown as Record<string, unknown>,
        });
        set((s) => {
          s.monteCarloResult = res;
          s.isCalculating = false;
        });
      } catch {
        set((s) => {
          s.isCalculating = false;
        });
      }
    },

    fetchRecommendations: async () => {
      try {
        const res = await apiClient.postV2<{ recommendations: Recommendation[] }>("/feasibility/recommendations", {
          body: get().input as Record<string, unknown>,
        });
        set((s) => {
          s.recommendations = res.recommendations;
        });
      } catch {
        /* 무시 */
      }
    },

    fetchModules: async () => {
      try {
        const res = await apiClient.getV2<{ modules: ModuleInfo[] }>("/feasibility/modules");
        set((s) => {
          s.modules = res.modules;
        });
      } catch {
        /* 무시 */
      }
    },

    commitVersion: async (message, projectId?) => {
      try {
        const pid = projectId || "default";
        const snapshot = { input: get().input, result: get().result };
        await apiClient.postV2(`/feasibility/repos/${pid}/commit`, {
          body: { message, snapshot } as unknown as Record<string, unknown>,
        });
      } catch {
        /* 무시 */
      }
    },

    fetchCommitLog: async (projectId) => {
      try {
        const res = await apiClient.getV2<{ commits: VCSCommit[] }>(`/feasibility/repos/${projectId}/log`);
        set((s) => {
          s.commits = res.commits;
        });
      } catch {
        /* 무시 */
      }
    },

    reset: () =>
      set((s) => {
        s.input = { ...DEFAULT_INPUT };
        s.boundProjectId = null;
        s.result = null;
        s.comparisonResults = [];
        s.monteCarloResult = null;
        s.recommendations = [];
        s.error = null;
        s.baselineNeedsInput = false;
        s.activeTab = "input";
      }),
  }))
);
