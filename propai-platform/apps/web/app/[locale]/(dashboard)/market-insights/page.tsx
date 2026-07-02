import { MarketInsightsWorkspaceClient } from "@/components/operations/MarketInsightsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type MarketInsightsPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function MarketInsightsPage({ params }: MarketInsightsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const meta = dictionary.modulePlaceholders["market-insights"];

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — MarketInsightsWorkspaceClient 내부에서 렌더
          (분석 파이프라인 실제 상태(report·genState·useLlm)가 그 컴포넌트 로컬 state에 있어,
          서버 셸까지 threading하지 않고 상태를 쥔 곳에서 직접 배선). */}
      {/* 실 시장분석 화면 헤더 — 목업 배너 제거(무목업), 제목만 유지. 본문은 실데이터(실거래·AI시세·보고서). */}
      <header className="space-y-1.5 px-2">
        <p className="text-[11px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
          {meta.eyebrow}
        </p>
        <h1 className="text-3xl font-[900] tracking-tighter text-[var(--text-primary)] sm:text-4xl">
          {meta.title}
        </h1>
        <p className="max-w-2xl text-sm font-medium text-[var(--text-secondary)]">
          {meta.description}
        </p>
      </header>
      <MarketInsightsWorkspaceClient />
    </div>
  );
}
