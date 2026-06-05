import { PermitAiWorkspaceClient } from "@/components/operations/PermitAiWorkspaceClient";
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
    <div className="grid gap-6">
      <PermitAiWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
