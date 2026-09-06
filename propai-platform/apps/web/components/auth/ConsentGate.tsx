"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

/**
 * 동의 게이트 — 약관·개인정보 동의가 미완인 사용자에게 **동의 화면을 먼저** 보인다.
 *
 * ★서버(`_require_consent` 미들웨어)가 보호 자원을 403 으로 막는다. 이 화면이 없으면
 *   서버는 막는데 **동의할 자리가 없다** — 그래서 서버 배포보다 이것이 먼저다.
 *
 * ★모집단은 소셜만이 아니다. 2026-09-06 라이브 실측: 미동의 8명 중 **이메일이 6명**
 *   (동의 기능 도입 2026-08-27 이전 계정) · 소셜 2명. 그래서 소셜 전용 화면이 아니다.
 */
export const CONSENT_EXEMPT_SUFFIXES = ["/login", "/register", "/forgot-password"] as const;

/** 약관을 **읽을 수 있어야** 동의할 수 있다 — legal 경로는 게이트가 막지 않는다. */
export function isConsentExemptPath(pathname: string): boolean {
  if (pathname.includes("/legal")) return true;
  return CONSENT_EXEMPT_SUFFIXES.some((s) => pathname.endsWith(s));
}

type Me = { consent_pending?: boolean };

const COPY: Record<Locale, Record<string, string>> = {
  ko: {
    eyebrow: "약관 동의",
    title: "서비스 이용에 동의해 주세요",
    body: "관련 법령에 따라 이용약관과 개인정보처리방침 동의가 필요합니다. 동의하시면 바로 이어서 이용하실 수 있습니다.",
    terms: "이용약관에 동의합니다 (필수)",
    privacy: "개인정보처리방침에 동의합니다 (필수)",
    marketing: "마케팅 정보 수신에 동의합니다 (선택)",
    view: "전문 보기",
    submit: "동의하고 계속하기",
    submitting: "처리 중…",
    required: "필수 항목 두 가지에 모두 동의해야 계속할 수 있습니다.",
    failed: "동의를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
  },
  en: {
    eyebrow: "CONSENT",
    title: "Please accept the terms",
    body: "We need your agreement to the Terms of Service and Privacy Policy before you continue.",
    terms: "I agree to the Terms of Service (required)",
    privacy: "I agree to the Privacy Policy (required)",
    marketing: "I agree to receive marketing messages (optional)",
    view: "Read",
    submit: "Agree and continue",
    submitting: "Working…",
    required: "Both required items must be accepted to continue.",
    failed: "Could not save your consent. Please try again shortly.",
  },
  "zh-CN": {
    eyebrow: "条款同意",
    title: "请同意服务条款",
    body: "根据相关法规，需要您同意服务条款与隐私政策后才能继续使用。",
    terms: "我同意服务条款（必需）",
    privacy: "我同意隐私政策（必需）",
    marketing: "我同意接收营销信息（可选）",
    view: "查看全文",
    submit: "同意并继续",
    submitting: "处理中…",
    required: "必须同意两项必需条款才能继续。",
    failed: "未能保存同意记录，请稍后重试。",
  },
};

export function ConsentGate({
  locale,
  pathname,
  authed,
  children,
}: {
  locale: Locale;
  pathname: string;
  authed: boolean;
  children: React.ReactNode;
}) {
  // ★null = 아직 모른다. false 로 초기화하면 **모르는 동안 통과**시켜 게이트가 무의미해진다.
  const [pending, setPending] = useState<boolean | null>(null);
  const [terms, setTerms] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = COPY[locale] ?? COPY.ko;

  const exempt = !authed || isConsentExemptPath(pathname);

  useEffect(() => {
    if (exempt) return;
    let alive = true;
    void apiClient
      .get<Me>("/auth/me", { useMock: false })
      .then((u) => {
        if (alive) setPending(Boolean(u?.consent_pending));
      })
      .catch(() => {
        // ★못 재면 막지 않는다 — 이 게이트의 오작동이 서비스를 세우면 안 된다.
        //   (서버 미들웨어가 최종 관문이므로 여기서 통과시켜도 자원은 보호된다.)
        if (alive) setPending(false);
      });
    return () => {
      alive = false;
    };
  }, [exempt, pathname]);

  if (exempt || pending !== true) return <>{children}</>;

  async function submit() {
    setError(null);
    if (!(terms && privacy)) {
      setError(t.required);
      return;
    }
    setBusy(true);
    try {
      await apiClient.post("/auth/me/consents", {
        body: { agree_terms: terms, agree_privacy: privacy, agree_marketing: marketing },
        useMock: false,
      });
      setPending(false);
    } catch (e) {
      const msg =
        e instanceof ApiClientError && typeof (e.payload as { detail?: unknown })?.detail === "string"
          ? String((e.payload as { detail?: string }).detail)
          : t.failed;
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const row = (
    checked: boolean,
    set: (v: boolean) => void,
    label: string,
    href?: string,
  ) => (
    <label className="flex items-start gap-3 text-sm text-[var(--text-secondary)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => set(e.target.checked)}
        className="mt-1 h-4 w-4"
      />
      <span className="flex-1">{label}</span>
      {href ? (
        <Link
          href={href}
          className="shrink-0 text-xs text-[var(--accent-strong)] underline-offset-4 hover:underline"
        >
          {t.view}
        </Link>
      ) : null}
    </label>
  );

  return (
    <main
      data-testid="consent-gate"
      className="mx-auto flex min-h-screen max-w-2xl items-center px-6 py-10"
    >
      <div className="w-full rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-lg)] md:p-10">
        <span className="inline-flex rounded-full bg-[rgba(14,116,144,0.12)] px-4 py-2 text-sm font-semibold text-[var(--accent-strong)]">
          {t.eyebrow}
        </span>
        <h1 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">{t.title}</h1>
        <p className="mt-4 text-sm leading-7 text-[var(--text-secondary)]">{t.body}</p>

        <div className="mt-8 space-y-4">
          {row(terms, setTerms, t.terms, `/${locale}/legal/terms`)}
          {row(privacy, setPrivacy, t.privacy, `/${locale}/legal/privacy`)}
          {row(marketing, setMarketing, t.marketing)}
        </div>

        {error ? (
          <div
            role="alert"
            className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] px-5 py-4 text-sm text-[rgb(146,64,14)]"
          >
            {error}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy}
          className="mt-8 w-full rounded-[var(--radius-md)] bg-[var(--accent-strong)] px-4 py-3 text-sm font-semibold text-white disabled:opacity-60"
        >
          {busy ? t.submitting : t.submit}
        </button>
      </div>
    </main>
  );
}
