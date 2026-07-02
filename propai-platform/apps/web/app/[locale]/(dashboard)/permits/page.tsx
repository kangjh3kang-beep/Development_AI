import { PermitAiWorkspaceClient } from "@/components/operations/PermitAiWorkspaceClient";
import { VisionBanner } from "@/components/common/VisionBanner";
import { ContextHeader } from "@/components/common/ContextHeader";
import { isValidLocale, type Locale } from "@/i18n/config";

type PermitsPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function PermitsPage({ params }: PermitsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  // 레거시 PermitsWorkspaceClient(정적 '로그인 필요' 폼)는 AI 분석과 중복 + 로그인 게이트 오류라 제거.
  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 생성허브 공용 대상 컨텍스트 헤더(additive) — 어느 프로젝트·토지 대상 분석인지 상시 표시. */}
      <ContextHeader />
      <VisionBanner variant="permit" />
      <PermitAiWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
