import { OperationsRouteHero } from "@/components/layout/OperationsRouteHero";
import { RemoteSupervisionRoom } from "@/features/webrtc/RemoteSupervisionRoom";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function WebRTCPage({ params }: PageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

    return (
    <div className="grid gap-6">
      <OperationsRouteHero
        eyebrow="WEBRTC / REMOTE SUPERVISION"
        title="원격 감리 화상회의"
        description="WebRTC 1.0 기반 실시간 화상 감리와 STT 음성 인식 회의록 자동 기록 시스템"
        statusLabel={dictionary.status.ready}
        localeLabel={locale}
        items={[
          "P2P 화상 통화 (coturn relay)",
          "STT 음성 인식 회의록",
          "ICE 3회 재시도 + 지수 백오프",
        ]}
      />
      <RemoteSupervisionRoom />
    </div>
  );
}
