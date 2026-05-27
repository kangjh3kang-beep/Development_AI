/**
 * 수지분석 v2 Zustand 스토어 — 상태 관리 + API 호출
 */
import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { apiClient } from "@/lib/api-client";

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
  activeTab: "input" | "result" | "montecarlo" | "version" | "tax";
  // 액션
  setInput: (patch: Partial<FeasibilityInput>) => void;
  setSelectedModule: (code: string) => void;
  setActiveTab: (tab: FeasibilityV2State["activeTab"]) => void;
  calculate: () => Promise<void>;
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
    result: null,
    comparisonResults: [],
    monteCarloResult: null,
    recommendations: [],
    commits: [],
    modules: [],
    selectedModule: "M06",
    isCalculating: false,
    error: null,
    activeTab: "input",

    setInput: (patch) =>
      set((s) => {
        Object.assign(s.input, patch);
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

    calculate: async () => {
      set((s) => {
        s.isCalculating = true;
        s.error = null;
      });
      try {
        const res = await apiClient.postV2<FeasibilityResult>("/feasibility/calculate", {
          body: get().input as Record<string, unknown>,
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
        s.result = null;
        s.comparisonResults = [];
        s.monteCarloResult = null;
        s.recommendations = [];
        s.error = null;
        s.activeTab = "input";
      }),
  }))
);
