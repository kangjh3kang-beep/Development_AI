"use client";

/**
 * 삭제 확인 모달 — 오삭제 방지.
 *
 * 삭제 대상 이름을 보여주고(복사 버튼 제공), 사용자가 그 이름을 정확히 입력해야만
 * 삭제 버튼이 활성화된다. 되돌릴 수 없는 삭제(프로젝트 등)에 사용.
 */

import { useEffect, useState } from "react";

type ConfirmDeleteModalProps = {
  open: boolean;
  /** 삭제 대상 이름(이 값을 그대로 입력해야 삭제 가능) */
  name: string;
  /** 모달 제목(기본: 프로젝트 삭제) */
  title?: string;
  /** 부가 설명 */
  description?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDeleteModal({
  open,
  name,
  title = "프로젝트 삭제",
  description,
  onConfirm,
  onCancel,
}: ConfirmDeleteModalProps) {
  const [input, setInput] = useState("");
  const [copied, setCopied] = useState(false);

  // 열릴 때마다 입력 초기화
  useEffect(() => {
    if (open) {
      setInput("");
      setCopied(false);
    }
  }, [open, name]);

  if (!open) return null;

  const match = input.trim() === (name ?? "").trim() && name.trim().length > 0;

  const copy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(name);
      } else {
        const ta = document.createElement("textarea");
        ta.value = name;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* noop */
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-2xl)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-rose-500/10 text-xl text-rose-500">⚠</div>
          <h2 className="text-base font-black text-[var(--text-primary)]">{title}</h2>
        </div>

        <p className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)]">
          이 삭제는 <b className="text-rose-500">되돌릴 수 없습니다.</b>{" "}
          {description || "실수 방지를 위해 아래 이름을 정확히 입력해야 삭제됩니다."}
        </p>

        {/* 복사 가능한 대상 이름 */}
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2.5">
          <span className="min-w-0 flex-1 truncate text-sm font-bold text-[var(--text-primary)]" title={name}>
            {name}
          </span>
          <button
            type="button"
            onClick={copy}
            className="shrink-0 rounded-lg border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]"
          >
            {copied ? "복사됨 ✓" : "복사"}
          </button>
        </div>

        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && match) onConfirm();
            if (e.key === "Escape") onCancel();
          }}
          placeholder="위 이름을 그대로 입력하세요"
          className="mt-3 w-full rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
        />

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)] hover:bg-[var(--surface-soft)]"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!match}
            className="rounded-xl bg-rose-500 px-4 py-2 text-sm font-black text-white hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            삭제
          </button>
        </div>
      </div>
    </div>
  );
}
