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

type NaverCallbackWorkspaceClientProps = {
  locale: Locale;
  code: string | null;
  state: string | null;
  redirectUri: string | null;
};

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
    eyebrow: "AUTH / NAVER CALLBACK",
    title: "네이버 로그인 완료 처리",
    description:
      "인가 코드를 실제 `/auth/naver/callback` API에 전달해 브라우저 세션을 복구합니다.",
    loading: "네이버 인증 코드를 교환하는 중입니다.",
    success: "네이버 인증이 완료되어 브라우저 세션을 저장했습니다.",
    missingParams: "네이버 callback 파라미터가 부족합니다. code·state를 확인하세요.",
    stateMismatch: "보안 검증(state) 불일치 — 로그인을 다시 시도해 주세요(CSRF 방지).",
    error: "네이버 인증을 완료하지 못했습니다.",
    openDashboard: "대시보드로 이동",
    backToLogin: "로그인으로 돌아가기",
  },
  en: {
    eyebrow: "AUTH / NAVER CALLBACK",
    title: "Naver callback completion",
    description:
      "Exchange the authorization code through the live `/auth/naver/callback` API and restore the browser session.",
    loading: "Exchanging the Naver authorization code.",
    success: "Naver authentication completed and the browser session has been stored.",
    missingParams:
      "The Naver callback payload is incomplete. Check that the code and state parameters are present.",
    stateMismatch: "Security check (state) mismatch — please try signing in again (CSRF protection).",
    error: "Naver authentication could not be completed.",
    openDashboard: "Open dashboard",
    backToLogin: "Back to login",
  },
  "zh-CN": {
    eyebrow: "AUTH / NAVER CALLBACK",
    title: "Naver 回调完成页",
    description:
      "通过真实 `/auth/naver/callback` API 交换授权码并恢复浏览器会话。",
    loading: "正在交换 Naver 授权码。",
    success: "Naver 认证完成，浏览器会话已保存。",
    missingParams: "Naver 回调参数不完整，请确认提供 code 与 state。",
    stateMismatch: "安全校验(state)不一致 — 请重新登录(防 CSRF)。",
    error: "无法完成 Naver 认证。",
    openDashboard: "进入仪表盘",
    backToLogin: "返回登录",
  },
};

const STORAGE_KEYS = {
  access: "propai_access_token",
  refresh: "propai_refresh_token",
} as const;

// 네이버 로그인 시작(login-url) 단계에서 보관한 state — 콜백에서 일치 검증(CSRF).
const NAVER_STATE_KEY = "naver_oauth_state";

function persistTokens(tokens: TokenResponse) {
  window.localStorage.setItem(STORAGE_KEYS.access, tokens.access_token);
  window.localStorage.setItem(STORAGE_KEYS.refresh, tokens.refresh_token);
  // ★네이버 로그인 직후에도 소유자 검사 → 이전 계정 로컬데이터 노출 차단(계정 격리).
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

export function NaverCallbackWorkspaceClient({
  locale,
  code,
  state,
  redirectUri,
}: NaverCallbackWorkspaceClientProps) {
  const router = useRouter();
  const labels = LABELS[locale] || LABELS["ko"];
  const hasRequiredParams = Boolean(code && state);
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
      // ★CSRF 방지(fail-closed): 이 브라우저가 로그인을 개시했다는 증거(sessionStorage 보관 state)가
      //  반드시 존재하고 콜백 state와 일치해야만 교환한다. 보관값이 없거나 불일치면 차단 —
      //  공격자는 피해자 브라우저의 same-origin sessionStorage에 값을 심을 수 없어 로그인 CSRF 불성립.
      //  (이펙트 본문 동기 setState 회피 위해 async run 내부에서 처리)
      const savedState = window.sessionStorage.getItem(NAVER_STATE_KEY);
      if (!savedState || savedState !== state) {
        if (active) setRequestState({ status: "error", message: labels.stateMismatch });
        return;
      }
      try {
        // ★네이버도 콜백 URL에 redirect_uri를 붙여주지 않는다(code·state만) →
        //  토큰 교환의 redirect_uri는 "로그인 단계에서 보낸 값"과 1바이트도 다르면 안 되므로
        //  현재 페이지(=등록된 콜백 주소)에서 결정적으로 재구성한다.
        const effectiveRedirectUri =
          redirectUri || `${window.location.origin}/${locale}/naver/callback`;
        const tokens = await apiClient.post<TokenResponse>("/auth/naver/callback", {
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

        window.sessionStorage.removeItem(NAVER_STATE_KEY);
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

  // ★인증 성공 시 자동으로 홈(대시보드)으로 이동.
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
