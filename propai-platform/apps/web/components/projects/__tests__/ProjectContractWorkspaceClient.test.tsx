import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ApiClientError,
  apiClient,
} from "@/lib/api-client";
import { ProjectContractWorkspaceClient } from "@/components/projects/ProjectContractWorkspaceClient";
import { renderWithQueryClient } from "@/test/render-with-query-client";

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

describe("ProjectContractWorkspaceClient", () => {
  it("renders the latest draft and hands it off to e-sign", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path) => {
      if (path === "/projects/project-contract-001") {
        return {
          id: "project-contract-001",
          name: "Mapo Contract Tower",
          status: "pre_construction",
          address: "Seoul Mapo-gu",
          total_area_sqm: 9800,
          created_at: "2026-03-24T00:00:00Z",
          updated_at: "2026-03-25T01:00:00Z",
        };
      }

      if (
        path === "/contracts/project-contract-001/latest?contract_type=construction"
      ) {
        return {
          draft_id: "draft-contract-001",
          project_id: "project-contract-001",
          project_name: "Mapo Contract Tower",
          contract_type: "construction",
          target_language: "en",
          title: "Mapo Contract Tower Construction agreement",
          counterparty_name: "Hanbit Contractors",
          effective_date: "2026-04-01T00:00:00Z",
          contract_amount_krw: 4800000000,
          document_url: "https://propai.local/contracts/draft-contract-001",
          status: "draft",
          sign_status: "not_requested",
          key_terms: [
            { label: "Counterparty", value: "Hanbit Contractors" },
          ],
          clauses: [
            { title: "Purpose", body: "Define scope and obligations." },
          ],
          summary: "Construction draft summary",
          rendered_markdown: "# Contract",
          esign_request_id: null,
          created_at: "2026-03-25T01:00:00Z",
        };
      }

      throw new Error(`Unexpected GET ${path}`);
    });

    vi.mocked(apiClient.post).mockImplementation(async (path) => {
      if (path === "/contracts/draft-contract-001/esign") {
        return {
          draft_id: "draft-contract-001",
          project_id: "project-contract-001",
          project_name: "Mapo Contract Tower",
          contract_type: "construction",
          target_language: "en",
          title: "Mapo Contract Tower Construction agreement",
          counterparty_name: "Hanbit Contractors",
          effective_date: "2026-04-01T00:00:00Z",
          contract_amount_krw: 4800000000,
          document_url: "https://propai.local/contracts/draft-contract-001",
          status: "esign_requested",
          sign_status: "requested",
          key_terms: [
            { label: "Counterparty", value: "Hanbit Contractors" },
          ],
          clauses: [
            { title: "Purpose", body: "Define scope and obligations." },
          ],
          summary: "Construction draft summary",
          rendered_markdown: "# Contract",
          esign_request_id: "esign-001",
          created_at: "2026-03-25T01:00:00Z",
        };
      }

      throw new Error(`Unexpected POST ${path}`);
    });

    renderWithQueryClient(
      <ProjectContractWorkspaceClient
        locale="en"
        projectId="project-contract-001"
      />,
    );

    expect(await screen.findByText("Mapo Contract Tower")).toBeInTheDocument();
    expect(
      await screen.findByText("Mapo Contract Tower Construction agreement"),
    ).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText("Signer email"),
      "signer@propai.dev",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Send e-sign request" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/contracts/draft-contract-001/esign",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText(/Sign status: requested/)).toBeInTheDocument();
  });

  it("generates a contract draft when no latest draft exists yet", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path) => {
      if (path === "/projects/project-contract-002") {
        return {
          id: "project-contract-002",
          name: "Bundang Office Campus",
          status: "design",
          address: "Seongnam Bundang-gu",
          total_area_sqm: 12400,
          created_at: "2026-03-24T00:00:00Z",
          updated_at: "2026-03-25T01:00:00Z",
        };
      }

      if (
        path === "/contracts/project-contract-002/latest?contract_type=construction"
      ) {
        throw new ApiClientError("Not found", 404, null);
      }

      throw new Error(`Unexpected GET ${path}`);
    });

    vi.mocked(apiClient.post).mockResolvedValue({
      draft_id: "draft-contract-002",
      project_id: "project-contract-002",
      project_name: "Bundang Office Campus",
      contract_type: "construction",
      target_language: "zh-CN",
      title: "Bundang Office Campus 施工合同",
      counterparty_name: "Bundang Office Campus Counterparty",
      effective_date: "2026-04-01T00:00:00Z",
      contract_amount_krw: 4800000000,
      document_url: "https://propai.local/contracts/draft-contract-002",
      status: "draft",
      sign_status: "not_requested",
      key_terms: [{ label: "合同类型", value: "施工合同" }],
      clauses: [{ title: "合同目的", body: "定义项目范围。" }],
      summary: "该施工合同草案面向 Bundang Office Campus 项目。",
      rendered_markdown: "# 合同",
      esign_request_id: null,
      created_at: "2026-03-25T01:00:00Z",
    });

    renderWithQueryClient(
      <ProjectContractWorkspaceClient
        locale="zh-CN"
        projectId="project-contract-002"
      />,
    );

    expect(await screen.findByText("Bundang Office Campus")).toBeInTheDocument();
    expect(
      await screen.findByText("尚未生成合同草案。请选择合同类型和语言，为当前项目生成首份草案。"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "生成合同草案" }),
    );

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/contracts/generate",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("Bundang Office Campus 施工合同")).toBeInTheDocument();
    expect(await screen.findByText("合同目的")).toBeInTheDocument();
  });

  it("renders a retryable draft query error and recovers", async () => {
    let shouldFailDraft = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path) => {
      if (path === "/projects/project-contract-003") {
        return {
          id: "project-contract-003",
          name: "Yeouido Office Tower",
          status: "planning",
          address: "Seoul Yeongdeungpo-gu",
          total_area_sqm: 15000,
          created_at: "2026-03-24T00:00:00Z",
          updated_at: "2026-03-25T01:00:00Z",
        };
      }

      if (
        path === "/contracts/project-contract-003/latest?contract_type=construction"
      ) {
        if (shouldFailDraft) {
          throw new Error("Contract draft fetch failed");
        }

        return null;
      }

      throw new Error(`Unexpected GET ${path}`);
    });

    renderWithQueryClient(
      <ProjectContractWorkspaceClient
        locale="en"
        projectId="project-contract-003"
      />,
    );

    expect(await screen.findByText("Contract draft unavailable")).toBeInTheDocument();
    expect(await screen.findByText("Contract draft fetch failed")).toBeInTheDocument();

    shouldFailDraft = false;

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText(
        "No contract draft has been generated yet. Pick a contract type and language to create the first draft for this project.",
      ),
    ).toBeInTheDocument();
  });
});
