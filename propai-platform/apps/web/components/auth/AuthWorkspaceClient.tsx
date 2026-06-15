"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { clearOnLogout, ensureDataOwner } from "@/lib/projectSync";
import type { Locale } from "@/i18n/config";

type AuthMode = "login" | "register";

type AuthWorkspaceClientProps = {
  locale: Locale;
  defaultMode: AuthMode;
};

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

type UserResponse = {
  id: string;
  tenant_id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
};

type SessionState = {
  user: UserResponse;
  expiresIn: number | null;
  source: AuthMode | "stored" | "refreshed";
};

type FeedbackState = {
  tone: "success" | "error" | "info";
  message: string;
};

type Labels = {
  eyebrow: string;
  title: string;
  description: string;
  modeLabels: Record<AuthMode, string>;
  modeDescriptions: Record<AuthMode, string>;
  loginFields: {
    email: string;
    password: string;
    submit: string;
  };
  registerFields: {
    name: string;
    companyName: string;
    email: string;
    password: string;
    submit: string;
  };
  runtimeTitle: string;
  runtimeDescription: string;
  runtimeMode: string;
  runtimeApiBase: string;
  runtimeToken: string;
  runtimeRefreshToken: string;
  runtimeModeLabels: {
    live: string;
    mock: string;
  };
  tokenPresent: string;
  tokenMissing: string;
  sessionTitle: string;
  sessionDescription: string;
  sessionEmpty: string;
  sessionLoading: string;
  sessionRole: string;
  sessionTenant: string;
  sessionCreatedAt: string;
  sessionExpiry: string;
  sessionSource: string;
  sessionSourceLabels: Record<SessionState["source"], string>;
  openDashboard: string;
  refreshSession: string;
  logout: string;
  switchLabel: string;
  switchLinks: Record<AuthMode, string>;
  submitting: string;
  successLabels: {
    login: string;
    register: string;
    sessionRefreshed: string;
    logout: string;
    sessionRestored: string;
    sessionCleared: string;
  };
  errorLabels: {
    login: string;
    register: string;
    refresh: string;
    logout: string;
    session: string;
  };
};

const STORAGE_KEYS = {
  access: "propai_access_token",
  refresh: "propai_refresh_token",
} as const;

