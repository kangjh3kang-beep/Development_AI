import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

export const dynamic = "force-dynamic";

export default async function RegulationsPage({
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
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
          법규 및 규제 모니터링 (Regulations)
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          건축법, 지구단위계획, 지자체 조례의 실시간 변경 사항을 KDX 데이터 연계망을 통해 모니터링하고 시사점을 도출합니다.
        </p>
      </header>
      
      <div className="grid gap-6">
         {/* Live Feed */}
         <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[var(--shadow-sm)]">
           <h2 className="text-sm font-bold uppercase tracking-widest text-[var(--text-tertiary)]">실시간 법령 개정 피드</h2>

           <div className="mt-6 space-y-4">
              <div className="flex items-start gap-4 p-4 rounded-xl bg-[var(--surface-soft)]">
                 <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-[var(--error)]"></div>
                 <div>
                    <h3 className="font-bold">국토의 계획 및 이용에 관한 법률 시행령 일부 개정</h3>
                    <p className="mt-1 text-sm text-[var(--text-tertiary)]">상업지역 내 주거복합건물 용적률 규제 완화 고시. (영향받는 프로젝트: 3건)</p>
                    <p className="mt-2 text-xs font-mono text-[var(--text-hint)]">2026. 03. 28</p>
                 </div>
              </div>
              <div className="flex items-start gap-4 p-4 rounded-xl hover:bg-[var(--surface-soft)] transition-colors">
                 <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-[var(--line-strong)]"></div>
                 <div>
                    <h3 className="font-bold">서울특별시 건축조례안 입법예고</h3>
                    <p className="mt-1 text-sm text-[var(--text-tertiary)]">제로에너지건축물 인증 의무 대상 확대. 기존 30세대 이상에서 모든 민간 신축으로 변경 검토.</p>
                    <p className="mt-2 text-xs font-mono text-[var(--text-hint)]">2026. 03. 15</p>
                 </div>
              </div>
           </div>
         </div>
      </div>
    </div>
  );
}
