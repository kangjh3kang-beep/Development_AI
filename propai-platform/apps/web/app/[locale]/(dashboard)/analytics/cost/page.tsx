import { ConstructionCostWorkspaceClient } from "@/components/analytics/ConstructionCostWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type CostAnalyticsPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function CostAnalyticsPage({
  params,
}: CostAnalyticsPageProps) {
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
        eyebrow="COST / PPI"
        title="공사비 인텔리전스 허브"
        description="KCCI 자재가, 프로젝트 추정 노출액, ECOS 기반 공사비 에스컬레이션 시나리오를 실백엔드에 연결해 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "자재가 히스토리와 가격 급등 경보",
          "프로젝트별 자재 노출액 추정",
          "PPI 연동 공사비 보정 시나리오",
        ]}
      />
      <ConstructionCostWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
