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
  /**
   * ★세션이 있는가 — `installReleaseHarness({ withSession })` 와 **의미가 맞아야** 한다.
   *   종전에는 `withSession` 이 localStorage 토큰 시드만 껐고 `/auth/me` 는 그대로
   *   200 + 사용자를 돌려줬다. 그래서 "세션 없음"을 요구한 스펙에서도 앱이 로그인 상태로
   *   판단해 `/en/login` 이 대시보드로 리다이렉트됐고, 로그인 화면 자체를 검사할 수 없었다.
   */
  hasSession: boolean;
};

function createState(withSession: boolean): MutableState {
  return {
    hasSession: withSession,
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
  // ★`/api/v1` 도 같은 핸들러가 답한다 — 앱의 주 클라이언트(`lib/api-client.ts`)가 그쪽으로 나간다.
  //   접두사만 다르고 자원 경로는 같으므로, 둘 다 벗겨 하나의 라우팅 표를 쓴다.
  const path = url.pathname.replace(/\/api\/(?:latest|v1)/, "") || "/";

  if (method === "POST" && (path === "/auth/login" || path === "/auth/register")) {
    state.hasSession = true; // 로그인 성공 = 이 시점부터 세션이 있다
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
    // 세션이 없으면 401 — 앱이 "미로그인"으로 판단해 로그인 화면을 그려야 한다.
    if (!state.hasSession) return json(route, { detail: "Not authenticated" }, 401);
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

  /**
   * ★쿼리 없는 `/projects` — **두 소비자가 서로 다른 키를 읽는다.**
   *
   *   종전에는 이 분기가 `{projects: […]}` 만 돌려줬다. 그런데 목록 화면의 실제 데이터원인
   *   `store/useProjectStore.ts:syncFromBackend()` 는 `apiClient.get("/projects")` 를
   *   **쿼리 없이** 부르고 `res.items` 를 읽는다 → `items` 가 없으니 `backend = []` 가 되고
   *   화면은 **"No projects yet"** 을 그렸다. 위 `page=1` 분기는 그 호출이 `page` 를 안 붙이므로
   *   **영원히 닿지 않는다.**
   *
   *   즉 픽스처를 보강해도 통과하지 않는 게 아니라, **픽스처가 앱이 읽지 않는 키에 담겨 있었다.**
   *   실측(2026-08-16): prod 빌드 로컬 재현에서 `/en/projects` DOM 이 "No projects yet".
   *
   *   → 한 응답에 **두 키를 함께** 담는다. 어느 소비자가 오든 같은 프로젝트를 본다.
   *     새 소비자가 또 다른 키를 읽으면 여기서 한 번만 늘리면 된다.
   */
  if (method === "GET" && path === "/projects") {
    return json(route, {
      items: [projectSummaryItem()],
      projects: [listProjectCard()],
      total: 1,
      page: 1,
      page_size: 20,
      has_next: false,
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

  const state = createState(withSession);
  await page.route("**/api/latest/**", async (route) => {
    await handleApiRoute(route, state);
  });

  // ★★`/api/v1/**` 도 가로챈다 — 이걸 빼면 스펙이 **환경에 의존**한다(2026-08-13 실측).
  //
  //   앱의 주 클라이언트(`lib/api-client.ts`)는 `/api/v1/**` 로 나간다. 해네스가 그걸 안 막으면:
  //     · 백엔드가 **없는** 로컬 → 네트워크 오류로 끝나 아무 일도 없다(초록)
  //     · 백엔드가 **있는** CI  → 시드한 가짜 토큰이 **401** 로 거부되고
  //       `lib/api-client.ts:426` 의 `handleSessionExpired()` 가 토큰을 지우고 **로그인으로
  //       리다이렉트**한다 → 페이지가 통째로 사라져 모든 `toBeVisible` 이 타임아웃(빨강)
  //   실제로 나이틀리 로그에 `navigated to /en/login?next=…` 가 찍혔고, 401 만 돌려주는 더미
  //   서버를 :8000 에 세워 로컬에서 **CI 와 동일한 10건 실패**를 재현해 확인했다.
  //
  //   이 스펙들은 인증 왕복을 검증하지 않는다 → 미지정 엔드포인트는 200 `{}` 로 답해
  //   **401 경로 자체가 생기지 않게** 한다. 데이터가 필요한 호출은 위 `/api/latest` 핸들러가 답한다.
  await page.route("**/api/v1/**", async (route) => {
    await handleApiRoute(route, state);
  });
}
