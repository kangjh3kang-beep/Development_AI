"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type ProjectSummary = { id: string; name: string; total_area_sqm: number | null };
type PaginatedResponse<T> = { items: T[]; page: number; page_size: number; has_next: boolean };
type StatusResponse = {
  status: string;
  operational_readiness_score: number;
  eui_grade: string;
  eui: number;
  sensor_health_ratio: number;
  highest_anomaly_severity: string;
};
type RiskResponse = {
  composite_risk_score: number;
  grade: string;
  var_95_ratio: number;
  p90_adjusted_cost_krw: number;
  summary: string;
};
type PermitResponse = {
  status: string;
  current_stage: string;
  readiness_score: number;
  progress_pct: number;
  submission_reference: string;
  missing_required_documents: string[];
};

const buildingTypes = [
  { label: "Office", value: "office" },
  { label: "Residential", value: "residential" },
  { label: "Retail", value: "retail" },
];
const permitTypes = [
  { label: "Building permit", value: "building_permit" },
  { label: "Development permit", value: "development_permit" },
  { label: "Occupancy approval", value: "occupancy_approval" },
];
const regions = [
  { label: "Seoul", value: "seoul" },
  { label: "Gyeonggi", value: "gyeonggi" },
  { label: "Default", value: "default" },
];
const yesNo = [
  { label: "No", value: "false" },
  { label: "Yes", value: "true" },
];

function errorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return "API authentication is required for live workspace calls.";
    }
    return `API request failed with status ${error.status}.`;
  }
  return error instanceof Error ? error.message : "Request failed.";
}

