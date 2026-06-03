import DeveloperProjection from "@/components/sales/DeveloperProjection";
import { isValidLocale } from "@/i18n/config";

export default async function SalesProjectionPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-lg font-black text-[var(--text-primary)]">분양 현장 현황 (시행사 투영)</h1>
        <p className="mt-0.5 text-xs text-[var(--text-secondary)]">집계 지표만 표시 — 고객/방문객 개인정보는 노출되지 않습니다.</p>
      </div>
      <DeveloperProjection />
    </div>
  );
}
