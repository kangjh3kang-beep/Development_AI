import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectDesignWorkspaceClient } from "@/components/projects/ProjectDesignWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DesignPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function DesignPage({ params }: DesignPageProps) {
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
        eyebrow="PROJECT / DESIGN"
        title="Project design live route"
        description="Use the routed project id to generate floor plans, auto IFC, and carbon analysis through the live design and BIM APIs."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Submit POST /design/floor-plan and POST /bim/generate-ifc",
          "Chain POST /bim/carbon from generated BIM quantities for project-scoped review",
        ]}
      />
      <ProjectDesignWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
