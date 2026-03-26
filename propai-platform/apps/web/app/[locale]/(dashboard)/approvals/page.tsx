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
        eyebrow="APPROVAL OPS / LIVE"
        title="Approval operations center"
        description="Operate pending approvals, tenant-wide audit filters, rationale review, and project-scoped batch decisions from one live workspace."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Tenant-wide approval queue and resolved decisions",
          "Approver-role and status filters",
          "Project-scoped bulk approve and reject actions",
        ]}
      />
      <ApprovalOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
