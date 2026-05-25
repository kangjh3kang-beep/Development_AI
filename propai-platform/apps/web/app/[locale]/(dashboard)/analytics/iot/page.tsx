import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type IoTPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function IoTPage({ params }: IoTPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["iot"].eyebrow}
        title={dictionary.modulePlaceholders["iot"].title}
        description={dictionary.modulePlaceholders["iot"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["iot"].items}
      />
      <OperationsIntelligenceWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
