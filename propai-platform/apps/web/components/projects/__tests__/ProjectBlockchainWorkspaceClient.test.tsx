import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectBlockchainWorkspaceClient } from "@/components/projects/ProjectBlockchainWorkspaceClient";
import { apiClient } from "@/lib/api-client";
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

describe("ProjectBlockchainWorkspaceClient", () => {
  it("creates and queries live escrow state for the routed project", async () => {
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects/project-chain-001") {
        return {
          id: "project-chain-001",
          name: "Jamsil Escrow Tower",
          status: "permit",
          address: "Seoul Songpa-gu",
          total_area_sqm: 7100,
          created_at: "2026-03-22T00:00:00Z",
          updated_at: "2026-03-22T01:00:00Z",
        };
      }

      if (path === "/blockchain/escrow/next-id") {
        return {
          next_escrow_id: 41,
        };
      }

      if (path === "/blockchain/escrow/41") {
        return {
          on_chain_escrow_id: 41,
          payer: "0x1111111111111111111111111111111111111111",
          payee: "0x2222222222222222222222222222222222222222",
          subcontractor: "0x3333333333333333333333333333333333333333",
          total_amount_wei: "0",
          remaining_amount_wei: "0",
          expires_at: 1760000000,
          condition_hash: `0x${"ab".repeat(32)}`,
          status: "PendingFunding",
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    vi.mocked(apiClient.post).mockResolvedValue({
      id: "escrow-db-001",
      project_id: "project-chain-001",
      status: "pending_funding",
      amount_wei: "0",
      on_chain_escrow_id: 41,
      tx_hash: "0xdeadbeef",
      contract_address: "0xcontract",
      buyer_address: "0x1111111111111111111111111111111111111111",
      seller_address: "0x2222222222222222222222222222222222222222",
      created_at: "2026-03-22T02:00:00Z",
    });

    renderWithQueryClient(
      <ProjectBlockchainWorkspaceClient
        locale="en"
        projectId="project-chain-001"
      />,
    );

    expect(await screen.findByText("Jamsil Escrow Tower")).toBeInTheDocument();
    expect(await screen.findByText("41")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create escrow" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/blockchain/escrow",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("pending_funding")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Load escrow status" }),
    );

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        "/blockchain/escrow/41",
        expect.objectContaining({
          useMock: false,
        }),
      );
    });

    expect(await screen.findByText("PendingFunding")).toBeInTheDocument();
  });

  it("renders retryable project and next-id query errors and recovers both", async () => {
    let shouldFailProject = true;
    let shouldFailNextId = true;

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
      if (path === "/projects/project-chain-retry-001") {
        if (shouldFailProject) {
          throw new Error("Blockchain project metadata unavailable");
        }

        return {
          id: "project-chain-retry-001",
          name: "Recovered Escrow Tower",
          status: "permit",
          address: "Sejong",
          total_area_sqm: 6900,
          created_at: "2026-03-22T00:00:00Z",
          updated_at: "2026-03-22T01:00:00Z",
        };
      }

      if (path === "/blockchain/escrow/next-id") {
        if (shouldFailNextId) {
          throw new Error("Next escrow id feed unavailable");
        }

        return {
          next_escrow_id: 84,
        };
      }

      throw new Error(`Unhandled GET path: ${path}`);
    });

    renderWithQueryClient(
      <ProjectBlockchainWorkspaceClient
        locale="en"
        projectId="project-chain-retry-001"
      />,
    );

    expect(
      await screen.findByText("Project metadata unavailable"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Blockchain project metadata unavailable"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Next escrow id unavailable")).toBeInTheDocument();
    expect(
      await screen.findByText("Next escrow id feed unavailable"),
    ).toBeInTheDocument();

    shouldFailProject = false;
    shouldFailNextId = false;

    const retryButtons = await screen.findAllByRole("button", { name: "Retry" });
    await userEvent.click(retryButtons[0]);
    await userEvent.click(retryButtons[1]);

    expect(await screen.findByText("Recovered Escrow Tower")).toBeInTheDocument();
    expect(await screen.findByText("84")).toBeInTheDocument();
  });
});
