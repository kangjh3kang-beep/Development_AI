"use client";

/**
 * Phase 1-A — 현장 진입(2차비번) 모달.
 * 비번 입력 → POST /sales/sites/{id}/enter → site_token(8h) sessionStorage 저장 → 워크스페이스 이동.
 * 에러 계약: 403(멤버 아님)·401(비번 불일치/남은시도)·409(비번 미설정)·429(잠김/대기분)·400(짧음).
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { storeSiteToken } from "@/lib/salesApi";
import type { Locale } from "@/i18n/config";

export interface EnterResponse {
  site_token: string;
  token_type: string;
  expires_in: number;
  site_id: string;
  role: string;
  role_label?: string;
  features: string[];
}

interface Props {
  locale: Locale;
  siteId: string;
  siteName: string;
  open: boolean;
  onClose: () => void;
  /** 진입 성공 시 호출(메타 전달). 미지정 시 워크스페이스로 라우팅. */
  onEntered?: (res: EnterResponse) => void;
}

export default function SiteEnterModal({ locale, siteId, siteName, open, onClose, onEntered }: Props) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setPassword("");
      setErr("");
      // 모바일·데스크 모두 즉시 입력 포커스
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open, siteId]);

  if (!open) return null;

  const submit = async () => {
    if (!password) {
      setErr("현장 비밀번호를 입력하세요.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const res = await apiClient.post<EnterResponse>(
        `/sales/sites/${siteId}/enter`,
        { body: { password } },
      );
      storeSiteToken(siteId, res.site_token, res.expires_in, {
        role: res.role,
        features: res.features,
      });
      if (onEntered) onEntered(res);
      else router.push(`/${locale}/sales/sites/${siteId}/workspace`);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="현장 진입"
    >
      <div
        className="w-full max-w-sm overflow-hidden rounded-t-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-md)] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 — accent 글로우 띠로 진입(보안) 행위임을 시각화 */}
        <div className="relative overflow-hidden border-b border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[var(--accent-soft)] blur-2xl"
          />
          <div className="relative flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[color:color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--accent-soft)] text-[var(--accent-strong)]">
              <LockKeyhole className="size-5" aria-hidden />
            </span>
            <div className="min-w-0">
              <span className="cc-label">SECURE ENTRY</span>
              <h2 className="text-base font-black leading-tight text-[var(--text-primary)]">현장 진입</h2>
            </div>
          </div>
        </div>

        <div className="p-5">
          <p className="mb-4 text-xs leading-relaxed text-[var(--text-secondary)]">
            <b className="text-[var(--text-primary)]">{siteName}</b> 현장의 2차 비밀번호를 입력하세요.
          </p>

          <input
            ref={inputRef}
            type="password"
            inputMode="text"
            autoComplete="off"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
            placeholder="현장 비밀번호"
            className="w-full rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 py-3.5 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-strong)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
          />

          {err && (
            <p className="mt-2 rounded-lg bg-[color:color-mix(in_srgb,var(--status-error)_12%,transparent)] px-2.5 py-2 text-xs font-semibold text-[var(--status-error)]">
              {err}
            </p>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={onClose}
              disabled={busy}
              className="flex-1 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-3.5 text-sm font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)] active:scale-95 disabled:opacity-50"
            >
              취소
            </button>
            <button
              onClick={submit}
              disabled={busy}
              className="flex-[2] rounded-xl bg-[var(--accent-strong)] px-4 py-3.5 text-sm font-black text-white shadow-[var(--shadow-sm)] transition hover:opacity-90 active:scale-95 disabled:opacity-50"
            >
              {busy ? "확인 중…" : "진입 →"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** 백엔드 에러 계약(403/401/409/429/400)을 사용자 친화 메시지로 변환. */
function friendlyError(e: unknown): string {
  if (e instanceof ApiClientError) {
    const detail = (e.payload as { detail?: string } | null)?.detail;
    switch (e.status) {
      case 403:
        return "이 현장의 멤버가 아닙니다. 현장 관리자에게 권한을 요청하세요.";
      case 401:
        return typeof detail === "string" && detail ? detail : "비밀번호가 일치하지 않습니다.";
      case 409:
        return "현장 비밀번호가 아직 설정되지 않았습니다. 현장 관리자(시행/대행 본부장↑)에게 설정을 요청하세요.";
      case 429:
        return typeof detail === "string" && detail
          ? detail
          : "비밀번호를 여러 번 틀려 일시적으로 잠겼습니다. 잠시 후 다시 시도하세요.";
      case 400:
        return "비밀번호가 너무 짧거나 비어 있습니다.";
      default:
        if (typeof detail === "string" && detail) return detail;
    }
  }
  return "진입에 실패했습니다. 잠시 후 다시 시도하세요.";
}
