import { PreCheckWorkspace } from "@/components/precheck/PreCheckWorkspace";
import { isValidLocale } from "@/i18n/config";

type PreCheckPageProps = {
  params: Promise<{ locale: string }>;
};

export default async function PreCheckPage({ params }: PreCheckPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <PreCheckWorkspace />
    </div>
  );
}
