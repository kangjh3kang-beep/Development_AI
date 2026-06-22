"use client";

/**
 * BIM 기반 물량·적산 내역(QTO) — BIM 매스(실치수) 또는 연면적·층수 역산으로 부위별 물량을
 * 산출하고 단가를 곱해 공사비로 직결(5D). 모델 변경 시 재계산. /api/v1/cost/estimate-overview.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";

type QtoItem = { name?: string; work?: string; element?: string; quantity?: number; unit?: string; unit_cost_won?: number; cost_won?: number };
type Overview = {
  total_gfa_sqm?: number; gfa_above_sqm?: number; gfa_below_sqm?: number;
  range?: { min_won?: number; expected_won?: number; max_won?: number };
  items?: QtoItem[]; qto_source?: string; geometry?: Record<string, unknown>; note?: string;
  // 전역정책 Phase0: 산출 근거·법령링크·신선도(백엔드 build_evidence_block 출력 — additive).
  evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[]; provenance?: { name?: string }[];
};

const won = (v?: number | null) => (v == null ? "—" : `${Math.round(v).toLocaleString()}원`);
const eok = (v?: number | null) => (v == null ? "—" : `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`);

export function QtoBreakdown({ projectId }: { projectId: string }) {
  const design = useProjectContextStore((s) => s.designData);
  const [res, setRes] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const gfa = design?.totalGfaSqm ?? null;
  const floors = design?.floorCount ?? null;
  const btype = design?.buildingType ?? null;

  const run = useCallback(async () => {
    if (!gfa || gfa <= 0) { setErr("설계(연면적) 데이터가 없습니다 — 먼저 AI 자동설계를 실행하세요."); return; }
    setLoading(true); setErr(null);
    try {
      const r = await apiClient.post<Overview>("/cost/estimate-overview", {
        body: {
          building_type: btype === "공동주택" || !btype ? "apartment" : btype,
          total_gfa_sqm: gfa,
          floor_count_above: floors && floors > 0 ? floors : 1,
          structure_type: "RC",
          project_id: projectId,
        },
        useMock: false, timeoutMs: 45000,
      });
      setRes(r);
    } catch { setErr("적산 계산에 실패했습니다."); } finally { setLoading(false); }
  }, [gfa, floors, btype, projectId]);

  useEffect(() => { if (gfa && gfa > 0) void run(); }, [gfa, run]);

  if (!gfa) {
    return <p className="rounded-xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 text-xs text-[var(--text-secondary)]">설계(연면적) 데이터가 있어야 BIM 적산이 가능합니다. ‘AI 자동설계(CAD)’를 먼저 실행하세요.</p>;
  }
  if (loading) return <p className="text-xs text-[var(--text-hint)]">BIM 물량·적산 계산 중…</p>;
  if (err) return <p className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300"><AlertTriangle className="size-3.5 shrink-0" aria-hidden />{err}</p>;
  if (!res) return null;

  const isBim = res.qto_source === "bim";
  const items = (res.items || []).filter((it) => (it.cost_won ?? 0) > 0 || (it.quantity ?? 0) > 0);

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-end">
        <button onClick={() => void run()} disabled={loading}
          className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
          ↻ 모델 반영 재계산
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="연면적" value={`${Math.round(res.total_gfa_sqm ?? gfa).toLocaleString()}㎡`} />
        <Tile label="공사비(예상)" value={eok(res.range?.expected_won)} sub={`${eok(res.range?.min_won)} ~ ${eok(res.range?.max_won)}`} accent />
        <Tile label="지상/지하" value={`${Math.round(res.gfa_above_sqm ?? 0).toLocaleString()} / ${Math.round(res.gfa_below_sqm ?? 0).toLocaleString()}㎡`} />
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">물량 출처 · 신뢰도</p>
          <p className={`mt-1 text-sm font-[1000] ${isBim ? "text-emerald-500" : "text-[var(--text-secondary)]"}`}>{isBim ? "BIM 모델 실치수" : "기하 추정"}</p>
          <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{isBim ? "신뢰도 높음 (±5% · IFC 실물량)" : "신뢰도 보통 (±12% · 연면적·층수 역산)"}</p>
        </div>
      </div>

      {items.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-[var(--line)]">
          <table className="w-full text-[11px]">
            <thead><tr className="bg-[var(--surface-strong)] text-[var(--text-tertiary)]">
              <th className="px-3 py-2 text-left font-bold">공종/부위</th>
              <th className="px-3 py-2 text-right font-bold">물량</th>
              <th className="px-3 py-2 text-right font-bold">단가</th>
              <th className="px-3 py-2 text-right font-bold">금액</th>
            </tr></thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-t border-[var(--line)]/60">
                  <td className="px-3 py-2 font-semibold text-[var(--text-primary)]">{it.name || it.work || it.element || "-"}</td>
                  <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{it.quantity != null ? `${Math.round(it.quantity).toLocaleString()}${it.unit || ""}` : "—"}</td>
                  <td className="px-3 py-2 text-right text-[var(--text-secondary)]">{won(it.unit_cost_won)}</td>
                  <td className="px-3 py-2 text-right font-bold text-[var(--text-primary)]">{won(it.cost_won)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {res.note && <p className="text-[10px] text-[var(--text-hint)]">{res.note}</p>}

      {/* 공사비 산출 근거(EvidencePanel) — adaptEvidence로 백엔드 evidence/legal_refs 조인.
          공사비는 법령근거 없음 → 산식·출처만 표기. items.length>0면 렌더(빈 패널 방지). */}
      {(() => {
        const ev = adaptEvidence(res.evidence, res.legal_refs);
        return ev.length > 0 ? <EvidencePanel items={ev} title="공사비 산출 근거" /> : null;
      })()}
    </div>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p className={`mt-1 text-sm font-[1000] ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}
