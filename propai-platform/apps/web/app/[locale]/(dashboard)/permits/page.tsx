import { PermitAiWorkspaceClient } from "@/components/operations/PermitAiWorkspaceClient";
import { PermitsWorkspaceClient } from "@/components/operations/PermitsWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type PermitsPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function PermitsPage({ params }: PermitsPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <PermitAiWorkspaceClient locale={locale as Locale} />
      <PermitsWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