const LABELS: Record<Locale, Labels> = {
  ko: {
    eyebrow: "AUTH / LIVE",
    title: "실사용 인증 작업 공간",
    description:
      "이제 로그인과 테넌트 관리자 등록이 placeholder가 아니라 실제 `/auth` API에 연결됩니다.",
    modeLabels: {
      login: "로그인",
      register: "관리자 등록",
    },
    modeDescriptions: {
      login: "기존 계정으로 JWT 세션을 발급합니다.",
      register: "새 테넌트와 첫 관리자 계정을 생성합니다.",
    },
    loginFields: {
      email: "이메일",
      password: "비밀번호",
      submit: "로그인",
    },
    registerFields: {
      name: "담당자 이름",
      companyName: "회사명 (개인은 비워두세요)",
      email: "관리자 이메일",
      password: "비밀번호",
      submit: "테넌트 등록",
    },
    runtimeTitle: "런타임 연결 상태",
    runtimeDescription:
      "auth 화면은 mock fallback 없이 실제 API를 우선 호출하고, 성공 시 브라우저 토큰을 즉시 갱신합니다.",
    runtimeMode: "작업 공간 모드",
    runtimeApiBase: "API Base URL",
    runtimeToken: "저장된 액세스 토큰",
    runtimeRefreshToken: "저장된 리프레시 토큰",
    runtimeModeLabels: {
      live: "실시간 연동",
      mock: "예시 데이터",
    },
    tokenPresent: "있음",
    tokenMissing: "없음",
    sessionTitle: "인증 세션",
    sessionDescription:
      "로그인 또는 등록 성공 후 `/auth/me`를 다시 호출해 현재 사용자 프로필을 확인합니다.",
    sessionEmpty: "아직 인증 세션이 없습니다.",
    sessionLoading: "저장된 세션을 확인하는 중입니다.",
    sessionRole: "역할",
    sessionTenant: "테넌트",
    sessionCreatedAt: "생성 시각",
    sessionExpiry: "토큰 만료(초)",
    sessionSource: "세션 출처",
    sessionSourceLabels: {
      login: "로그인 직후",
      register: "등록 직후",
      stored: "브라우저 저장 세션",
      refreshed: "토큰 갱신 직후",
    },
    openDashboard: "대시보드로 이동",
    refreshSession: "세션 갱신",
    logout: "로그아웃",
    switchLabel: "다른 인증 경로",
    switchLinks: {
      login: "기존 계정 로그인",
      register: "신규 테넌트 등록",
    },
    submitting: "처리 중...",
    successLabels: {
      login: "로그인에 성공했고 세션을 저장했습니다.",
      register: "테넌트 관리자 등록에 성공했고 세션을 저장했습니다.",
      sessionRefreshed: "리프레시 토큰으로 세션을 갱신했습니다.",
      logout: "로그아웃이 완료되어 브라우저 세션을 정리했습니다.",
      sessionRestored: "브라우저에 저장된 세션을 복구했습니다.",
      sessionCleared: "브라우저 저장 세션을 제거했습니다.",
    },
    errorLabels: {
      login: "로그인 요청을 처리하지 못했습니다.",
      register: "관리자 등록 요청을 처리하지 못했습니다.",
      refresh: "세션 갱신 요청을 처리하지 못했습니다.",
      logout: "로그아웃 요청을 처리하지 못했습니다.",
      session: "저장된 세션을 확인하지 못했습니다.",
    },
  },
  en: {
    eyebrow: "AUTH / LIVE",
    title: "Live authentication workspace",
    description:
      "Login and tenant-admin onboarding now run against the real `/auth` API instead of placeholder screens.",
    modeLabels: {
      login: "Login",
      register: "Register admin",
    },
    modeDescriptions: {
      login: "Issue a JWT session for an existing account.",
      register: "Create a new tenant and its first administrator.",
    },
    loginFields: {
      email: "Email",
      password: "Password",
      submit: "Run login",
    },
    registerFields: {
      name: "Operator name",
      companyName: "Company (optional)",
      email: "Admin email",
      password: "Password",
      submit: "Create tenant",
    },
    runtimeTitle: "Runtime connection",
    runtimeDescription:
      "The auth surface prefers live API calls without a mock fallback and refreshes browser tokens immediately after success.",
    runtimeMode: "Workspace mode",
    runtimeApiBase: "API Base URL",
    runtimeToken: "Stored access token",
    runtimeRefreshToken: "Stored refresh token",
    runtimeModeLabels: {
      live: "LIVE",
      mock: "MOCK",
    },
    tokenPresent: "Present",
    tokenMissing: "Missing",
    sessionTitle: "Authenticated session",
    sessionDescription:
      "After login or registration, the client re-reads `/auth/me` to validate the active profile.",
    sessionEmpty: "No authenticated session is currently available.",
    sessionLoading: "Checking the stored browser session.",
    sessionRole: "Role",
    sessionTenant: "Tenant",
    sessionCreatedAt: "Created at",
    sessionExpiry: "Token expiry (sec)",
    sessionSource: "Session source",
    sessionSourceLabels: {
      login: "Fresh login",
      register: "Fresh registration",
      stored: "Stored browser session",
      refreshed: "Refreshed session",
    },
    openDashboard: "Open dashboard",
    refreshSession: "Refresh session",
    logout: "Run logout",
    switchLabel: "Alternative path",
    switchLinks: {
      login: "Use an existing account",
      register: "Create a new tenant",
    },
    submitting: "Submitting...",
    successLabels: {
      login: "Login succeeded and the browser session has been stored.",
      register: "Registration succeeded and the browser session has been stored.",
      sessionRefreshed: "The browser session has been refreshed with the refresh token.",
      logout: "Logout completed and the browser session has been cleared.",
      sessionRestored: "A stored browser session was restored.",
      sessionCleared: "The browser session has been cleared.",
    },
    errorLabels: {
      login: "The login request could not be completed.",
      register: "The registration request could not be completed.",
      refresh: "The refresh request could not be completed.",
      logout: "The logout request could not be completed.",
      session: "The stored session could not be verified.",
    },
  },
  "zh-CN": {
    eyebrow: "AUTH / LIVE",
    title: "实时认证工作台",
    description: "登录和租户管理员注册现在直接连接真实 `/auth` API，而不是占位页面。",
    modeLabels: {
      login: "登录",
      register: "注册管理员",
    },
    modeDescriptions: {
      login: "为现有账号签发 JWT 会话。",
      register: "创建新的租户和首个管理员账号。",
    },
    loginFields: {
      email: "邮箱",
      password: "密码",
      submit: "执行登录",
    },
    registerFields: {
      name: "负责人姓名",
      companyName: "公司名称(可选)",
      email: "管理员邮箱",
      password: "密码",
      submit: "创建租户",
    },
    runtimeTitle: "运行时连接状态",
    runtimeDescription: "auth 页面优先调用真实 API，成功后立即刷新浏览器中的令牌。",
    runtimeMode: "工作台模式",
    runtimeApiBase: "API Base URL",
    runtimeToken: "已存储访问令牌",
    runtimeRefreshToken: "已存储刷新令牌",
    runtimeModeLabels: {
      live: "LIVE",
      mock: "MOCK",
    },
    tokenPresent: "已存在",
    tokenMissing: "不存在",
    sessionTitle: "认证会话",
    sessionDescription: "登录或注册后，客户端会重新读取 `/auth/me` 以确认当前用户资料。",
    sessionEmpty: "当前没有可用的认证会话。",
    sessionLoading: "正在检查浏览器中保存的会话。",
    sessionRole: "角色",
    sessionTenant: "租户",
    sessionCreatedAt: "创建时间",
    sessionExpiry: "令牌过期时间（秒）",
    sessionSource: "会话来源",
    sessionSourceLabels: {
      login: "登录后",
      register: "注册后",
      stored: "浏览器已存储会话",
      refreshed: "刷新后",
    },
    openDashboard: "进入仪表盘",
    refreshSession: "刷新会话",
    logout: "执行登出",
    switchLabel: "其他入口",
    switchLinks: {
      login: "使用现有账号",
      register: "创建新租户",
    },
    submitting: "处理中...",
    successLabels: {
      login: "登录成功，浏览器会话已保存。",
      register: "注册成功，浏览器会话已保存。",
      sessionRefreshed: "已通过刷新令牌更新浏览器会话。",
      logout: "登出完成，浏览器会话已清除。",
      sessionRestored: "已恢复浏览器中保存的会话。",
      sessionCleared: "已清除浏览器会话。",
    },
    errorLabels: {
      login: "无法完成登录请求。",
      register: "无法完成注册请求。",
      refresh: "无法完成刷新请求。",
      logout: "无法完成登出请求。",
      session: "无法验证已保存的会话。",
    },
  },
};

