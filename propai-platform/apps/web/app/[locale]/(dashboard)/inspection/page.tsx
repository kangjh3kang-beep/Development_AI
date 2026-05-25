import { InspectionOperationsWorkspaceClient } from "@/components/analytics/InspectionOperationsWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type InspectionPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function InspectionPage({
  params,
}: InspectionPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["inspection"].eyebrow}
        title={dictionary.modulePlaceholders["inspection"].title}
        description={dictionary.modulePlaceholders["inspection"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["inspection"].items}
      />
      <InspectionOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
