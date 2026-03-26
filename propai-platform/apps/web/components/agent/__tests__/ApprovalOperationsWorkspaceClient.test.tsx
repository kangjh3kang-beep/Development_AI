import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalOperationsWorkspaceClient } from "@/components/agent/ApprovalOperationsWorkspaceClient";
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

describe("ApprovalOperationsWorkspaceClient", () => {
  beforeEach(() => {
    act(() => {
      useProjectStore.setState({
        currentProjectId: null,
        recentProjectIds: [],
        activeModule: null,
      });
    });
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
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

  it("runs project-scoped bulk approval actions and refreshes both audit lists", async () => {
    let approvalsDecided = false;

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-approval-001",
              name: "Approval Ops Asset",
              status: "planning",
              address: "Seoul",
              total_area_sqm: 4400,
              updated_at: "2026-03-26T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?limit=12&project_id=project-approval-001") {
        return {
          items: [
            {
              task_id: "task-approval-001",
              project_id: "project-approval-001",
              domain: "finance",
              status: "completed",
              confidence_score: 0.7,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: approvalsDecided ? "approved" : "pending",
              approver_role: "investment-committee",
              narrative:
                "Capital structure analysis completed with confidence 70%. Recommendation: proceed-with-conditions.",
              created_at: "2026-03-26T00:00:00Z",
            },
          ],
        };
      }

      if (
        path ===
        "/agents/domain/approvals?limit=12&status=pending&project_id=project-approval-001"
      ) {
        return {
          items: approvalsDecided
            ? []
            : [
                {
                  approval_id: "approval-001",
                  task_id: "task-approval-001",
                  project_id: "project-approval-001",
                  domain: "finance",
                  approver_role: "investment-committee",
                  status: "pending",
                  rationale: "Finance review pending committee approval.",
                  recommendation: "proceed-with-conditions",
                  confidence_score: 0.7,
                  created_at: "2026-03-26T00:00:00Z",
                },
                {
                  approval_id: "approval-002",
                  task_id: "task-approval-002",
                  project_id: "project-approval-001",
                  domain: "development",
                  approver_role: "risk-committee",
                  status: "pending",
                  rationale: "Development review pending risk committee approval.",
                  recommendation: "escalate",
                  confidence_score: 0.55,
                  created_at: "2026-03-26T00:00:00Z",
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
          items: [],
          updated_count: 2,
        };
      }

      throw new Error(`Unhandled POST path: ${path}`);
    });

    renderWithQueryClient(<ApprovalOperationsWorkspaceClient locale="en" />);

    expect(await screen.findByText("Approval Ops Asset")).toBeInTheDocument();

    await userEvent.type(
      await screen.findByLabelText("Bulk decision note (optional)"),
      "Approved after approval center review.",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Approve all pending" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/agents/domain/approvals/decision-batch",
        expect.objectContaining({
          useMock: false,
          body: {
            project_id: "project-approval-001",
            approval_ids: ["approval-001", "approval-002"],
            decision: "approved",
            rationale: "Approved after approval center review.",
          },
        }),
      );
    });

    expect(
      await screen.findByText("No approval items match the current filters."),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/Capital structure analysis completed with confidence 70%/i),
    ).toBeInTheDocument();
  });

  it("switches to the tenant-wide audit view and filters by approver role", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects?page=1&page_size=20") {
        return {
          items: [
            {
              id: "project-approval-002",
              name: "Tenant Audit Asset",
              status: "planning",
              address: "Busan",
              total_area_sqm: 3200,
              updated_at: "2026-03-26T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          has_next: false,
        };
      }

      if (path === "/agents/domain/history?limit=12&project_id=project-approval-002") {
        return { items: [] };
      }

      if (
        path ===
        "/agents/domain/approvals?limit=12&status=pending&project_id=project-approval-002"
      ) {
        return { items: [] };
      }

      if (path === "/agents/domain/history?limit=12") {
        return {
          items: [
            {
              task_id: "task-tenant-001",
              project_id: "project-tenant-001",
              domain: "finance",
              status: "completed",
              confidence_score: 0.73,
              recommendation: "proceed-with-conditions",
              findings: [],
              approval_required: true,
              approval_status: "approved",
              approver_role: "risk-committee",
              narrative: "Tenant-wide finance history item.",
              created_at: "2026-03-26T00:00:00Z",
            },
          ],
        };
      }

      if (
        path ===
        "/agents/domain/approvals?limit=12&status=all&approver_role=risk-committee"
      ) {
        return {
          items: [
            {
              approval_id: "approval-tenant-001",
              task_id: "task-tenant-001",
              project_id: "project-tenant-001",
              domain: "finance",
              approver_role: "risk-committee",
              status: "approved",
              rationale: "Approved by risk committee.",
              recommendation: "proceed-with-conditions",
              confidence_score: 0.73,
              created_at: "2026-03-26T00:00:00Z",
              decided_at: "2026-03-26T01:00:00Z",
            },
          ],
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(<ApprovalOperationsWorkspaceClient locale="en" />);

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Scope" }),
      "tenant",
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Approval status" }),
      "all",
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Approver role" }),
      "risk-committee",
    );

    expect(await screen.findByText(/Approved by risk committee\./i)).toBeInTheDocument();
    expect(
      await screen.findAllByText(/Project ID: project-tenant-001/i),
    ).not.toHaveLength(0);
    expect(await screen.findByText(/Decided:/i)).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith(
      "/agents/domain/approvals?limit=12&status=all&approver_role=risk-committee",
      expect.objectContaining({ useMock: false }),
    );
  });
});
