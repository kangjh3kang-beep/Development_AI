import { TaxOperationsWorkspaceClient } from "@/components/analytics/TaxOperationsWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type TaxPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function TaxPage({ params }: TaxPageProps) {
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
        eyebrow="TAX / LIVE OPS"
        title="세금 라이브 센터"
        description="실제 tax API에 연결해 프로젝트 기준의 세액, 세율, 공제, 절세 팁을 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "프로젝트 FK 기반 실세금 계산",
          "취득세 / 보유세 / 양도세 시나리오",
          "공제 항목과 절세 팁 확인",
        ]}
      />
      <TaxOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
