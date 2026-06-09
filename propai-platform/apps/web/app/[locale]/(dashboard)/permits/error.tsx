"use client";

// 인허가 분석(구획도 지도 포함) 화면 전용 에러 경계.
// 이 화면 안에서만 에러를 가두므로, 사이드바·다른 메뉴 이동은 막히지 않는다.
// "다시 시도"는 이 영역만 reset 한다.
export default function PermitsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 p-8">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-red-500/10 text-red-400">
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
      </div>
      <h2 className="text-2xl font-black text-[var(--text-primary)]">인허가 분석을 불러오는 중 문제가 발생했습니다</h2>
      <p className="text-sm text-[var(--text-secondary)] max-w-md text-center">
        지도/분석을 표시하는 중 오류가 났습니다. 다른 메뉴는 그대로 이용할 수 있습니다.
      </p>
      <p className="text-xs text-[var(--text-hint)]">{error.message}</p>
      <button
        onClick={reset}
        className="rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-white hover:brightness-110 transition-all"
      >
        다시 시도
      </button>
    </div>
  );
}
