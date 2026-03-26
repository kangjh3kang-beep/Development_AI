import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectBimWorkspaceClient } from "@/components/projects/ProjectBimWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/get-dictionary";

type BimPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function BimPage({ params }: BimPageProps) {
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
        eyebrow="PROJECT / BIM"
        title="Project BIM live route"
        description="Use the routed project id to generate BIM quantities and geometry summaries through the live BIM APIs."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Submit POST /bim/generate-ifc from the project detail route",
          "Load GET /bim/threejs/{project_id} to review generated geometry coverage",
        ]}
      />
      <ProjectBimWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
