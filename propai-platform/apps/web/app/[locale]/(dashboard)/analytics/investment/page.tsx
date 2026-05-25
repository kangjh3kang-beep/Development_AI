import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { InvestmentOperationsWorkspaceClient } from "@/components/analytics/InvestmentOperationsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type InvestmentPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function InvestmentPage({ params }: InvestmentPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["investment"].eyebrow}
        title={dictionary.modulePlaceholders["investment"].title}
        description={dictionary.modulePlaceholders["investment"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["investment"].items}
      />
      <InvestmentOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
