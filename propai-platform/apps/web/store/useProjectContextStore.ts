import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ── Types ── */

interface AnalysisResult {
  module: string;
  completedAt: string;
  summary: Record<string, unknown>;
}

interface SiteAnalysisData {
  estimatedValue: number | null;
  landAreaSqm: number | null;
  zoneCode: string | null;
  address: string | null;
  pnu: string | null;
}

interface DesignData {
  totalGfaSqm: number | null;
  floorCount: number | null;
  buildingType: string | null;
  bcr: number | null;
  far: number | null;
}

interface FeasibilityData {
  totalCostWon: number | null;
  totalRevenueWon: number | null;
  profitRatePct: number | null;
  grade: string | null;
}

interface EsgData {
  embodiedCarbonKg: number | null;
  operationalCarbonKg: number | null;
  totalCarbonPerSqm: number | null;
}

interface ComplianceData {
  bcrCompliant: boolean | null;
  farCompliant: boolean | null;
  heightCompliant: boolean | null;
  violations: string[];
}

/* ── Lifecycle stage order ── */

const LIFECYCLE_STAGES = [
  "site-analysis",
  "legal",
  "design",
  "bim",
  "construction",
  "feasibility",
  "finance",
  "esg",
  "permit",
  "report",
] as const;

export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

/* ── State interface ── */

export interface ProjectContextState {
  // Current project
  projectId: string | null;
  projectName: string;
  projectStatus: string;

  // Lifecycle stage tracking
  completedStages: string[];
  currentStage: string | null;

  // Cross-module data (capillary network)
  siteAnalysis: SiteAnalysisData | null;
  designData: DesignData | null;
  feasibilityData: FeasibilityData | null;
  esgData: EsgData | null;
  complianceData: ComplianceData | null;

  // Analysis history
  analysisResults: AnalysisResult[];

  // Actions
  setProject: (id: string, name: string, status: string) => void;
  clearProject: () => void;

  updateSiteAnalysis: (data: SiteAnalysisData) => void;
  updateDesignData: (data: DesignData) => void;
  updateFeasibilityData: (data: FeasibilityData) => void;
  updateEsgData: (data: EsgData) => void;
  updateComplianceData: (data: ComplianceData) => void;

  markStageComplete: (stage: string) => void;
  setCurrentStage: (stage: string) => void;
  addAnalysisResult: (result: AnalysisResult) => void;

  // Computed
  getNextRecommendedStage: () => string | null;
}

/* ── Initial cross-module state ── */

const INITIAL_CROSS_MODULE = {
  siteAnalysis: null as SiteAnalysisData | null,
  designData: null as DesignData | null,
  feasibilityData: null as FeasibilityData | null,
  esgData: null as EsgData | null,
  complianceData: null as ComplianceData | null,
};

/* ── Store ── */

export const useProjectContextStore = create<ProjectContextState>()(
  persist(
    (set, get) => ({
      // Current project
      projectId: null,
      projectName: "",
      projectStatus: "",

      // Lifecycle
      completedStages: [],
      currentStage: null,

      // Cross-module
      ...INITIAL_CROSS_MODULE,

      // Analysis history
      analysisResults: [],

      /* ── Actions ── */

      setProject: (id, name, status) => {
        const prev = get();
        // If switching projects, reset cross-module data
        if (prev.projectId !== id) {
          set({
            projectId: id,
            projectName: name,
            projectStatus: status,
            completedStages: [],
            currentStage: null,
            analysisResults: [],
            ...INITIAL_CROSS_MODULE,
          });
        } else {
          set({ projectId: id, projectName: name, projectStatus: status });
        }
      },

      clearProject: () => {
        set({
          projectId: null,
          projectName: "",
          projectStatus: "",
          completedStages: [],
          currentStage: null,
          analysisResults: [],
          ...INITIAL_CROSS_MODULE,
        });
      },

      updateSiteAnalysis: (data) => {
        set({ siteAnalysis: data });
      },

      updateDesignData: (data) => {
        set({ designData: data });
      },

      updateFeasibilityData: (data) => {
        set({ feasibilityData: data });
      },

      updateEsgData: (data) => {
        set({ esgData: data });
      },

      updateComplianceData: (data) => {
        set({ complianceData: data });
      },

      markStageComplete: (stage) => {
        const prev = get();
        if (prev.completedStages.includes(stage)) return;
        set({
          completedStages: [...prev.completedStages, stage],
        });
      },

      setCurrentStage: (stage) => {
        set({ currentStage: stage });
      },

      addAnalysisResult: (result) => {
        set((state) => ({
          analysisResults: [...state.analysisResults, result],
        }));
      },

      getNextRecommendedStage: () => {
        const { completedStages } = get();
        for (const stage of LIFECYCLE_STAGES) {
          if (!completedStages.includes(stage)) {
            return stage;
          }
        }
        return null;
      },
    }),
    {
      name: "propai-project-context",
    },
  ),
);

export { LIFECYCLE_STAGES };
export type {
  AnalysisResult,
  SiteAnalysisData,
  DesignData,
  FeasibilityData,
  EsgData,
  ComplianceData,
};
