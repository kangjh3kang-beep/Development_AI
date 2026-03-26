import { ProjectsOverviewClient } from "@/components/projects/ProjectsOverviewClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ProjectsPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ProjectsPage({ params }: ProjectsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

  return (
    <div className="grid gap-6">
      <ModulePlaceholder
        eyebrow={dictionary.pages.projects.eyebrow}
        title={dictionary.pages.projects.title}
        description={dictionary.pages.projects.description}
        statusLabel={dictionary.status.ready}
        localeLabel={locale}
        items={[
          dictionary.pages.projects.items.first,
          dictionary.pages.projects.items.second,
          dictionary.pages.projects.items.third,
        ]}
      />
      <ProjectsOverviewClient
        locale={locale}
        labels={dictionary.workspace}
        moduleLabels={{
          design: dictionary.nav.design,
          bim: dictionary.nav.bim,
          finance: dictionary.nav.finance,
          drone: dictionary.nav.drone,
          blockchain: dictionary.nav.blockchain,
          report: dictionary.nav.report,
          tax: dictionary.nav.tax,
          inspection: dictionary.nav.inspection,
        }}
      />
    </div>
  );
}
