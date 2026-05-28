"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Card, CardContent } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { useProjectStore } from "@/store/use-project-store";

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type SupportedModuleKey =
  | "cad"
  | "contracts"
  | "design"
  | "bim"
  | "finance"
  | "drone"
  | "blockchain"
  | "report";

type ProjectSummaryClientProps = {
  locale: string;
  projectId: string;
  moduleLabels: {
    contracts: string;
    design: string;
    bim: string;
    finance: string;
    drone: string;
    blockchain: string;
    report: string;
  };
};

type ModuleEntry = {
  id: SupportedModuleKey;
  href: string;
  label: string;
  mode: "live" | "editor";
  note: string;
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatNumber(locale: string, value: number | null) {
  if (value == null) {
    return "-";
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 2,
  }).format(value);
}

function extractErrorMessage(error: unknown) {

function createModuleEntries(
  locale: string,
  projectId: string,
  moduleLabels: ProjectSummaryClientProps["moduleLabels"],
): ModuleEntry[] {
  return [
    {
      id: "contracts",
      href: `/${locale}/projects/${projectId}/contracts`,
      label: moduleLabels.contracts,
      mode: "live",
      note: "Contract draft generation and e-sign handoff are live.",
    },
    {
      id: "cad",
      href: `/${locale}/projects/${projectId}/cad`,
      label: "CAD",
      mode: "editor",
      note: "Editor route is available, but CAD dependency and type-check issues remain unresolved.",
    },
    {
      id: "design",
      href: `/${locale}/projects/${projectId}/design`,
      label: moduleLabels.design,
      mode: "live",
      note: "Floor plan, auto IFC, and carbon chains are live.",
    },
    {
      id: "bim",
      href: `/${locale}/projects/${projectId}/bim`,
      label: moduleLabels.bim,
      mode: "live",
      note: "Auto IFC generation and geometry summary are live.",
    },
    {
      id: "finance",
      href: `/${locale}/projects/${projectId}/finance`,
      label: moduleLabels.finance,
      mode: "live",
      note: "AVM and jeonse-risk chaining are live.",
    },
    {
      id: "drone",
      href: `/${locale}/projects/${projectId}/drone`,
      label: moduleLabels.drone,
      mode: "live",
      note: "Drone inspection persistence is live.",
    },
    {
      id: "blockchain",
      href: `/${locale}/projects/${projectId}/blockchain`,
      label: moduleLabels.blockchain,
      mode: "live",
      note: "Escrow creation and on-chain lookup are live.",
    },
    {
      id: "report",
      href: `/${locale}/projects/${projectId}/report`,
      label: moduleLabels.report,
      mode: "live",
      note: "Investor report generation is live.",
    },
  ];
}

function buildNextActions(project: ProjectResponse, liveModuleCount: number) {
  const actions = [
    `Current backend status: ${project.status}.`,
    `Use the ${liveModuleCount} live project subroutes to validate downstream module persistence.`,
  ];

  if (!project.address) {
    actions.push("Add an address to improve AVM, inspection, and reporting fidelity.");
  } else {
    actions.push(`Address-linked workflows are ready for ${project.address}.`);
  }

  actions.push(
    "Keep CAD on the editor-only route until the current Three.js and dependency blockers are resolved.",
  );

  return actions;
}

export function ProjectSummaryClient({
  locale,
  projectId,
  moduleLabels,
}: ProjectSummaryClientProps) {
  const activeModule = useProjectStore((state) => state.activeModule);
  const setActiveModule = useProjectStore((state) => state.setActiveModule);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);
  const runtimeConfig = ({ mode: "local" as string, hasAccessToken: false });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "overview-live"],
    queryFn: () =>
      (async () => ({} as ProjectResponse))(),
  });

  useEffect(() => {
    setCurrentProject(projectId);
  }, [projectId, setCurrentProject]);

  const moduleEntries = createModuleEntries(locale, projectId, moduleLabels);
  const liveModules = moduleEntries.filter((entry) => entry.mode === "live");
  const previewModules = moduleEntries.filter((entry) => entry.mode === "editor");

  if (projectQuery.isLoading) {
    return (
      <div className="grid gap-4">
        <SkeletonLoader count={1} itemClassName="h-40" />
        <SkeletonLoader count={1} itemClassName="h-56" />
      </div>
    );
  }

  if (projectQuery.error) {
    return (
      <Card>
        <CardContent className="p-6 text-sm leading-7 text-[var(--spot)]">
          {extractErrorMessage(projectQuery.error)}
        </CardContent>
      </Card>
    );
  }

  if (!projectQuery.data) {
    return null;
  }

  const project = projectQuery.data;
  const nextActions = buildNextActions(project, liveModules.length);

  return (
    <section className="grid gap-4">
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm text-[var(--text-tertiary)]">
                {project.address ?? "Address pending"}
              </p>
              <h3 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                {project.name}
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                {project.status}
              </span>
              <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
              </span>
            </div>
          </div>
          <p className="mt-4 text-sm text-[var(--text-secondary)]">
            Last updated: {formatDate(locale, project.updated_at)}
          </p>
          <div className="mt-6 grid gap-3 md:grid-cols-4">
            <SummaryTile label="Project ID" value={project.id} />
            <SummaryTile
              label="Total area"
              value={`${formatNumber(locale, project.total_area_sqm)} sqm`}
            />
            <SummaryTile
              label="Created"
              value={formatDate(locale, project.created_at)}
            />
            <SummaryTile
              label="Coordinates"
              value={
                project.latitude != null && project.longitude != null
                  ? `${project.latitude}, ${project.longitude}`
                  : "-"
              }
            />
          </div>
          <div className="mt-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
              Module routes
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {moduleEntries.map((entry) => (
                <Link
                  key={entry.id}
                  href={entry.href}
                  onClick={() => setActiveModule(entry.id)}
                  className={`rounded-full px-4 py-2 text-sm font-medium ${
                    activeModule === entry.id
                      ? "bg-[var(--accent-strong)] text-[#ffffff]"
                      : "border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)]"
                  }`}
                >
                  {entry.label}
                </Link>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="bg-[var(--surface-strong)]">
          <CardContent className="p-6">
            <h4 className="text-lg font-semibold text-[var(--text-primary)]">
              Live route coverage
            </h4>
            <ul className="mt-4 grid gap-3">
              {liveModules.map((entry) => (
                <li
                  key={entry.id}
                  className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm leading-7 text-[var(--text-secondary)]"
                >
                  <span className="font-semibold text-[var(--text-primary)]">
                    {entry.label}
                  </span>{" "}
                  · {entry.note}
                </li>
              ))}
              {previewModules.map((entry) => (
                <li
                  key={entry.id}
                  className="rounded-[var(--radius-md)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm leading-7 text-[var(--text-tertiary)]"
                >
                  <span className="font-semibold text-[var(--text-primary)]">
                    {entry.label}
                  </span>{" "}
                  · {entry.note}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card className="bg-[var(--surface-strong)]">
          <CardContent className="p-6">
            <h4 className="text-lg font-semibold text-[var(--text-primary)]">
              Next actions
            </h4>
            <ul className="mt-4 grid gap-3">
              {nextActions.map((item) => (
                <li
                  key={item}
                  className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm leading-7 text-[var(--text-secondary)]"
                >
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function SummaryTile({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--surface-soft)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-hint)]">
        {label}
      </p>
      <p className="mt-3 break-all text-sm leading-7 text-[var(--text-secondary)]">
        {value}
      </p>
    </div>
  );
}
