import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { isValidLocale } from "@/i18n/config";

type AnalysisPageProps = {
  params: Promise<{ locale: string }>;
};

// 종합 부지분석 — 주소 하나로 7개 카테고리(실효용적률·공급면적·시세·실거래·분양가·입지·개발계획)를
// 자동 분석하는 자족형 패널을 마운트하는 페이지. 여기서는 별도 입력/상태 없이 그대로 띄우기만 한다.
// ★정정(2026-08-06): 종전 주석은 "패널이 자체 주소검색을 보유하므로"라고 썼는데 **사실이 아니다** —
//   ComprehensiveAnalysisPanel 에는 자체 주소 입력이 없고, 주소는 SatongMapShell(지도셸)이
//   **유일한 진입 경로**다. 모바일 IA P1 이 "대상이 없으면 셸을 펼친다"로 바꾼 근거가 이 사실이다.
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
