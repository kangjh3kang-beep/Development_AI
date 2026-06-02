/**
 * 면책 고지 — 전 페이지·분석결과 공통.
 *
 * 모든 분석 결과는 참고용이며 사통팔땅은 책임을 지지 않고 최종판단은 사용자에게 있음을 고지한다.
 * dashboard layout에 전역 1회 배치하여 모든 페이지에 노출된다.
 */

export const DISCLAIMER_TEXT =
  "본 분석결과는 참고용이며, 오류가 있을 수 있습니다. 이와 관련해 사통팔땅은 어떠한 책임도 지지 않습니다. 최종판단은 사용자가 최종 결정하는 것입니다.";

export function Disclaimer({ className = "" }: { className?: string }) {
  return (
    <p
      role="note"
      className={`flex items-start gap-2 rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-[11px] leading-relaxed text-[var(--text-tertiary)] ${className}`}
    >
      <span aria-hidden className="shrink-0">⚠️</span>
      <span>{DISCLAIMER_TEXT}</span>
    </p>
  );
}
