import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type TenantPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function TenantPage({ params }: TenantPageProps) {
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
        eyebrow="TENANT / EXPERIENCE"
        title="테넌트 경험 센터"
        description="feedback 분석과 NPS/점유 건전성을 실제 tenant API에 연결해 운영 응답 체계를 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "피드백 sentiment + AI reply",
          "NPS / churn risk 계산",
          "건물 점유 건전성 등급화",
        ]}
      />
      <OperationsIntelligenceWorkspaceClient
        locale={locale as Locale}
        sections={["tenant"]}
        showHero={false}
      />
    </div>
  );
}
