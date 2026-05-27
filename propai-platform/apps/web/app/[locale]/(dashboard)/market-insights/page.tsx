import { MarketInsightsWorkspaceClient } from "@/components/operations/MarketInsightsWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
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
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
      <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["market-insights"].eyebrow}
        title={dictionary.modulePlaceholders["market-insights"].title}
        description={dictionary.modulePlaceholders["market-insights"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["market-insights"].items}
      />
      <MarketInsightsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
