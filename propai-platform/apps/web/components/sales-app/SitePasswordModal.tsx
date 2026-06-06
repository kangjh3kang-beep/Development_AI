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
        className="w-full max-w-sm rounded-t-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5 shadow-[var(--shadow-md)] sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xl">🛠</span>
          <h2 className="text-base font-black text-[var(--text-primary)]">현장 2차 비밀번호 설정</h2>
        </div>
        <p className="mb-4 text-xs text-[var(--text-secondary)]">
          현장 진입에 사용할 2차 비밀번호를 설정/변경합니다. 변경 시 기존 잠금이 초기화됩니다.
        </p>

        {done ? (
          <>
            <p className="rounded-lg bg-emerald-500/10 px-3 py-3 text-sm font-semibold text-emerald-300">
              ✅ 비밀번호가 저장되었습니다.
            </p>
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-xl bg-[var(--accent-strong)] px-4 py-3 text-sm font-black text-white"
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
              className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
              placeholder="비밀번호 확인"
              className="mt-2 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
            {err && <p className="mt-2 text-xs font-semibold text-rose-400">{err}</p>}
            <div className="mt-4 flex gap-2">
              <button
                onClick={onClose}
                disabled={busy}
                className="flex-1 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)] px-4 py-3 text-sm font-bold text-[var(--text-secondary)] disabled:opacity-50"
              >
                취소
              </button>
              <button
                onClick={submit}
                disabled={busy}
                className="flex-[2] rounded-xl bg-[var(--accent-strong)] px-4 py-3 text-sm font-black text-white disabled:opacity-50"
              >
                {busy ? "저장 중…" : "저장"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
