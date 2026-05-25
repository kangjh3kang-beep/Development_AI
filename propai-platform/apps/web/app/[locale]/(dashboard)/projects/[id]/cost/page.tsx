import BimCostDashboard from "@/components/cost/BimCostDashboard";

export default async function CostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <BimCostDashboard projectId={id} />;
}
