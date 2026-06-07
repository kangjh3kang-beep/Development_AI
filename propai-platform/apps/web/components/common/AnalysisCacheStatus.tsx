"use client";

/**
 * 분석 캐시 상태 배지/배너 — 무거운 분석(지형·환경·AVM·디지털트윈 등) 공용.
 *
 * - isFresh: 입력 불변 → "검증된 분석 재사용" 배지(재실행 안 함).
 * - isStale: 입력(원·첨부·보강 데이터) 변경 감지 → "재분석 권장" 배너 + 재분석 버튼.
 * - 캐시 없음(둘 다 false): 아무것도 렌더하지 않음(패널 기본 실행 UI 사용).
 */
export function AnalysisCacheStatus({
  isFresh,
  isStale,
  at,
  relativeLabel,
  onRerun,
  busy,
  rerunLabel = "재분석",
}: {
  isFresh: boolean;
  isStale: boolean;
  at: number | null;
  relativeLabel: string;
  onRerun: () => void;
  busy?: boolean;
  rerunLabel?: string;
}) {
  if (isStale) {
    return (
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2">
        <p className="text-xs text-amber-200">
          🔄 입력값(원·첨부·보강 데이터)이 변경되었습니다 — 기존 결과를 표시 중이며{" "}
          <b>재분석을 권장</b>합니다.
        </p>
        <button
          onClick={onRerun}
          disabled={busy}
          className="h-8 whitespace-nowrap rounded-lg bg-amber-500 px-4 text-xs font-black text-black hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "분석 중…" : rerunLabel}
        </button>
      </div>
    );
  }
  if (isFresh) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5">
        <span className="text-xs font-bold text-emerald-300">
          ✓ 검증된 분석 재사용
        </span>
        {relativeLabel && (
          <span className="text-[11px] text-[var(--text-secondary)]">
            · {relativeLabel} · 입력 불변 시 재실행하지 않습니다
          </span>
        )}
      </div>
    );
  }
  return null;
}
