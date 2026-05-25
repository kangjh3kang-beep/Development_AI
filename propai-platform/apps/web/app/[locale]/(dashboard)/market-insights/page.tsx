import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

export const dynamic = "force-dynamic";

export default async function MarketInsightsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;

  return (
    <div className="flex flex-col gap-8">
      <header className="rounded-[var(--radius-3xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-10 shadow-[var(--shadow-lg)] relative overflow-hidden group">
        <div className="absolute inset-0 bg-gradient-to-br from-[var(--accent-strong)]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
        <div className="relative z-10">
          <h1 className="text-4xl font-[1000] tracking-tighter text-[var(--text-primary)] mb-3">
            Market Insights <span className="text-[var(--accent-strong)] tracking-normal italic font-black text-xl ml-2">.KRW</span>
          </h1>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)]">
            실시간 한국은행 기준금리 추이, 건설 원자재 지수, 오피스 공실률 등<br/>부동산 개발 사업성에 직결되는 거시경제 지표를 AI 모델에 통합하기 전 최종 검증합니다.
          </p>
        </div>
      </header>

      <div className="grid gap-8 md:grid-cols-2">
         {/* Interest Rate */}
         <div className="rounded-[var(--radius-3xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-md)]">
            <div className="flex items-center justify-between mb-8">
               <h2 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-tertiary)]">Interest Rate Trend</h2>
               <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-black text-[var(--accent-strong)] uppercase">LIVE</span>
            </div>
            <div className="flex h-[240px] items-end justify-between px-4 pb-4 border-b border-[var(--line)]">
               {[3.5, 3.5, 3.25, 3.0, 2.75, 2.5].map((rate, i) => (
                 <div key={i} className="flex flex-col items-center gap-4 group cursor-help">
                   <div
                     className="w-10 bg-gradient-to-t from-[var(--accent-strong)]/20 to-[var(--accent-strong)] rounded-t-xl relative transition-all group-hover:scale-y-110 shadow-[0_0_20px_var(--accent-strong)]/10"
                     style={{ height: `${(rate / 4) * 100}%` }}
                   >
                     <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-[var(--surface-inverted)] text-[var(--text-inverted)] px-2 py-1 rounded text-[9px] font-black opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                        {rate}%
                     </div>
                   </div>
                   <span className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-tighter">Q{6-i} '24</span>
                 </div>
               ))}
            </div>
         </div>

         {/* Materials Cost */}
         <div className="rounded-[var(--radius-3xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow-md)]">
            <h2 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-tertiary)] mb-8">Construction Material Index</h2>
            <div className="space-y-4">
              <div className="flex justify-between items-center p-6 rounded-3xl bg-[var(--error-soft)] border border-[var(--error)]/20 group hover:shadow-[0_0_30px_var(--error)]/10 transition-all">
                 <div>
                    <span className="text-[9px] font-black text-[var(--error)] uppercase tracking-widest mb-1 block">Critical Alert</span>
                    <h4 className="font-black text-[var(--text-primary)] text-lg uppercase tracking-tight">Cement <span className="text-[10px] font-bold opacity-40">/ TON</span></h4>
                 </div>
                 <div className="text-right">
                    <p className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tight">120K <span className="text-sm font-bold opacity-30">₩</span></p>
                    <p className="text-[10px] font-black text-[var(--error)] mt-1 animate-pulse">▲ 5.2% (MoM)</p>
                 </div>
              </div>
              <div className="flex justify-between items-center p-6 rounded-3xl bg-[var(--info-soft)] border border-[var(--info)]/20 group hover:shadow-[0_0_30px_var(--info)]/10 transition-all">
                 <div>
                    <span className="text-[9px] font-black text-[var(--info)] uppercase tracking-widest mb-1 block">Stabilizing</span>
                    <h4 className="font-black text-[var(--text-primary)] text-lg uppercase tracking-tight">Rebar <span className="text-[10px] font-bold opacity-40">/ TON</span></h4>
                 </div>
                 <div className="text-right">
                    <p className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tight">890K <span className="text-sm font-bold opacity-30">₩</span></p>
                    <p className="text-[10px] font-black text-[var(--info)] mt-1">▼ 1.5% (MoM)</p>
                 </div>
              </div>
            </div>
         </div>
      </div>
    </div>
  );
}
