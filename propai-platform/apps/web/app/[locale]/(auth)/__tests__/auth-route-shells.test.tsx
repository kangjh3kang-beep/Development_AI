import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import KakaoCallbackPage from "../kakao/callback/page";
import LoginPage from "../login/page";
import RegisterPage from "../register/page";

vi.mock("@/components/auth/AuthWorkspaceClient", () => ({
  AuthWorkspaceClient: ({
    locale,
    defaultMode,
  }: {
    locale: string;
    defaultMode: "login" | "register";
  }) => (
    <div data-testid="auth-workspace">
      <span>{locale}</span>
      <span>{defaultMode}</span>
    </div>
  ),
}));

vi.mock("@/components/auth/KakaoCallbackWorkspaceClient", () => ({
  KakaoCallbackWorkspaceClient: ({
    locale,
    code,
    tenantId,
  }: {
    locale: string;
    code: string | null;
    tenantId: string | null;
  }) => (
    <div data-testid="kakao-callback-workspace">
      <span>{locale}</span>
      <span>{code}</span>
      <span>{tenantId}</span>
    </div>
  ),
}));

describe("Auth route shells", () => {
  it("renders the login route with the live auth workspace", async () => {
    render(await LoginPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByTestId("auth-workspace")).toHaveTextContent("en");
    expect(screen.getByTestId("auth-workspace")).toHaveTextContent("login");
  });

  it("renders the register route with the live auth workspace", async () => {
    render(await RegisterPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByTestId("auth-workspace")).toHaveTextContent("en");
    expect(screen.getByTestId("auth-workspace")).toHaveTextContent("register");
  });

  it("renders the Kakao callback route with the completion workspace", async () => {
    render(
      await KakaoCallbackPage({
        params: Promise.resolve({ locale: "en" }),
        searchParams: Promise.resolve({
          code: "kakao-code-001",
          tenant_id: "tenant-001",
        }),
      }),
    );

    expect(screen.getByTestId("kakao-callback-workspace")).toHaveTextContent("en");
    expect(screen.getByTestId("kakao-callback-workspace")).toHaveTextContent(
      "kakao-code-001",
    );
    expect(screen.getByTestId("kakao-callback-workspace")).toHaveTextContent(
      "tenant-001",
    );
  });
});
