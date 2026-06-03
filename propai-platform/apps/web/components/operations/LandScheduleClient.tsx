"use client";

/**
 * 토지조서(편입토지 관리) — 지번·소유자·지분·매입가·계약/동의 관리 + 집계 + 지도 + 엑셀.
 * 등기정보분석과 상호 연동(행별 자동채움/링크). 프로젝트별 영속 + 서버 동기화.
 */

import { useCallback, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";
import type { Locale } from "@/i18n/config";

function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr") {
      return "https://api.4t8t.net/api/v1";
    }
  }
  return "/api/proxy";
}

const won = (v: number | null | undefined) =>
  v == null || v === 0 ? "-" : v >= 1e8 ? `${(v / 1e8).toFixed(2)}억` : `${Math.round(v / 1e4).toLocaleString()}만`;

function Bar({ label, ratio, color }: { label: string; ratio: number; color: string }) {
  const pct = Math.round(ratio * 100);
  return (
    <div>
      <div className="flex justify-between text-[11px] text-[var(--text-secondary)]"><span>{label}</span><span className="font-bold">{pct}%</span></div>
      <div className="mt-1 h-2 rounded-full bg-[var(--surface-strong)]">
        <div className="h-2 rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export function LandScheduleClient({ locale }: { locale: Locale }) {
  const router = useRouter();
  const { locale: rl } = (useParams() as { locale?: string }) || {};
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const rows = useLandScheduleStore((s) => s.byProject[projectId || "_default"] || []);
  const addRow = useLandScheduleStore((s) => s.addRow);
  const updateRow = useLandScheduleStore((s) => s.updateRow);
  const removeRow = useLandScheduleStore((s) => s.removeRow);
  const [addr, setAddr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const agg = useMemo(() => {
    const n = rows.length;
    const area = rows.reduce((a, r) => a + (r.area_sqm || 0), 0);
    const priv = rows.filter((r) => r.owner_type === "사유지").reduce((a, r) => a + (r.area_sqm || 0), 0);
    const pub = rows.filter((r) => r.owner_type === "국공유지").reduce((a, r) => a + (r.area_sqm || 0), 0);
    const contracted = rows.filter((r) => r.contracted).length;
    const useC = rows.filter((r) => r.land_use_consent).length;
    const distC = rows.filter((r) => r.district_consent).length;
    const expSum = rows.reduce((a, r) => a + (r.expected_price || 0), 0);
    const purSum = rows.reduce((a, r) => a + (r.purchase_price || 0), 0);
    return { n, area, priv, pub, contracted, useC, distC, expSum, purSum,
      contractRatio: n ? contracted / n : 0, useRatio: n ? useC / n : 0, distRatio: n ? distC / n : 0 };
  }, [rows]);

  const add = useCallback(() => {
    const a = addr.trim();
    addRow(projectId, a ? { jibun: a } : {});
    setAddr("");
  }, [addr, projectId, addRow]);

  // 등기분석으로 행 자동채움(소유자·지분·소유구분·면적)
  const autofill = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id);
    try {
      const res = await apiClient.post<{ land?: { owner_type?: string; land_area_sqm?: number }; ai?: { ownership?: { current_owner?: string; share?: string } } }>(
        "/registry/analyze", { body: { address: r.jibun.trim() }, useMock: false, timeoutMs: 120000 });
      const own = res.ai?.ownership || {};
      const land = res.land || {};
      updateRow(projectId, r.id, {
        owner: own.current_owner && own.current_owner !== "데이터 없음" ? own.current_owner : r.owner,
        share: own.share && own.share !== "데이터 없음" ? own.share : r.share,
        area_sqm: land.land_area_sqm ?? r.area_sqm,
        owner_type: r.owner_type || (land.owner_type?.includes("국") || land.owner_type?.includes("공") ? "국공유지" : land.owner_type ? "사유지" : ""),
      });
    } catch { /* noop */ } finally { setBusy(null); }
  }, [projectId, updateRow]);

  const openAnalysis = (jibun: string) => {
    router.push(`/${rl || locale}/registry-analysis?addr=${encodeURIComponent(jibun)}`);
  };

  const downloadExcel = useCallback(async () => {
    setBusy("excel");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/registry/land-schedule/excel`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ project_name: projectName || "토지조서", rows }),
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `토지조서_${projectName || "프로젝트"}.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch { /* noop */ } finally { setBusy(null); }
  }, [rows, projectName]);

  const inputCls = "w-full rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-1.5 py-1 text-[11px] text-[var(--text-primary)] outline-none";

  return (
    <div className="grid gap-6">
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🗂️</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">토지조서 (편입토지 관리)</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">필지별 소유·지분·매입가·계약/동의 관리 + 집계 + 구획도 + 엑셀. 등기정보분석과 상호 연동.</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <div className="min-w-[260px] flex-1">
              <ProjectAddressInput value={addr} onChange={setAddr} label="필지 추가(지번)" placeholder="지번 주소 검색" pickerLabel="분석 히스토리" />
            </div>
            <button onClick={add} className="rounded-xl border border-dashed border-[var(--line-strong)] px-3.5 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">＋ 필지 추가</button>
            <button onClick={downloadExcel} disabled={busy === "excel" || rows.length === 0}
              className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
              {busy === "excel" ? "생성 중…" : "📊 토지조서 엑셀"}
            </button>
          </div>
        </CardContent>
      </Card>

      {rows.length > 0 && (
        <>
          {/* 표 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-4 overflow-x-auto">
              <table className="w-full min-w-[980px] text-[11px]">
                <thead>
                  <tr className="border-b border-[var(--line)] text-[var(--text-tertiary)]">
                    {["#", "지번", "소유자", "지분", "면적㎡", "소유구분", "매입예정가(원)", "매입가(원)", "계약", "토지사용", "지구단위", "등기분석", ""].map((h) => (
                      <th key={h} className="px-1.5 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id} className="border-b border-[var(--line)]/50">
                      <td className="px-1.5 py-1 text-[var(--text-tertiary)]">{i + 1}</td>
                      <td className="px-1.5 py-1 min-w-[160px]"><input className={inputCls} value={r.jibun} onChange={(e) => updateRow(projectId, r.id, { jibun: e.target.value })} /></td>
                      <td className="px-1.5 py-1 min-w-[90px]"><input className={inputCls} value={r.owner} onChange={(e) => updateRow(projectId, r.id, { owner: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-16"><input className={inputCls} value={r.share} onChange={(e) => updateRow(projectId, r.id, { share: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-20"><input className={inputCls} type="number" value={r.area_sqm ?? ""} onChange={(e) => updateRow(projectId, r.id, { area_sqm: e.target.value ? Number(e.target.value) : null })} /></td>
                      <td className="px-1.5 py-1 w-24">
                        <select className={inputCls} value={r.owner_type} onChange={(e) => updateRow(projectId, r.id, { owner_type: e.target.value as LandRow["owner_type"] })}>
                          <option value="">-</option><option value="사유지">사유지</option><option value="국공유지">국공유지</option>
                        </select>
                      </td>
                      <td className="px-1.5 py-1 w-28"><input className={inputCls} type="number" value={r.expected_price ?? ""} onChange={(e) => updateRow(projectId, r.id, { expected_price: e.target.value ? Number(e.target.value) : null })} /></td>
                      <td className="px-1.5 py-1 w-28"><input className={inputCls} type="number" value={r.purchase_price ?? ""} onChange={(e) => updateRow(projectId, r.id, { purchase_price: e.target.value ? Number(e.target.value) : null })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.contracted} onChange={(e) => updateRow(projectId, r.id, { contracted: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.land_use_consent} onChange={(e) => updateRow(projectId, r.id, { land_use_consent: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.district_consent} onChange={(e) => updateRow(projectId, r.id, { district_consent: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 whitespace-nowrap">
                        <button onClick={() => autofill(r)} disabled={busy === r.id} className="mr-1 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] disabled:opacity-50">{busy === r.id ? "…" : "자동채움"}</button>
                        <button onClick={() => openAnalysis(r.jibun)} className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">분석 ↗</button>
                      </td>
                      <td className="px-1.5 py-1"><button onClick={() => removeRow(projectId, r.id)} className="text-rose-500">✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* 집계 + 진행바 + 보상비 */}
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <p className="text-sm font-black text-[var(--accent-strong)]">📊 토지조서 집계</p>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["총 필지수", `${agg.n}필지`],
                  ["부지면적", `${Math.round(agg.area).toLocaleString()}㎡`],
                  ["사유지 / 국공유지", `${Math.round(agg.priv).toLocaleString()} / ${Math.round(agg.pub).toLocaleString()}㎡`],
                  ["매입예정가 합계", `${won(agg.expSum)}원`],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                    <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                    <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                  </div>
                ))}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <Bar label="확보비율(계약확정)" ratio={agg.contractRatio} color="#14b8a6" />
                <Bar label="토지사용 동의율" ratio={agg.useRatio} color="#3b82f6" />
                <Bar label="지구단위 동의율" ratio={agg.distRatio} color="#8b5cf6" />
              </div>
              <div className="mt-4 flex flex-wrap gap-4 text-xs">
                <span className="text-[var(--text-secondary)]">보상비(매입가) 합계: <b className="text-[var(--text-primary)]">{won(agg.purSum)}원</b></span>
                <span className="text-[var(--text-secondary)]">미확보 잔여(예정−매입): <b className="text-amber-400">{won(agg.expSum - agg.purSum)}원</b></span>
              </div>
            </CardContent>
          </Card>

          {/* 구획도 (필지 전체) */}
          <ParcelBoundaryMap parcels={rows.map((r) => r.jibun).filter(Boolean)} />
        </>
      )}
    </div>
  );
}
