import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectSummaryClient } from "@/components/projects/ProjectSummaryClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/get-dictionary";

type ProjectDetailPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ProjectDetailPage({
  params,
}: ProjectDetailPageProps) {
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
        eyebrow="PROJECT / OVERVIEW"
        title="Project live overview"
        description="Use the routed project id to review live backend metadata and navigate directly into the project-scoped module workspaces."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load GET /projects/{id} as the source of truth for project metadata",
          "Navigate into live contracts, finance, report, inspection, BIM, design, and blockchain subroutes",
          "Keep CAD explicitly separated as an editor-only route until its dependency blockers are resolved",
        ]}
      />
      <ProjectSummaryClient
        locale={locale}
        projectId={id}
        moduleLabels={{
          contracts: dictionary.nav.contracts,
          design: dictionary.nav.design,
          bim: dictionary.nav.bim,
          finance: dictionary.nav.finance,
          drone: dictionary.nav.drone,
          blockchain: dictionary.nav.blockchain,
          report: dictionary.nav.report,
        }}
      />
    </div>
  );
}
