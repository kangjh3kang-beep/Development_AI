import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { isValidLocale } from "@/i18n/config";

type AnalysisPageProps = {
  params: Promise<{ locale: string }>;
};

// 종합 부지분석 — 주소 하나로 7개 카테고리(실효용적률·공급면적·시세·실거래·분양가·입지·개발계획)를
// 자동 분석하는 자족형 패널을 마운트하는 페이지. 패널이 자체 주소검색·LLM 모델선택을 보유하므로
// 여기서는 별도 입력/상태 없이 그대로 띄우기만 한다.
export default async function AnalysisPage({ params }: AnalysisPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <ComprehensiveAnalysisPanel />
    </div>
  );
}
