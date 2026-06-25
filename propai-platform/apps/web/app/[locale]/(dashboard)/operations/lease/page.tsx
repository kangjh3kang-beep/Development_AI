import { LeaseOpsWorkspace } from "@/components/lease-ops/LeaseOpsWorkspace";
import { isValidLocale, type Locale } from "@/i18n/config";

type LeaseOpsPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function LeaseOpsPage({ params }: LeaseOpsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <LeaseOpsWorkspace locale={locale as Locale} />
    </div>
  );
}
