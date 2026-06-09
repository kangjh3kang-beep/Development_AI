"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

type KakaoCallbackWorkspaceClientProps = {
  locale: Locale;
  code: string | null;
  redirectUri: string | null;
};

type CallbackLabels = {
  eyebrow: string;
  title: string;
  description: string;
  loading: string;
  success: string;
  missingParams: string;
  error: string;
  openDashboard: string;
  backToLogin: string;
};

const LABELS: Record<Locale, CallbackLabels> = {
  ko: {
    eyebrow: "AUTH / KAKAO CALLBACK",
    title: "카카오 로그인 완료 처리",
    description:
      "인가 코드를 실제 `/auth/kakao/callback` API에 전달해 브라우저 세션을 복구합니다.",
    loading: "카카오 인증 코드를 교환하는 중입니다.",
    success: "카카오 인증이 완료되어 브라우저 세션을 저장했습니다.",
    missingParams: "카카오 callback 파라미터가 부족합니다. code를 확인하세요.",
    error: "카카오 인증을 완료하지 못했습니다.",
    openDashboard: "대시보드로 이동",
    backToLogin: "로그인으로 돌아가기",
  },
  en: {
    eyebrow: "AUTH / KAKAO CALLBACK",
    title: "Kakao callback completion",
    description:
      "Exchange the authorization code through the live `/auth/kakao/callback` API and restore the browser session.",
    loading: "Exchanging the Kakao authorization code.",
    success: "Kakao authentication completed and the browser session has been stored.",
    missingParams:
      "The Kakao callback payload is incomplete. Check that the code parameter is present.",
    error: "Kakao authentication could not be completed.",
    openDashboard: "Open dashboard",
    backToLogin: "Back to login",
  },
  "zh-CN": {
    eyebrow: "AUTH / KAKAO CALLBACK",
    title: "Kakao 回调完成页",
    description:
      "通过真实 `/auth/kakao/callback` API 交换授权码并恢复浏览器会话。",
    loading: "正在交换 Kakao 授权码。",
    success: "Kakao 认证完成，浏览器会话已保存。",
    missingParams: "Kakao 回调参数不完整，请确认提供 code。",
    error: "无法完成 Kakao 认证。",
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

export function KakaoCallbackWorkspaceClient({
  locale,
  code,
  redirectUri,
}: KakaoCallbackWorkspaceClientProps) {
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
      try {
        // ★카카오는 콜백 URL에 redirect_uri를 붙여주지 않는다(code만 전달) →
        //  쿼리파라미터(redirectUri)는 실제 플로우에서 거의 항상 null이다.
        //  토큰 교환의 redirect_uri는 "로그인 단계에서 보낸 값"과 1바이트도 다르면 안 되므로
        //  현재 페이지(=등록된 콜백 주소)에서 결정적으로 재구성한다. 쿼리값이 있으면 우선 사용.
        const effectiveRedirectUri =
          redirectUri || `${window.location.origin}/${locale}/kakao/callback`;
        const tokens = await apiClient.post<TokenResponse>("/auth/kakao/callback", {
          body: {
            code,
            redirect_uri: effectiveRedirectUri,
          },
          useMock: false,
        });

        if (!active) {
          return;
        }

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
  }, [code, hasRequiredParams, labels.error, labels.success, redirectUri, locale]);

  // ★인증 성공 시 자동으로 홈(대시보드)으로 이동 — 성공화면에 멈춰 "오류처럼" 보이는 문제 해결.
  //  세션 저장(persistTokens) 직후 약간의 지연으로 성공 메시지를 보여준 뒤 전환한다.
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
