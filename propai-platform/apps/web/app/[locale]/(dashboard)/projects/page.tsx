import Link from "next/link";
import { ProjectsOverviewClient } from "@/components/projects/ProjectsOverviewClient";
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
  const meta = dictionary.modulePlaceholders["projects"];

  return (
    <div className="grid gap-6">
      {/* 실 목록 화면 헤더 — 목업 배너 제거(무목업), 제목+생성 CTA만 유지 */}
      <header className="flex flex-wrap items-end justify-between gap-4 px-2">
        <div className="space-y-1.5">
          <div className="flex items-center gap-3">
            <span className="cc-meta">{meta.eyebrow}</span>
            <span className="cc-live"><i />LIVE</span>
          </div>
          <h1 className="text-3xl font-[900] tracking-tighter text-[var(--text-primary)] sm:text-4xl">
            {meta.title}
          </h1>
          <p className="max-w-2xl text-sm font-medium text-[var(--text-secondary)]">
            {meta.description}
          </p>
        </div>
        <Link
          href={`/${locale}/projects/new`}
          className="inline-flex items-center gap-2 whitespace-nowrap rounded-2xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] transition-all hover:-translate-y-0.5 hover:scale-[1.02] active:scale-95"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M5 12h14M12 5v14"/></svg>
          새 프로젝트
        </Link>
      </header>
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
