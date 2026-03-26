import { FeasibilityWorkspaceClient } from "@/components/feasibility/FeasibilityWorkspaceClient";
import { isValidLocale } from "@/i18n/config";

type LocalizedFeasibilityPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function LocalizedFeasibilityPage({
  params,
}: LocalizedFeasibilityPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return <FeasibilityWorkspaceClient />;
}
