"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { ensureDataOwner } from "@/lib/projectSync";
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
  brand: string;
  loadingTitle: string;
  loadingDesc: string;
  successTitle: string;
  successDesc: string;
  redirecting: string;
  goNow: string;
  errorTitle: string;
  error: string;
  missingParams: string;
  openDashboard: string;
  backToLogin: string;
};

// ★사용자 친화 카피 — 개발자 용어(인가 코드·API 경로·세션 복구) 제거, 상태만 간단명료히 안내.
const LABELS: Record<Locale, CallbackLabels> = {
  ko: {
    brand: "카카오 로그인",
    loadingTitle: "로그인하는 중",
    loadingDesc: "카카오 계정으로 안전하게 로그인하고 있어요.",
    successTitle: "로그인되었습니다",
    successDesc: "환영합니다. 곧 대시보드로 이동합니다.",
    redirecting: "이동 중…",
    goNow: "지금 이동",
    errorTitle: "로그인하지 못했어요",
    error: "카카오 로그인을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    missingParams: "로그인 정보가 올바르지 않습니다. 처음부터 다시 시도해 주세요.",
    openDashboard: "대시보드로 이동",
    backToLogin: "로그인 다시 시도",
  },
  en: {
    brand: "Kakao Login",
    loadingTitle: "Signing you in",
    loadingDesc: "Securely signing in with your Kakao account.",
    successTitle: "You're signed in",
    successDesc: "Welcome back. Taking you to the dashboard.",
    redirecting: "Redirecting…",
    goNow: "Go now",
    errorTitle: "Sign-in failed",
    error: "We couldn't complete the Kakao login. Please try again shortly.",
    missingParams: "The sign-in info is invalid. Please start over.",
    openDashboard: "Open dashboard",
    backToLogin: "Try again",
  },
  "zh-CN": {
    brand: "Kakao 登录",
    loadingTitle: "正在登录",
    loadingDesc: "正在通过 Kakao 账号安全登录。",
    successTitle: "登录成功",
    successDesc: "欢迎回来，即将进入仪表盘。",
    redirecting: "正在跳转…",
    goNow: "立即进入",
    errorTitle: "登录失败",
    error: "无法完成 Kakao 登录，请稍后重试。",
    missingParams: "登录信息无效，请重新开始。",
    openDashboard: "进入仪表盘",
    backToLogin: "重试",
  },
};

const STORAGE_KEYS = {
  access: "propai_access_token",
  refresh: "propai_refresh_token",
} as const;

function persistTokens(tokens: TokenResponse) {
  window.localStorage.setItem(STORAGE_KEYS.access, tokens.access_token);
  window.localStorage.setItem(STORAGE_KEYS.refresh, tokens.refresh_token);
  // ★카카오 로그인 직후에도 소유자 검사 → 이전 계정 로컬데이터 노출 차단(계정 격리).
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
    errorMessage?: string;
  }>({
    status: "loading",
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
        setRequestState({ status: "success" });
      } catch (error) {
        if (!active) {
          return;
        }

        setRequestState({
          status: "error",
          errorMessage: resolveApiErrorMessage(error, labels.error),
        });
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [code, hasRequiredParams, labels.error, redirectUri, locale]);

  // ★인증 성공 시 자동으로 홈(대시보드)으로 이동 — 성공화면에 멈춰 "오류처럼" 보이는 문제 해결.
  //  세션 저장(persistTokens) 직후 약간의 지연으로 성공 메시지를 보여준 뒤 전환한다.
  useEffect(() => {
    if (requestState.status !== "success") {
      return;
    }
    const timer = setTimeout(() => {
      router.replace(`/${locale}`);
    }, 1100);
    return () => clearTimeout(timer);
  }, [requestState.status, router, locale]);

  const status = hasRequiredParams ? requestState.status : "error";

  // 상태별 카피(개발자 용어 없이 간단명료).
  const title =
    status === "success"
      ? labels.successTitle
      : status === "error"
        ? labels.errorTitle
        : labels.loadingTitle;
  const desc = !hasRequiredParams
    ? labels.missingParams
    : status === "success"
      ? labels.successDesc
      : status === "error"
        ? requestState.errorMessage || labels.error
        : labels.loadingDesc;

  // 상태 오브 색(로딩=액센트, 성공=에메랄드, 오류=앰버).
  const orb =
    status === "success"
      ? { ring: "rgba(16,185,129,0.30)", fill: "rgba(16,185,129,0.12)", color: "#10b981" }
      : status === "error"
        ? { ring: "rgba(245,158,11,0.32)", fill: "rgba(245,158,11,0.12)", color: "#f59e0b" }
        : { ring: "var(--line)", fill: "transparent", color: "var(--accent-strong)" };

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-10">
      {/* 은은한 브랜드 글로우 배경 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(60% 45% at 50% 32%, color-mix(in srgb, var(--accent-strong) 14%, transparent), transparent 72%)",
        }}
      />
      <div className="w-full max-w-sm rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-8 text-center shadow-[var(--shadow-lg)]">
        {/* 상태 오브 — 스피너 / 체크 / 경고 */}
        <div
          className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border-2"
          style={{ borderColor: orb.ring, backgroundColor: orb.fill }}
          role="status"
          aria-live="polite"
        >
          {status === "loading" ? (
            <span
              className="h-8 w-8 animate-spin rounded-full border-[3px]"
              style={{ borderColor: "var(--line)", borderTopColor: orb.color }}
            />
          ) : status === "success" ? (
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke={orb.color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M20 6 9 17l-5-5" />
            </svg>
          ) : (
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={orb.color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M12 8v5" /><path d="M12 16.5v.5" />
              <circle cx="12" cy="12" r="9" />
            </svg>
          )}
        </div>

        <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--accent-strong)]">
          {labels.brand}
        </p>
        <h1 className="mt-1.5 text-2xl font-bold text-[var(--text-primary)]">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{desc}</p>

        {/* 성공: 자동이동 안내 + 즉시 이동 / 오류: 다시 시도 */}
        {status === "success" ? (
          <p className="mt-6 inline-flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent-strong)]" />
            {labels.redirecting}
            <button
              type="button"
              onClick={() => router.replace(`/${locale}`)}
              className="font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
            >
              {labels.goNow}
            </button>
          </p>
        ) : null}

        {status === "error" ? (
          <div className="mt-6 flex flex-col gap-2">
            <Button onClick={() => router.replace(`/${locale}/login`)}>{labels.backToLogin}</Button>
            <Link
              href={`/${locale}`}
              className="text-xs font-semibold text-[var(--text-tertiary)] underline-offset-2 hover:text-[var(--text-secondary)] hover:underline"
            >
              {labels.openDashboard}
            </Link>
          </div>
        ) : null}
      </div>
    </main>
  );
}
