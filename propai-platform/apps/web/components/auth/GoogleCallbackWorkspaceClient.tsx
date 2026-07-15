"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { ensureDataOwner } from "@/lib/projectSync";
import type { Locale } from "@/i18n/config";

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

type GoogleCallbackWorkspaceClientProps = {
  locale: Locale;
  code: string | null;
  state: string | null;
  redirectUri: string | null;
};

// 로그인 시작(login-url) 단계에서 보관한 state — 콜백에서 일치 검증(CSRF/세션고정 방지).
const GOOGLE_STATE_KEY = "google_oauth_state";

type CallbackLabels = {
  eyebrow: string;
  title: string;
  description: string;
  loading: string;
  success: string;
  missingParams: string;
  stateMismatch: string;
  error: string;
  openDashboard: string;
  backToLogin: string;
};

const LABELS: Record<Locale, CallbackLabels> = {
  ko: {
    eyebrow: "AUTH / GOOGLE CALLBACK",
    title: "구글 로그인 완료 처리",
    description:
      "인가 코드를 실제 `/auth/google/callback` API에 전달해 브라우저 세션을 복구합니다.",
    loading: "구글 인증 코드를 교환하는 중입니다.",
    success: "구글 인증이 완료되어 브라우저 세션을 저장했습니다.",
    missingParams: "구글 callback 파라미터가 부족합니다. code를 확인하세요.",
    stateMismatch: "보안 검증(state) 불일치 — 로그인을 다시 시도해 주세요(CSRF 방지).",
    error: "구글 인증을 완료하지 못했습니다.",
    openDashboard: "대시보드로 이동",
    backToLogin: "로그인으로 돌아가기",
  },
  en: {
    eyebrow: "AUTH / GOOGLE CALLBACK",
    title: "Google callback completion",
    description:
      "Exchange the authorization code through the live `/auth/google/callback` API and restore the browser session.",
    loading: "Exchanging the Google authorization code.",
    success: "Google authentication completed and the browser session has been stored.",
    missingParams:
      "The Google callback payload is incomplete. Check that the code parameter is present.",
    stateMismatch: "Security check (state) mismatch — please try signing in again (CSRF protection).",
    error: "Google authentication could not be completed.",
    openDashboard: "Open dashboard",
    backToLogin: "Back to login",
  },
  "zh-CN": {
    eyebrow: "AUTH / GOOGLE CALLBACK",
    title: "Google 回调完成页",
    description:
      "通过真实 `/auth/google/callback` API 交换授权码并恢复浏览器会话。",
    loading: "正在交换 Google 授权码。",
    success: "Google 认证完成，浏览器会话已保存。",
    missingParams: "Google 回调参数不完整，请确认提供 code。",
    stateMismatch: "安全校验(state)不一致 — 请重新登录(防 CSRF)。",
    error: "无法完成 Google 认证。",
    openDashboard: "进入仪表盘",
    backToLogin: "返回登录",
  },
};

const STORAGE_KEYS = {
  access: "propai_access_token",
  refresh: "propai_refresh_token",
} as const;

function persistTokens(tokens: TokenResponse) {
  window.localStorage.setItem(STORAGE_KEYS.access, tokens.access_token);
  window.localStorage.setItem(STORAGE_KEYS.refresh, tokens.refresh_token);
  // ★구글 로그인 직후에도 소유자 검사 → 이전 계정 로컬데이터 노출 차단(계정 격리).
  ensureDataOwner();
}

function resolveApiErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiClientError) {
    if (
      typeof error.payload === "object" &&
      error.payload !== null &&
      "detail" in error.payload &&
      typeof (error.payload as { detail?: unknown }).detail === "string"
    ) {
      return (error.payload as { detail: string }).detail;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

export function GoogleCallbackWorkspaceClient({
  locale,
  code,
  state,
  redirectUri,
}: GoogleCallbackWorkspaceClientProps) {
  const router = useRouter();
  const labels = LABELS[locale] || LABELS["ko"];
  const hasRequiredParams = Boolean(code);
  const [requestState, setRequestState] = useState<{
    status: "loading" | "success" | "error";
    message: string;
  }>({
    status: "loading",
    message: labels.loading,
  });

  useEffect(() => {
    if (!hasRequiredParams) {
      return;
    }

    let active = true;

    const run = async () => {
      // ★CSRF/세션고정 방지: 로그인 시작 시 sessionStorage에 보관한 state와 콜백 state가
      //  일치해야 교환한다. 보관값이 있는데 불일치면 차단(보관값 없으면 구버전 호환으로 통과).
      const savedState = window.sessionStorage.getItem(GOOGLE_STATE_KEY);
      if (savedState && state && savedState !== state) {
        if (active) setRequestState({ status: "error", message: labels.stateMismatch });
        return;
      }
      try {
        // ★구글도 콜백 URL에 redirect_uri를 붙여주지 않는다(code만 전달) →
        //  토큰 교환의 redirect_uri는 "로그인 단계에서 보낸 값"과 1바이트도 다르면 안 되므로
        //  현재 페이지(=등록된 콜백 주소)에서 결정적으로 재구성한다. 쿼리값이 있으면 우선 사용.
        const effectiveRedirectUri =
          redirectUri || `${window.location.origin}/${locale}/google/callback`;
        const tokens = await apiClient.post<TokenResponse>("/auth/google/callback", {
          body: {
            code,
            state,
            redirect_uri: effectiveRedirectUri,
          },
          useMock: false,
        });

        if (!active) {
          return;
        }

        window.sessionStorage.removeItem(GOOGLE_STATE_KEY);
        persistTokens(tokens);
        setRequestState({
          status: "success",
          message: labels.success,
        });
      } catch (error) {
        if (!active) {
          return;
        }

        setRequestState({
          status: "error",
          message: resolveApiErrorMessage(error, labels.error),
        });
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [code, state, hasRequiredParams, labels.error, labels.success, labels.stateMismatch, redirectUri, locale]);

  // ★인증 성공 시 자동으로 홈(대시보드)으로 이동 — 성공화면에 멈춰 "오류처럼" 보이는 문제 해결.
  useEffect(() => {
    if (requestState.status !== "success") {
      return;
    }
    const timer = setTimeout(() => {
      router.replace(`/${locale}`);
    }, 800);
    return () => clearTimeout(timer);
  }, [requestState.status, router, locale]);

  const status = hasRequiredParams ? requestState.status : "error";
  const message = hasRequiredParams ? requestState.message : labels.missingParams;

  const feedbackClassName =
    status === "error"
      ? "border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
      : status === "success"
        ? "border-[rgba(13,148,136,0.28)] bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
        : "border-[rgba(14,116,144,0.24)] bg-[rgba(14,116,144,0.08)] text-[rgb(14,116,144)]";

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl items-center px-6 py-10">
      <Card className="w-full rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8 md:p-10">
          <span className="inline-flex rounded-full bg-[rgba(14,116,144,0.12)] px-4 py-2 text-sm font-semibold text-[var(--accent-strong)]">
            {labels.eyebrow}
          </span>
          <CardTitle className="mt-5 text-3xl font-bold text-[var(--text-primary)] md:text-4xl">
            {labels.title}
          </CardTitle>
          <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)] md:text-base">
            {labels.description}
          </p>

          <div
            className={`mt-8 rounded-[var(--radius-xl)] border px-5 py-4 text-sm ${feedbackClassName}`}
            role="status"
          >
            {message}
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <Button
              disabled={status !== "success"}
              onClick={() => router.push(`/${locale}`)}
            >
              {labels.openDashboard}
            </Button>
            <Link
              href={`/${locale}/login`}
              className="rounded-full border border-[var(--line)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface-strong)]"
            >
              {labels.backToLogin}
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
