import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectFinanceWorkspaceClient } from "@/components/projects/ProjectFinanceWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type FinancePageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function FinancePage({ params }: FinancePageProps) {
  const { locale, id } = await params;

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
        eyebrow="PROJECT / FINANCE"
        title="Project finance live route"
        description="Use the routed project id to run persisted AVM valuation and jeonse risk analysis against the live finance APIs."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Chain POST /avm with POST /finance/jeonse-risk",
          "Review persisted pricing, ratio, and risk output for this project path",
        ]}
      />
      <ProjectFinanceWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
