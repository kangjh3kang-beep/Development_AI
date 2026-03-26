import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { OperationsIntelligenceWorkspaceClient } from "@/components/analytics/OperationsIntelligenceWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type IoTPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function IoTPage({ params }: IoTPageProps) {
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
        eyebrow="OPS / INTELLIGENCE"
        title="운영 인텔리전스 워크스페이스"
        description="예지정비, 테넌트 경험, 자산 인텔리전스를 실제 운영 API 체인으로 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "예지정비 anomaly detection",
          "테넌트 sentiment / NPS",
          "자산 인텔리전스 복합 점수",
        ]}
      />
      <OperationsIntelligenceWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
