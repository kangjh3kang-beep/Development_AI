import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectReportWorkspaceClient } from "@/components/projects/ProjectReportWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { ReportPdfDownload } from "@/components/projects/ReportPdfDownload";
import { BankReadyReportBuilder } from "@/components/report/BankReadyReportBuilder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

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
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
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
          <span className="rounded-lg bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
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
          <ReportPdfDownload projectId={id} />
        </div>
      </div>
      <ProjectReportWorkspaceClient locale={locale as Locale} projectId={id} />
      <NextStageCta locale={locale} currentStage="report" />
    </div>
  );
}
