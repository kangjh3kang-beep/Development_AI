import { DigitalTwinAnomalyDashboard } from "@/components/digital-twin/DigitalTwinAnomalyDashboard";
import { DigitalTwinControlTowerWorkspaceClient } from "@/components/digital-twin/DigitalTwinControlTowerWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";

type DigitalTwinPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function DigitalTwinPage({
  params,
}: DigitalTwinPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <DigitalTwinControlTowerWorkspaceClient locale={locale as Locale} />
      <DigitalTwinAnomalyDashboard />
    </div>
  );
}
