import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { InvestmentOperationsWorkspaceClient } from "@/components/analytics/InvestmentOperationsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type InvestmentPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function InvestmentPage({ params }: InvestmentPageProps) {
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
        eyebrow="INVESTMENT / OPS"
        title="투자 운영 컨트롤타워"
        description="AI 비용, 투자자 보고서, 포털 게재를 실제 백엔드와 연결해 투자 운영 실행 체인을 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "AI 사용량/예산 게이트 실연동",
          "다국어 투자자 리포트 생성",
          "부동산 포털 일괄 게재 + 시장 데이터",
        ]}
      />
      <InvestmentOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
