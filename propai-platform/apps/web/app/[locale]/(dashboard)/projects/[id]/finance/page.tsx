import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectFinanceWorkspaceClient } from "@/components/projects/ProjectFinanceWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

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
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
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
