import { HarnessControlDashboard } from "@/components/tenant/HarnessControlDashboard";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type TenantPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function TenantPage({ params }: TenantPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
      <HarnessControlDashboard />
    </div>
  );
}
