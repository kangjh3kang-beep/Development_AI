import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectBlockchainWorkspaceClient } from "@/components/projects/ProjectBlockchainWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type BlockchainPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function BlockchainPage({
  params,
}: BlockchainPageProps) {
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
        eyebrow="PROJECT / BLOCKCHAIN"
        title="Project blockchain live route"
        description="Use the routed project id to inspect next escrow state, create an escrow record, and query on-chain status through the live blockchain APIs."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Read GET /blockchain/escrow/next-id and create POST /blockchain/escrow records",
          "Query GET /blockchain/escrow/{id} for project-scoped escrow status review",
        ]}
      />
      <ProjectBlockchainWorkspaceClient
        locale={locale as Locale}
        projectId={id}
      />
    </div>
  );
}
