import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { CarbonEmissionsWorkspaceClient } from "@/components/analytics/CarbonEmissionsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type CarbonPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function CarbonPage({ params }: CarbonPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["carbon"].eyebrow}
        title={dictionary.modulePlaceholders["carbon"].title}
        description={dictionary.modulePlaceholders["carbon"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["carbon"].items}
      />
      <CarbonEmissionsWorkspaceClient
        dictionary={dictionary.modulePlaceholders["carbon"] as unknown as Record<string, string>}
        locale={locale}
      />
    </div>
  );
}
