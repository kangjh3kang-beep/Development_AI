import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectBlockchainWorkspaceClient } from "@/components/projects/ProjectBlockchainWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";

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
  const runtimeMode = isMockMode()
    ? dictionary.workspace.modeMock
    : dictionary.workspace.modeLive;

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
            <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["blockchain"].eyebrow}
        title={dictionary.modulePlaceholders["blockchain"].title}
        description={dictionary.modulePlaceholders["blockchain"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["blockchain"].items}
      />
      <ProjectBlockchainWorkspaceClient
        locale={locale as Locale}
        projectId={id}
      />
    </div>
  );
}
