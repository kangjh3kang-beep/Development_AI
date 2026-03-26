import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentOrchestrationWorkspaceClient } from "@/components/agent/AgentOrchestrationWorkspaceClient";
import { apiClient } from "@/lib/api-client";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import { useProjectStore } from "@/store/use-project-store";

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;

    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiClient: {
    getRuntimeConfig: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe("AgentOrchestrationWorkspaceClient", () => {
  beforeEach(() => {
    act(() => {
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    act(() => {
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
  });

  it("runs focused and orchestration analyses against the live domain agents api", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-001",
              name: "Mapo Prime Asset",
              status: "planning",
              address: "Seoul Mapo-gu",
              total_area_sqm: 2450,
              updated_at: "2026-03-22T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-001&limit=6") {
        return {
          items: [
            {
              task_id: "task-history-001",
              project_id: "project-001",
              domain: "finance",
              status: "completed",
              confidence_score: 0.71,
              recommendation: "proceed-with-conditions",
              findings: [{ factor: "ltv", impact: "negative" }],
              approval_required: true,
              approval_status: "pending",
              approver_role: "investment-committee",
              narrative:
                "Capital structure analysis completed with confidence 71%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?project_id=project-001&limit=6") {
        return {
          items: [
            {
              approval_id: "approval-001",
              task_id: "task-history-001",
              project_id: "project-001",
              domain: "finance",
              approver_role: "investment-committee",
              status: "pending",
              rationale:
                "Capital structure analysis requires human review before release.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.71,
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/agents/domain/run") {
        return {
          task_id: "task-focused-001",
          project_id: "project-001",
          domain: "asset",
          status: "completed",
          confidence_score: 0.74,
          recommendation: "proceed-with-conditions",
          findings: [
            {
              factor: "ltv",
              impact: "negative",
            },
          ],
          approval_required: true,
          approval_status: "pending",
        };
      }

      if (path === "/agents/domain/multi-analysis") {
        return {
          portfolio_summary:
            "4 domain analyses completed. 2 recommend proceed and 2 require conditions or escalation.",
          items: [
            {
              task_id: "task-asset-001",
              project_id: "project-001",
              domain: "asset",
              status: "completed",
              confidence_score: 0.82,
              recommendation: "proceed",
              findings: [],
              approval_required: false,
              approval_status: "not-required",
            },
            {
              task_id: "task-development-001",
              project_id: "project-001",
              domain: "development",
              status: "completed",
              confidence_score: 0.69,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: "pending",
            },
          ],
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Domain agent orchestration workspace"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Mapo Prime Asset")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Run focused analysis" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/run",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            project_id: "project-001",
            domain: "asset",
          }),
        }),
      );
    });

    expect(
      await screen.findAllByText(/Recommendation:\s*Proceed with conditions/i),
    ).not.toHaveLength(0);
    expect(await screen.findAllByText(/Approval:\s*Pending/i)).not.toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: "Run orchestration" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/multi-analysis",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            project_id: "project-001",
            domains: ["asset", "development", "transaction", "finance"],
          }),
        }),
      );
    });

    expect(
      await screen.findByText(/4 domain analyses completed\./i),
    ).toBeInTheDocument();
    expect(await screen.findAllByText("Development execution")).not.toHaveLength(0);
    expect(await screen.findByText("Execution history")).toBeInTheDocument();
    expect(
      await screen.findByText(/Capital structure analysis completed/i),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Approver role: investment-committee/i)).toBeInTheDocument();
    expect(useProjectStore.getState().currentProjectId).toBe("project-001");
  });

  it("shows an auth error before execution when no live runtime is available", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: true,
      hasAccessToken: false,
      mode: "mock",
    });
    vi.mocked(apiClient.get).mockResolvedValue({
      items: [],
      page: 1,
      page_size: 20,
      has_next: false,
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    await userEvent.click(
      screen.getByRole("button", { name: "Run focused analysis" }),
    );

    expect(await screen.findAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
      "API authentication is required for live workspace calls.",
    );
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("renders the project query error state and retries the live picker", async () => {
    let shouldFailProjects = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path !== "/projects?page=1&page_size=20") {
        throw new Error(`Unhandled GET path: ${path}`);
      }

      if (shouldFailProjects) {
        throw new Error("Agent project picker unavailable");
      }

      return {
        items: [
          {
            id: "project-002",
            name: "Recovered Agent Asset",
            status: "planning",
            address: "Busan Haeundae-gu",
            total_area_sqm: 3150,
            updated_at: "2026-03-23T00:00:00Z",
          },
        ],
        page: 1,
        page_size: 20,
        has_next: false,
      };
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("The project list could not be loaded."),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        "The live project picker failed to load. Manual UUID input remains available.",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Agent project picker unavailable"),
    ).toBeInTheDocument();

    shouldFailProjects = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered Agent Asset")).toBeInTheDocument();
  });

  it("renders history and approval query errors and retries both read models", async () => {
    let shouldFailHistory = true;
    let shouldFailApprovals = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-003",
              name: "History Retry Asset",
              status: "planning",
              address: "Seoul Gangnam-gu",
              total_area_sqm: 5100,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-003&limit=6") {
        if (shouldFailHistory) {
          throw new Error("Agent history unavailable");
        }

        return {
          items: [
            {
              task_id: "task-history-003",
              project_id: "project-003",
              domain: "asset",
              status: "completed",
              confidence_score: 0.81,
              recommendation: "proceed",
              findings: [],
              approval_required: false,
              approval_status: "not-required",
              approver_role: null,
              narrative:
                "Asset management analysis completed with confidence 81%. Recommendation: proceed.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?project_id=project-003&limit=6") {
        if (shouldFailApprovals) {
          throw new Error("Agent approvals unavailable");
        }

        return {
          items: [
            {
              approval_id: "approval-003",
              task_id: "task-history-004",
              project_id: "project-003",
              domain: "development",
              approver_role: "risk-committee",
              status: "pending",
              rationale:
                "Development execution analysis requires human review before release.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.69,
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    expect(
      await screen.findByText("Execution history unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Agent history unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Approval queue unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Agent approvals unavailable")).toBeInTheDocument();

    shouldFailHistory = false;
    shouldFailApprovals = false;

    const retryButtons = screen.getAllByRole("button", { name: "Retry" });
    await userEvent.click(retryButtons[0]);
    await userEvent.click(retryButtons[1]);

    expect(
      await screen.findByText(/Asset management analysis completed with confidence 81%/i),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Approver role: risk-committee/i)).toBeInTheDocument();
  });

  it("approves a pending queue item and refreshes both approval queue and history", async () => {
    let approvalDecided = false;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-004",
              name: "Approval Action Asset",
              status: "planning",
              address: "Seoul Seocho-gu",
              total_area_sqm: 6200,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-004&limit=6") {
        return {
          items: [
            {
              task_id: "task-history-004",
              project_id: "project-004",
              domain: "development",
              status: "completed",
              confidence_score: 0.69,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: approvalDecided ? "approved" : "pending",
              approver_role: "risk-committee",
              narrative:
                "Development execution analysis completed with confidence 69%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?project_id=project-004&limit=6") {
        return {
          items: approvalDecided
            ? []
            : [
                {
                  approval_id: "approval-004",
                  task_id: "task-history-004",
                  project_id: "project-004",
                  domain: "development",
                  approver_role: "risk-committee",
                  status: "pending",
                  rationale:
                    "Development execution analysis requires human review before release.",
                  recommendation: "proceed-with-conditions",
                  confidence_score: 0.69,
                  created_at: "2026-03-23T00:00:00Z",
                },
              ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/agents/domain/approvals/approval-004/decision") {
        approvalDecided = true;
        return {
          approval_id: "approval-004",
          task_id: "task-history-004",
          project_id: "project-004",
          domain: "development",
          approver_role: "risk-committee",
          status: "approved",
          rationale: "Approved in agent workspace.",
          recommendation: "proceed-with-conditions",
          confidence_score: 0.69,
          created_at: "2026-03-23T00:00:00Z",
          decided_at: "2026-03-23T01:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    expect(await screen.findByText("Approval queue")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/approvals/approval-004/decision",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            decision: "approved",
          }),
        }),
      );
    });

    expect(
      await screen.findByText("No persisted approvals are queued for the active project."),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Approval:\s*Approved/i)).toBeInTheDocument();
  });

  it("sends a custom decision note when rejecting a pending queue item", async () => {
    let approvalDecided = false;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-005",
              name: "Decision Note Asset",
              status: "planning",
              address: "Incheon Yeonsu-gu",
              total_area_sqm: 4100,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-005&limit=6") {
        return {
          items: [
            {
              task_id: "task-history-005",
              project_id: "project-005",
              domain: "transaction",
              status: "completed",
              confidence_score: 0.58,
              recommendation: "escalate",
              findings: [],
              approval_required: true,
              approval_status: approvalDecided ? "rejected" : "pending",
              approver_role: "manager",
              narrative:
                "Transaction strategy analysis completed with confidence 58%. Recommendation: escalate.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?project_id=project-005&limit=6") {
        return {
          items: approvalDecided
            ? []
            : [
                {
                  approval_id: "approval-005",
                  task_id: "task-history-005",
                  project_id: "project-005",
                  domain: "transaction",
                  approver_role: "manager",
                  status: "pending",
                  rationale:
                    "Transaction strategy analysis requires human review before release.",
                  recommendation: "escalate",
                  confidence_score: 0.58,
                  created_at: "2026-03-23T00:00:00Z",
                },
              ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/agents/domain/approvals/approval-005/decision") {
        approvalDecided = true;
        return {
          approval_id: "approval-005",
          task_id: "task-history-005",
          project_id: "project-005",
          domain: "transaction",
          approver_role: "manager",
          status: "rejected",
          rationale: "Rejected pending lease rollover evidence.",
          recommendation: "escalate",
          confidence_score: 0.58,
          created_at: "2026-03-23T00:00:00Z",
          decided_at: "2026-03-23T02:00:00Z",
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    const noteInput = await screen.findByLabelText("Decision note (optional)");
    await userEvent.type(noteInput, "Rejected pending lease rollover evidence.");
    await userEvent.click(await screen.findByRole("button", { name: "Reject" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/approvals/approval-005/decision",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            decision: "rejected",
            rationale: "Rejected pending lease rollover evidence.",
          }),
        }),
      );
    });

    expect(
      await screen.findByText("No persisted approvals are queued for the active project."),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Approval:\s*Rejected/i)).toBeInTheDocument();
  });

  it("bulk-approves all pending queue items for the active project", async () => {
    let approvalsDecided = false;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-006",
              name: "Bulk Approval Asset",
              status: "planning",
              address: "Seoul Yongsan-gu",
              total_area_sqm: 7800,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-006&limit=6") {
        return {
          items: [
            {
              task_id: "task-history-006a",
              project_id: "project-006",
              domain: "asset",
              status: "completed",
              confidence_score: 0.74,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: approvalsDecided ? "approved" : "pending",
              approver_role: "manager",
              narrative:
                "Asset management analysis completed with confidence 74%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-23T00:00:00Z",
            },
            {
              task_id: "task-history-006b",
              project_id: "project-006",
              domain: "finance",
              status: "completed",
              confidence_score: 0.66,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: approvalsDecided ? "approved" : "pending",
              approver_role: "investment-committee",
              narrative:
                "Capital structure analysis completed with confidence 66%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?project_id=project-006&limit=6") {
        return {
          items: approvalsDecided
            ? []
            : [
                {
                  approval_id: "approval-006a",
                  task_id: "task-history-006a",
                  project_id: "project-006",
                  domain: "asset",
                  approver_role: "manager",
                  status: "pending",
                  rationale:
                    "Asset management analysis requires human review before release.",
                  recommendation: "proceed-with-conditions",
                  confidence_score: 0.74,
                  created_at: "2026-03-23T00:00:00Z",
                },
                {
                  approval_id: "approval-006b",
                  task_id: "task-history-006b",
                  project_id: "project-006",
                  domain: "finance",
                  approver_role: "investment-committee",
                  status: "pending",
                  rationale:
                    "Capital structure analysis requires human review before release.",
                  recommendation: "proceed-with-conditions",
                  confidence_score: 0.66,
                  created_at: "2026-03-23T00:00:00Z",
                },
              ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path: string) => {
      if (path === "/agents/domain/approvals/decision-batch") {
        approvalsDecided = true;
        return {
          items: [
            {
              approval_id: "approval-006a",
              task_id: "task-history-006a",
              project_id: "project-006",
              domain: "asset",
              approver_role: "manager",
              status: "approved",
              rationale: "Approved the full pending queue after portfolio review.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.74,
              created_at: "2026-03-23T00:00:00Z",
              decided_at: "2026-03-23T03:00:00Z",
            },
            {
              approval_id: "approval-006b",
              task_id: "task-history-006b",
              project_id: "project-006",
              domain: "finance",
              approver_role: "investment-committee",
              status: "approved",
              rationale: "Approved the full pending queue after portfolio review.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.66,
              created_at: "2026-03-23T00:00:00Z",
              decided_at: "2026-03-23T03:00:00Z",
            },
          ],
          updated_count: 2,
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    const bulkNoteInput = await screen.findByLabelText("Bulk decision note (optional)");
    await userEvent.type(
      bulkNoteInput,
      "Approved the full pending queue after portfolio review.",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Approve all pending" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/approvals/decision-batch",
        expect.objectContaining({
          useMock: false,
          body: expect.objectContaining({
            project_id: "project-006",
            approval_ids: ["approval-006a", "approval-006b"],
            decision: "approved",
            rationale: "Approved the full pending queue after portfolio review.",
          }),
        }),
      );
    });

    expect(
      await screen.findByText("No persisted approvals are queued for the active project."),
    ).toBeInTheDocument();
    expect(await screen.findAllByText(/Approval:\s*Approved/i)).not.toHaveLength(0);
  });

  it("switches to the tenant-wide audit view and renders resolved approvals", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-007",
              name: "Audit Filter Asset",
              status: "planning",
              address: "Daegu Suseong-gu",
              total_area_sqm: 5200,
              updated_at: "2026-03-23T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?project_id=project-007&limit=6") {
        return { items: [] };
      }

      if (path === "/agents/domain/approvals?project_id=project-007&limit=6") {
        return { items: [] };
      }

      if (path === "/agents/domain/history?limit=6") {
        return {
          items: [
            {
              task_id: "task-history-007",
              project_id: "project-tenant-008",
              domain: "finance",
              status: "completed",
              confidence_score: 0.72,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: "approved",
              approver_role: "investment-committee",
              narrative:
                "Capital structure analysis completed with confidence 72%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-23T00:00:00Z",
            },
          ],
        };
      }

      if (path === "/agents/domain/approvals?limit=6") {
        return { items: [] };
      }

      if (path === "/agents/domain/approvals?limit=6&status=all") {
        return {
          items: [
            {
              approval_id: "approval-007a",
              task_id: "task-history-007",
              project_id: "project-tenant-008",
              domain: "finance",
              approver_role: "investment-committee",
              status: "approved",
              rationale: "Approved after tenant-wide audit review.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.72,
              created_at: "2026-03-23T00:00:00Z",
              decided_at: "2026-03-23T04:00:00Z",
            },
            {
              approval_id: "approval-007b",
              task_id: "task-history-007b",
              project_id: "project-tenant-009",
              domain: "development",
              approver_role: "risk-committee",
              status: "rejected",
              rationale: "Rejected after tenant-wide audit review.",
              recommendation: "escalate",
              confidence_score: 0.51,
              created_at: "2026-03-23T00:00:00Z",
              decided_at: "2026-03-23T05:00:00Z",
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<AgentOrchestrationWorkspaceClient locale="en" />);

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Scope" }),
      "tenant",
    );

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Approval status" }),
      "all",
    );

    expect(
      await screen.findAllByText("Project ID: project-tenant-008"),
    ).not.toHaveLength(0);
    expect(await screen.findByText("Project ID: project-tenant-009")).toBeInTheDocument();
    expect(await screen.findAllByText(/Decided:/i)).not.toHaveLength(0);
    expect(await screen.findAllByText(/Approval:\s*Approved/i)).not.toHaveLength(0);
  });
});
