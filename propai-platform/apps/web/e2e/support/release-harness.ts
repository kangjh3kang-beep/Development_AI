import type { Page, Route } from "@playwright/test";

const ACCESS_TOKEN = "playwright-access-token";
const REFRESH_TOKEN = "playwright-refresh-token";

export const RELEASE_PROJECT_ID = "project-release-001";
export const RELEASE_PROJECT_NAME = "Release Cutover Tower";

function listProjectCard() {
  return {
    id: RELEASE_PROJECT_ID,
    name: RELEASE_PROJECT_NAME,
    location: "Seoul Mapo-gu",
    phase: "planning",
    updatedAt: "2026-03-26T00:00:00Z",
    nextAction: "Validate release cutover workflows.",
    modules: [
      "design",
      "bim",
      "finance",
      "drone",
      "blockchain",
      "report",
      "tax",
      "inspection",
    ],
  };
}

function projectSummaryItem() {
  return {
    id: RELEASE_PROJECT_ID,
    name: RELEASE_PROJECT_NAME,
    status: "planning",
    address: "Seoul Mapo-gu 100",
    total_area_sqm: 9800,
    updated_at: "2026-03-26T00:00:00Z",
  };
}

function projectDetail() {
  return {
    id: RELEASE_PROJECT_ID,
    name: RELEASE_PROJECT_NAME,
    status: "planning",
    address: "Seoul Mapo-gu 100",
    latitude: 37.5519,
    longitude: 126.9227,
    total_area_sqm: 9800,
    created_at: "2026-03-25T00:00:00Z",
    updated_at: "2026-03-26T00:00:00Z",
  };
}

function dashboardStats() {
  return {
    total_projects: 21,
    active_webhooks: 6,
    active_api_keys: 4,
    ai_cost_month_usd: 1243.56,
    ai_tokens_month: 880000,
    projects_by_status: {
      planning: 7,
      execution: 9,
      completed: 5,
    },
  };
}

function digitalTwinAnomalies() {
  return {
    anomalies: [
      {
        timestamp: "2026-03-26T09:00:00Z",
        sensor_type: "vibration",
        value: 4.8,
        anomaly_score: -0.41,
        is_anomaly: true,
        severity: "warning",
      },
      {
        timestamp: "2026-03-26T09:05:00Z",
        sensor_type: "vibration",
        value: 3.1,
        anomaly_score: 0.08,
        is_anomaly: false,
        severity: "info",
      },
      {
        timestamp: "2026-03-26T09:10:00Z",
        sensor_type: "temperature",
        value: 28.2,
        anomaly_score: -0.12,
        is_anomaly: false,
        severity: "info",
      },
    ],
    summary: {
      total_sensors: 24,
      anomalies_detected: 3,
      critical_count: 0,
      warning_count: 3,
      last_scan_at: "2026-03-26T09:10:00Z",
    },
  };
}

type MutableState = {
  contractSignStatus: "not_requested" | "requested";
  esignRequestId: string | null;
  pendingApprovals: Array<{
    approval_id: string;
    task_id: string;
    project_id: string;
    domain: string;
    approver_role: string;
    status: string;
    rationale: string;
    recommendation: string;
    confidence_score: number;
    created_at: string;
    decided_at?: string | null;
  }>;
  digitalTwinStatus: Record<string, unknown> | null;
  riskSnapshot: Record<string, unknown> | null;
  permitSnapshot: Record<string, unknown> | null;
  feasibilityReport: Record<string, unknown>;
};

