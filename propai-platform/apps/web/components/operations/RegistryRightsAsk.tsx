"use client";

/**
 * 권리분석 결과에 **원하는 것을 되묻는** 입력.
 *
 * ★**등기부를 다시 사지 않는다.** 이미 산출된 분석 JSON 만 보낸다(1,200원/필지).
 * ★판정하지 않는다 — 분석이 유효한지는 호출부(`isAnalyzed`)가 정하고,
 *   여기서는 **받은 것을 그대로** 보낸다(형 컴포넌트의 규율과 동일).
 * ★라이브 실측(2026-09-05)에서 이 경로의 LLM 이 **산술을 4.4배 틀렸다**.
 *   서버가 `derived` 로 계산을 실어 고쳤고(94.3% → 21.6%), 그래서 화면에
 *   **근거(basis)를 항상 함께** 보여 준다 — 답만 보이면 검산할 수 없다.
 */

import { useState } from "react";

import { askRightsQuestion, MAX_QUESTION_CHARS, type RightsAnswer } from "@/lib/registry-rights-ask";

export function RegistryRightsAsk({
  analysis,
}: {
  analysis: Record<string, unknown> | null | undefined;
}) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<RightsAnswer | null>(null);

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      setRes(await askRightsQuestion(analysis, q));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="rights-ask" className="mt-2 rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3">
      <p className="mb-1.5 text-[11px] font-bold tracking-wider text-[var(--text-hint)]">
        추가 분석 — 이 권리분석 결과에 대해 물어보세요
      </p>
      <div className="flex gap-2">
        <input
          data-testid="rights-ask-input"
          value={q}
          maxLength={MAX_QUESTION_CHARS}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
          placeholder="예) 매입해서 개발하려는데 권리관계상 가장 위험한 게 뭔가요?"
          className="h-10 flex-1 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
        />
        <button
          data-testid="rights-ask-submit"
          onClick={() => void submit()}
          disabled={busy || !q.trim()}
          className="h-10 rounded-[var(--radius-md)] border border-[var(--line)] px-4 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-40"
        >
          {busy ? "분석 중…" : "질문"}
        </button>
      </div>

      {res && (
        <div className="mt-2.5 space-y-1.5 text-sm">
          {res.answer && (
            <p data-testid="rights-ask-answer" className="whitespace-pre-wrap text-[var(--text-primary)]">
              {res.answer}
            </p>
          )}
          {/* ★근거는 **항상** 보인다 — 답만 보이면 사용자가 검산할 수 없다.
              이 경로의 LLM 이 실제로 산술을 틀린 적이 있다(실측). */}
          {res.basis && (
            <p data-testid="rights-ask-basis" className="text-[11px] leading-relaxed text-[var(--text-secondary)]">
              근거 · {res.basis}
            </p>
          )}
          {/* ★실패·한계 사유도 화면까지 온다 — 무언 실패 금지(§유료 규율 4). */}
          {res.caveat && (
            <p data-testid="rights-ask-caveat" className="text-[11px] leading-relaxed text-[var(--text-hint)]">
              ⚠ {res.caveat}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
