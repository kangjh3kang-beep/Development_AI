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
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <DigitalTwinControlTowerWorkspaceClient locale={locale as Locale} />
      <DigitalTwinAnomalyDashboard />
    </div>
  );
}
