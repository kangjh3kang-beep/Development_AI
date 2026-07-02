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
        {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시.
            sitePipeline=true: 부지분석 SSOT 기반 분석 3단계 실제 상태 자동 파생(default 브랜치와 동일). */}
        <ContextHeader sitePipeline />
        <PreCheckWorkspace />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시.
          sitePipeline=true: 부지분석 SSOT(수집=주소·면적, 검증=근거트레이스, 전문가=특이부지·종상향)
          에서 분석 3단계 실제 상태를 자동 파생해 함께 표시(deriveSitePipelineSteps). */}
      <ContextHeader sitePipeline />
      <SatongMapShell locale={locale} />
    </div>
  );
}
