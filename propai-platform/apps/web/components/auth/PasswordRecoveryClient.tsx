"use client";

/**
 * 비밀번호 분실 복구 플로우(회원 시스템 2026-07).
 *
 * - ForgotPasswordClient: 이메일 입력 → POST /auth/password/forgot.
 *   서버는 계정 존재 여부와 무관하게 항상 동일 200(열거 방지) — UI도 동일 안내만 표시.
 * - ResetPasswordClient: 링크(?token=...) 진입 → GET /auth/password/reset/validate 로
 *   사전 확인 → 유효하면 새 비밀번호 입력 → POST /auth/password/reset.
 *   만료(발송 후 30분)·사용됨이면 재요청 안내.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

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

function AuthShell({ meta, title, description, children }: {
  meta: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <main className="relative isolate mx-auto flex min-h-screen max-w-6xl items-center px-6 py-10">
      <div className="pointer-events-none fixed inset-0 -z-10 bg-[var(--surface-soft)]">
        <div className="cc-grid-bg cc-grid-bg--radial" />
        <div className="cc-scanline" />
      </div>
      <section className="mx-auto w-full max-w-lg">
        <Card className="cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />
          <CardContent className="relative p-8 md:p-10">
            <div className="mb-6 space-y-3">
              <span className="cc-meta">{meta} · 사통팔땅</span>
              <h1 className="text-3xl font-bold text-[var(--text-primary)]">{title}</h1>
              <p className="text-sm leading-7 text-[var(--text-secondary)]">{description}</p>
            </div>
            {children}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  비밀번호 찾기                                                       */
/* ------------------------------------------------------------------ */

