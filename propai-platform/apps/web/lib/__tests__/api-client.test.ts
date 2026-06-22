import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const resolveMockRequest = vi.fn();

vi.mock("@/mocks/handlers", () => ({
  resolveMockRequest,
}));

async function loadApiClient(
  env: Record<string, string | undefined> = {},
) {
  vi.resetModules();
  vi.unstubAllEnvs();
  window.localStorage.clear();

  for (const [key, value] of Object.entries(env)) {
    if (value !== undefined) {
      vi.stubEnv(key, value);
    }
  }

  return import("@/lib/api-client");
}

describe("apiClient", () => {
  beforeEach(() => {
    resolveMockRequest.mockReset();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("reports mock mode when mocks are explicitly enabled", async () => {
    const { apiClient } = await loadApiClient({
      NEXT_PUBLIC_USE_MOCKS: "true",
    });

    expect(apiClient.getRuntimeConfig()).toEqual({
      apiBaseUrl: "http://localhost:8000/api/v1",
      useMocksByDefault: true,
      hasAccessToken: false,
      mode: "mock",
    });
  });

  it("reports live mode and detects localStorage token when mocks are disabled", async () => {
    const { apiClient } = await loadApiClient({
      NEXT_PUBLIC_USE_MOCKS: "false",
    });

    window.localStorage.setItem("propai_access_token", "live-token");

    expect(apiClient.getRuntimeConfig()).toEqual({
      apiBaseUrl: "http://localhost:8000/api/v1",
      useMocksByDefault: false,
      hasAccessToken: true,
      mode: "live",
    });
  });

  it("returns a mock response without calling fetch when the mock handler resolves", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    resolveMockRequest.mockResolvedValue({ source: "mock" });

    const { apiClient } = await loadApiClient({
      NEXT_PUBLIC_USE_MOCKS: "true",
    });
    const response = await apiClient.get<{ source: string }>("/projects");

    expect(response).toEqual({ source: "mock" });
    expect(resolveMockRequest).toHaveBeenCalledWith("GET", "/projects");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("falls back to fetch and injects the stored access token for live calls", async () => {
    resolveMockRequest.mockResolvedValue(undefined);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: {
          "content-type": "application/json",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { apiClient } = await loadApiClient({
      NEXT_PUBLIC_USE_MOCKS: "false",
    });
    window.localStorage.setItem("propai_access_token", "token-123");

    await apiClient.post("/tax/calculate", {
      body: {
        taxable_value: 1200000000,
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/tax/calculate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ taxable_value: 1200000000 }),
        headers: expect.objectContaining({
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: "Bearer token-123",
        }),
      }),
    );
  });

  it("raises ApiClientError with the parsed payload when the API responds with an error", async () => {
    resolveMockRequest.mockResolvedValue(undefined);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Forbidden" }), {
          status: 403,
          headers: {
            "content-type": "application/json",
          },
        }),
      ),
    );

    const { apiClient } = await loadApiClient({
      NEXT_PUBLIC_USE_MOCKS: "false",
    });

    await expect(apiClient.get("/system/version")).rejects.toMatchObject({
      name: "ApiClientError",
      status: 403,
      payload: {
        detail: "Forbidden",
      },
    });
  });
});
