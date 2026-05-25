import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { EnergyOperationsWorkspaceClient } from "@/components/analytics/EnergyOperationsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ESGPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ESGPage({ params }: ESGPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["esg"].eyebrow}
        title={dictionary.modulePlaceholders["esg"].title}
        description={dictionary.modulePlaceholders["esg"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["esg"].items}
      />
      <EnergyOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
