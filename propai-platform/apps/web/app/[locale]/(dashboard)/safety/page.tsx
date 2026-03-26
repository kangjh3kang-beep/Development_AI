import { OperationsRouteHero } from "@/components/layout/OperationsRouteHero";
import { SafetyCCTVDashboard } from "@/components/safety/SafetyCCTVDashboard";
import { ParkingLogView } from "@/components/safety/ParkingLogView";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function SafetyPage({ params }: PageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

    return (
    <div className="grid gap-6">
      <OperationsRouteHero
        eyebrow="SAFETY / VISION AI"
        title="지능형 CCTV 관제 대시보드"
        description="YOLOv8 비전 AI 기반 공사현장 안전모·조끼 미착용 실시간 감지 및 주차 관제 시스템"
        statusLabel={dictionary.status.ready}
        localeLabel={locale}
        items={[
          "실시간 CCTV 스트림 모니터링",
          "안전 위반 적발 알림 피드",
          "주차장 출입차 OCR 로깅",
        ]}
      />
      <SafetyCCTVDashboard />
      <ParkingLogView />
    </div>
  );
}
