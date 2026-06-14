"use client";

/**
 * 피드백 위젯 — 자가성장 엔진 Phase 4 (설계서 §6.4).
 *
 * LLM 분석 출력 하단에 👍/👎 버튼을 인라인으로 붙여 사용자 피드백(ai_feedback)을 모은다.
 * - 👎 누르면 교정 텍스트(선택)·평점(선택)을 적어 보낼 수 있다(학습 신호).
 * - 비로그인(익명)도 보낼 수 있고, 전송이 실패해도 화면 흐름은 막지 않는다.
 * - 한 번 보내면 "감사합니다"로 바뀌어 중복 전송을 막는다.
 *
 * 백엔드 계약: POST /api/v1/growth/feedback (인증 선택·익명 허용)
 *   body: { target_type, verdict, service?, analysis_type?, content_hash?, correction?, rating?, payload? }
 *   → { id, accepted }
 *   ※ apiClient 가 /api/v1 를 자동으로 붙이므로 경로는 "/growth/feedback" (이중 prefix 금지).
 */

import { useCallback, useState } from "react";

import { apiClient } from "@/lib/api-client";

type TargetType = "llm_output" | "analysis" | "recommendation";
type Verdict = "up" | "down";

type FeedbackResult = { id: string; accepted: boolean };

export function FeedbackWidget({
  targetType,
  service,
  analysisType,
  contentHash,
  payload,
}: {
  /** 피드백 대상 종류 (기본: LLM 출력) */
  targetType?: TargetType;
  /** LLM service 명(base_interpreter.name 등) — 서버 집계 키 */
  service?: string;
  /** analysis_ledger.analysis_type 와 정합 */
  analysisType?: string;
  /** analysis_ledger.content_hash 조인키 */
  contentHash?: string;
  /** 추가 컨텍스트(서버가 PII 마스킹) */
  payload?: Record<string, unknown>;
}) {
  // "idle"=초기, "form"=👎 상세입력, "sent"=전송완료
  const [state, setState] = useState<"idle" | "form" | "sent">("idle");
  const [sending, setSending] = useState(false);
  const [correction, setCorrection] = useState("");
  const [rating, setRating] = useState<number | null>(null);

  const submit = useCallback(
    async (verdict: Verdict) => {
      if (sending || state === "sent") return; // 중복 전송 방지
      setSending(true);
      try {
        await apiClient.post<FeedbackResult>("/growth/feedback", {
          body: {
            target_type: targetType ?? "llm_output",
            verdict,
            ...(service ? { service } : {}),
            ...(analysisType ? { analysis_type: analysisType } : {}),
            ...(contentHash ? { content_hash: contentHash } : {}),
            ...(correction.trim() ? { correction: correction.trim() } : {}),
            ...(rating != null ? { rating } : {}),
            ...(payload ? { payload } : {}),
          },
          useMock: false,
        });
      } catch {
        /* 전송 실패는 조용히 무시 — 분석 화면 흐름을 막지 않는다(익명·베스트에포트). */
      } finally {
        setState("sent");
      }
    },
    [state, sending, targetType, service, analysisType, contentHash, correction, rating, payload],
  );

  if (state === "sent") {
    return (
      <span className="text-[11px] text-[var(--text-hint)]">
        🙏 피드백 감사합니다
      </span>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] text-[var(--text-hint)]">이 분석이 도움이 되었나요?</span>
      <button
        type="button"
        disabled={sending}
        onClick={() => void submit("up")}
        className="inline-flex items-center gap-1 rounded-full border border-[var(--line)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:border-emerald-500/40 hover:text-emerald-400 disabled:opacity-50"
        aria-label="도움이 됨"
      >
        👍 도움됨
      </button>
      <button
        type="button"
        disabled={sending}
        onClick={() => setState((s) => (s === "form" ? "idle" : "form"))}
        className="inline-flex items-center gap-1 rounded-full border border-[var(--line)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:border-rose-500/40 hover:text-rose-400 disabled:opacity-50"
        aria-label="개선 필요"
        aria-expanded={state === "form"}
      >
        👎 개선필요
      </button>

      {state === "form" && (
        <div className="mt-1 flex w-full flex-col gap-1.5">
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            placeholder="무엇이 잘못되었는지 알려주시면 학습에 반영합니다 (선택)"
            rows={2}
            maxLength={4000}
            className="w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1.5 text-[11px] text-[var(--text-primary)] placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:outline-none"
          />
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1">
              <span className="text-[10px] text-[var(--text-hint)]">평점(선택):</span>
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setRating((r) => (r === n ? null : n))}
                  className={`text-[12px] leading-none transition-opacity ${
                    rating != null && n <= rating ? "opacity-100" : "opacity-30 hover:opacity-70"
                  }`}
                  aria-label={`${n}점`}
                >
                  ⭐
                </button>
              ))}
            </div>
            <button
              type="button"
              disabled={sending}
              onClick={() => void submit("down")}
              className="rounded-full bg-[var(--accent-strong)] px-3 py-0.5 text-[11px] font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {sending ? "전송 중…" : "보내기"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
