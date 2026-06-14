import { isValidLocale } from "@/i18n/config";
import { MeetingRoomsListClient } from "@/components/collaboration/MeetingRoomsListClient";

type Props = {
  params: Promise<{ locale: string }>;
};

export default async function MeetingRoomsPage({ params }: Props) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-8 min-h-screen pb-20">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">프로젝트 회의방</h1>
        <p className="mt-1 max-w-2xl text-sm text-[var(--text-secondary)]">
          프로젝트를 선택해 회의방에 입장합니다 — 팀·협력업체 협업, 외부 협력업체(교통·환경·토목 등) 심의
          초대를 관리합니다. 자료교환·화상회의·심의 검증은 후속 단계에서 확장됩니다.
        </p>
      </div>
      <MeetingRoomsListClient locale={locale} />
    </div>
  );
}