export function ForgotPasswordClient({ locale }: { locale: Locale }) {
  const [email, setEmail] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [requested, setRequested] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setFeedback(null);
    try {
      const res = await apiClient.post<{ message: string }>("/auth/password/forgot", {
        body: { email },
        useMock: false,
      });
      // 서버 계약: 계정 존재 여부와 무관하게 동일 메시지(열거 방지)
      setRequested(true);
      setFeedback({
        tone: "success",
        message: `${res.message} 메일이 도착하지 않으면 스팸함을 확인해 주세요. 링크는 발송 후 30분 이내 1회만 사용할 수 있습니다.`,
      });
    } catch (error) {
      const status = error instanceof ApiClientError ? error.status : 0;
      setFeedback({
        tone: "error",
        message:
          status === 429
            ? resolveErrorMessage(error, "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
            : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthShell
      meta="RECOVERY"
      title="비밀번호 찾기"
      description="가입하신 이메일 주소를 입력하면 비밀번호 재설정 링크를 보내드립니다."
    >
      <form className="grid gap-4" onSubmit={handleSubmit}>
        <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
          <span>이메일</span>
          <Input
            name="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="가입한 이메일 주소"
            required
            disabled={requested}
          />
        </label>
        <Button type="submit" disabled={isSubmitting || requested}>
          {isSubmitting ? "처리 중..." : requested ? "발송 요청 완료" : "재설정 링크 받기"}
        </Button>
      </form>
      {feedback ? (
        <div
          className={`mt-4 rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(feedback.tone)}`}
          role="status"
        >
          {feedback.message}
        </div>
      ) : null}
      <div className="mt-6 flex items-center justify-between text-sm">
        <Link
          href={`/${locale}/login`}
          className="cc-label text-[var(--accent-strong)] underline-offset-4 hover:underline"
        >
          ← 로그인으로 돌아가기
        </Link>
        <span className="text-xs text-[var(--text-tertiary)]">
          소셜 로그인 계정은 해당 소셜 서비스에서 로그인해 주세요.
        </span>
      </div>
    </AuthShell>
  );
}

/* ------------------------------------------------------------------ */
/*  비밀번호 재설정                                                     */
/* ------------------------------------------------------------------ */

type ResetPhase = "checking" | "invalid" | "ready" | "done";

export function ResetPasswordClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [phase, setPhase] = useState<ResetPhase>("checking");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      if (!token) {
        setPhase("invalid");
        return;
      }
      try {
        const res = await apiClient.get<{ valid: boolean }>(
          `/auth/password/reset/validate?token=${encodeURIComponent(token)}`,
          { useMock: false },
        );
        if (!cancelled) setPhase(res.valid ? "ready" : "invalid");
      } catch {
        if (!cancelled) setPhase("invalid");
      }
    };
    void check();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password !== passwordConfirm) {
      setFeedback({ tone: "error", message: "새 비밀번호가 서로 일치하지 않습니다." });
      return;
    }
    setIsSubmitting(true);
    setFeedback(null);
    try {
      const res = await apiClient.post<{ message: string }>("/auth/password/reset", {
        body: { token, new_password: password },
        useMock: false,
      });
      setPhase("done");
      setFeedback({ tone: "success", message: res.message });
    } catch (error) {
      const status = error instanceof ApiClientError ? error.status : 0;
      if (status === 400) {
        // 만료/사용됨/무효 — 서버 통일 메시지 그대로 표시
        setFeedback({
          tone: "error",
          message: resolveErrorMessage(error, "유효하지 않거나 만료된 링크입니다."),
        });
        setPhase("invalid");
      } else if (status === 422) {
        setFeedback({
          tone: "error",
          message:
            "비밀번호 정책을 확인해 주세요 — 10자 이상, 영문 대/소문자·숫자·특수문자 중 3종 이상.",
        });
      } else {
        setFeedback({
          tone: "error",
          message: "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AuthShell
      meta="RESET"
      title="비밀번호 재설정"
      description="새 비밀번호를 설정합니다. 완료되면 보안을 위해 모든 기기에서 로그아웃됩니다."
    >
      {phase === "checking" ? (
        <p className="text-sm text-[var(--text-secondary)]">링크를 확인하는 중입니다...</p>
      ) : null}

      {phase === "invalid" ? (
        <div className="grid gap-4">
          <div className={`rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass("error")}`}>
            링크가 만료되었거나 이미 사용되었습니다. 재설정 링크는 발송 후 30분 이내 1회만
            사용할 수 있습니다.
          </div>
          <Button onClick={() => router.push(`/${locale}/forgot-password`)}>
            재설정 링크 다시 요청하기
          </Button>
        </div>
      ) : null}

      {phase === "ready" ? (
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
            <span>새 비밀번호</span>
            <Input
              name="new-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="10자 이상 · 영문/숫자/특수문자 조합"
              required
              minLength={10}
              autoComplete="new-password"
            />
            <span className="text-xs font-normal text-[var(--text-tertiary)]">
              10자 이상, 영문 대/소문자·숫자·특수문자 중 3종 이상을 조합해 주세요.
            </span>
          </label>
          <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
            <span>새 비밀번호 확인</span>
            <Input
              name="new-password-confirm"
              type="password"
              value={passwordConfirm}
              onChange={(event) => setPasswordConfirm(event.target.value)}
              placeholder="한 번 더 입력"
              required
              minLength={10}
              autoComplete="new-password"
            />
          </label>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "처리 중..." : "비밀번호 변경"}
          </Button>
        </form>
      ) : null}

      {phase === "done" ? (
        <div className="grid gap-4">
          <Button onClick={() => router.push(`/${locale}/login`)}>로그인하러 가기</Button>
        </div>
      ) : null}

      {feedback && phase !== "invalid" ? (
        <div
          className={`mt-4 rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(feedback.tone)}`}
          role="status"
        >
          {feedback.message}
        </div>
      ) : null}
    </AuthShell>
  );
}

/* ------------------------------------------------------------------ */
/*  이메일 인증 확인                                                    */
/* ------------------------------------------------------------------ */

export function VerifyEmailClient({ locale }: { locale: Locale }) {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [state, setState] = useState<"working" | "success" | "failed">("working");
  const [message, setMessage] = useState("이메일 인증을 확인하는 중입니다...");

  useEffect(() => {
    let cancelled = false;
    const confirm = async () => {
      if (!token) {
        setState("failed");
        setMessage("인증 링크가 올바르지 않습니다. 메일의 링크를 다시 확인해 주세요.");
        return;
      }
      try {
        const res = await apiClient.post<{ message: string }>("/auth/email/verify/confirm", {
          body: { token },
          useMock: false,
        });
        if (!cancelled) {
          setState("success");
          setMessage(res.message);
        }
      } catch (error) {
        if (!cancelled) {
          setState("failed");
          setMessage(
            resolveErrorMessage(
              error,
              "인증 링크가 만료되었거나 이미 사용되었습니다. 계정 화면에서 인증 메일을 다시 요청해 주세요.",
            ),
          );
        }
      }
    };
    void confirm();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthShell
      meta="VERIFY"
      title="이메일 인증"
      description="회원가입 시 발송된 인증 링크를 확인합니다."
    >
      <div
        className={`rounded-[var(--radius-md)] border px-4 py-3 text-sm ${feedbackClass(
          state === "success" ? "success" : state === "failed" ? "error" : "info",
        )}`}
        role="status"
      >
        {message}
      </div>
      <div className="mt-6">
        <Link
          href={`/${locale}`}
          className="cc-label text-[var(--accent-strong)] underline-offset-4 hover:underline"
        >
          ← 홈으로 이동
        </Link>
      </div>
    </AuthShell>
  );
}
