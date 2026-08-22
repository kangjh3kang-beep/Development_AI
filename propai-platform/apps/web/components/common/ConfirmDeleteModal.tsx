"use client";

/**
 * 삭제 확인 모달 — 오삭제 방지.
 *
 * 삭제 대상 이름을 보여주고(복사 버튼 제공), 사용자가 그 이름을 정확히 입력해야만
 * 삭제 버튼이 활성화된다. 되돌릴 수 없는 삭제(프로젝트 등)에 사용.
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useModalFocus } from "@/hooks/useModalFocus";
import { AlertTriangle, Check } from "lucide-react";

import { DISMISS_Z, useDismissible } from "@/lib/satong-dismiss";

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
  const dialogRef = useRef<HTMLDivElement>(null);

  // ★모달 포커스 생명주기(초기 포커스·트랩·복귀). ESC 는 별개 계약(registerDismissible)이라
  //   여기서 다루지 않는다 — 두 곳에서 처리하면 한 번 눌러 둘이 닫힌다(#697 이 겪은 결함).
  // ★훅은 **early return 앞**에 둔다. 아래 `if (!open) return null` 뒤에 두면 조건부 호출이
  //   되어 렌더마다 훅 순서가 달라진다(react-hooks/rules-of-hooks 가 잡아 줬다).
  //   대신 `open` 을 그대로 넘겨 닫힘 상태에서는 훅이 스스로 아무것도 하지 않게 한다.
  useModalFocus(dialogRef, open);
  const [copied, setCopied] = useState(false);

  // 열릴 때마다 입력 초기화
  useEffect(() => {
    if (open) {
      setInput("");
      setCopied(false);
    }
  }, [open, name]);

  // ESC 로 취소 — **조정기로 이관**(종전에는 아래 입력의 onKeyDown 이었다).
  // 종전 결함: 사용자가 '복사' 버튼이나 본문을 클릭해 포커스가 입력에서 벗어나면 ESC 가
  //   아무 일도 하지 않았다(핸들러가 입력에만 붙어 있었다).
  // ★정정(R2) — 초판 주석은 "문서 뷰어 모달 위에 겹쳐 열리는 경로가 실재한다"고 적었으나
  //   **거짓이다**: 이 확인창의 소비처는 `components/projects/ProjectsOverviewClient.tsx`
  //   하나뿐이고(전수 확인), 문서뷰어 쪽 삭제는 확인창 없이 바로 지운다.
  //   그래도 한 칸 위(`nestedOverModal`)로 등록한다 — 되돌릴 수 없는 삭제를 확인하는 창은
  //   무엇 위에 뜨든 가장 먼저 닫혀야 하고, 단독으로 열려도 최댓값이라 동작은 같다.
  useDismissible(DISMISS_Z.nestedOverModal, open, onCancel);

  if (!open || typeof document === "undefined") return null;

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

  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="w-full max-w-md rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-2xl)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-500"><AlertTriangle className="size-5" aria-hidden /></div>
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
            {copied ? (<span className="inline-flex items-center gap-1">복사됨 <Check className="size-3.5" aria-hidden /></span>) : "복사"}
          </button>
        </div>

        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && match) onConfirm();
            // ESC 는 여기서 처리하지 않는다 — 위 `useDismissible` 이 포커스와 무관하게 받는다.
            // (여기 남겨 두면 같은 keydown 에 onCancel 이 두 번 불린다.)
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
    </div>,
    document.body,
  );
}
