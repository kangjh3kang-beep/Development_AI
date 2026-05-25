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
        eyebrow={dictionary.modulePlaceholders["report"].eyebrow}
        title={dictionary.modulePlaceholders["report"].title}
        description={dictionary.modulePlaceholders["report"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["report"].items}
      />
      <ProjectReportWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
