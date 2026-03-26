export type IntegrationMode = "mock" | "live" | "waiting";

export type ProjectModuleKey =
  | "design"
  | "bim"
  | "finance"
  | "drone"
  | "blockchain"
  | "report"
  | "tax"
  | "inspection";

export type ProjectCard = {
  id: string;
  name: string;
  location: string;
  phase: string;
  updatedAt: string;
  nextAction: string;
  modules: ProjectModuleKey[];
};

export type ProjectListResponse = {
  projects: ProjectCard[];
  total: number;
  updatedAt: string;
};

export type ProjectDetailResponse = {
  project: ProjectCard;
  summary: {
    budget: string;
    schedule: string;
    risk: string;
  };
  timeline: string[];
  nextSteps: string[];
};

export type DashboardOverviewResponse = {
  metrics: Array<{
    id: string;
    label: string;
    value: string;
  }>;
  featuredProjectId: string;
};

export type IntegrationStatusResponse = {
  channels: Array<{
    id: "rest" | "graphql" | "realtime";
    label: string;
    mode: IntegrationMode;
    detail: string;
  }>;
};
