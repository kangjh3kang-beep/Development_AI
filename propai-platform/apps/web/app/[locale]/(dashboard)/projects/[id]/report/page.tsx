import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { ProjectReportWorkspaceClient } from "@/components/projects/ProjectReportWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { ReportDownloadMenu } from "@/components/report/ReportDownloadMenu";
import { BankReadyReportBuilder } from "@/components/report/BankReadyReportBuilder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";

type ReportPageProps = {
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
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
      <ModuleCommandStrip label="REPORT · 통합 보고서" meta={runtimeMode} />
      <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["report"].eyebrow}
        title={dictionary.modulePlaceholders["report"].title}
        description={dictionary.modulePlaceholders["report"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["report"].items}
      />

      {/* Innovation 4: Bank-Ready Report Engine —
          프로젝트 통합보고서(부지~ESG 10섹션, 프로젝트 상세에 표시)와는 별개의 산출물.
          PF대출 심사 제출용 "은행 PF" 전용 보고서임을 명확히 라벨링(혼동 제거). */}
      <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="rounded-lg bg-[var(--accent-soft)] px-3 py-1 label-caps text-[var(--accent-strong)]">
            은행 PF 제출용
          </span>
          <p className="text-sm font-bold text-[var(--text-primary)]">PF대출 심사 보고서</p>
          <span className="text-xs text-[var(--text-secondary)]">
            — 프로젝트 통합 분석보고서와는 별개의 금융기관 제출 전용 산출물입니다.
          </span>
        </div>
        <BankReadyReportBuilder />
      </div>

      <div className="flex justify-end">
        <div className="w-full max-w-xs">
          {/* 통합 보고서 생성엔진: PDF·PPT·Word 중 선택 다운로드(같은 데이터·같은 디자인) */}
          <ReportDownloadMenu projectId={id} />
        </div>
      </div>
      <ProjectReportWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} currentStage="report" />
    </div>
  );
}
