"use client";

/**
 * 내 계정 · 보안(일반 회원용 — 관리자 콘솔과 별개).
 *
 * - 프로필 요약(/auth/me) + 이메일 인증 상태·재발송
 * - 비밀번호 변경(현재 비밀번호 확인 → 성공 시 전 기기 로그아웃 → 재로그인 유도)
 * - 회원탈퇴(영향 고지 → 본인확인 → POST /auth/account/withdraw → 세션 정리)
 *   · 비밀번호 계정: 비밀번호 재확인 / 소셜 전용 계정: 최근 재로그인 필요(서버 검증)
 *   · 조직에 다른 이용자가 있는 유일 관리자는 서버가 409로 이관을 요구(안내 표시)
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { clearOnLogout } from "@/lib/projectSync";
import type { Locale } from "@/i18n/config";

type MeResponse = {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
  email_verified?: boolean;
  has_password?: boolean;
};

type Feedback = { tone: "success" | "error" | "info"; message: string };

function feedbackClass(tone: Feedback["tone"]): string {
  if (tone === "error") {
    return "border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]";
  }
  if (tone === "success") {
    return "border-[rgba(13,148,136,0.28)] bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]";
  }
  return "border-[rgba(14,116,144,0.24)] bg-[rgba(14,116,144,0.08)] text-[rgb(14,116,144)]";
}

function resolveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    const payload = error.payload as { detail?: unknown } | null;
    if (payload && typeof payload.detail === "string") return payload.detail;
  }
  return fallback;
}

function clearSessionAndGo(router: ReturnType<typeof useRouter>, target: string) {
  clearOnLogout();
  window.localStorage.removeItem("propai_access_token");
  window.localStorage.removeItem("propai_refresh_token");
  router.push(target);
}

export function AccountSecurityClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 비밀번호 변경 폼
  const [pwForm, setPwForm] = useState({ current: "", next: "", confirm: "" });
  const [pwFeedback, setPwFeedback] = useState<Feedback | null>(null);
  const [pwSubmitting, setPwSubmitting] = useState(false);

  // 이메일 인증
  const [verifyFeedback, setVerifyFeedback] = useState<Feedback | null>(null);
  const [verifySubmitting, setVerifySubmitting] = useState(false);

  // 탈퇴 폼
  const [showWithdraw, setShowWithdraw] = useState(false);
  const [wdForm, setWdForm] = useState({ password: "", reason: "", confirmText: "" });
  const [wdFeedback, setWdFeedback] = useState<Feedback | null>(null);
  const [wdSubmitting, setWdSubmitting] = useState(false);

  const loadMe = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const user = await apiClient.get<MeResponse>("/auth/me", { useMock: false });
      setMe(user);
    } catch (error) {
      const status = error instanceof ApiClientError ? error.status : 0;
      setLoadError(
        status === 401 || status === 403
          ? "로그인이 필요합니다."
          : "계정 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  const handleChangePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pwForm.next !== pwForm.confirm) {
      setPwFeedback({ tone: "error", message: "새 비밀번호가 서로 일치하지 않습니다." });
      return;
    }
    setPwSubmitting(true);
    setPwFeedback(null);
    try {
      const res = await apiClient.post<{ message: string }>("/auth/password/change", {
        body: { current_password: pwForm.current, new_password: pwForm.next },
        useMock: false,
        // 현재 비밀번호 오입력 시 서버가 401을 반환 — 이는 세션만료가 아니라 폼 검증 실패이므로
        // 전역 세션만료 처리(강제 로그아웃·토큰 파기)를 건너뛰고 폼에서 정직하게 안내한다.
        skipSessionExpiry: true,
      });
      setPwFeedback({ tone: "success", message: `${res.message} 3초 후 로그인 화면으로 이동합니다.` });
      // 전 기기 로그아웃(서버 refresh 전량 revoke) — 로컬 세션도 정리 후 재로그인 유도
      setTimeout(() => clearSessionAndGo(router, `/${locale}/login`), 3000);
    } catch (error) {
      const status = error instanceof ApiClientError ? error.status : 0;
      setPwFeedback({
        tone: "error",
        message:
          status === 422
            ? "새 비밀번호 정책을 확인해 주세요 — 10자 이상, 영문 대/소문자·숫자·특수문자 중 3종 이상."
            : resolveErrorMessage(error, "비밀번호 변경을 처리하지 못했습니다."),
      });
    } finally {
      setPwSubmitting(false);
    }
  };

  const handleRequestVerify = async () => {
    setVerifySubmitting(true);
    setVerifyFeedback(null);
    try {
      const res = await apiClient.post<{ message: string }>("/auth/email/verify/request", {
        body: {},
        useMock: false,
      });
      setVerifyFeedback({ tone: "success", message: res.message });
    } catch (error) {
      setVerifyFeedback({
        tone: "error",
        message: resolveErrorMessage(error, "인증 메일 요청을 처리하지 못했습니다."),
      });
    } finally {
      setVerifySubmitting(false);
    }
  };

  const handleWithdraw = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (wdForm.confirmText.trim() !== "탈퇴합니다") {
      setWdFeedback({ tone: "error", message: "확인 문구 “탈퇴합니다”를 정확히 입력해 주세요." });
      return;
    }
    setWdSubmitting(true);
    setWdFeedback(null);
    try {
      await apiClient.post("/auth/account/withdraw", {
        body: {
          password: me?.has_password === false ? undefined : wdForm.password,
          reason: wdForm.reason.trim() || undefined,
        },
        useMock: false,
        // 비밀번호 오입력(401)·소셜 재인증 필요(403)는 세션만료가 아니라 본인확인 실패이므로
        // 전역 강제 로그아웃을 건너뛰고 폼에서 안내한다.
        skipSessionExpiry: true,
      });
      setWdFeedback({
        tone: "success",
        message: "탈퇴가 완료되었습니다. 이용해 주셔서 감사합니다. 잠시 후 홈으로 이동합니다.",
      });
      setTimeout(() => clearSessionAndGo(router, `/${locale}`), 2500);
    } catch (error) {
      // 409: 조직 이관 필요 / 403: 소셜 재로그인 필요 — 서버 통상어 안내 그대로 표시
      setWdFeedback({
        tone: "error",
        message: resolveErrorMessage(error, "탈퇴 요청을 처리하지 못했습니다."),
      });
    } finally {
      setWdSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 pb-20">
        <div className="h-10 w-56 animate-pulse rounded-xl bg-[var(--surface-soft)]" />
        <div className="h-40 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        <div className="h-64 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
      </div>
    );
  }

  if (loadError || !me) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-4 py-24 text-center">
        <p className="text-sm text-[var(--text-secondary)]">{loadError ?? "계정 정보를 불러오지 못했습니다."}</p>
        <Button onClick={() => router.push(`/${locale}/login`)}>로그인하러 가기</Button>
      </div>
    );
  }

  const isSocialOnly = me.has_password === false;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 pb-20">
      <div className="space-y-2">
        <span className="cc-meta">ACCOUNT · SECURITY</span>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">내 계정 · 보안</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          비밀번호와 계정 상태를 관리합니다. 탈퇴 즉시 로그인이 차단되며 복구할 수 없습니다.
        </p>
      </div>

      {/* 프로필 + 이메일 인증 */}
      <Card className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)]">
        <CardContent className="grid gap-4 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-lg font-bold text-[var(--text-primary)]">{me.name}</p>
              <p className="text-sm text-[var(--text-tertiary)]">{me.email}</p>
            </div>
            <span
              className={`rounded-full border px-3 py-1 text-xs font-bold ${
                me.email_verified
                  ? "border-[rgba(13,148,136,0.3)] text-[rgb(15,118,110)]"
                  : "border-[rgba(217,119,6,0.35)] text-[rgb(146,64,14)]"
              }`}
            >
              {me.email_verified ? "이메일 인증 완료" : "이메일 미인증"}
            </span>
          </div>
          {!me.email_verified ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
              <p className="text-sm text-[var(--text-secondary)]">
                이메일 인증을 완료하면 계정 보안이 강화되고 중요한 안내를 이메일로 받을 수 있습니다.
              </p>
              <Button variant="secondary" onClick={() => void handleRequestVerify()} disabled={verifySubmitting}>
                {verifySubmitting ? "요청 중..." : "인증 메일 보내기"}
              </Button>
            </div>
          ) : null}
          {verifyFeedback ? (
            <div role="status" className={`rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(verifyFeedback.tone)}`}>
              {verifyFeedback.message}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* 비밀번호 변경 */}
      <Card className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)]">
        <CardContent className="grid gap-4 p-6">
          <h2 className="text-lg font-bold text-[var(--text-primary)]">비밀번호 변경</h2>
          {isSocialOnly ? (
            <p className="text-sm text-[var(--text-secondary)]">
              소셜 로그인 계정은 비밀번호가 없습니다. 로그인은 연결된 소셜 계정(카카오·구글·네이버)으로 진행됩니다.
            </p>
          ) : (
            <form className="grid gap-4" onSubmit={handleChangePassword}>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>현재 비밀번호</span>
                <Input
                  type="password"
                  value={pwForm.current}
                  onChange={(e) => setPwForm((c) => ({ ...c, current: e.target.value }))}
                  required
                  autoComplete="current-password"
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>새 비밀번호</span>
                <Input
                  type="password"
                  value={pwForm.next}
                  onChange={(e) => setPwForm((c) => ({ ...c, next: e.target.value }))}
                  required
                  minLength={10}
                  autoComplete="new-password"
                  placeholder="10자 이상 · 영문/숫자/특수문자 조합"
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>새 비밀번호 확인</span>
                <Input
                  type="password"
                  value={pwForm.confirm}
                  onChange={(e) => setPwForm((c) => ({ ...c, confirm: e.target.value }))}
                  required
                  minLength={10}
                  autoComplete="new-password"
                />
              </label>
              <div>
                <Button type="submit" disabled={pwSubmitting}>
                  {pwSubmitting ? "처리 중..." : "비밀번호 변경"}
                </Button>
              </div>
              <p className="text-xs text-[var(--text-tertiary)]">
                변경 즉시 보안을 위해 모든 기기에서 로그아웃되며 다시 로그인해야 합니다.
              </p>
            </form>
          )}
          {pwFeedback ? (
            <div role="status" className={`rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(pwFeedback.tone)}`}>
              {pwFeedback.message}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* 회원탈퇴 */}
      <Card className="rounded-[var(--radius-2xl)] border border-[rgba(217,119,6,0.35)] bg-[var(--surface-strong)]">
        <CardContent className="grid gap-4 p-6">
          <h2 className="text-lg font-bold text-[rgb(146,64,14)]">회원탈퇴</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text-secondary)]">
            <li>탈퇴 즉시 로그인과 모든 기기의 세션이 차단됩니다.</li>
            <li>30일 유예기간 이후 개인정보는 복구 불가능하게 익명화됩니다.</li>
            <li>관계 법령상 보존 의무가 있는 정보(계약·결제 기록 등)는 법정 기간 동안 분리 보관 후 파기됩니다.</li>
            <li>동일 이메일 재가입은 탈퇴 후 30일이 지나야 가능합니다.</li>
            <li>조직에 다른 구성원이 있는 경우, 소유권 이관 후 탈퇴할 수 있습니다.</li>
          </ul>
          {!showWithdraw ? (
            <div>
              <Button variant="secondary" onClick={() => setShowWithdraw(true)}>
                탈퇴 진행하기
              </Button>
            </div>
          ) : (
            <form className="grid gap-4" onSubmit={handleWithdraw}>
              {isSocialOnly ? (
                <p className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
                  소셜 로그인 계정은 본인 확인을 위해 <b>최근 10분 이내에 소셜 로그인</b>한 상태에서만
                  탈퇴할 수 있습니다. 오래 전에 로그인했다면 로그아웃 후 다시 로그인해 주세요.
                </p>
              ) : (
                <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                  <span>비밀번호 확인</span>
                  <Input
                    type="password"
                    value={wdForm.password}
                    onChange={(e) => setWdForm((c) => ({ ...c, password: e.target.value }))}
                    required
                    autoComplete="current-password"
                  />
                </label>
              )}
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>탈퇴 사유 (선택)</span>
                <Input
                  value={wdForm.reason}
                  onChange={(e) => setWdForm((c) => ({ ...c, reason: e.target.value }))}
                  maxLength={500}
                  placeholder="서비스 개선에 참고하겠습니다"
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>
                  확인 문구 입력: <b>탈퇴합니다</b>
                </span>
                <Input
                  value={wdForm.confirmText}
                  onChange={(e) => setWdForm((c) => ({ ...c, confirmText: e.target.value }))}
                  required
                  placeholder="탈퇴합니다"
                />
              </label>
              <div className="flex gap-3">
                <Button type="submit" disabled={wdSubmitting}>
                  {wdSubmitting ? "처리 중..." : "탈퇴 확정"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setShowWithdraw(false)}>
                  취소
                </Button>
              </div>
            </form>
          )}
          {wdFeedback ? (
            <div role="status" className={`rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(wdFeedback.tone)}`}>
              {wdFeedback.message}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
