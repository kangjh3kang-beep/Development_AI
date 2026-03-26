import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectReportWorkspaceClient } from "@/components/projects/ProjectReportWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ReportPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
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
        eyebrow="PROJECT / REPORT"
        title="Project report live route"
        description="Use the routed project id to generate multilingual investor reports through the live reporting APIs."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Submit POST /reports/investor/generate from the project detail route",
          "Review multilingual report variants and generated sections on-screen",
        ]}
      />
      <ProjectReportWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
