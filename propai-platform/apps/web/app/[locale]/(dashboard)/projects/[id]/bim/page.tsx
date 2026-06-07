import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectBimWorkspaceClient } from "@/components/projects/ProjectBimWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
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
        eyebrow={dictionary.modulePlaceholders["bim"].eyebrow}
        title={dictionary.modulePlaceholders["bim"].title}
        description={dictionary.modulePlaceholders["bim"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["bim"].items}
      />
      <ProjectBimWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} />
    </div>
  );
}
