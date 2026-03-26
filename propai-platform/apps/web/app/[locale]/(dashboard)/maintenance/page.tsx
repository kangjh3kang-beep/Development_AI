import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type MaintenancePageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function MaintenancePage({
  params,
}: MaintenancePageProps) {
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
        eyebrow="MAINTENANCE / OPS"
        title="예지정비 운영센터"
        description="실시간 운영 데이터 대신 실제 maintenance API로 설비 이상 징후와 워크오더 흐름을 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "설비 telemetry 기반 anomaly detection",
          "심각도 + RUL + HVAC 효율 점수",
          "워크오더 생성 여부 확인",
        ]}
      />
      <OperationsIntelligenceWorkspaceClient
        locale={locale as Locale}
        sections={["maintenance"]}
        showHero={false}
      />
    </div>
  );
}
