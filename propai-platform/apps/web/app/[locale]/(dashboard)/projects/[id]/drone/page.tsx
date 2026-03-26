import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectDroneWorkspaceClient } from "@/components/projects/ProjectDroneWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type DronePageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function DronePage({ params }: DronePageProps) {
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
        eyebrow="PROJECT / DRONE"
        title="Project drone live route"
        description="Use the routed project id to run persisted drone inspection against the live image-based defect detection API."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "Load the current project context from GET /projects/{id}",
          "Submit POST /drone/inspect from the project detail route",
          "Review persisted defect counts, severity summary, and detected issues",
        ]}
      />
      <ProjectDroneWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
