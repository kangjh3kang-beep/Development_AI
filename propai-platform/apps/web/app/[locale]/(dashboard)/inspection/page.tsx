import { InspectionOperationsWorkspaceClient } from "@/components/analytics/InspectionOperationsWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type InspectionPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function InspectionPage({
  params,
}: InspectionPageProps) {
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
        eyebrow="INSPECTION / DRONE"
        title="현장 점검 라이브 센터"
        description="실제 drone API에 연결해 이미지 기반 하자 탐지, 심각도 집계, flight_id 저장 흐름을 검증합니다."
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={[
          "이미지 URL 기반 defect detection",
          "심각도별 집계와 처리 이미지 수 확인",
          "프로젝트 / flight_id 단위 inspection persistence",
        ]}
      />
      <InspectionOperationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
