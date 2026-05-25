import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

// Force Next.js to not statically cache if we want dynamic mock maps later
export const dynamic = "force-dynamic";

export default async function AiPortfolioPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  const dictionary = await getDictionary(locale as Locale);

  return (
    <div className="flex flex-col gap-6">
      <header className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] p-8 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
          {dictionary.nav.dashboard}
        </p>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-[var(--text-primary)]">
          AI 포트폴리오 맵 (Portfolio Map)
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          전국 주요 입지에 진행 중인 자산 포트폴리오의 실시간 상태 및 예상 NPV 총합을 거시적으로 모니터링합니다.
        </p>
      </header>
      
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] flex items-center justify-center p-12 min-h-[500px]">
          <p className="text-sm font-semibold tracking-widest uppercase text-[var(--text-hint)] animate-pulse">
            Map Interface Rendering (MapboxGL)
          </p>
        </div>
        <div className="flex flex-col gap-4">
           {/* Summary Cards */}
           <div className="rounded-[var(--radius-xl)] bg-[var(--accent-strong)] p-6 shadow-[var(--shadow-xl)]">
             <p className="text-xs font-bold uppercase tracking-widest text-white/60">총 예상 순현재가치 (Total NPV)</p>
             <p className="mt-2 text-3xl font-black text-white">4조 8,200억 원</p>
           </div>

           <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[var(--shadow-sm)]">
             <p className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">활성화된 프로젝트 (Active)</p>
             <p className="mt-2 text-3xl font-black text-[var(--text-primary)]">14개 현장</p>
           </div>

           <div className="rounded-[var(--radius-xl)] border border-[var(--error)]/20 bg-[var(--error-soft)] p-6 shadow-[var(--shadow-sm)]">
             <p className="text-xs font-bold uppercase tracking-widest text-[var(--error)]">리스크 감지 (At Risk)</p>
             <p className="mt-2 text-3xl font-black text-[var(--error)]">2개 현장</p>
             <p className="mt-2 text-xs font-semibold text-[var(--error)]">- 송파 오피스 신축 (인허가 지연)</p>
           </div>
        </div>
      </div>
    </div>
  );
}
