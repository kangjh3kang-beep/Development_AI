"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import {
  LEASE_STATUSES,
  type ContractCreateInput,
  type ContractsResponse,
  type LeaseAnalyzeResponse,
  type LeaseSummaryResponse,
  type MutationResponse,
  type NpsResponse,
  type TenantCreateInput,
  type TenantsResponse,
} from "./types";

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS = LEASE_STATUSES.map((value) => ({ value, label: value }));

const STATUS_LABEL_KO: Record<string, string> = {
  active: "임대중",
  occupied: "입주",
  leased: "임대완료",
  expired: "만료",
  vacant: "공실",
  pending: "대기",
};

function statusLabel(status: string) {
  return STATUS_LABEL_KO[status.toLowerCase()] ?? status;
}

// 상태 → sa-chip 톤(의미색 토큰). 다크/라이트 모두 토큰이 명암을 보장.
function statusBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "active" || s === "occupied" || s === "leased") return "sa-chip--success";
  if (s === "pending") return "sa-chip--warning";
  if (s === "expired") return "sa-chip--error";
  return "sa-chip--muted";
}

function formatKrw(value: number | null | undefined) {
  if (value == null) return "-";
  return `${Math.round(value).toLocaleString()} 원`;
}

/** ApiClientError를 권한(403)/인증(401) 구분 메시지로 변환. */
function extractErrorMessage(error: unknown): {
  message: string;
  forbidden: boolean;
} {
  if (error instanceof ApiClientError) {
    if (error.status === 403)
      return {
        message:
          "이 기능을 사용할 권한이 없습니다. 임대·임차인 관리는 운영 권한(leases:read/write)이 필요합니다. 관리자에게 권한 부여를 요청하세요.",
        forbidden: true,
      };
    if (error.status === 401)
      return { message: "로그인이 필요합니다. 다시 로그인해 주세요.", forbidden: false };
    return {
      message: `API 요청이 상태 ${error.status}(으)로 실패했습니다.`,
      forbidden: false,
    };
  }
  if (error instanceof Error) return { message: error.message, forbidden: false };
  return { message: "요청에 실패했습니다.", forbidden: false };
}

/* ------------------------------------------------------------------ */
/*  Small UI pieces                                                   */
/* ------------------------------------------------------------------ */

function KpiTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`cc-bracketed relative overflow-hidden rounded-[var(--radius-xl)] border p-4 ${
        accent
          ? "border-[var(--data-accent-line)] bg-[var(--data-accent-soft)]"
          : "border-[var(--line)] bg-[var(--surface)]"
      }`}
    >
      {accent && (
        <>
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--br" />
        </>
      )}
      <p className="cc-label text-[var(--text-tertiary)]">{label}</p>
      <p
        className={`mt-2 cc-num text-2xl font-bold ${
          accent ? "cc-num--data" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <p className="cc-meta">{title}</p>
        <div className="mt-4">{children}</div>
      </CardContent>
    </Card>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-semibold text-[var(--text-secondary)]">
      {children}
    </span>
  );
}

const inputClass =
  "w-full rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent)]";

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

// 차트 막대색 — 디자인 토큰(의미색)만 사용. SVG fill은 var() 허용.
const BAR_COLORS = [
  "var(--data-accent)",
  "var(--status-success)",
  "var(--status-warning)",
  "var(--status-error)",
  "var(--status-info)",
  "var(--text-tertiary)",
];

export function LeaseOpsWorkspace({ locale }: { locale: Locale }) {
  void locale; // 라벨은 하드코딩(다국어 무관) — 시그니처 호환 유지
  const queryClient = useQueryClient();
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  /* ── Queries ── */
  const summaryQuery = useQuery({
    queryKey: ["lease-ops", "summary"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<LeaseSummaryResponse>("/lease-ops/summary", { useMock: false }),
  });
  const tenantsQuery = useQuery({
    queryKey: ["lease-ops", "tenants"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<TenantsResponse>("/lease-ops/tenants", { useMock: false }),
  });

  const [statusFilter, setStatusFilter] = useState<string>("");
  const contractsQuery = useQuery({
    queryKey: ["lease-ops", "contracts", statusFilter],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ContractsResponse>(
        statusFilter
          ? `/lease-ops/contracts?status=${encodeURIComponent(statusFilter)}`
          : "/lease-ops/contracts",
        { useMock: false },
      ),
  });

  /* 권한(403) 통합 판정 — 어느 한 쿼리라도 403이면 안내 배너 노출 */
  const forbidden = useMemo(() => {
    return [summaryQuery.error, tenantsQuery.error, contractsQuery.error].some(
      (e) => extractErrorMessage(e).forbidden,
    );
  }, [summaryQuery.error, tenantsQuery.error, contractsQuery.error]);

  const summary = summaryQuery.data;
  const tenants = useMemo(
    () => tenantsQuery.data?.tenants ?? [],
    [tenantsQuery.data],
  );
  const contracts = contractsQuery.data?.contracts ?? [];

  /* ── Tenant form ── */
  const [tenantForm, setTenantForm] = useState<TenantCreateInput>({
    name: "",
    contact: "",
    business_type: "",
  });
  const [tenantMsg, setTenantMsg] = useState<string>("");
  const tenantMutation = useMutation({
    mutationFn: (body: TenantCreateInput) =>
      apiClient.post<MutationResponse>("/lease-ops/tenants", {
        useMock: false,
        body: body as unknown as Record<string, unknown>,
      }),
    onSuccess: (res) => {
      if (res?.ok) {
        setTenantMsg("임차인이 등록되었습니다.");
        setTenantForm({ name: "", contact: "", business_type: "" });
        void queryClient.invalidateQueries({ queryKey: ["lease-ops", "tenants"] });
      } else {
        setTenantMsg(res?.message ?? "등록에 실패했습니다.");
      }
    },
    onError: (e) => setTenantMsg(extractErrorMessage(e).message),
  });

  /* ── Contract form ── */
  const emptyContract: ContractCreateInput = {
    unit_label: "",
    lessee: "",
    deposit: undefined,
    monthly_rent: undefined,
    start_date: "",
    end_date: "",
    area_sqm: undefined,
    status: "active",
  };
  const [contractForm, setContractForm] =
    useState<ContractCreateInput>(emptyContract);
  const [contractMsg, setContractMsg] = useState<string>("");
  const contractMutation = useMutation({
    mutationFn: (body: ContractCreateInput) =>
      apiClient.post<MutationResponse>("/lease-ops/contracts", {
        useMock: false,
        body: body as unknown as Record<string, unknown>,
      }),
    onSuccess: (res) => {
      if (res?.ok) {
        setContractMsg("임대계약이 등록되었습니다.");
        setContractForm(emptyContract);
        void queryClient.invalidateQueries({ queryKey: ["lease-ops", "contracts"] });
        void queryClient.invalidateQueries({ queryKey: ["lease-ops", "summary"] });
      } else {
        setContractMsg(res?.message ?? "등록에 실패했습니다.");
      }
    },
    onError: (e) => setContractMsg(extractErrorMessage(e).message),
  });

  /* ── Status change ── */
  const statusMutation = useMutation({
    mutationFn: (vars: { id: string; status: string }) =>
      apiClient.patch<MutationResponse>(
        `/lease-ops/contracts/${vars.id}/status`,
        { useMock: false, body: { status: vars.status } },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lease-ops", "contracts"] });
      void queryClient.invalidateQueries({ queryKey: ["lease-ops", "summary"] });
    },
  });

  /* ── (결합) Lease AI analysis ── */
  const [analyzeText, setAnalyzeText] = useState<string>("");
  const [analyzeResult, setAnalyzeResult] = useState<string>("");
  const [analyzeAvailable, setAnalyzeAvailable] = useState<boolean>(true);
  const analyzeMutation = useMutation({
    mutationFn: (text: string) =>
      apiClient.post<LeaseAnalyzeResponse>("/leases/analyze", {
        useMock: false,
        body: { text, content: text },
      }),
    onSuccess: (res) => {
      const out =
        res?.summary ?? res?.analysis ?? res?.result ?? res?.message ?? "";
      setAnalyzeResult(out || "분석 결과가 비어 있습니다.");
    },
    onError: (e) => {
      const { message } = extractErrorMessage(e);
      if (e instanceof ApiClientError && e.status === 404) {
        setAnalyzeAvailable(false);
      }
      setAnalyzeResult(message);
    },
  });

  /* ── (결합) NPS satisfaction ── */
  const [npsResult, setNpsResult] = useState<string>("");
  const [npsAvailable, setNpsAvailable] = useState<boolean>(true);
  const npsMutation = useMutation({
    mutationFn: () =>
      apiClient.post<NpsResponse>("/tenant/satisfaction/nps", {
        useMock: false,
        body: {},
      }),
    onSuccess: (res) => {
      const score = res?.nps ?? res?.score;
      setNpsResult(
        score != null
          ? `NPS 점수: ${score}`
          : (res?.message ?? "만족도 데이터가 없습니다."),
      );
    },
    onError: (e) => {
      const { message } = extractErrorMessage(e);
      if (e instanceof ApiClientError && e.status === 404) {
        setNpsAvailable(false);
      }
      setNpsResult(message);
    },
  });

  /* ── Charts data ── */
  const byStatusData = useMemo(() => {
    const bs = summary?.by_status ?? {};
    return Object.entries(bs).map(([status, count]) => ({
      status: statusLabel(status),
      count: Number(count) || 0,
    }));
  }, [summary]);

  const tenantNameById = useMemo(() => {
    const map = new Map<string, string>();
    tenants.forEach((t) => map.set(t.id, t.name));
    return map;
  }, [tenants]);

  /* ── Error banner (첫 실패 쿼리 기준) ── */
  const firstError =
    summaryQuery.error ?? tenantsQuery.error ?? contractsQuery.error;
  const queryError = firstError ? extractErrorMessage(firstError) : null;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      {/* Hero — 임대 운영 관제 헤더 */}
      <Card className="cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <div className="cc-grid-bg opacity-40" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <CardContent className="relative z-10 p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="cc-meta">LEASE · OPERATIONS</span>
            <span className="rounded-full bg-[var(--accent-soft)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              임대·임차인 관리
            </span>
            {runtimeConfig.mode === "live" ? (
              <span className="cc-live"><i />LIVE</span>
            ) : (
              <span className="cc-chip-data">HYBRID</span>
            )}
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            공실률·임대수익 대시보드와 임차인·계약 관리
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            임차인과 임대계약을 등록·관리하고, 공실률과 월/연 임대수익을 실시간으로
            집계합니다. 계약 상태 변경 시 대시보드가 자동 갱신됩니다.
          </p>

          {!canUseLiveApi && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              임대·임차인 관리를 사용하려면 로그인이 필요합니다.
            </div>
          )}

          {forbidden && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[color:color-mix(in_srgb,var(--status-warning)_40%,transparent)] bg-[color:color-mix(in_srgb,var(--status-warning)_12%,transparent)] p-5 text-sm leading-7 text-[var(--text-primary)]">
              이 기능을 사용할 권한이 없습니다. 임대·임차인 관리는 운영 권한이 필요합니다.
              구독자(viewer) 권한으로는 조회가 제한될 수 있습니다. 관리자에게 권한
              부여를 요청하세요.
            </div>
          )}

          {!forbidden && queryError && (
            <div className="mt-6">
              <WorkspaceQueryErrorCard
                title="데이터 로드 실패"
                description="임대·임차인 데이터를 불러오지 못했습니다. 다시 시도해 주세요."
                message={queryError.message}
                actionLabel="재시도"
                onRetry={() => {
                  void summaryQuery.refetch();
                  void tenantsQuery.refetch();
                  void contractsQuery.refetch();
                }}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dashboard KPIs */}
      <SectionCard title="운영 대시보드">
        {summaryQuery.isLoading ? (
          <SkeletonLoader count={1} itemClassName="h-24" />
        ) : summary?.ok ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <KpiTile label="총 세대" value={String(summary.total_units)} />
              <KpiTile label="임대중" value={String(summary.leased)} />
              <KpiTile label="공실" value={String(summary.vacant)} />
              <KpiTile
                label="공실률"
                value={`${summary.vacancy_rate_pct}%`}
                accent
              />
              <KpiTile
                label="월 임대료 합계"
                value={formatKrw(summary.monthly_rent_total)}
              />
              <KpiTile
                label="연 환산 수익"
                value={formatKrw(summary.annual_income_est)}
              />
            </div>

            {byStatusData.length > 0 && (
              <div className="mt-6 h-56 w-full">
                <p className="mb-2 text-xs font-semibold text-[var(--text-secondary)]">
                  상태별 분포
                </p>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={byStatusData}>
                    <XAxis
                      dataKey="status"
                      tick={{ fontSize: 12, fill: "var(--text-tertiary)" }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fontSize: 12, fill: "var(--text-tertiary)" }}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface)",
                        border: "1px solid var(--line)",
                        borderRadius: 12,
                        color: "var(--text-primary)",
                      }}
                    />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                      {byStatusData.map((_, i) => (
                        <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </>
        ) : (
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
            아직 집계할 임대계약 데이터가 없습니다. 임차인과 계약을 등록하면 공실률과
            임대수익이 자동으로 산출됩니다.
          </div>
        )}
      </SectionCard>

      {/* Tenants */}
      <SectionCard title="임차인 관리">
        <form
          className="grid gap-3 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            setTenantMsg("");
            if (!tenantForm.name.trim()) {
              setTenantMsg("임차인명을 입력하세요.");
              return;
            }
            tenantMutation.mutate({
              name: tenantForm.name.trim(),
              contact: tenantForm.contact?.trim() || undefined,
              business_type: tenantForm.business_type?.trim() || undefined,
            });
          }}
        >
          <label>
            <FieldLabel>임차인명 *</FieldLabel>
            <input
              className={inputClass}
              value={tenantForm.name}
              onChange={(e) =>
                setTenantForm((f) => ({ ...f, name: e.target.value }))
              }
              placeholder="예: 홍길동 / (주)가나상사"
            />
          </label>
          <label>
            <FieldLabel>연락처</FieldLabel>
            <input
              className={inputClass}
              value={tenantForm.contact ?? ""}
              onChange={(e) =>
                setTenantForm((f) => ({ ...f, contact: e.target.value }))
              }
              placeholder="010-0000-0000"
            />
          </label>
          <label>
            <FieldLabel>업종</FieldLabel>
            <input
              className={inputClass}
              value={tenantForm.business_type ?? ""}
              onChange={(e) =>
                setTenantForm((f) => ({ ...f, business_type: e.target.value }))
              }
              placeholder="예: 음식점, 사무실"
            />
          </label>
          <div className="sm:col-span-3 flex items-center gap-3">
            <button
              type="submit"
              disabled={tenantMutation.isPending}
              className="rounded-[var(--radius-lg)] bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[var(--accent)] disabled:opacity-60"
            >
              {tenantMutation.isPending ? "등록 중..." : "임차인 등록"}
            </button>
            {tenantMsg && (
              <span className="text-sm text-[var(--text-secondary)]">
                {tenantMsg}
              </span>
            )}
          </div>
        </form>

        <div className="mt-6">
          {tenantsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-12" />
          ) : tenants.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="cc-label pb-3 pr-4">임차인명</th>
                    <th className="cc-label pb-3 pr-4">연락처</th>
                    <th className="cc-label pb-3">업종</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => (
                    <tr key={t.id} className="border-t border-[var(--line)]">
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                        {t.name}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {t.contact ?? "-"}
                      </td>
                      <td className="py-3 text-[var(--text-secondary)]">
                        {t.business_type ?? "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              등록된 임차인이 없습니다. 위 폼에서 임차인을 등록하세요.
            </div>
          )}
        </div>
      </SectionCard>

      {/* Contracts */}
      <SectionCard title="임대계약 관리">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            setContractMsg("");
            if (!contractForm.unit_label.trim()) {
              setContractMsg("세대(호실)명을 입력하세요.");
              return;
            }
            if (!contractForm.lessee) {
              setContractMsg("임차인을 선택하세요.");
              return;
            }
            contractMutation.mutate({
              unit_label: contractForm.unit_label.trim(),
              lessee: contractForm.lessee,
              deposit: contractForm.deposit,
              monthly_rent: contractForm.monthly_rent,
              start_date: contractForm.start_date || undefined,
              end_date: contractForm.end_date || undefined,
              area_sqm: contractForm.area_sqm,
              status: contractForm.status || "active",
            });
          }}
        >
          <label>
            <FieldLabel>세대(호실) *</FieldLabel>
            <input
              className={inputClass}
              value={contractForm.unit_label}
              onChange={(e) =>
                setContractForm((f) => ({ ...f, unit_label: e.target.value }))
              }
              placeholder="예: 101호"
            />
          </label>
          <label>
            <FieldLabel>임차인 *</FieldLabel>
            <select
              className={inputClass}
              value={contractForm.lessee}
              onChange={(e) =>
                setContractForm((f) => ({ ...f, lessee: e.target.value }))
              }
            >
              <option value="">선택하세요</option>
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <FieldLabel>보증금(원)</FieldLabel>
            <input
              type="number"
              min={0}
              className={inputClass}
              value={contractForm.deposit ?? ""}
              onChange={(e) =>
                setContractForm((f) => ({
                  ...f,
                  deposit: e.target.value === "" ? undefined : Number(e.target.value),
                }))
              }
            />
          </label>
          <label>
            <FieldLabel>월 임대료(원)</FieldLabel>
            <input
              type="number"
              min={0}
              className={inputClass}
              value={contractForm.monthly_rent ?? ""}
              onChange={(e) =>
                setContractForm((f) => ({
                  ...f,
                  monthly_rent:
                    e.target.value === "" ? undefined : Number(e.target.value),
                }))
              }
            />
          </label>
          <label>
            <FieldLabel>계약 시작일</FieldLabel>
            <input
              type="date"
              className={inputClass}
              value={contractForm.start_date ?? ""}
              onChange={(e) =>
                setContractForm((f) => ({ ...f, start_date: e.target.value }))
              }
            />
          </label>
          <label>
            <FieldLabel>계약 종료일</FieldLabel>
            <input
              type="date"
              className={inputClass}
              value={contractForm.end_date ?? ""}
              onChange={(e) =>
                setContractForm((f) => ({ ...f, end_date: e.target.value }))
              }
            />
          </label>
          <label>
            <FieldLabel>전용면적(㎡)</FieldLabel>
            <input
              type="number"
              min={0}
              step="0.01"
              className={inputClass}
              value={contractForm.area_sqm ?? ""}
              onChange={(e) =>
                setContractForm((f) => ({
                  ...f,
                  area_sqm:
                    e.target.value === "" ? undefined : Number(e.target.value),
                }))
              }
            />
          </label>
          <label>
            <FieldLabel>상태</FieldLabel>
            <select
              className={inputClass}
              value={contractForm.status ?? "active"}
              onChange={(e) =>
                setContractForm((f) => ({ ...f, status: e.target.value }))
              }
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {statusLabel(o.value)}
                </option>
              ))}
            </select>
          </label>
          <div className="sm:col-span-2 lg:col-span-4 flex items-center gap-3">
            <button
              type="submit"
              disabled={contractMutation.isPending}
              className="rounded-[var(--radius-lg)] bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[var(--accent)] disabled:opacity-60"
            >
              {contractMutation.isPending ? "등록 중..." : "임대계약 등록"}
            </button>
            {contractMsg && (
              <span className="text-sm text-[var(--text-secondary)]">
                {contractMsg}
              </span>
            )}
          </div>
        </form>

        {/* Status filter + list */}
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-[var(--text-secondary)]">
            상태 필터:
          </span>
          <select
            className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">전체</option>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {statusLabel(o.value)}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4">
          {contractsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-14" />
          ) : contracts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="cc-label pb-3 pr-4">세대</th>
                    <th className="cc-label pb-3 pr-4">임차인</th>
                    <th className="cc-label pb-3 pr-4">보증금</th>
                    <th className="cc-label pb-3 pr-4">월 임대료</th>
                    <th className="cc-label pb-3 pr-4">계약기간</th>
                    <th className="cc-label pb-3 pr-4">면적</th>
                    <th className="cc-label pb-3 pr-4">상태</th>
                    <th className="cc-label pb-3">상태 변경</th>
                  </tr>
                </thead>
                <tbody>
                  {contracts.map((c) => (
                    <tr key={c.id} className="border-t border-[var(--line)]">
                      <td className="py-3 pr-4 font-semibold text-[var(--text-primary)]">
                        {c.unit_label}
                      </td>
                      <td className="py-3 pr-4 text-[var(--text-secondary)]">
                        {c.lessee_name ?? tenantNameById.get(c.id) ?? "-"}
                      </td>
                      <td className="cc-num py-3 pr-4 text-[var(--text-secondary)]">
                        {formatKrw(c.deposit)}
                      </td>
                      <td className="cc-num py-3 pr-4 text-[var(--text-secondary)]">
                        {formatKrw(c.monthly_rent)}
                      </td>
                      <td className="cc-num py-3 pr-4 text-[var(--text-secondary)] whitespace-nowrap">
                        {c.start_date ?? "-"} ~ {c.end_date ?? "-"}
                      </td>
                      <td className="cc-num py-3 pr-4 text-[var(--text-secondary)]">
                        {c.area_sqm != null ? `${c.area_sqm.toLocaleString()}㎡` : "-"}
                      </td>
                      <td className="py-3 pr-4">
                        <span className={`sa-chip ${statusBadge(c.status)}`}>
                          {statusLabel(c.status)}
                        </span>
                      </td>
                      <td className="py-3">
                        <select
                          className="rounded-[var(--radius-lg)] border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none"
                          value={c.status}
                          disabled={statusMutation.isPending}
                          onChange={(e) =>
                            statusMutation.mutate({
                              id: c.id,
                              status: e.target.value,
                            })
                          }
                        >
                          {STATUS_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {statusLabel(o.value)}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {statusFilter
                ? "해당 상태의 임대계약이 없습니다."
                : "등록된 임대계약이 없습니다. 위 폼에서 계약을 등록하세요."}
            </div>
          )}
        </div>
      </SectionCard>

      {/* (결합) Lease AI analysis */}
      {analyzeAvailable && (
        <SectionCard title="계약서 AI 분석 (결합)">
          <p className="mb-3 text-sm leading-7 text-[var(--text-secondary)]">
            임대차 계약서 내용을 붙여넣으면 AI가 핵심 조항·리스크를 분석합니다.
          </p>
          <textarea
            className={`${inputClass} min-h-28 resize-y`}
            value={analyzeText}
            onChange={(e) => setAnalyzeText(e.target.value)}
            placeholder="계약서 텍스트를 입력하세요."
          />
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              disabled={analyzeMutation.isPending || !analyzeText.trim()}
              onClick={() => {
                setAnalyzeResult("");
                analyzeMutation.mutate(analyzeText.trim());
              }}
              className="rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface-soft)] disabled:opacity-60"
            >
              {analyzeMutation.isPending ? "분석 중..." : "분석 시작"}
            </button>
          </div>
          {analyzeResult && (
            <div className="mt-4 whitespace-pre-wrap rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {analyzeResult}
            </div>
          )}
        </SectionCard>
      )}

      {/* (결합) NPS satisfaction */}
      {npsAvailable && (
        <SectionCard title="임차인 만족도 (NPS, 결합)">
          <p className="mb-3 text-sm leading-7 text-[var(--text-secondary)]">
            임차인 만족도 순추천지수(NPS)를 조회합니다.
          </p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={npsMutation.isPending}
              onClick={() => {
                setNpsResult("");
                npsMutation.mutate();
              }}
              className="rounded-[var(--radius-lg)] border border-[var(--line-strong)] bg-[var(--surface)] px-5 py-2.5 text-sm font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface-soft)] disabled:opacity-60"
            >
              {npsMutation.isPending ? "조회 중..." : "NPS 조회"}
            </button>
            {npsResult && (
              <span className="text-sm text-[var(--text-secondary)]">
                {npsResult}
              </span>
            )}
          </div>
        </SectionCard>
      )}
    </section>
  );
}
