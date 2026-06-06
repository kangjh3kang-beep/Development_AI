"use client";

/**
 * Phase 1-E — 직원관리 집계 패널(scope 토글: 현장별 / 종합).
 *
 * GET /market/staff/overview?scope=site|all&site_id= — 멤버·계약·출근·수수료 집계.
 * scope=all은 내가 관리/소유하는 전 현장 union(여러 현장을 뛰는 프리랜서 통합).
 * 관리역할(AGENCY/GM_DIRECTOR/TEAM_LEAD↑) 전용 — 게이팅은 SiteWorkspaceClient에서 수행.
 *
 * 일반 apiClient(전역 토큰)로 호출(PUBLIC 컨텐츠, X-Site-Token 불필요).
 * 백엔드 계약(_workspace/54 §7)과 필드명 정합.
 */
import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

interface SiteSummary {
  site_id: string;
  site_name?: string;
  member_count: number;
  contract_count: number;
  attendance_count: number;
  commission_gross: number;
}

interface Totals {
  member_count: number;
  contract_count: number;
  attendance_count: number;
  commission_gross: number;
}

interface OverviewResponse {
  scope: string;
  site_count: number;
  sites: SiteSummary[];
  totals: Totals;
}

function won(n: number): string {
  return `${Math.round(n || 0).toLocaleString("ko-KR")}원`;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4">
      <p className="text-[11px] font-bold text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-1 text-lg font-black text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

export default function StaffOverviewPanel({ siteId }: { siteId: string }) {
  const [scope, setScope] = useState<"site" | "all">("site");
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    const params = new URLSearchParams({ scope });
    if (scope === "site" && siteId) params.set("site_id", siteId);
    apiClient
      .get<OverviewResponse>(`/market/staff/overview?${params.toString()}`)
      .then((r) => {
        setData(r);
        setErr("");
      })
      .catch(() => setErr("직원 집계를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [scope, siteId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="sa-seg" role="tablist" aria-label="집계 범위">
        {(["site", "all"] as const).map((s) => (
          <button
            key={s}
            role="tab"
            aria-selected={scope === s}
            data-active={scope === s}
            onClick={() => setScope(s)}
            className="sa-seg__item"
          >
            {s === "site" ? "현장별" : "종합(전 현장)"}
          </button>
        ))}
      </div>

      {scope === "all" && (
        <p className="text-xs text-[var(--text-tertiary)]">
          ⓘ 내가 관리·소유하는 전 현장을 통합 집계합니다(여러 현장을 뛰는 인원 포함).
        </p>
      )}

      {err && <p className="text-sm font-semibold text-[var(--status-error)]">{err}</p>}

      {loading ? (
        <div className="grid gap-2 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="sa-skeleton h-20 rounded-2xl" />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid gap-2 sm:grid-cols-4">
            <StatCard label="멤버" value={`${data.totals.member_count.toLocaleString("ko-KR")}명`} />
            <StatCard label="계약" value={`${data.totals.contract_count.toLocaleString("ko-KR")}건`} />
            <StatCard label="출근" value={`${data.totals.attendance_count.toLocaleString("ko-KR")}회`} />
            <StatCard label="수수료(gross)" value={won(data.totals.commission_gross)} />
          </div>

          {data.sites.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--surface-soft)] px-4 py-10 text-center text-sm text-[var(--text-secondary)]">
              집계할 현장이 없습니다.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-2xl border border-[var(--line)]">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-tertiary)]">
                    <th className="px-3 py-2 text-left text-xs font-bold">현장</th>
                    <th className="px-3 py-2 text-right text-xs font-bold">멤버</th>
                    <th className="px-3 py-2 text-right text-xs font-bold">계약</th>
                    <th className="px-3 py-2 text-right text-xs font-bold">출근</th>
                    <th className="px-3 py-2 text-right text-xs font-bold">수수료</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sites.map((s) => (
                    <tr key={s.site_id} className="border-b border-[var(--line)] last:border-0">
                      <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{s.site_name || s.site_id}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{s.member_count.toLocaleString("ko-KR")}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{s.contract_count.toLocaleString("ko-KR")}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{s.attendance_count.toLocaleString("ko-KR")}</td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(s.commission_gross)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
