"use client";

/**
 * Phase 1-A — 현장 2차비번 설정/변경 모달(can_manage 권한자 전용).
 * POST /sales/sites/{id}/password { password }. 400(짧음)·403(권한없음) 안내.
 */
import { useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

interface Props {
  siteId: string;
  open: boolean;
  onClose: () => void;
  onDone?: () => void;
}

export default function SitePasswordModal({ siteId, open, onClose, onDone }: Props) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (open) {
      setPassword("");
      setConfirm("");
      setErr("");
      setDone(false);
    }
  }, [open]);

  if (!open) return null;

  const submit = async () => {
    if (password.length < 4) {
      setErr("비밀번호는 4자 이상이어야 합니다.");
      return;
    }
    if (password !== confirm) {
      setErr("두 비밀번호가 일치하지 않습니다.");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await apiClient.post(`/sales/sites/${siteId}/password`, { body: { password } });
      setDone(true);
      onDone?.();
    } catch (e) {
      let msg = "비밀번호 설정에 실패했습니다.";
      if (e instanceof ApiClientError) {
        const detail = (e.payload as { detail?: string } | null)?.detail;
        if (e.status === 403) msg = "2차 비밀번호를 설정할 권한이 없습니다.";
        else if (e.status === 400) msg = "비밀번호가 너무 짧습니다(4자 이상).";
        else if (typeof detail === "string" && detail) msg = detail;
      }
      setErr(msg);
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
      aria-label="현장 비밀번호 설정"
    >
      <div
        className="w-full max-w-sm overflow-hidden rounded-t-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-md)] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 모달 헤더 — 관리(설정) 행위 시각화 */}
        <div className="relative overflow-hidden border-b border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[var(--accent-soft)] blur-2xl"
          />
          <div className="relative flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[color:color-mix(in_srgb,var(--accent-strong)_30%,transparent)] bg-[var(--accent-soft)] text-lg">
              🛠
            </span>
            <div className="min-w-0">
              <span className="cc-label">SITE PASSWORD</span>
              <h2 className="text-base font-black leading-tight text-[var(--text-primary)]">현장 2차 비밀번호 설정</h2>
            </div>
          </div>
        </div>

        <div className="p-5">
          <p className="mb-4 text-xs leading-relaxed text-[var(--text-secondary)]">
            현장 진입에 사용할 2차 비밀번호를 설정/변경합니다. 변경 시 기존 잠금이 초기화됩니다.
          </p>

          {done ? (
            <>
              <p className="flex items-center gap-2 rounded-xl border border-[color:color-mix(in_srgb,var(--status-success)_38%,transparent)] bg-[color:color-mix(in_srgb,var(--status-success)_12%,transparent)] px-3.5 py-3 text-sm font-semibold text-[var(--status-success)]">
                <span aria-hidden>✅</span> 비밀번호가 저장되었습니다.
              </p>
              <button
                onClick={onClose}
                className="mt-4 w-full rounded-xl bg-[var(--accent-strong)] px-4 py-3.5 text-sm font-black text-white shadow-[var(--shadow-sm)] transition hover:opacity-90 active:scale-95"
              >
                닫기
              </button>
            </>
          ) : (
            <>
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="새 비밀번호 (4자 이상)"
                className="w-full rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 py-3.5 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-strong)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
              />
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
                placeholder="비밀번호 확인"
                className="mt-2 w-full rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 py-3.5 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-strong)] focus:shadow-[0_0_0_3px_var(--accent-soft)]"
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
                  {busy ? "저장 중…" : "저장"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
