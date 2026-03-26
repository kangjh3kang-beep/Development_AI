import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { EnergyOperationsWorkspaceClient } from "@/components/analytics/EnergyOperationsWorkspaceClient";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type ESGPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function ESGPage({ params }: ESGPageProps) {
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
        eyebrow="ENERGY / CERT"
        title="에너지 인증 워크스페이스"
        description="KEPCO 전기요금과 프로젝트별 에너지/ZEB 인증 추정을 실 API에 연결해 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "KEPCO 요금 계산 실연동",
          "프로젝트별 에너지 등급/ZEB 추정",
          "BEMS 절감률과 권고안 검증",
        ]}
      />
      <EnergyOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
