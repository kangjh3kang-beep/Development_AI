import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { runtimeMode } from "@/lib/runtime-mode";

type MaintenancePageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function MaintenancePage({
  params,
}: MaintenancePageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeModeLabel =
    runtimeMode() === "live"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
            <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["maintenance"].eyebrow}
        title={dictionary.modulePlaceholders["maintenance"].title}
        description={dictionary.modulePlaceholders["maintenance"].description}
        statusLabel={runtimeModeLabel}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["maintenance"].items}
      />
      <OperationsIntelligenceWorkspaceClient
        locale={locale as Locale}
        sections={["maintenance"]}
        showHero={false}
      />
    </div>
  );
}
