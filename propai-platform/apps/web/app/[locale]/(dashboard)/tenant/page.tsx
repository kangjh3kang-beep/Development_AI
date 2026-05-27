import { HarnessControlDashboard } from "@/components/tenant/HarnessControlDashboard";
import { TenantWorkspaceClient } from "@/components/operations/TenantWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type TenantPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function TenantPage({ params }: TenantPageProps) {
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
        eyebrow={dictionary.modulePlaceholders["tenant"].eyebrow}
        title={dictionary.modulePlaceholders["tenant"].title}
        description={dictionary.modulePlaceholders["tenant"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["tenant"].items}
      />
      <HarnessControlDashboard />
      <TenantWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
