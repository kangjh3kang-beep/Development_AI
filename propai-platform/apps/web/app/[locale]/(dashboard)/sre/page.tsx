import { OperationsRouteHero } from "@/components/layout/OperationsRouteHero";
import { SREDashboard } from "@/components/sre/SREDashboard";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function SREPage({ params }: PageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);

    return (
    <div className="grid gap-6">
      <OperationsRouteHero
        eyebrow="SRE / DEVOPS ADMIN"
        title="인프라 관제소"
        description="Prometheus 메트릭, S3 재난복구 백업 기록, Grafana 모니터링을 통합한 SRE 어드민 대시보드"
        statusLabel={dictionary.status.ready}
        localeLabel={locale}
        items={[
          "CPU/메모리/에러율 실시간 메트릭",
          "S3 DR 백업 기록 및 RTO 위젯",
          "Grafana 임베딩 모니터링",
        ]}
      />
      <SREDashboard />
    </div>
  );
}
