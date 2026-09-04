import { RegulationsWorkspaceClient } from "@/components/operations/RegulationsWorkspaceClient";
import { ContextHeader } from "@/components/common/ContextHeader";
import { isValidLocale, type Locale } from "@/i18n/config";

type RegulationsPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function RegulationsPage({ params }: RegulationsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      {/* 생성허브 공용 대상 컨텍스트 헤더(additive·permits/page.tsx 미러) — 어느 프로젝트·토지 대상 분석인지 상시 표시. */}
      <ContextHeader />
      <RegulationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
