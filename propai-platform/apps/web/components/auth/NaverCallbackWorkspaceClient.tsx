"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  classifySocialLoginError,
  socialLoginErrorMessage,
} from "@/lib/socialLoginError";
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
  /** 공급자가 돌려보낸 오류(OAuth 2.0 §4.1.2.1). 종전에는 읽지 않고 버렸다. */
  providerError?: string | null;
  providerErrorDescription?: string | null;
};

type CallbackLabels = {
  eyebrow: string;
  /** ★제목은 **상태마다 다르다**. 하나로 두면 오류일 때 「로그인되었습니다」를 띄운다.
   *  2026-09-06 라이브 실측: 파라미터 없이 콜백을 열면 본문은 실패를 말하는데
   *  제목은 「로그인되었습니다」였다 — 형제 카카오만 errorTitle 을 갖고 있었다(§29). */
  loadingTitle: string;
  successTitle: string;
  errorTitle: string;
  description: string;
  loading: string;
  success: string;
  missingParams: string;
  stateMismatch: string;
  error: string;
  openDashboard: string;
  backToLogin: string;
};

// ★테스트가 문구를 손으로 다시 적지 않도록 **내보낸다**.
//   2026-09-06 실측: 콜백 테스트 3종이 이 문구를 파일 안에 **상수로 복사**해 두고 있었고,
//   그래서 문구를 고치자 8건이 깨졌다(네이버 4 · 구글 4 · 카카오는 문구 불변이라 우연히 통과).
//   ★그때 내가 「이 테스트들은 바뀐 문구를 단언하지 않는다」고 **오보**했다 —
//     문구 리터럴로 훑었는데 테스트는 그것을 **상수 이름**으로 들고 있었다.
//   여기서 파생시키면 문구를 다듬어도 「어느 상태에 어느 라벨이 뜨는가」라는 계약만 남는다.
export const LABELS: Record<Locale, CallbackLabels> = {
  // ★사용자 대면 문구 — **내부 구현을 말하지 않는다.**
  //   2026-09-06 실측: 여기에 「인가 코드를 실제 `/auth/…/callback` API에 전달해」라고
  //   적혀 있었다(카카오엔 0건 · 네이버·구글에만 1건씩 — 형제가 갈렸다).
  //   ★네이버 검수가 요구하는 **4번 캡처(완료 화면)** 가 정확히 이 화면이라,
  //     심사자에게 **내부 API 경로가 찍힌 화면**을 제출하게 된다.
  //   톤은 카카오 콜백(형제 중 정돈된 쪽)에 맞춘다.
  ko: {
    eyebrow: "AUTH / NAVER CALLBACK",
    loadingTitle: "로그인하는 중",
    successTitle: "로그인되었습니다",
    errorTitle: "로그인하지 못했어요",
    description: "네이버 계정으로 안전하게 로그인하고 있어요. 잠시 후 자동으로 이동합니다.",
    loading: "로그인하는 중",
    success: "네이버 계정으로 로그인되었습니다. 잠시 후 이동합니다.",
    missingParams: "로그인 정보가 올바르지 않습니다. 처음부터 다시 시도해 주세요.",
    stateMismatch: "보안 확인에 실패했습니다. 처음부터 다시 시도해 주세요.",
    error: "네이버 로그인을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    openDashboard: "대시보드로 이동",
    backToLogin: "로그인으로 돌아가기",
  },
  en: {
    eyebrow: "AUTH / NAVER CALLBACK",
    loadingTitle: "Signing you in",
    successTitle: "You're signed in",
    errorTitle: "Sign-in failed",
    description: "Signing you in securely with Naver. You'll be redirected shortly.",
    loading: "Signing in",
    success: "Signed in with Naver. Redirecting you now.",
    missingParams: "The sign-in info is invalid. Please start over.",
    stateMismatch: "Security check failed. Please start over.",
    error: "Could not finish signing in with Naver. Please try again shortly.",
    openDashboard: "Open dashboard",
    backToLogin: "Back to login",
  },
  "zh-CN": {
    eyebrow: "AUTH / NAVER CALLBACK",
    loadingTitle: "正在登录",
    successTitle: "已登录",
    errorTitle: "登录失败",
    description: "正在使用 Naver 账号安全登录，稍后将自动跳转。",
    loading: "正在登录",
    success: "已使用 Naver 账号登录，即将跳转。",
    missingParams: "登录信息无效，请重新开始。",
    stateMismatch: "安全校验失败，请重新开始。",
    error: "无法完成 Naver 登录，请稍后重试。",
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
  providerError = null,
  providerErrorDescription = null,
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
      let savedState: string | null = null;
      try {
        savedState = window.sessionStorage.getItem(NAVER_STATE_KEY);
      } catch {
        // sessionStorage 접근 불가(프라이빗 모드·차단) → fail-closed(무한로딩 방지, 아래 가드가 차단).
      }
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

  // ★공급자 오류를 먼저 판정한다 — 이것이 있으면 code 가 없는 것은 **결과**이지 원인이 아니다.
  //   종전에는 무조건 `missingParams` 를 냈고 그건 원인과 무관한 문구였다.
  //   사용자 취소와 설정 오류는 **다음 행동이 다르므로** 갈라서 말한다.
  const providerVerdict = classifySocialLoginError(providerError, providerErrorDescription);
  const providerMessage = socialLoginErrorMessage(providerVerdict, locale);

  const status =
    providerVerdict.kind !== "none" ? "error" : hasRequiredParams ? requestState.status : "error";
  const message =
    providerMessage ?? (hasRequiredParams ? requestState.message : labels.missingParams);

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
            {status === "error"
              ? labels.errorTitle
              : status === "success"
                ? labels.successTitle
                : labels.loadingTitle}
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
