import { TaxOperationsWorkspaceClient } from "@/components/analytics/TaxOperationsWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type TaxPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function TaxPage({ params }: TaxPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["tax"].eyebrow}
        title={dictionary.modulePlaceholders["tax"].title}
        description={dictionary.modulePlaceholders["tax"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["tax"].items}
      />
      <TaxOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
