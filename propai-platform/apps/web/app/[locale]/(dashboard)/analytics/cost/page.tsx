import { ConstructionCostWorkspaceClient } from "@/components/analytics/ConstructionCostWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type CostAnalyticsPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function CostAnalyticsPage({
  params,
}: CostAnalyticsPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["cost"].eyebrow}
        title={dictionary.modulePlaceholders["cost"].title}
        description={dictionary.modulePlaceholders["cost"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["cost"].items}
      />
      <ConstructionCostWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
