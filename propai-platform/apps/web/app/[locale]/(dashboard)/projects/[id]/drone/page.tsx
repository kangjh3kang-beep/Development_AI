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
        eyebrow={dictionary.modulePlaceholders["drone"].eyebrow}
        title={dictionary.modulePlaceholders["drone"].title}
        description={dictionary.modulePlaceholders["drone"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["drone"].items}
      />
      <ProjectDroneWorkspaceClient locale={locale as Locale} projectId={id} />
    </div>
  );
}
