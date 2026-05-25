import { KdxMonitoringWorkspaceClient } from "@/components/dashboard/kdx/KdxMonitoringWorkspaceClient";
import { isValidLocale } from "@/i18n/config";

type LocalizedKdxDashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function LocalizedKdxDashboardPage({
  params,
}: LocalizedKdxDashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div data-testid="kdx-monitoring-workspace">
      <KdxMonitoringWorkspaceClient />
    </div>
  );
}
