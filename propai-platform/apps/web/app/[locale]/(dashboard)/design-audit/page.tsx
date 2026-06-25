import { DesignAuditWorkspace } from "@/components/design-audit/DesignAuditWorkspace";
import { isValidLocale, type Locale } from "@/i18n/config";

/** 설계안 AI 심사(DA-7) — 4단 스테퍼(부지→개요→도면→실행) 페이지. */
export default async function DesignAuditPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <DesignAuditWorkspace locale={locale as Locale} />
    </div>
  );
}
