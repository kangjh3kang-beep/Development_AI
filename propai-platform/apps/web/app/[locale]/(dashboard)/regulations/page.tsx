import { RegulationsWorkspaceClient } from "@/components/operations/RegulationsWorkspaceClient";
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
      <RegulationsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
