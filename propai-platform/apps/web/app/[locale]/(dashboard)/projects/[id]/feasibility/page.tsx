import { isValidLocale } from "@/i18n/config";
import { FeasibilityEditorV2 } from "@/components/feasibility/FeasibilityEditorV2";

type Props = {
  params: Promise<{ locale: string; id: string }>;
};

export default async function FeasibilityPage({ params }: Props) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-12 min-h-screen pb-20 transition-colors duration-500">
      {/* ── Premium Hero Header ── */}
      <div className="relative overflow-hidden rounded-[3rem] bg-[var(--surface-strong)] p-12 lg:p-16 shadow-[var(--shadow-2xl)] border border-[var(--line-strong)]">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)] opacity-[0.05] dark:opacity-10 blur-[80px]" />
        
        <div className="relative z-10 flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl space-y-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)] backdrop-blur-md transition-all">
                <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] animate-pulse" />
                Financial Intelligence
              </span>
            </div>
            
            <h1 className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)] sm:text-6xl lg:text-7xl leading-[1.05]">
              AI 수지분석 및 <br/>
              <span className="text-[var(--accent-strong)] drop-shadow-sm font-[1000]">수익률 검토.</span>
            </h1>

            <p className="max-w-xl text-lg font-bold leading-relaxed text-[var(--text-secondary)] italic tracking-tight underline decoration-[var(--line)] underline-offset-8">
              &quot;15개 개발유형, 38종 세무 알고리즘, 전국 229개 시군구 조례를 실시간 통합 분석하여 최적의 투자의사결정을 지원합니다.&quot;
            </p>
          </div>

          <div className="hidden lg:block">
            <div className="h-32 w-32 rounded-[2.5rem] bg-[var(--surface-soft)] border border-[var(--line-strong)] flex items-center justify-center text-[var(--accent-strong)] backdrop-blur-3xl animate-float shadow-[var(--shadow-lg)]">
               <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/></svg>
            </div>
          </div>
        </div>
      </div>

      <div className="animate-premium-fade" style={{ animationDelay: '200ms' }}>
        <FeasibilityEditorV2 projectId={id} />
      </div>
    </div>
  );
}
