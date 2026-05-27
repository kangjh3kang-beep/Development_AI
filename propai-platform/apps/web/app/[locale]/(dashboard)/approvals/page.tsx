import { ApprovalOperationsWorkspaceClient } from "@/components/agent/ApprovalOperationsWorkspaceClient";
import { OperationsRouteHero } from "@/components/layout/OperationsRouteHero";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ApprovalsPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ApprovalsPage({ params }: ApprovalsPageProps) {
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
      <OperationsRouteHero
        eyebrow={dictionary.pages.approvalCenter.eyebrow}
        title={dictionary.pages.approvalCenter.title}
        description={dictionary.pages.approvalCenter.description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          dictionary.pages.approvalCenter.items.first,
          dictionary.pages.approvalCenter.items.second,
          dictionary.pages.approvalCenter.items.third,
        ]}
      />
      <ApprovalOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
