import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { ProjectContractWorkspaceClient } from "@/components/projects/ProjectContractWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
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
      <ModuleCommandStrip label="CONTRACTS · 계약 관리" meta={runtimeMode} />
      <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["contracts"].eyebrow}
        title={dictionary.modulePlaceholders["contracts"].title}
        description={dictionary.modulePlaceholders["contracts"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["contracts"].items}
      />
      <ProjectContractWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} />
    </div>
  );
}
