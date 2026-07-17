"use client";

import { useEffect, useState } from "react";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { MyPageShell } from "./MyPageShell";

type Me = {
  name: string;
  email: string;
  phone?: string | null;
  email_verified?: boolean;
  has_password?: boolean;
  created_at?: string;
};

function resolveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    const payload = error.payload as { detail?: unknown } | null;
    if (payload && typeof payload.detail === "string") return payload.detail;
    // pydantic 422 상세(배열)는 첫 메시지만 통상어로.
    if (payload && Array.isArray(payload.detail) && payload.detail[0]?.msg) {
      return String(payload.detail[0].msg).replace(/^Value error,\s*/, "");
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function ProfileClient({ locale }: { locale: Locale }) {
  const [me, setMe] = useState<Me | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [notice, setNotice] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  // ★로드 실패를 무징후로 삼켜 '이메일 미인증'을 허위 단정하지 않도록 명시 상태(성장루프 LOW 수렴).
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    void apiClient
      .get<Me>("/auth/me", { useMock: false })
      .then((u) => {
        setMe(u);
        setName(u.name ?? "");
        setPhone(u.phone ?? "");
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);

  const save = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const updated = await apiClient.patch<Me>("/auth/me", {
        body: { name, phone },
        useMock: false,
      });
      setMe(updated);
      setName(updated.name ?? "");
      setPhone(updated.phone ?? "");
      setNotice({ kind: "info", text: "프로필이 저장되었습니다." });
    } catch (error) {
      setNotice({ kind: "error", text: resolveErrorMessage(error, "저장에 실패했습니다.") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <MyPageShell
      locale={locale}
      title="프로필 관리"
      description="이름과 연락처를 수정할 수 있습니다. 이메일 변경은 보안 확인 절차가 필요해 준비 중입니다."
    >
      {notice ? (
        <div
          role="status"
          className={`mb-5 rounded-[var(--radius-xl)] border px-5 py-3.5 text-sm ${
            notice.kind === "error"
              ? "border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
              : "border-[rgba(13,148,136,0.28)] bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
          }`}
        >
          {notice.text}
        </div>
      ) : null}

      {loadError ? (
        <div
          role="status"
          className="mb-5 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] px-5 py-3.5 text-sm text-[rgb(146,64,14)]"
        >
          프로필 정보를 불러오지 못했습니다. 잠시 후 새로고침해 주세요. (표시된 값이 실제 계정
          정보가 아닐 수 있습니다.)
        </div>
      ) : null}

      <section className="max-w-xl rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-6">
        <div className="space-y-4">
          <div>
            <label htmlFor="profile-email" className="text-xs font-semibold text-[var(--text-tertiary)]">
              이메일(로그인 계정)
            </label>
            <input
              id="profile-email"
              type="email"
              value={me?.email ?? ""}
              readOnly
              disabled
              className="mt-1 block w-full rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--text-tertiary)]"
            />
            {/* 로드 성공 시에만 인증 상태를 단정 표기(실패 시 '미인증' 허위 단정 방지). */}
            {me ? (
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                {me.email_verified ? "인증 완료된 이메일입니다." : "이메일 인증이 아직 완료되지 않았습니다(계정 보안 탭에서 인증)."}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor="profile-name" className="text-xs font-semibold text-[var(--text-tertiary)]">
              이름
            </label>
            <input
              id="profile-name"
              type="text"
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)]"
            />
          </div>

          <div>
            <label htmlFor="profile-phone" className="text-xs font-semibold text-[var(--text-tertiary)]">
              휴대전화(선택)
            </label>
            <input
              id="profile-phone"
              type="tel"
              maxLength={32}
              placeholder="010-0000-0000"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="mt-1 block w-full rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-sm text-[var(--text-primary)]"
            />
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              비우고 저장하면 등록된 번호가 삭제됩니다.
            </p>
          </div>
        </div>

        <button
          type="button"
          disabled={busy || !me}
          onClick={() => void save()}
          className="mt-6 rounded-full bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          저장
        </button>
      </section>
    </MyPageShell>
  );
}
