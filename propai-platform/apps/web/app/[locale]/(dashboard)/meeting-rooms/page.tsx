import { isValidLocale } from "@/i18n/config";
import { MeetingRoomsListClient } from "@/components/collaboration/MeetingRoomsListClient";
import { DesignCenterPageFrame } from "@/components/design-center/DesignCenterPageFrame";

type Props = {
  params: Promise<{ locale: string }>;
};

export default async function MeetingRoomsPage({ params }: Props) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <DesignCenterPageFrame
      locale={locale}
      activeId="meeting-rooms"
      title="프로젝트 회의방"
      description="프로젝트별 회의방에서 팀·협력업체 협업과 심의 검증 초대를 한 곳에서 관리합니다."
      status="ready"
      statusLabel="협업 허브"
      metrics={[
        { label: "범위", value: "프로젝트별", description: "회의방 입장" },
        { label: "협력자", value: "외부 초대", description: "교통 · 환경 · 토목" },
        { label: "확장", value: "자료·화상", description: "후속 단계" },
      ]}
    >
      <MeetingRoomsListClient locale={locale} />
    </DesignCenterPageFrame>
  );
}