function createState(): MutableState {
  return {
    contractSignStatus: "not_requested",
    esignRequestId: null,
    pendingApprovals: [
      {
        approval_id: "approval-release-001",
        task_id: "task-release-001",
        project_id: RELEASE_PROJECT_ID,
        domain: "finance",
        approver_role: "investment-committee",
        status: "pending",
        rationale: "Capital structure analysis requires committee review.",
        recommendation: "proceed-with-conditions",
        confidence_score: 0.74,
        created_at: "2026-03-26T00:00:00Z",
      },
      {
        approval_id: "approval-release-002",
        task_id: "task-release-002",
        project_id: RELEASE_PROJECT_ID,
        domain: "development",
        approver_role: "risk-committee",
        status: "pending",
        rationale: "Development plan requires risk review before release.",
        recommendation: "escalate",
        confidence_score: 0.61,
        created_at: "2026-03-26T00:05:00Z",
      },
    ],
    digitalTwinStatus: null,
    riskSnapshot: null,
    permitSnapshot: null,
    feasibilityReport: {
      id: "feasibility-release-001",
      project_id: RELEASE_PROJECT_ID,
      scenario_name: "stored-case",
      npv: 1200000000,
      irr: 0.118,
      payback_period_months: 72,
      total_investment_krw: 1500000000,
      total_revenue_krw: 3100000000,
      risk_score: 0.31,
      discount_rate: 0.05,
      annual_growth_rate: 0.02,
      analysis_years: 10,
      exit_value_krw: 1800000000,
      cashflows: [
        {
          year: 1,
          revenue_krw: 280000000,
          operating_cost_krw: 95000000,
          net_cashflow_krw: 185000000,
          discounted_cashflow_krw: 176190476.19,
        },
      ],
      assumptions: {},
      created_at: "2026-03-26T00:00:00Z",
    },
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function notFound(route: Route, message: string) {
  return json(route, { detail: message }, 404);
}

function buildHistory(state: MutableState) {
  return [
    {
      task_id: "task-history-001",
      project_id: RELEASE_PROJECT_ID,
      domain: "finance",
      status: "completed",
      confidence_score: 0.74,
      recommendation: "proceed-with-conditions",
      findings: [],
      approval_required: true,
      approval_status: state.pendingApprovals.length > 0 ? "pending" : "approved",
      approver_role: "investment-committee",
      narrative:
        "Capital structure analysis completed with confidence 74%. Recommendation: proceed-with-conditions.",
      created_at: "2026-03-26T00:00:00Z",
    },
  ];
}

function latestContract(state: MutableState) {
  return {
    draft_id: "draft-release-001",
    project_id: RELEASE_PROJECT_ID,
    project_name: RELEASE_PROJECT_NAME,
    contract_type: "construction",
    target_language: "en",
    title: `${RELEASE_PROJECT_NAME} Construction agreement`,
    counterparty_name: "Hanbit Contractors",
    effective_date: "2026-04-01T00:00:00Z",
    contract_amount_krw: 4800000000,
    document_url: "https://propai.local/contracts/draft-release-001",
    status: state.contractSignStatus === "requested" ? "esign_requested" : "draft",
    sign_status: state.contractSignStatus,
    key_terms: [{ label: "Counterparty", value: "Hanbit Contractors" }],
    clauses: [{ title: "Purpose", body: "Define scope and obligations." }],
    summary: "Construction draft summary",
    rendered_markdown: "# Contract",
    esign_request_id: state.esignRequestId,
    created_at: "2026-03-26T00:00:00Z",
  };
}

async function handleApiRoute(route: Route, state: MutableState) {
  const request = route.request();
  const url = new URL(request.url());
  const method = request.method();
  const path = url.pathname.replace("/api/latest", "") || "/";

  if (method === "POST" && (path === "/auth/login" || path === "/auth/register")) {
    return json(route, {
      access_token: ACCESS_TOKEN,
      refresh_token: REFRESH_TOKEN,
      token_type: "bearer",
      expires_in: 3600,
    });
  }

  if (method === "POST" && path === "/auth/refresh") {
    return json(route, {
      access_token: ACCESS_TOKEN,
      refresh_token: REFRESH_TOKEN,
      token_type: "bearer",
      expires_in: 3600,
    });
  }

  if (method === "GET" && path === "/auth/me") {
    return json(route, {
      id: "user-release-001",
      tenant_id: "tenant-release-001",
      email: "ops@propai.dev",
      name: "Release Operator",
      role: "admin",
      is_active: true,
      created_at: "2026-03-25T00:00:00Z",
    });
  }

  if (method === "POST" && path === "/auth/logout") {
    return json(route, { success: true });
  }

  if (method === "GET" && path === "/dashboard/stats") {
    return json(route, dashboardStats());
  }

  if (method === "GET" && path === "/system/version") {
    return json(route, {
      app_name: "PropAI API",
      version: "30.0.0",
      environment: "production",
      api_prefixes: ["/api/v1", "/api/latest"],
    });
  }

  if (method === "GET" && path === "/system/health/full") {
    return json(route, {
      status: "healthy",
      version: "30.0.0",
      environment: "production",
      services: {
        qdrant: "healthy",
        redis: "healthy",
      },
      checked_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "GET" && path === "/projects" && url.searchParams.get("page") === "1") {
    return json(route, {
      items: [projectSummaryItem()],
      page: 1,
      page_size: 20,
      has_next: false,
    });
  }

  if (method === "GET" && path === "/projects") {
    return json(route, {
      projects: [listProjectCard()],
      total: 1,
      updatedAt: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "GET" && path === `/projects/${RELEASE_PROJECT_ID}`) {
    return json(route, projectDetail());
  }

  if (method === "POST" && path === "/avm") {
    return json(route, {
      id: "avm-release-001",
      project_id: RELEASE_PROJECT_ID,
      estimated_price: 2400000000,
      price_per_sqm: 1655172,
      confidence_score: 0.82,
      comparable_count: 9,
      model_version: "v43-avm",
      created_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "POST" && path === "/finance/jeonse-risk") {
    return json(route, {
      jeonse_ratio: 0.75,
      risk_level: "MEDIUM",
      risk_score: 0.48,
      analysis: "The jeonse ratio remains below the highest-risk band.",
      factors: [
        {
          factor: "ratio-band",
          detail: "The ratio remains below 80 percent.",
        },
      ],
    });
  }

  if (method === "GET" && path === `/finance/feasibility/${RELEASE_PROJECT_ID}/latest`) {
    return json(route, state.feasibilityReport);
  }

  if (method === "POST" && path === "/finance/feasibility") {
    state.feasibilityReport = {
      ...state.feasibilityReport,
      id: "feasibility-release-002",
      scenario_name: "base-case",
      npv: 1450000000,
      irr: 0.131,
      payback_period_months: 60,
      total_revenue_krw: 3300000000,
      risk_score: 0.22,
      created_at: "2026-03-26T00:10:00Z",
    };
    return json(route, state.feasibilityReport);
  }

  if (method === "POST" && path === "/reports/investor/generate") {
    return json(route, {
      project_id: RELEASE_PROJECT_ID,
      report_type: "investor",
      generated_sections: ["executive-summary", "market"],
      variants: [
        {
          report_id: "report-release-ko-001",
          target_language: "ko",
          title: `${RELEASE_PROJECT_NAME} Investor Brief`,
          quality_score: 0.94,
          translated_text: "Prime Seoul office exposure with strong leasing momentum.",
        },
      ],
    });
  }

  if (method === "POST" && path === "/design/floor-plan") {
    return json(route, {
      design_id: "design-release-001",
      file_url: "https://cdn.example.com/design-release-001.png",
      room_count: 3,
      generation_method: "sdxl",
      vision_validation: {
        detected_rooms: 3,
        expected_rooms: 3,
        confidence: 0.88,
        match: true,
      },
    });
  }

  if (method === "POST" && path === "/bim/generate-ifc") {
    return json(route, {
      id: "bim-release-001",
      project_id: RELEASE_PROJECT_ID,
      total_volume_m3: 12450.5,
      total_area_sqm: 9800,
      material_breakdown: [{ type: "IfcWall", count: 40 }],
      element_count: 160,
      ifc_version: "IFC4",
      created_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "POST" && path === "/bim/carbon") {
    return json(route, {
      total_embodied_carbon: 420000,
      total_operational_carbon: 1500000,
      total_carbon: 1920000,
      breakdown: [],
      reduction_tips: ["Reduce concrete intensity in the wall package."],
    });
  }

  if (method === "GET" && path === `/bim/threejs/${RELEASE_PROJECT_ID}`) {
    return json(route, {
      project_id: RELEASE_PROJECT_ID,
      format: "threejs_buffergeometry",
      total_elements: 12,
      geometries: [
        { id: "g1", type: "IfcWall" },
        { id: "g2", type: "IfcWall" },
        { id: "g3", type: "IfcSlab" },
      ],
    });
  }

  if (
    method === "GET" &&
    path === `/contracts/${RELEASE_PROJECT_ID}/latest` &&
    url.searchParams.get("contract_type") === "construction"
  ) {
    return json(route, latestContract(state));
  }

  if (method === "POST" && path === "/contracts/generate") {
    return json(route, latestContract(state));
  }

  if (method === "POST" && path === "/contracts/draft-release-001/esign") {
    state.contractSignStatus = "requested";
    state.esignRequestId = "esign-release-001";
    return json(route, latestContract(state));
  }

  if (method === "POST" && path === "/maintenance/detect-anomaly") {
    return json(route, {
      alert_id: "maintenance-release-001",
      project_id: RELEASE_PROJECT_ID,
      anomaly_score: 0.87,
      remaining_useful_life_days: 24,
      hvac_efficiency_score: 78.4,
      severity: "warning",
      recommendation: "Schedule HVAC inspection within 48 hours.",
      work_order_id: "WO-20260326-001",
    });
  }

  if (method === "POST" && path === "/tenant/feedback/analyze") {
    return json(route, {
      ticket_id: "tenant-feedback-001",
      project_id: RELEASE_PROJECT_ID,
      sentiment_score: 0.68,
      sentiment_label: "positive",
      ai_reply: "A same-day maintenance follow-up has been scheduled for the tenant.",
      created_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "POST" && path === "/tenant/satisfaction/nps") {
    return json(route, {
      financial_health_id: "tenant-health-001",
      project_id: RELEASE_PROJECT_ID,
      nps: 41.2,
      churn_risk_score: 0.18,
      health_grade: "B",
      created_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "POST" && path === "/digital-twin/asset-intelligence") {
    return json(route, {
      snapshot_id: "asset-release-001",
      project_id: RELEASE_PROJECT_ID,
      composite_score: 84.2,
      grade: "B",
      adjusted_value_krw: 20150000000,
      component_scores: {
        maintenance: 78.1,
        tenant: 81.2,
        market: 88.5,
        climate: 79.0,
      },
      capex_recommendations: [
        {
          strategy_name: "HVAC reliability retrofit",
          expected_roi: 0.16,
          payback_months: 24,
        },
      ],
      created_at: "2026-03-26T00:00:00Z",
    });
  }

  if (method === "GET" && path === "/digital-twin/anomalies") {
    return json(route, digitalTwinAnomalies());
  }

  if (method === "GET" && path === `/digital-twin/status/${RELEASE_PROJECT_ID}/latest`) {
    return state.digitalTwinStatus
      ? json(route, state.digitalTwinStatus)
      : notFound(route, "No digital twin status");
  }

  if (method === "POST" && path === "/digital-twin/status/snapshot") {
    state.digitalTwinStatus = {
      status: "watch",
      operational_readiness_score: 74.5,
      eui_grade: "B",
      eui: 157.2,
      sensor_health_ratio: 0.92,
      highest_anomaly_severity: "warning",
    };
    return json(route, state.digitalTwinStatus);
  }

  if (method === "GET" && path === `/risk/unified/${RELEASE_PROJECT_ID}/latest`) {
    return state.riskSnapshot
      ? json(route, state.riskSnapshot)
      : notFound(route, "No unified risk");
  }

  if (method === "POST" && path === "/risk/unified/analyze") {
    state.riskSnapshot = {
      composite_risk_score: 48.6,
      grade: "C",
      var_95_ratio: 0.091,
      p90_adjusted_cost_krw: 20230000000,
      summary: "Unified risk grade C with manageable downside.",
    };
    return json(route, state.riskSnapshot);
  }

  if (method === "GET" && path === `/permits/${RELEASE_PROJECT_ID}/latest`) {
    return state.permitSnapshot
      ? json(route, state.permitSnapshot)
      : notFound(route, "No permit snapshot");
  }

  if (method === "POST" && path === "/permits/submit") {
    state.permitSnapshot = {
      status: "submitted",
      current_stage: "submitted",
      readiness_score: 100,
      progress_pct: 40,
      submission_reference: "SEUMTER-20260326-REL01-ABC123",
      missing_required_documents: [],
    };
    return json(route, state.permitSnapshot);
  }

  if (method === "GET" && path === "/agents/domain/history") {
    return json(route, { items: buildHistory(state) });
  }

  if (method === "GET" && path === "/agents/domain/approvals") {
    const status = url.searchParams.get("status") ?? "pending";

    if (status === "pending") {
      return json(route, { items: state.pendingApprovals });
    }

    if (status === "all") {
      return json(route, {
        items:
          state.pendingApprovals.length > 0
            ? state.pendingApprovals
            : [
                {
                  approval_id: "approval-release-001",
                  task_id: "task-release-001",
                  project_id: RELEASE_PROJECT_ID,
                  domain: "finance",
                  approver_role: "investment-committee",
                  status: "approved",
                  rationale: "Approved after approval center review.",
                  recommendation: "proceed-with-conditions",
                  confidence_score: 0.74,
                  created_at: "2026-03-26T00:00:00Z",
                  decided_at: "2026-03-26T00:15:00Z",
                },
              ],
      });
    }

    return json(route, { items: [] });
  }

  if (method === "POST" && path === "/agents/domain/approvals/decision-batch") {
    state.pendingApprovals = [];
    return json(route, {
      items: [],
      updated_count: 2,
    });
  }

  if (method === "GET" && path === "/kdx/overview") {
    return json(route, {
      connection_status: "connected",
      throughput_tps: 182,
      data_sync_latency_ms: 240,
      latest_metric: {
        region_code: "11",
        metric_type: "price_index",
        value: 512340000,
        currency: "KRW",
        recorded_at: "2026-03-26T00:00:00Z",
      },
      recent_logs: [
        {
          id: "kdx-log-001",
          source: "kdx-ingestor",
          event_type: "sync",
          status: "success",
          created_at: "2026-03-26T00:00:00Z",
        },
      ],
    });
  }

  return notFound(route, `Unhandled ${method} ${path}`);
}

export async function installReleaseHarness(
  page: Page,
  options: { withSession?: boolean } = {},
) {
  const withSession = options.withSession ?? true;

  await page.addInitScript(
    ({ shouldSeedSession, accessToken, refreshToken }) => {
      localStorage.removeItem("propai_access_token");
      localStorage.removeItem("propai_refresh_token");

      if (shouldSeedSession) {
        localStorage.setItem("propai_access_token", accessToken);
        localStorage.setItem("propai_refresh_token", refreshToken);
      }

      class MockWebSocket {
        static CONNECTING = 0;
        static OPEN = 1;
        static CLOSING = 2;
        static CLOSED = 3;

        url: string;
        readyState = MockWebSocket.OPEN;
        onopen: ((event: Event) => void) | null = null;
        onmessage: ((event: MessageEvent) => void) | null = null;
        onerror: ((event: Event) => void) | null = null;
        onclose: ((event: CloseEvent) => void) | null = null;

        constructor(url: string) {
          this.url = url;
          setTimeout(() => {
            this.onopen?.(new Event("open"));
          }, 0);
          setTimeout(() => {
            this.onmessage?.(
              new MessageEvent("message", {
                data: JSON.stringify({
                  event_type: "market_tick",
                  timestamp: 1711411200,
                  seoul_index: 102.4,
                  transaction_volume: 18,
                }),
              }),
            );
          }, 25);
        }

        addEventListener(type: string, listener: EventListener) {
          if (type === "open") {
            this.onopen = listener as (event: Event) => void;
          }
          if (type === "message") {
            this.onmessage = listener as (event: MessageEvent) => void;
          }
          if (type === "error") {
            this.onerror = listener as (event: Event) => void;
          }
          if (type === "close") {
            this.onclose = listener as (event: CloseEvent) => void;
          }
        }

        removeEventListener() {}

        send() {}

        close() {
          this.readyState = MockWebSocket.CLOSED;
          this.onclose?.(new CloseEvent("close"));
        }
      }

      window.WebSocket = MockWebSocket as unknown as typeof WebSocket;
    },
    {
      shouldSeedSession: withSession,
      accessToken: ACCESS_TOKEN,
      refreshToken: REFRESH_TOKEN,
    },
  );

  const state = createState();
  await page.route("**/api/latest/**", async (route) => {
    await handleApiRoute(route, state);
  });
}
