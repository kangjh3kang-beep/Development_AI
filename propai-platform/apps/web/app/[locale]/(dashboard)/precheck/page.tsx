import { PreCheckWorkspace } from "@/components/precheck/PreCheckWorkspace";
import { SatongMapShell } from "@/components/precheck/SatongMapShell";
import { isValidLocale } from "@/i18n/config";

type PreCheckPageProps = {
  params: Promise<{ locale: string }>;
  searchParams?: Promise<{ legacy?: string }>;
};

export default async function PreCheckPage({ params, searchParams }: PreCheckPageProps) {
  const { locale } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};

  if (!isValidLocale(locale)) {
    return null;
  }

  if (resolvedSearchParams.legacy === "1") {
    return (
      <div className="grid grid-cols-1 gap-6 min-w-0">
        <PreCheckWorkspace />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <SatongMapShell locale={locale} />
    </div>
  );
}
