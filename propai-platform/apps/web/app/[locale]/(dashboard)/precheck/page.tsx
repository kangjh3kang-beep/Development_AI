import { PreCheckWorkspace } from "@/components/precheck/PreCheckWorkspace";
import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { ContextHeader } from "@/components/common/ContextHeader";
import { isValidLocale } from "@/i18n/config";

type PreCheckPageProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ legacy?: string }>;
};

export default async function PreCheckPage({ params, searchParams }: PreCheckPageProps) {
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};

  if (!isValidLocale(locale)) {
    return null;
  }

  if (resolvedSearchParams.legacy === "1") {
    return (
      <div className="grid grid-cols-1 gap-6 min-w-0">
        {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시. */}
        <ContextHeader />
        <PreCheckWorkspace />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시. */}
      <ContextHeader />
      <SatongMapShell locale={locale} />
    </div>
  );
}