function persistTokens(tokens: TokenResponse) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEYS.access, tokens.access_token);
  window.localStorage.setItem(STORAGE_KEYS.refresh, tokens.refresh_token);
  // ★새 토큰 적용 직후 소유자 검사: 이전 계정 로컬데이터가 남아있으면 즉시 비운다(계정 격리).
  ensureDataOwner();
}

function clearTokens() {
  if (typeof window === "undefined") {
    return;
  }
  // ★로그아웃: 분석/프로젝트 로컬데이터 + 소유자표식 완전 제거(계정 간 격리).
  clearOnLogout();
  window.localStorage.removeItem(STORAGE_KEYS.access);
  window.localStorage.removeItem(STORAGE_KEYS.refresh);
}

function hasStoredAccessToken() {
  if (typeof window === "undefined") {
    return false;
  }
  return Boolean(window.localStorage.getItem(STORAGE_KEYS.access)?.trim());
}

function getStoredRefreshToken() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(STORAGE_KEYS.refresh)?.trim() ?? "";
}

function hasStoredRefreshToken() {
  return Boolean(getStoredRefreshToken());
}

function isAuthFailure(error: unknown) {
  return (
    error instanceof ApiClientError &&
    (error.status === 401 || error.status === 403)
  );
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
    if (
      typeof error.payload === "object" &&
      error.payload !== null &&
      "message" in error.payload &&
      typeof (error.payload as { message?: unknown }).message === "string"
    ) {
      return (error.payload as { message: string }).message;
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

function formatDateTime(locale: Locale, value: string) {
  try {
    return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : locale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatRole(role: string) {
  return role
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

export function AuthWorkspaceClient({
  locale,
  defaultMode,
}: AuthWorkspaceClientProps) {
  const router = useRouter();
  const labels = LABELS[locale] || LABELS["ko"];
  const runtime = useMemo(() => apiClient.getRuntimeConfig(), []);
  const [mode, setMode] = useState<AuthMode>(defaultMode);
  const [session, setSession] = useState<SessionState | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(false);
  const [storedTokenPresent, setStoredTokenPresent] = useState(runtime.hasAccessToken);
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });
  const [registerForm, setRegisterForm] = useState({
    name: "",
    companyName: "",
    email: "",
    password: "",
  });

  const requestRefresh = useCallback(async () => {
    const refreshToken = getStoredRefreshToken();

    if (!refreshToken) {
      return null;
    }

    const tokens = await apiClient.post<TokenResponse>("/auth/refresh", {
      body: {
        refresh_token: refreshToken,
      },
      useMock: false,
    });

    persistTokens(tokens);
    setStoredTokenPresent(true);
    return tokens;
  }, []);

  const loadSession = useCallback(
    async (
      source: SessionState["source"],
      expiresIn: number | null,
      allowRefresh = true,
    ) => {
      if (!hasStoredAccessToken()) {
        if (allowRefresh && hasStoredRefreshToken()) {
          try {
            const refreshed = await requestRefresh();
            if (refreshed) {
              await loadSession(
                source === "stored" ? "stored" : "refreshed",
                refreshed.expires_in,
                false,
              );
              return;
            }
          } catch {
            // fall through to local clear and feedback below
          }
        }

        setSession(null);
        setStoredTokenPresent(false);
        setIsSessionLoading(false);
        return;
      }

      setIsSessionLoading(true);

      try {
        const user = await apiClient.get<UserResponse>("/auth/me", { useMock: false });
        setSession({ user, expiresIn, source });
        setStoredTokenPresent(true);

        // 로그인 성공 → 대시보드 홈으로 자동 이동 (홈은 /{locale}, /dashboard 라우트는 없음=404)
        if (source === "login" || source === "register") {
          router.push(`/${locale}`);
          return;
        }
      } catch (error) {
        if (allowRefresh && hasStoredRefreshToken() && isAuthFailure(error)) {
          try {
            const refreshed = await requestRefresh();
            if (refreshed) {
              await loadSession(
                source === "stored" ? "stored" : "refreshed",
                refreshed.expires_in,
                false,
              );
              return;
            }
          } catch (refreshError) {
            clearTokens();
            setSession(null);
            setStoredTokenPresent(false);
            setFeedback({
              tone: "error",
              message: resolveApiErrorMessage(
                refreshError,
                labels.errorLabels.refresh,
              ),
            });
            return;
          }
        }

        clearTokens();
        setSession(null);
        setStoredTokenPresent(false);
        setFeedback({
          tone: "error",
          message: resolveApiErrorMessage(error, labels.errorLabels.session),
        });
      } finally {
        setIsSessionLoading(false);
      }
    },
    [labels, requestRefresh],
  );

  useEffect(() => {
    if (typeof window === "undefined" || !hasStoredAccessToken()) {
      return;
    }

    void loadSession("stored", null);
  }, [loadSession]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setFeedback(null);

    try {
      const tokens =
        mode === "login"
          ? await apiClient.post<TokenResponse>("/auth/login", {
              body: loginForm,
              useMock: false,
            })
          : await apiClient.post<TokenResponse>("/auth/register", {
              body: {
                name: registerForm.name,
                company_name: registerForm.companyName,
                email: registerForm.email,
                password: registerForm.password,
              },
              useMock: false,
            });

      persistTokens(tokens);
      setStoredTokenPresent(true);
      // ★로그인/등록 성공 시 즉시 대시보드로 이동 — 추가 /auth/me 왕복을 기다리지 않아
      //  perceived 로딩시간이 절반↓. 세션 검증은 대시보드(ProjectSyncProvider/AuthButton)가 수행.
      if (mode === "login" || mode === "register") {
        router.push(`/${locale}`);
        return;
      }
      await loadSession(mode, tokens.expires_in);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: resolveApiErrorMessage(
          error,
          mode === "login" ? labels.errorLabels.login : labels.errorLabels.register,
        ),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRefreshSession = async () => {
    setIsSubmitting(true);
    setFeedback(null);

    try {
      const refreshed = await requestRefresh();
      if (!refreshed) {
        setFeedback({
          tone: "error",
          message: labels.errorLabels.refresh,
        });
        return;
      }

      await loadSession("refreshed", refreshed.expires_in, false);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: resolveApiErrorMessage(error, labels.errorLabels.refresh),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogout = async () => {
    setIsSubmitting(true);

    try {
      const refreshToken = getStoredRefreshToken();
      if (refreshToken) {
        await apiClient.post("/auth/logout", {
          body: {
            refresh_token: refreshToken,
          },
          useMock: false,
        });
      }
      setFeedback({
        tone: "success",
        message: labels.successLabels.logout,
      });
    } catch {
      setFeedback({
        tone: "info",
        message: labels.successLabels.sessionCleared,
      });
    } finally {
      clearTokens();
      setSession(null);
      setStoredTokenPresent(false);
      setIsSubmitting(false);
    }
  };

  const feedbackClassName =
    feedback?.tone === "error"
      ? "border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
      : feedback?.tone === "success"
        ? "border-[rgba(13,148,136,0.28)] bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
        : "border-[rgba(14,116,144,0.24)] bg-[rgba(14,116,144,0.08)] text-[rgb(14,116,144)]";

  const gateMeta = mode === "register" ? "ENROLL TENANT" : "SECURE ACCESS";
  const gateTitle = mode === "register" ? "사통팔땅 관리자 등록" : "사통팔땅 로그인";
  const gateDescription =
    mode === "register"
      ? "새 테넌트와 첫 관리자 계정을 생성합니다."
      : "서비스 이용을 위해 계정에 로그인해 주세요.";

  return (
    <main className="relative isolate mx-auto flex min-h-screen max-w-6xl items-center px-6 py-10">
      {/* 관제탑 게이트 배경 — 정밀 그리드 + 미세 주사선(고정 백드롭, 폼 무영향) */}
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[var(--surface-soft)]">
        <div className="cc-grid-bg cc-grid-bg--radial" />
        <div className="cc-scanline" />
      </div>

      <section className="mx-auto w-full max-w-lg">
        <Card className="cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
          {/* HUD 코너 브래킷 ⌜ ⌝ ⌞ ⌟ */}
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />
          <CardContent className="relative p-8 md:p-10">
            <div className="mb-6 space-y-3">
              {/* 모노 메타라벨 + 실시간 가동 도트 */}
              <div className="flex items-center justify-between gap-3">
                <span className="cc-meta">{gateMeta} · 사통팔땅</span>
                <span className="cc-live">
                  <i />
                  LIVE
                </span>
              </div>
              <h1 className="text-3xl font-bold text-[var(--text-primary)] md:text-4xl">
                {gateTitle}
              </h1>
              <p className="text-sm leading-7 text-[var(--text-secondary)] md:text-base">
                {gateDescription}
              </p>
            </div>

            <div className="cc-panel">
              <header className="cc-panel__head">
                <span className="cc-label text-[var(--text-secondary)]">
                  {mode === "register" ? "CREDENTIALS · 신규" : "CREDENTIALS · 게이트"}
                </span>
                <span className="cc-chip-data">
                  {runtime.mode === "live" ? "LIVE" : "MOCK"}
                </span>
              </header>
              <div className="cc-panel__body">

              <form className="grid gap-4" onSubmit={handleSubmit}>
                {mode === "register" ? (
                  <>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.registerFields.name}</span>
                      <Input
                        name="name"
                        value={registerForm.name}
                        onChange={(event) =>
                          setRegisterForm((current) => ({
                            ...current,
                            name: event.target.value,
                          }))
                        }
                        placeholder={labels.registerFields.name}
                        required
                        minLength={1}
                        maxLength={100}
                      />
                    </label>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.registerFields.companyName}</span>
                      <Input
                        name="companyName"
                        value={registerForm.companyName}
                        onChange={(event) =>
                          setRegisterForm((current) => ({
                            ...current,
                            companyName: event.target.value,
                          }))
                        }
                        placeholder={labels.registerFields.companyName}
                        maxLength={200}
                      />
                    </label>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.registerFields.email}</span>
                      <Input
                        name="email"
                        type="email"
                        value={registerForm.email}
                        onChange={(event) =>
                          setRegisterForm((current) => ({
                            ...current,
                            email: event.target.value,
                          }))
                        }
                        placeholder="admin@company.com"
                        required
                      />
                    </label>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.registerFields.password}</span>
                      <Input
                        name="password"
                        type="password"
                        value={registerForm.password}
                        onChange={(event) =>
                          setRegisterForm((current) => ({
                            ...current,
                            password: event.target.value,
                          }))
                        }
                        placeholder="********"
                        required
                        minLength={8}
                      />
                    </label>
                    <Button type="submit" disabled={isSubmitting}>
                      {isSubmitting ? labels.submitting : labels.registerFields.submit}
                    </Button>
                  </>
                ) : (
                  <>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.loginFields.email}</span>
                      <Input
                        name="email"
                        type="email"
                        value={loginForm.email}
                        onChange={(event) =>
                          setLoginForm((current) => ({
                            ...current,
                            email: event.target.value,
                          }))
                        }
                        placeholder="operator@company.com"
                        required
                      />
                    </label>
                    <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                      <span>{labels.loginFields.password}</span>
                      <Input
                        name="password"
                        type="password"
                        value={loginForm.password}
                        onChange={(event) =>
                          setLoginForm((current) => ({
                            ...current,
                            password: event.target.value,
                          }))
                        }
                        placeholder="********"
                        required
                      />
                    </label>
                    <Button type="submit" disabled={isSubmitting}>
                      {isSubmitting ? labels.submitting : labels.loginFields.submit}
                    </Button>
                    <div className="relative my-4 flex items-center">
                      <div className="flex-grow border-t border-[var(--line-subtle)]"></div>
                      <span className="cc-label mx-4 text-[var(--text-tertiary)]">SNS · 간편 로그인</span>
                      <div className="flex-grow border-t border-[var(--line-subtle)]"></div>
                    </div>
                    <div className="grid gap-2">
                      <button
                        type="button"
                        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-md)] px-4 py-2.5 text-sm font-semibold transition-all hover:brightness-95 active:scale-[0.98]"
                        style={{ backgroundColor: "#FEE500", color: "#000000" }}
                        onClick={async () => {
                          try {
                            // ★카카오는 콜백 시 redirect_uri를 돌려주지 않으므로(코드만 전달),
                            //  로그인 단계에서 "현재 도메인 기준 콜백주소"를 명시 전달해야
                            //  콜백 교환 때와 정확히 일치한다(불일치=KOE006). 환경(www/no-www/로컬) 무관 정확.
                            const redirectUri = `${window.location.origin}/${locale}/kakao/callback`;
                            // 서버가 REST 키로 카카오 인가 URL을 조립해 반환(키 비노출) → 이동.
                            const res = await apiClient.get<{ url: string }>(
                              `/auth/kakao/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
                              { useMock: false },
                            );
                            if (res?.url) window.location.href = res.url;
                          } catch {
                            alert("카카오 로그인 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
                          }
                        }}
                      >
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
                          <path d="M12 3C6.477 3 2 6.556 2 10.944c0 2.825 1.848 5.292 4.673 6.643-.24 1.144-1.127 4.148-1.18 4.402-.066.315.11.312.243.224.103-.069 3.528-2.324 4.887-3.216.44.062.89.096 1.349.096 5.523 0 10-3.556 10-7.944C22 6.556 17.523 3 12 3z"/>
                        </svg>
                        카카오 로그인
                      </button>
                      <button
                        type="button"
                        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-md)] px-4 py-2.5 text-sm font-semibold transition-all hover:brightness-95 active:scale-[0.98]"
                        style={{ backgroundColor: "#03C75A", color: "#FFFFFF" }}
                        onClick={async () => {
                          try {
                            // ★카카오와 동일 패턴: 현재 도메인 기준 콜백주소를 명시 전달해야
                            //  토큰 교환 때와 정확히 일치한다(불일치=CSRF/redirect 오류).
                            const redirectUri = `${window.location.origin}/${locale}/naver/callback`;
                            // 서버가 client_id로 인가 URL을 조립해 반환(키 비노출) + state(CSRF) 발급.
                            const res = await apiClient.get<{ url: string; state?: string }>(
                              `/auth/naver/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
                              { useMock: false },
                            );
                            // ★네이버 state는 콜백에서 회신·검증해야 하므로 sessionStorage에 보관(CSRF 방지).
                            if (res?.state) {
                              window.sessionStorage.setItem("naver_oauth_state", res.state);
                            }
                            if (res?.url) window.location.href = res.url;
                          } catch (error) {
                            // 키 미등록(503) → 관리자 안내. 그 외도 동일 안내.
                            const msg =
                              error instanceof ApiClientError && error.status === 503
                                ? "네이버 로그인 미설정(관리자 키 등록 필요)입니다."
                                : "네이버 로그인 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
                            alert(msg);
                          }
                        }}
                      >
                        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
                          <path d="M16.273 12.845 7.376 0H0v24h7.727V11.155L16.624 24H24V0h-7.727v12.845z"/>
                        </svg>
                        네이버 로그인
                      </button>
                      <button
                        type="button"
                        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-md)] border border-[var(--line)] bg-white px-4 py-2.5 text-sm font-semibold text-black transition-all hover:bg-gray-50 active:scale-[0.98]"
                        onClick={async () => {
                          try {
                            // ★카카오와 동일 패턴: 현재 도메인 기준 콜백주소 명시 전달(교환 시 1:1 일치).
                            const redirectUri = `${window.location.origin}/${locale}/google/callback`;
                            // 서버가 client_id로 인가 URL을 조립해 반환(키 비노출) → 이동.
                            const res = await apiClient.get<{ url: string }>(
                              `/auth/google/login-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
                              { useMock: false },
                            );
                            if (res?.url) window.location.href = res.url;
                          } catch (error) {
                            const msg =
                              error instanceof ApiClientError && error.status === 503
                                ? "구글 로그인 미설정(관리자 키 등록 필요)입니다."
                                : "구글 로그인 준비 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
                            alert(msg);
                          }
                        }}
                      >
                        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                        </svg>
                        Google 로그인
                      </button>
                    </div>
                  </>
                )}
              </form>

              {feedback ? (
                <div
                  className={`mt-4 rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClassName}`}
                  role="status"
                >
                  {feedback.message}
                </div>
              ) : null}
              </div>
            </div>

            {/* 인증 경로 전환 + 시스템 메타 푸터 */}
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <Link
                href={`/${locale}/${mode === "login" ? "register" : "login"}`}
                className="cc-label text-[var(--accent-strong)] underline-offset-4 hover:underline"
              >
                {mode === "login"
                  ? labels.switchLinks.register + " →"
                  : "← " + labels.switchLinks.login}
              </Link>
              <span className="cc-label text-[var(--text-tertiary)]">
                ENCRYPTED · JWT
              </span>
            </div>

            {/* 법적 고지 — 가입·이용 시 동의 대상 문서 링크(비로그인 열람 가능) */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
              <span>가입·이용 시 아래 약관에 동의하는 것으로 간주됩니다.</span>
              <span className="flex items-center gap-2">
                <Link href={`/${locale}/legal/terms`} className="text-[var(--text-secondary)] underline-offset-4 hover:text-[var(--text-primary)] hover:underline">서비스이용약관</Link>
                <span aria-hidden>·</span>
                <Link href={`/${locale}/legal/privacy`} className="text-[var(--text-secondary)] underline-offset-4 hover:text-[var(--text-primary)] hover:underline">개인정보처리방침</Link>
              </span>
            </div>

          </CardContent>
        </Card>

        {/* 런타임/세션 디버그 패널 제거 — 프로덕션에서 불필요 */}
        {/* eslint-disable-next-line no-constant-condition */}
        {(false as boolean) && <div className="grid gap-6">
          <Card className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-6">
              <CardTitle className="text-xl text-[var(--text-primary)]">
                {labels.runtimeTitle}
              </CardTitle>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.runtimeDescription}
              </p>
              <dl className="mt-5 grid gap-3 text-sm">
                <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                  <dt className="text-[var(--text-tertiary)]">{labels.runtimeMode}</dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {runtime.mode === "live"
                      ? labels.runtimeModeLabels.live
                      : labels.runtimeModeLabels.mock}
                  </dd>
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                  <dt className="text-[var(--text-tertiary)]">{labels.runtimeApiBase}</dt>
                  <dd className="mt-1 break-all font-mono text-xs text-[var(--text-primary)]">
                    {runtime.apiBaseUrl}
                  </dd>
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                  <dt className="text-[var(--text-tertiary)]">{labels.runtimeToken}</dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {storedTokenPresent || session ? labels.tokenPresent : labels.tokenMissing}
                  </dd>
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
                  <dt className="text-[var(--text-tertiary)]">
                    {labels.runtimeRefreshToken}
                  </dt>
                  <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                    {hasStoredRefreshToken() ? labels.tokenPresent : labels.tokenMissing}
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-6">
              <CardTitle className="text-xl text-[var(--text-primary)]">
                {labels.sessionTitle}
              </CardTitle>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.sessionDescription}
              </p>

              <div className="mt-5 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] p-5">
                {isSessionLoading ? (
                  <p className="text-sm text-[var(--text-secondary)]">
                    {labels.sessionLoading}
                  </p>
                ) : session ? (
                  <div className="space-y-4">
                    <div>
                      <p className="text-lg font-semibold text-[var(--text-primary)]">
                        {session.user.name}
                      </p>
                      <p className="text-sm text-[var(--text-tertiary)]">
                        {session.user.email}
                      </p>
                    </div>
                    <dl className="grid gap-3 text-sm">
                      <div className="grid gap-1">
                        <dt className="text-[var(--text-tertiary)]">{labels.sessionRole}</dt>
                        <dd className="font-semibold text-[var(--text-primary)]">
                          {formatRole(session.user.role)}
                        </dd>
                      </div>
                      <div className="grid gap-1">
                        <dt className="text-[var(--text-tertiary)]">{labels.sessionTenant}</dt>
                        <dd className="break-all font-mono text-xs text-[var(--text-primary)]">
                          {session.user.tenant_id}
                        </dd>
                      </div>
                      <div className="grid gap-1">
                        <dt className="text-[var(--text-tertiary)]">{labels.sessionCreatedAt}</dt>
                        <dd className="text-[var(--text-primary)]">
                          {formatDateTime(locale, session.user.created_at)}
                        </dd>
                      </div>
                      <div className="grid gap-1">
                        <dt className="text-[var(--text-tertiary)]">{labels.sessionExpiry}</dt>
                        <dd className="text-[var(--text-primary)]">
                          {session.expiresIn ?? "n/a"}
                        </dd>
                      </div>
                      <div className="grid gap-1">
                        <dt className="text-[var(--text-tertiary)]">{labels.sessionSource}</dt>
                        <dd className="text-[var(--text-primary)]">
                          {labels.sessionSourceLabels[session.source]}
                        </dd>
                      </div>
                    </dl>
                    <div className="flex flex-wrap gap-3">
                      <Button onClick={() => router.push(`/${locale}`)}>
                        {labels.openDashboard}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          void handleRefreshSession();
                        }}
                        disabled={isSubmitting || !hasStoredRefreshToken()}
                      >
                        {labels.refreshSession}
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          void handleLogout();
                        }}
                        disabled={isSubmitting}
                      >
                        {labels.logout}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-[var(--text-secondary)]">
                    {labels.sessionEmpty}
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>}
      </section>
    </main>
  );
}
