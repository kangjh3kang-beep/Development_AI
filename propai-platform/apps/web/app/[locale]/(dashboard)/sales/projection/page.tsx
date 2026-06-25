import DeveloperProjection from "@/components/sales/DeveloperProjection";
import { isValidLocale } from "@/i18n/config";

export default async function SalesProjectionPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isValidLocale(locale)) return null;
  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <span className="cc-meta">DEVELOPER · PROJECTION</span>
          <h1 className="mt-1 text-lg font-black text-[var(--text-primary)]">분양 현장 요약 현황 (시행사용)</h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">현장별 요약 숫자만 표시합니다 — 고객·방문객 개인정보는 보이지 않습니다.</p>
        </div>
        <span className="cc-chip-data ml-auto">PII MASKED</span>
      </div>
      <DeveloperProjection />
    </div>
  );
}
