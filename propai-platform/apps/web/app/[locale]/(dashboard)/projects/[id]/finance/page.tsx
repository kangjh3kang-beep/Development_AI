import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { ProjectFinanceWorkspaceClient } from "@/components/projects/ProjectFinanceWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";

type FinancePageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function FinancePage({ params }: FinancePageProps) {
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
      <ModuleCommandStrip label="FINANCE · 금융·자금조달" meta={runtimeMode} />
      <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["finance"].eyebrow}
        title={dictionary.modulePlaceholders["finance"].title}
        description={dictionary.modulePlaceholders["finance"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["finance"].items}
      />
      <ProjectFinanceWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} currentStage="finance" />
    </div>
  );
}
