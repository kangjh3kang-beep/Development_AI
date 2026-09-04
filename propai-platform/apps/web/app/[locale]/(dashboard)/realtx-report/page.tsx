import { RealtxReportPanel } from "@/components/dashboard/RealtxReportPanel";
import { isValidLocale } from "@/i18n/config";

type RealtxReportPageProps = {
  params: Promise<{ locale: string }>;
};

// 실거래 신고내역 현황분석 — MOLIT 계약상태 6필드(해제·해제일·거래유형·등기일자·매수/매도
// 법인개인)의 소비 표면. 종전에는 대시보드 생성허브 안에 **데이터 패널**로만 있어 카드 8개
// 아래(라이브 y≈2,921px)에 묻혀 있었다. 형제 8개 산출물과 같은 형태(카드 → 전용 라우트)로 올린다.
export default async function RealtxReportPage({ params }: RealtxReportPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-6">
      <RealtxReportPanel />
    </div>
  );
}
