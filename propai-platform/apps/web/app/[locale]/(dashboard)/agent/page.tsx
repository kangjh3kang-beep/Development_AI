import { AgentOrchestrationWorkspaceClient } from "@/components/agent/AgentOrchestrationWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type AgentPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function AgentPage({ params }: AgentPageProps) {
  const { locale } = await params;

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
        eyebrow={dictionary.pages.agent.eyebrow}
        title={dictionary.pages.agent.title}
        description={dictionary.pages.agent.description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          dictionary.pages.agent.items.first,
          dictionary.pages.agent.items.second,
          dictionary.pages.agent.items.third,
        ]}
      />
      <AgentOrchestrationWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
