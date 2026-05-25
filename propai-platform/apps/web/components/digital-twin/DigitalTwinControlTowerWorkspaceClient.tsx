"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
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
    <section className="grid gap-10 font-sans">
      <Card className="rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden group">
        <CardContent className="p-10 lg:p-14 relative">
          <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[80px] transition-all duration-1000 group-hover:scale-150" />
          
          <div className="relative z-10 flex flex-wrap items-center gap-4">
            <span className="rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] backdrop-blur-md">
              <span className="mr-2 inline-block h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
              v53.2 CONTROL TOWER
            </span>
            <span className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">
              {runtime.mode === "live" ? "ACTIVE TELEMETRY" : "HISTORICAL REPLAY"}
            </span>
          </div>

          <h3 className="relative z-10 mt-8 text-4xl font-[1000] text-[var(--text-primary)] tracking-tighter leading-tight max-w-4xl italic">
            Digital twin, risk, and permit <span className="text-[var(--accent-strong)]">readiness.</span>
          </h3>
          <p className="relative z-10 mt-6 max-w-3xl text-lg font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
            Run the v53 operations loop from real-time telemetry to unified risk scoring and permit lifecycle tracking.
          </p>

          <div className="mt-12 grid gap-6 md:grid-cols-2 relative z-10">
            <div className="space-y-3">
              <label className="ml-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">Target Project</label>
              <Select
                value={selectedProjectId}
                onValueChange={(value) => setSelectedProjectId(value)}
                options={projectsQuery.data?.items.map((project) => ({ label: project.name, value: project.id })) ?? []}
                className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)]/50 px-8 font-bold"
              />
            </div>
            <div className="space-y-3">
              <label className="ml-5 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">Manual Override (UUID)</label>
              <Input 
                value={manualProjectId} 
                onChange={(event) => setManualProjectId(event.target.value)} 
                placeholder="00000000-0000-0000-0000-000000000000" 
                className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)]/50 px-8 font-mono text-sm"
              />
            </div>
          </div>
          
          <div className="mt-8 flex items-center gap-3 ml-5">
            <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)]" />
            <p className="text-sm font-black text-[var(--text-primary)] uppercase tracking-widest">
              CURRENT TARGET: <span className="text-[var(--accent-strong)]">{(selectedProject?.name ?? activeProjectId) || "NOT_ASSIGNED"}</span>
            </p>
          </div>

          <AnimatePresence>
            {workspaceError && (
              <motion.p 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-6 ml-5 text-sm font-black text-[var(--spot)] uppercase tracking-widest animate-pulse"
              >
                [SYSTEM_ERROR] {workspaceError}
              </motion.p>
            )}
          </AnimatePresence>
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

      <div className="grid gap-8 xl:grid-cols-3">
        {/* --- Digital Twin Status --- */}
        <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-12 border-t-8 border-[var(--info)]">
            <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">DIMENSION_01</p>
            <CardTitle className="mt-3 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">Digital Twin Status<span className="text-[var(--info)]">.</span></CardTitle>
            
            <form className="mt-8 grid gap-4" onSubmit={handleStatus}>
              <Select label="Building type" value={statusForm.buildingType} onValueChange={(value) => setStatusForm((current) => ({ ...current, buildingType: value }))} options={buildingTypes} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <Input type="number" value={statusForm.grossFloorArea} onChange={(event) => setStatusForm((current) => ({ ...current, grossFloorArea: event.target.value }))} placeholder="Gross floor area (sqm)" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <Input type="number" value={statusForm.annualEnergy} onChange={(event) => setStatusForm((current) => ({ ...current, annualEnergy: event.target.value }))} placeholder="Annual energy use (kWh)" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <div className="grid gap-3 grid-cols-3">
                <Input type="number" value={statusForm.occupancyRate} onChange={(event) => setStatusForm((current) => ({ ...current, occupancyRate: event.target.value }))} placeholder="Occ %" className="h-14 rounded-2xl px-2 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
                <Input type="number" value={statusForm.sensorCount} onChange={(event) => setStatusForm((current) => ({ ...current, sensorCount: event.target.value }))} placeholder="Sens" className="h-14 rounded-2xl px-2 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
                <Input type="number" value={statusForm.onlineSensorCount} onChange={(event) => setStatusForm((current) => ({ ...current, onlineSensorCount: event.target.value }))} placeholder="Online" className="h-14 rounded-2xl px-2 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
              </div>
              <Button type="submit" disabled={!canUseLiveApi || pending === "status"} className="h-14 rounded-2xl bg-[var(--info-strong)] text-white font-black uppercase tracking-widest shadow-[var(--shadow-glow)] mt-2">
                {pending === "status" ? "UPDATING..." : "COMMIT SNAPSHOT"}
              </Button>
            </form>

            <div className="mt-10 pt-8 border-t border-[var(--line)]">
              {statusQuery.error ? (
                <WorkspaceQueryErrorCard title="Status Unavailable" description="..." message={errorMessage(statusQuery.error)} actionLabel="Retry" onRetry={() => void statusQuery.refetch()} />
              ) : statusQuery.data ? (
                <div className="grid gap-3">
                  <Stat label="Operational Status" value={statusQuery.data.status} color="text-[var(--info)]" />
                  <Stat label="Readiness Index" value={`${statusQuery.data.operational_readiness_score.toFixed(1)}%`} />
                  <Stat label="EUI Benchmark" value={`${statusQuery.data.eui_grade} / ${statusQuery.data.eui.toFixed(1)}`} />
                  <Stat label="Sensor Health" value={`${(statusQuery.data.sensor_health_ratio * 100).toFixed(1)}%`} />
                  <div className="rounded-2xl bg-[var(--surface-soft)] p-4 flex items-center justify-between border border-[var(--line-subtle)]">
                    <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">ANOMALY_LEVEL</span>
                    <span className={`text-xs font-black uppercase tracking-widest ${statusQuery.data.highest_anomaly_severity === 'critical' ? 'text-[var(--spot)]' : 'text-[var(--text-secondary)]'}`}>
                       {statusQuery.data.highest_anomaly_severity}
                    </span>
                  </div>
                </div>
              ) : (
                <Empty title="NO_TELEMETRY" body="Run snapshot action to persist the first operations status record." />
              )}
            </div>
          </CardContent>
        </Card>

        {/* --- Unified Risk Engine --- */}
        <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-12 border-t-8 border-[var(--accent-strong)]">
            <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">DIMENSION_02</p>
            <CardTitle className="mt-3 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">Unified Risk Engine<span className="text-[var(--accent-strong)]">.</span></CardTitle>
            
            <form className="mt-8 grid gap-4" onSubmit={handleRisk}>
              <Input type="number" value={riskForm.baseProjectCost} onChange={(event) => setRiskForm((current) => ({ ...current, baseProjectCost: event.target.value }))} placeholder="Base cost (KRW)" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <div className="grid gap-3 grid-cols-2">
                <Input type="number" value={riskForm.marketRiskScore} onChange={(event) => setRiskForm((current) => ({ ...current, marketRiskScore: event.target.value }))} placeholder="Market" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
                <Input type="number" value={riskForm.climateRiskScore} onChange={(event) => setRiskForm((current) => ({ ...current, climateRiskScore: event.target.value }))} placeholder="Climate" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              </div>
              <div className="grid gap-3 grid-cols-2">
                <Input type="number" value={riskForm.ltvRatio} onChange={(event) => setRiskForm((current) => ({ ...current, ltvRatio: event.target.value }))} placeholder="LTV" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
                <Input type="number" value={riskForm.dscr} onChange={(event) => setRiskForm((current) => ({ ...current, dscr: event.target.value }))} placeholder="DSCR" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              </div>
              <div className="grid gap-2 grid-cols-3">
                <Input type="number" value={riskForm.permitReadinessRatio} onChange={(event) => setRiskForm((current) => ({ ...current, permitReadinessRatio: event.target.value }))} placeholder="Permit" className="h-14 rounded-2xl px-1 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
                <Input type="number" value={riskForm.occupancyRate} onChange={(event) => setRiskForm((current) => ({ ...current, occupancyRate: event.target.value }))} placeholder="Occ" className="h-14 rounded-2xl px-1 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
                <Input type="number" value={riskForm.presaleRatio} onChange={(event) => setRiskForm((current) => ({ ...current, presaleRatio: event.target.value }))} placeholder="Pre" className="h-14 rounded-2xl px-1 text-center border-[var(--line)] bg-[var(--surface-soft)] font-mono" />
              </div>
              <Button type="submit" disabled={!canUseLiveApi || pending === "risk"} className="h-14 rounded-2xl bg-[var(--accent-strong)] text-white font-black uppercase tracking-widest shadow-[var(--shadow-glow)] mt-2">
                {pending === "risk" ? "ANALYZING..." : "EXECUTE_RISK_AI"}
              </Button>
            </form>

             <div className="mt-10 pt-8 border-t border-[var(--line)]">
              {riskQuery.error ? (
                <WorkspaceQueryErrorCard title="Risk Sync Failed" description="..." message={errorMessage(riskQuery.error)} actionLabel="Retry" onRetry={() => void riskQuery.refetch()} />
              ) : riskQuery.data ? (
                <div className="grid gap-3">
                  <Stat label="Composite Score" value={riskQuery.data.composite_risk_score.toFixed(1)} color="text-[var(--accent-strong)]" />
                  <Stat label="Asset Grade" value={riskQuery.data.grade} />
                  <Stat label="VaR 95% Ratio" value={`${(riskQuery.data.var_95_ratio * 100).toFixed(1)}%`} />
                  <Stat label="P90 Adj. Cost" value={new Intl.NumberFormat(locale, { style: "currency", currency: "KRW", maximumFractionDigits: 0 }).format(riskQuery.data.p90_adjusted_cost_krw)} />
                  <div className="rounded-2xl bg-[var(--surface-soft)] p-5 border border-[var(--line-subtle)]">
                    <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] mb-2">SUMMARY_REPORT</p>
                    <p className="text-xs font-bold leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)]">{riskQuery.data.summary}</p>
                  </div>
                </div>
              ) : (
                <Empty title="AWAITING_INPUT" body="Run unified risk engine after updating status or permit context." />
              )}
            </div>
          </CardContent>
        </Card>

        {/* --- Permit Readiness --- */}
        <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-12 border-t-8 border-[var(--success)]">
            <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">DIMENSION_03</p>
            <CardTitle className="mt-3 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">Permit Lifecycle<span className="text-[var(--success)]">.</span></CardTitle>
            
            <form className="mt-8 grid gap-4" onSubmit={handlePermit}>
              <Select label="Permit type" value={permitForm.permitType} onValueChange={(value) => setPermitForm((current) => ({ ...current, permitType: value }))} options={permitTypes} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <Select label="Region" value={permitForm.region} onValueChange={(value) => setPermitForm((current) => ({ ...current, region: value }))} options={regions} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <Input type="number" value={permitForm.buildingArea} onChange={(event) => setPermitForm((current) => ({ ...current, buildingArea: event.target.value }))} placeholder="Building area (sqm)" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <div className="grid gap-3 grid-cols-3">
                <Select label="Pb" value={permitForm.isPublic} onValueChange={(value) => setPermitForm((current) => ({ ...current, isPublic: value }))} options={yesNo} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
                <Select label="Ag" value={permitForm.isAgricultural} onValueChange={(value) => setPermitForm((current) => ({ ...current, isAgricultural: value }))} options={yesNo} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
                <Select label="Sm" value={permitForm.submitToSeumter} onValueChange={(value) => setPermitForm((current) => ({ ...current, submitToSeumter: value }))} options={yesNo} className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              </div>
              <Input value={permitForm.submittedDocumentIds} onChange={(event) => setPermitForm((current) => ({ ...current, submittedDocumentIds: event.target.value }))} placeholder="Doc IDs (e.g. BA-01, BA-02)" className="h-14 rounded-2xl border-[var(--line)] bg-[var(--surface-soft)]" />
              <Button type="submit" disabled={!canUseLiveApi || pending === "permit"} className="h-14 rounded-2xl bg-[var(--success-strong)] text-white font-black uppercase tracking-widest shadow-[0_0_20px_rgba(var(--success-rgb),0.3)] mt-2">
                {pending === "permit" ? "SUBMITTING..." : "INIT_LIFECYCLE"}
              </Button>
            </form>

             <div className="mt-10 pt-8 border-t border-[var(--line)]">
              {permitQuery.error ? (
                <WorkspaceQueryErrorCard title="Permit Sync Error" description="..." message={errorMessage(permitQuery.error)} actionLabel="Retry" onRetry={() => void permitQuery.refetch()} />
              ) : permitQuery.data ? (
                <div className="grid gap-3">
                  <Stat label="Current Status" value={permitQuery.data.status} color="text-[var(--success)]" />
                  <Stat label="Current Stage" value={permitQuery.data.current_stage} />
                  <Stat label="Readiness Index" value={`${permitQuery.data.readiness_score.toFixed(1)}%`} />
                  <div className="space-y-2 p-5 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line-subtle)]">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">PROGRESS</span>
                      <span className="text-xs font-black text-[var(--text-primary)] antialiased">{permitQuery.data.progress_pct.toFixed(0)}%</span>
                    </div>
                    <div className="h-2 w-full bg-[var(--surface-strong)] rounded-full overflow-hidden border border-[var(--line)]">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: `${permitQuery.data.progress_pct}%` }}
                        transition={{ duration: 1, ease: "circOut" }}
                        className="h-full bg-[var(--success)] shadow-[0_0_10px_var(--success)]" 
                      />
                    </div>
                  </div>
                  <div className="rounded-2xl bg-[var(--surface-soft)] p-4 border border-[var(--line-subtle)]">
                    <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] mb-2">METADATA</p>
                    <p className="text-xs font-bold text-[var(--text-secondary)] italic truncate antialiased">REF: {permitQuery.data.submission_reference}</p>
                    {permitQuery.data.missing_required_documents.length ? (
                      <p className="mt-2 text-[10px] font-black text-[var(--spot)] uppercase tracking-tight antialiased animate-pulse"> MISSING: {permitQuery.data.missing_required_documents.join(", ")}</p>
                    ) : null}
                  </div>
                </div>
              ) : (
                <Empty title="NO_ACTIVE_LIFE" body="Submit the first permit package to populate the tracking read model." />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function Stat({ label, value, color = "text-[var(--text-primary)]" }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between rounded-2xl bg-[var(--surface-soft)] p-4 border border-[var(--line-subtle)] shadow-sm">
      <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</span>
      <span className={`text-sm font-[1000] tracking-tight ${color}`}>{value}</span>
    </div>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-3xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/30 p-8 text-center flex flex-col items-center gap-4">
       <div className="h-12 w-12 rounded-2xl bg-[var(--surface-strong)] flex items-center justify-center text-[var(--text-hint)] grayscale opacity-50">📡</div>
       <div className="space-y-1">
         <p className="text-xs font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">{title}</p>
         <p className="text-[10px] font-medium leading-relaxed text-[var(--text-hint)]/60 italic">{body}</p>
       </div>
    </div>
  );
}