async function optionalGet<T>(path: string) {
  try {
    return await apiClient.get<T>(path, { useMock: false });
  } catch (error) {
    if (error instanceof ApiClientError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function DigitalTwinControlTowerWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const queryClient = useQueryClient();
  const runtime = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtime.mode === "live" || runtime.hasAccessToken;
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [statusForm, setStatusForm] = useState({
    buildingType: "office",
    grossFloorArea: "4200",
    annualEnergy: "756000",
    occupancyRate: "0.91",
    sensorCount: "24",
    onlineSensorCount: "22",
    criticalAlarmCount: "0",
  });
  const [riskForm, setRiskForm] = useState({
    baseProjectCost: "18500000000",
    marketRiskScore: "52",
    ltvRatio: "0.65",
    dscr: "1.18",
    permitReadinessRatio: "0.55",
    occupancyRate: "0.91",
    presaleRatio: "0.42",
    climateRiskScore: "38",
    costVolatilityRatio: "0.12",
  });
  const [permitForm, setPermitForm] = useState({
    permitType: "building_permit",
    region: "seoul",
    buildingArea: "4200",
    isPublic: "false",
    isAgricultural: "false",
    submitToSeumter: "true",
    submittedDocumentIds: "BA-01, BA-02, BA-03, BA-04, BA-05",
  });
  const [pending, setPending] = useState<"status" | "risk" | "permit" | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects", "digital-twin-control-tower"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>("/projects?page=1&page_size=20", {
        useMock: false,
      }),
  });

  useEffect(() => {
    if (!selectedProjectId && projectsQuery.data?.items.length) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data, selectedProjectId]);

  const selectedProject =
    projectsQuery.data?.items.find((project) => project.id === selectedProjectId) ?? null;
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";

  useEffect(() => {
    if (!selectedProject?.total_area_sqm) return;
    const area = Math.round(selectedProject.total_area_sqm).toString();
    setStatusForm((current) => ({ ...current, grossFloorArea: area }));
    setPermitForm((current) => ({ ...current, buildingArea: area }));
  }, [selectedProject?.id, selectedProject?.total_area_sqm]);

  const statusQuery = useQuery({
    queryKey: ["digital-twin-status", activeProjectId],
    enabled: canUseLiveApi && Boolean(activeProjectId),
    queryFn: () => optionalGet<StatusResponse>(`/digital-twin/status/${activeProjectId}/latest`),
  });
  const riskQuery = useQuery({
    queryKey: ["unified-risk", activeProjectId],
    enabled: canUseLiveApi && Boolean(activeProjectId),
    queryFn: () => optionalGet<RiskResponse>(`/risk/unified/${activeProjectId}/latest`),
  });
  const permitQuery = useQuery({
    queryKey: ["permit-status", activeProjectId],
    enabled: canUseLiveApi && Boolean(activeProjectId),
    queryFn: () => optionalGet<PermitResponse>(`/permits/${activeProjectId}/latest`),
  });

  async function handleStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    if (!activeProjectId) return setWorkspaceError("A real project UUID is required.");
    setPending("status");
    try {
      await apiClient.post("/digital-twin/status/snapshot", {
        useMock: false,
        body: {
          project_id: activeProjectId,
          building_type: statusForm.buildingType,
          gross_floor_area_sqm: Number(statusForm.grossFloorArea),
          annual_energy_kwh: Number(statusForm.annualEnergy),
          occupancy_rate: Number(statusForm.occupancyRate),
          sensor_count: Number(statusForm.sensorCount),
          online_sensor_count: Number(statusForm.onlineSensorCount),
          critical_alarm_count: Number(statusForm.criticalAlarmCount),
          recent_outdoor_temps_c: [21, 24, 26, 27],
          recent_energy_readings_kwh: [1950, 2120, 2280, 2360],
          target_outdoor_temp_c: 28,
        },
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["digital-twin-status", activeProjectId] }),
        queryClient.invalidateQueries({ queryKey: ["unified-risk", activeProjectId] }),
      ]);
    } catch (error) {
      setWorkspaceError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function handleRisk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    if (!activeProjectId) return setWorkspaceError("A real project UUID is required.");
    setPending("risk");
    try {
      await apiClient.post("/risk/unified/analyze", {
        useMock: false,
        body: {
          project_id: activeProjectId,
          base_project_cost_krw: Number(riskForm.baseProjectCost),
          market_risk_score: Number(riskForm.marketRiskScore),
          ltv_ratio: Number(riskForm.ltvRatio),
          dscr: Number(riskForm.dscr),
          permit_readiness_ratio: Number(riskForm.permitReadinessRatio),
          occupancy_rate: Number(riskForm.occupancyRate),
          presale_ratio: Number(riskForm.presaleRatio),
          climate_risk_score: Number(riskForm.climateRiskScore),
          cost_volatility_ratio: Number(riskForm.costVolatilityRatio),
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["unified-risk", activeProjectId] });
    } catch (error) {
      setWorkspaceError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function handlePermit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    if (!activeProjectId) return setWorkspaceError("A real project UUID is required.");
    setPending("permit");
    try {
      await apiClient.post("/permits/submit", {
        useMock: false,
        body: {
          project_id: activeProjectId,
          permit_type: permitForm.permitType,
          region: permitForm.region,
          building_area_sqm: Number(permitForm.buildingArea),
          is_public: permitForm.isPublic === "true",
          is_agricultural: permitForm.isAgricultural === "true",
          applicant_name: "PropAI Ops",
          submit_to_seumter: permitForm.submitToSeumter === "true",
          submitted_document_ids: permitForm.submittedDocumentIds.split(",").map((item) => item.trim()).filter(Boolean),
        },
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["permit-status", activeProjectId] }),
        queryClient.invalidateQueries({ queryKey: ["unified-risk", activeProjectId] }),
      ]);
    } catch (error) {
      setWorkspaceError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="grid gap-6">
      <Card className="rounded-[2rem] bg-[var(--surface-strong)] shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              v53.2 control tower
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[rgba(19,33,47,0.7)]">
              {runtime.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--foreground)]">
            Digital twin, risk, and permit readiness
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[rgba(19,33,47,0.72)]">
            Run the v53 operations loop from telemetry to unified risk scoring and permit tracking.
          </p>
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            <Select
              label="Project"
              value={selectedProjectId}
              onValueChange={(value) => setSelectedProjectId(value)}
              options={projectsQuery.data?.items.map((project) => ({ label: project.name, value: project.id })) ?? []}
            />
            <Input value={manualProjectId} onChange={(event) => setManualProjectId(event.target.value)} placeholder="Manual project UUID" />
          </div>
          <p className="mt-3 text-sm text-[rgba(19,33,47,0.68)]">
            Current target: {(selectedProject?.name ?? activeProjectId) || "-"}
          </p>
          {workspaceError ? <p className="mt-4 text-sm text-[var(--spot)]">{workspaceError}</p> : null}
        </CardContent>
      </Card>

      {projectsQuery.error ? (
        <WorkspaceQueryErrorCard
          title="Project picker unavailable"
          description="The live project list failed to load, but manual UUID targeting remains available."
          message={errorMessage(projectsQuery.error)}
          actionLabel="Retry"
          onRetry={() => void projectsQuery.refetch()}
        />
      ) : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card><CardContent className="p-6"><p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">Digital twin status</p><CardTitle className="mt-2 text-xl">Persist operations status</CardTitle><form className="mt-5 grid gap-3" onSubmit={handleStatus}><Select label="Building type" value={statusForm.buildingType} onValueChange={(value) => setStatusForm((current) => ({ ...current, buildingType: value }))} options={buildingTypes} /><Input type="number" value={statusForm.grossFloorArea} onChange={(event) => setStatusForm((current) => ({ ...current, grossFloorArea: event.target.value }))} placeholder="Gross floor area (sqm)" /><Input type="number" value={statusForm.annualEnergy} onChange={(event) => setStatusForm((current) => ({ ...current, annualEnergy: event.target.value }))} placeholder="Annual energy use (kWh)" /><div className="grid gap-3 md:grid-cols-3"><Input type="number" value={statusForm.occupancyRate} onChange={(event) => setStatusForm((current) => ({ ...current, occupancyRate: event.target.value }))} placeholder="Occupancy rate" /><Input type="number" value={statusForm.sensorCount} onChange={(event) => setStatusForm((current) => ({ ...current, sensorCount: event.target.value }))} placeholder="Sensors" /><Input type="number" value={statusForm.onlineSensorCount} onChange={(event) => setStatusForm((current) => ({ ...current, onlineSensorCount: event.target.value }))} placeholder="Online" /></div><Button type="submit" disabled={!canUseLiveApi || pending === "status"}>{pending === "status" ? "Saving..." : "Save status snapshot"}</Button></form>{statusQuery.error ? <div className="mt-5"><WorkspaceQueryErrorCard title="Status snapshot unavailable" description="The latest persisted digital twin status could not be loaded." message={errorMessage(statusQuery.error)} actionLabel="Retry" onRetry={() => void statusQuery.refetch()} /></div> : statusQuery.data ? <div className="mt-5 grid gap-3"><Stat label="Status" value={statusQuery.data.status} /><Stat label="Readiness" value={`${statusQuery.data.operational_readiness_score.toFixed(1)}%`} /><Stat label="EUI" value={`${statusQuery.data.eui_grade} / ${statusQuery.data.eui.toFixed(1)}`} /><Stat label="Sensor health" value={`${(statusQuery.data.sensor_health_ratio * 100).toFixed(1)}%`} /><p className="rounded-[1rem] bg-[var(--surface-soft)] p-3 text-sm leading-7 text-[rgba(19,33,47,0.68)]">Anomaly severity {statusQuery.data.highest_anomaly_severity}</p></div> : <Empty title="No digital twin status yet" body="Run the snapshot action to persist the first v53 operations status record." />}</CardContent></Card>

        <Card><CardContent className="p-6"><p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">Unified risk engine</p><CardTitle className="mt-2 text-xl">Score seven risk dimensions</CardTitle><form className="mt-5 grid gap-3" onSubmit={handleRisk}><Input type="number" value={riskForm.baseProjectCost} onChange={(event) => setRiskForm((current) => ({ ...current, baseProjectCost: event.target.value }))} placeholder="Base project cost (KRW)" /><div className="grid gap-3 md:grid-cols-2"><Input type="number" value={riskForm.marketRiskScore} onChange={(event) => setRiskForm((current) => ({ ...current, marketRiskScore: event.target.value }))} placeholder="Market risk score" /><Input type="number" value={riskForm.climateRiskScore} onChange={(event) => setRiskForm((current) => ({ ...current, climateRiskScore: event.target.value }))} placeholder="Climate risk score" /></div><div className="grid gap-3 md:grid-cols-2"><Input type="number" value={riskForm.ltvRatio} onChange={(event) => setRiskForm((current) => ({ ...current, ltvRatio: event.target.value }))} placeholder="LTV ratio" /><Input type="number" value={riskForm.dscr} onChange={(event) => setRiskForm((current) => ({ ...current, dscr: event.target.value }))} placeholder="DSCR" /></div><div className="grid gap-3 md:grid-cols-3"><Input type="number" value={riskForm.permitReadinessRatio} onChange={(event) => setRiskForm((current) => ({ ...current, permitReadinessRatio: event.target.value }))} placeholder="Permit readiness" /><Input type="number" value={riskForm.occupancyRate} onChange={(event) => setRiskForm((current) => ({ ...current, occupancyRate: event.target.value }))} placeholder="Occupancy rate" /><Input type="number" value={riskForm.presaleRatio} onChange={(event) => setRiskForm((current) => ({ ...current, presaleRatio: event.target.value }))} placeholder="Presale ratio" /></div><Input type="number" value={riskForm.costVolatilityRatio} onChange={(event) => setRiskForm((current) => ({ ...current, costVolatilityRatio: event.target.value }))} placeholder="Cost volatility ratio" /><Button type="submit" disabled={!canUseLiveApi || pending === "risk"}>{pending === "risk" ? "Analyzing..." : "Analyze unified risk"}</Button></form>{riskQuery.error ? <div className="mt-5"><WorkspaceQueryErrorCard title="Unified risk unavailable" description="The latest persisted risk assessment could not be loaded." message={errorMessage(riskQuery.error)} actionLabel="Retry" onRetry={() => void riskQuery.refetch()} /></div> : riskQuery.data ? <div className="mt-5 grid gap-3"><Stat label="Composite" value={riskQuery.data.composite_risk_score.toFixed(1)} /><Stat label="Grade" value={riskQuery.data.grade} /><Stat label="VaR95" value={`${(riskQuery.data.var_95_ratio * 100).toFixed(1)}%`} /><Stat label="P90 cost" value={new Intl.NumberFormat(locale, { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(riskQuery.data.p90_adjusted_cost_krw)} /><p className="rounded-[1rem] bg-[var(--surface-soft)] p-3 text-sm leading-7 text-[rgba(19,33,47,0.68)]">{riskQuery.data.summary}</p></div> : <Empty title="No unified risk assessment yet" body="Run the risk engine after updating status or permit context." />}</CardContent></Card>

        <Card><CardContent className="p-6"><p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">Permit readiness</p><CardTitle className="mt-2 text-xl">Submit and track permit packages</CardTitle><form className="mt-5 grid gap-3" onSubmit={handlePermit}><Select label="Permit type" value={permitForm.permitType} onValueChange={(value) => setPermitForm((current) => ({ ...current, permitType: value }))} options={permitTypes} /><Select label="Region" value={permitForm.region} onValueChange={(value) => setPermitForm((current) => ({ ...current, region: value }))} options={regions} /><Input type="number" value={permitForm.buildingArea} onChange={(event) => setPermitForm((current) => ({ ...current, buildingArea: event.target.value }))} placeholder="Building area (sqm)" /><div className="grid gap-3 md:grid-cols-3"><Select label="Public" value={permitForm.isPublic} onValueChange={(value) => setPermitForm((current) => ({ ...current, isPublic: value }))} options={yesNo} /><Select label="Agricultural" value={permitForm.isAgricultural} onValueChange={(value) => setPermitForm((current) => ({ ...current, isAgricultural: value }))} options={yesNo} /><Select label="Submit" value={permitForm.submitToSeumter} onValueChange={(value) => setPermitForm((current) => ({ ...current, submitToSeumter: value }))} options={yesNo} /></div><Input value={permitForm.submittedDocumentIds} onChange={(event) => setPermitForm((current) => ({ ...current, submittedDocumentIds: event.target.value }))} placeholder="Submitted document IDs (comma separated)" /><Button type="submit" disabled={!canUseLiveApi || pending === "permit"}>{pending === "permit" ? "Submitting..." : "Submit permit package"}</Button></form>{permitQuery.error ? <div className="mt-5"><WorkspaceQueryErrorCard title="Permit tracker unavailable" description="The latest persisted permit submission could not be loaded." message={errorMessage(permitQuery.error)} actionLabel="Retry" onRetry={() => void permitQuery.refetch()} /></div> : permitQuery.data ? <div className="mt-5 grid gap-3"><Stat label="Status" value={permitQuery.data.status} /><Stat label="Stage" value={permitQuery.data.current_stage} /><Stat label="Readiness" value={`${permitQuery.data.readiness_score.toFixed(1)}%`} /><Stat label="Progress" value={`${permitQuery.data.progress_pct.toFixed(1)}%`} /><p className="rounded-[1rem] bg-[var(--surface-soft)] p-3 text-sm leading-7 text-[rgba(19,33,47,0.68)]">Ref {permitQuery.data.submission_reference}{permitQuery.data.missing_required_documents.length ? ` · Missing ${permitQuery.data.missing_required_documents.join(", ")}` : ""}</p></div> : <Empty title="No permit submission yet" body="Submit the first permit package to populate the tracking read model." />}</CardContent></Card>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="rounded-[1rem] bg-[var(--surface-soft)] p-3 text-sm"><p className="text-[rgba(19,33,47,0.5)]">{label}</p><p className="mt-1 font-semibold text-[var(--foreground)]">{value}</p></div>;
}

function Empty({ title, body }: { title: string; body: string }) {
  return <div className="mt-5 rounded-[1rem] border border-dashed border-[var(--line)] p-4 text-sm"><p className="font-semibold text-[var(--foreground)]">{title}</p><p className="mt-2 leading-7 text-[rgba(19,33,47,0.68)]">{body}</p></div>;
}
