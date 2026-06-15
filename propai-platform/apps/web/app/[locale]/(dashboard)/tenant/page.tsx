import { TenantWorkspaceClient } from "@/components/operations/TenantWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";

/**
 * 임차인 포털(자산 운영) — 준공 후 임대 자산의 임차인 관리 워크스페이스.
 * ※ 과거엔 무관한 시스템 하네스 제어 대시보드(HarnessControlDashboard)와 일반 ModulePlaceholder가
 *   함께 렌더돼 페이지 목적이 흐려졌다('tenant' 이름 충돌). → 임차인 관리 워크스페이스만 단일 노출.
 */
type TenantPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function TenantPage({ params }: TenantPageProps) {
  const { locale } = await params;
  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <TenantWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
