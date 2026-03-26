import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthWorkspaceClient } from "@/components/auth/AuthWorkspaceClient";
import { ApiClientError, apiClient } from "@/lib/api-client";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

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

describe("AuthWorkspaceClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
    pushMock.mockReset();
    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: false,
      mode: "live",
    });
  });

  it("logs in against the live auth api, stores tokens, and exposes the active session", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "access-token-001",
      refresh_token: "refresh-token-001",
      token_type: "bearer",
      expires_in: 3600,
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "user-001",
      tenant_id: "tenant-001",
      email: "operator@propai.ai",
      name: "Operations Lead",
      role: "admin",
      is_active: true,
      created_at: "2026-03-23T00:00:00Z",
    });

    render(<AuthWorkspaceClient locale="en" defaultMode="login" />);

    await userEvent.type(screen.getByLabelText("Email"), "operator@propai.ai");
    await userEvent.type(screen.getByLabelText("Password"), "test1234");
    await userEvent.click(screen.getByRole("button", { name: "Run login" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/login",
        expect.objectContaining({
          useMock: false,
          body: {
            email: "operator@propai.ai",
            password: "test1234",
          },
        }),
      );
    });

    await waitFor(() => {
      expect(window.localStorage.getItem("propai_access_token")).toBe(
        "access-token-001",
      );
    });

    expect(await screen.findByText("Operations Lead")).toBeInTheDocument();
    expect(screen.getByText("operator@propai.ai")).toBeInTheDocument();
    expect(screen.getByText("Fresh login")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Open dashboard" }));
    expect(pushMock).toHaveBeenCalledWith("/en");
  });

  it("registers a tenant admin and posts the expected payload to the auth api", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "access-token-002",
      refresh_token: "refresh-token-002",
      token_type: "bearer",
      expires_in: 1800,
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "user-002",
      tenant_id: "tenant-002",
      email: "admin@tenant.ai",
      name: "Tenant Owner",
      role: "admin",
      is_active: true,
      created_at: "2026-03-23T01:00:00Z",
    });

    render(<AuthWorkspaceClient locale="en" defaultMode="register" />);

    await userEvent.type(screen.getByLabelText("Operator name"), "Tenant Owner");
    await userEvent.type(screen.getByLabelText("Company name"), "Tenant AI");
    await userEvent.type(screen.getByLabelText("Admin email"), "admin@tenant.ai");
    await userEvent.type(screen.getByLabelText(/^Password$/), "strongpass1");
    await userEvent.click(screen.getByRole("button", { name: "Create tenant" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/register",
        expect.objectContaining({
          useMock: false,
          body: {
            name: "Tenant Owner",
            company_name: "Tenant AI",
            email: "admin@tenant.ai",
            password: "strongpass1",
          },
        }),
      );
    });

    expect(await screen.findByText("Tenant Owner")).toBeInTheDocument();
    expect(screen.getByText("Fresh registration")).toBeInTheDocument();
  });

  it("restores a stored browser session and runs logout", async () => {
    window.localStorage.setItem("propai_access_token", "stored-access-token");
    window.localStorage.setItem("propai_refresh_token", "stored-refresh-token");

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get).mockResolvedValue({
      id: "user-003",
      tenant_id: "tenant-003",
      email: "stored@propai.ai",
      name: "Stored User",
      role: "manager",
      is_active: true,
      created_at: "2026-03-23T02:00:00Z",
    });
    vi.mocked(apiClient.post).mockResolvedValue({
      success: true,
      message: "Logout completed.",
      logged_out_at: "2026-03-23T03:00:00Z",
    });

    render(<AuthWorkspaceClient locale="en" defaultMode="login" />);

    expect(await screen.findByText("Stored User")).toBeInTheDocument();
    expect(screen.getByText("Stored browser session")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Run logout" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/logout",
        expect.objectContaining({
          useMock: false,
          body: {
            refresh_token: "stored-refresh-token",
          },
        }),
      );
    });

    expect(window.localStorage.getItem("propai_access_token")).toBeNull();
    expect(window.localStorage.getItem("propai_refresh_token")).toBeNull();
    expect(
      screen.getByText("Logout completed and the browser session has been cleared."),
    ).toBeInTheDocument();
  });

  it("refreshes a stored session when the access token has expired", async () => {
    window.localStorage.setItem("propai_access_token", "expired-access-token");
    window.localStorage.setItem("propai_refresh_token", "stored-refresh-token");

    vi.mocked(apiClient.getRuntimeConfig).mockReturnValue({
      apiBaseUrl: "http://localhost:8000/api/latest",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });

    vi.mocked(apiClient.get)
      .mockRejectedValueOnce(
        new ApiClientError("Expired token", 401, {
          detail: "Expired token",
        }),
      )
      .mockResolvedValueOnce({
        id: "user-004",
        tenant_id: "tenant-004",
        email: "refresh@propai.ai",
        name: "Refreshed User",
        role: "manager",
        is_active: true,
        created_at: "2026-03-23T04:00:00Z",
      });

    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "fresh-access-token",
      refresh_token: "fresh-refresh-token",
      token_type: "bearer",
      expires_in: 1800,
    });

    render(<AuthWorkspaceClient locale="en" defaultMode="login" />);

    expect(await screen.findByText("Refreshed User")).toBeInTheDocument();
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/refresh",
        expect.objectContaining({
          useMock: false,
          body: {
            refresh_token: "stored-refresh-token",
          },
        }),
      );
    });
    expect(window.localStorage.getItem("propai_access_token")).toBe(
      "fresh-access-token",
    );
    expect(screen.getByText("Stored browser session")).toBeInTheDocument();
  });
});
