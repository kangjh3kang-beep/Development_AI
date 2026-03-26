import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectContractWorkspaceClient } from "@/components/projects/ProjectContractWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ProjectContractsPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ProjectContractsPage({
  params,
}: ProjectContractsPageProps) {
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
        eyebrow="PROJECT / CONTRACTS"
        title="Project contract automation live route"
        description="Use the routed project id to generate a localized contract draft, reload the latest persisted contract, and hand it off to the live e-sign workflow."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load GET /projects/{id} as the project-aware source of truth",
          "Submit POST /contracts/generate for sale, lease, construction, and consulting drafts",
          "Handoff the generated draft through POST /contracts/{draft_id}/esign to reuse the live e-sign write path",
        ]}
      />
      <ProjectContractWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
