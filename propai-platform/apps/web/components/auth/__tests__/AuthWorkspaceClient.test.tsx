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

  it("logs in against the live auth api, stores tokens, and redirects to the locale home", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "access-token-001",
      refresh_token: "refresh-token-001",
      token_type: "bearer",
      expires_in: 3600,
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
    expect(window.localStorage.getItem("propai_refresh_token")).toBe(
      "refresh-token-001",
    );

    // Login success redirects straight to the locale home; the client no longer
    // re-reads /auth/me on the auth surface itself.
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/en");
    });
  });

  it("registers a tenant admin, posts the expected payload, and redirects to the locale home", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      access_token: "access-token-002",
      refresh_token: "refresh-token-002",
      token_type: "bearer",
      expires_in: 1800,
    });

    render(<AuthWorkspaceClient locale="en" defaultMode="register" />);

    await userEvent.type(screen.getByLabelText("Operator name"), "Tenant Owner");
    await userEvent.type(
      screen.getByLabelText("Company (optional)"),
      "Tenant AI",
    );
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

    await waitFor(() => {
      expect(window.localStorage.getItem("propai_access_token")).toBe(
        "access-token-002",
      );
    });
    expect(pushMock).toHaveBeenCalledWith("/en");
  });

  it("validates a stored browser session against /auth/me on mount", async () => {
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

    render(<AuthWorkspaceClient locale="en" defaultMode="login" />);

    // A stored access token triggers a live /auth/me validation on mount; the
    // session is not surfaced on the auth screen (it is consumed downstream),
    // so we assert the verification call rather than any rendered profile card.
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        "/auth/me",
        expect.objectContaining({ useMock: false }),
      );
    });

    // A successful validation must not clear the stored tokens.
    expect(window.localStorage.getItem("propai_access_token")).toBe(
      "stored-access-token",
    );
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

    // The first /auth/me fails with 401, so the client exchanges the stored
    // refresh token for a fresh pair before retrying validation.
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

    await waitFor(() => {
      expect(window.localStorage.getItem("propai_access_token")).toBe(
        "fresh-access-token",
      );
    });
    // /auth/me is called twice: the initial (401) attempt and the post-refresh retry.
    expect(vi.mocked(apiClient.get).mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
