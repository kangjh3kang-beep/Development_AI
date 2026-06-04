"use client";

/**
 * 토지조서(편입토지 관리) — 지번·소유자·지분·매입가·계약/동의 관리 + 집계 + 지도 + 엑셀.
 * 등기정보분석과 상호 연동(행별 자동채움/링크). 프로젝트별 영속 + 서버 동기화.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";
import { NearbyTransactionsMap } from "@/components/map/NearbyTransactionsMap";
import { analyzeRegistry } from "@/lib/registry-analyze";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useLandScheduleStore, type LandRow } from "@/store/useLandScheduleStore";
import type { Locale } from "@/i18n/config";

const EMPTY_ROWS: LandRow[] = []; // zustand v5: 안정적 참조(매 렌더 새 [] 반환→무한루프 방지)

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
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const rows = useLandScheduleStore((s) => s.byProject[projectId || "_default"] ?? EMPTY_ROWS);
  const addRow = useLandScheduleStore((s) => s.addRow);
  const updateRow = useLandScheduleStore((s) => s.updateRow);
  const removeRow = useLandScheduleStore((s) => s.removeRow);
  const setRows = useLandScheduleStore((s) => s.setRows);
  const [addr, setAddr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [highlight, setHighlight] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  // 필지 상태(계약/동의) → 색상·라벨 (지도·표 강조)
  const rowStatus = useCallback((r: LandRow): { color: string; label: string } => {
    if (r.contracted) return { color: "#10b981", label: "계약완료" };
    if (r.land_use_consent || r.district_consent) return { color: "#f59e0b", label: "동의(미계약)" };
    return { color: "#ef4444", label: "미동의·미계약" };
  }, []);
  const { statusColors, statusLabels } = useMemo(() => {
    const colors: Record<string, string> = {};
    const labels: Record<string, string> = {};
    for (const r of rows) {
      if (!r.jibun) continue;
      const s = rowStatus(r);
      colors[r.jibun] = s.color;
      labels[r.jibun] = s.label;
    }
    return { statusColors: colors, statusLabels: labels };
  }, [rows, rowStatus]);

  // 엑셀 업로드(대량 지번 일괄 입력)
  const importExcel = useCallback(async (file: File) => {
    setBusy("import");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${apiBase()}/registry/land-schedule/import`, {
        method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd,
      });
      const data = await res.json();
      const imported: LandRow[] = (data.rows || []).map((r: Partial<LandRow>) => ({
        id: Math.random().toString(36).slice(2, 9),
        jibun: r.jibun || "", owner: r.owner || "", share: r.share || "",
        area_sqm: r.area_sqm ?? null, owner_type: (r.owner_type as LandRow["owner_type"]) || "",
        expected_price: r.expected_price ?? null, purchase_price: r.purchase_price ?? null,
        contracted: !!r.contracted, land_use_consent: !!r.land_use_consent, district_consent: !!r.district_consent,
      }));
      if (imported.length) setRows(projectId, [...rows, ...imported]);
      else alert("가져올 행이 없습니다. '지번' 컬럼이 있는 엑셀인지 확인하세요.");
    } catch {
      alert("엑셀 업로드에 실패했습니다.");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, [projectId, rows, setRows]);

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

  // 소유구분 문자열 → 사유지/국공유지 매핑
  const toOwnerType = (s?: string | null): LandRow["owner_type"] =>
    s?.includes("국") || s?.includes("공") ? "국공유지" : s ? "사유지" : "";

  // 부지분석(프로젝트) → 토지조서 행 시드. 다필지면 전부, 단일이면 1행. (#1·#2·#4)
  const loadFromProject = useCallback(() => {
    const mk = (jibun: string, area: number | null, ot: string): LandRow => ({
      id: Math.random().toString(36).slice(2, 9),
      jibun, owner: "", share: "", area_sqm: area, owner_type: toOwnerType(ot),
      expected_price: null, purchase_price: null,
      contracted: false, land_use_consent: false, district_consent: false, pdf_url: null,
    });
    const parcels = siteAnalysis?.parcels;
    if (parcels && parcels.length) {
      setRows(projectId, parcels.map((p) => mk(p.address, p.areaSqm ?? null, p.ownerType)));
    } else if (siteAnalysis?.address) {
      setRows(projectId, [mk(siteAnalysis.address, siteAnalysis.landAreaSqm ?? null, "")]);
    }
  }, [projectId, siteAnalysis, setRows]);

  // 프로젝트 전환 시 토지조서가 비어있으면 부지분석 필지로 자동 시드(기존 작업은 보존)
  useEffect(() => {
    if (!projectId) return;
    if (rows.length > 0) return;
    if (!siteAnalysis?.parcels?.length && !siteAnalysis?.address) return;
    loadFromProject();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis]);

  // 등기분석으로 행 자동채움(소유자·지분·소유구분·면적). 등기 실패 시에도 공부정보는 채움.
  const autofill = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice("");
    try {
      const res = await analyzeRegistry<{
        status?: string; message?: string;
        land?: { owner_type?: string; land_area_sqm?: number; ownership_form?: string };
        ai?: { ownership?: { current_owner?: string; share?: string } };
        fetched?: { pdf_url?: string | null };
      }>({ address: r.jibun.trim() });
      const own = res.ai?.ownership || {};
      const land = res.land || {};
      const ownerStr = own.current_owner && own.current_owner !== "데이터 없음" ? own.current_owner : "";
      // 공부 토지정보(면적/소유구분)는 항상 반영. 소유자·지분은 등기 성공 시 반영.
      updateRow(projectId, r.id, {
        owner: ownerStr || r.owner,
        share: own.share && own.share !== "데이터 없음" ? own.share : r.share,
        area_sqm: land.land_area_sqm ?? r.area_sqm,
        owner_type: toOwnerType(land.owner_type) || (land.ownership_form ? "사유지" : r.owner_type),
        pdf_url: res.fetched?.pdf_url ?? r.pdf_url,
      });
      if (res.status !== "ok" || !ownerStr) {
        setNotice(
          `「${r.jibun}」 공부 토지정보는 채웠으나, 소유자·지분(등기)은 가져오지 못했습니다` +
          (res.message ? ` — ${res.message}` : "(등기 발급 연동 확인 필요)") +
          ". 등기부등본 내용을 직접 입력하면 권리분석이 가능합니다.",
        );
      }
    } catch {
      setNotice(`「${r.jibun}」 등기 분석에 실패했습니다. 잠시 후 다시 시도하세요.`);
    } finally { setBusy(null); }
  }, [projectId, updateRow]);

  // 매입예정가 적정가 분석(주소→PNU 공시지가 × 지역 시세보정). 결과는 수정 가능.
  const estimatePrice = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice("");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/land-price/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address: r.jibun.trim(), area_sqm: r.area_sqm ?? undefined }),
      });
      const d = await res.json();
      if (d?.ok && d.estimated_total_won) {
        updateRow(projectId, r.id, {
          expected_price: d.estimated_total_won,
          ...(d.area_sqm && !r.area_sqm ? { area_sqm: d.area_sqm } : {}),
        });
        setNotice(`「${r.jibun}」 ${d.rationale}`);
      } else {
        setNotice(`「${r.jibun}」 적정가 추정 실패 — ${d?.message || "공시지가 확인 필요"}. ‘자동채움’으로 면적·공부정보를 먼저 채워보세요.`);
      }
    } catch {
      setNotice(`「${r.jibun}」 적정가 추정에 실패했습니다.`);
    } finally { setBusy(null); }
  }, [projectId, updateRow]);

  // 예상 시세 추정(공시지가 기준+실거래 비교). 감정평가 아님, 매입예정가 채움(수정가능).
  const deskAppraise = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice("");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/land-price/desk-appraisal`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address: r.jibun.trim(), area_sqm: r.area_sqm ?? undefined }),
      });
      const d = await res.json();
      if (d?.ok && d.appraised_total_won) {
        updateRow(projectId, r.id, {
          expected_price: d.appraised_total_won,
          ...(d.area_sqm && !r.area_sqm ? { area_sqm: d.area_sqm } : {}),
        });
        const methods = (d.methods || []).map((m: { method: string; unit_price: number }) => `${m.method} ${Math.round(m.unit_price).toLocaleString()}원/㎡`).join(" · ");
        const cc = d.cross_check ? ` · 복수 시나리오 교차검증 평균 ${d.cross_check.mean.toLocaleString()}원/㎡(CV ${d.cross_check.cv_pct}%)` : "";
        setNotice(`「${r.jibun}」 예상 시세 추정 ${d.appraised_price_per_sqm.toLocaleString()}원/㎡ (신뢰 ${Math.round(d.confidence * 100)}%, ±${d.range_per_sqm.low.toLocaleString()}~${d.range_per_sqm.high.toLocaleString()}) — ${methods}${cc}. ${d.weight_note}. ${d.disclaimer}`);
      } else {
        setNotice(`「${r.jibun}」 예상 시세 추정 실패 — ${d?.message || "공시지가 확인 필요"}. ‘자동채움’으로 공부정보를 먼저 채워보세요.`);
      }
    } catch {
      setNotice(`「${r.jibun}」 예상 시세 추정에 실패했습니다.`);
    } finally { setBusy(null); }
  }, [projectId, updateRow]);

  // 토지 예상가치 추정 리포트 PDF 다운로드(감정평가서 아님)
  const deskAppraisalPdf = useCallback(async (r: LandRow) => {
    if (!r.jibun.trim()) return;
    setBusy(r.id); setNotice("");
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiBase()}/land-price/desk-appraisal/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ address: r.jibun.trim(), area_sqm: r.area_sqm ?? undefined }),
      });
      const ct = res.headers.get("content-type") || "";
      if (!res.ok || !ct.includes("pdf")) {
        const j = await res.json().catch(() => ({}));
        setNotice(`「${r.jibun}」 추정 리포트 생성 실패 — ${j?.message || "공시지가 확인 필요"}`);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `토지예상가치추정_${r.jibun.trim()}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setNotice(`「${r.jibun}」 추정 리포트 PDF 생성에 실패했습니다.`);
    } finally { setBusy(null); }
  }, []);

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
            {(siteAnalysis?.parcels?.length || siteAnalysis?.address) && (
              <button onClick={loadFromProject} title="프로젝트 부지분석의 필지(다필지 포함)를 토지조서로 불러옵니다"
                className="rounded-xl border border-[var(--line-strong)] px-3.5 py-2 text-xs font-bold text-[var(--accent-strong)] hover:border-[var(--accent-strong)]">
                ⤵ 프로젝트 필지 불러오기{siteAnalysis?.parcels?.length ? ` (${siteAnalysis.parcels.length})` : ""}
              </button>
            )}
            <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void importExcel(f); }} />
            <button onClick={() => fileRef.current?.click()} disabled={busy === "import"}
              className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
              {busy === "import" ? "업로드 중…" : "⬆ 엑셀 업로드"}
            </button>
            <button onClick={downloadExcel} disabled={busy === "excel" || rows.length === 0}
              className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
              {busy === "excel" ? "생성 중…" : "📊 토지조서 엑셀"}
            </button>
          </div>
        </CardContent>
      </Card>

      {notice && (
        <div className="flex items-start justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-300">
          <span>⚠ {notice}</span>
          <button onClick={() => setNotice("")} className="shrink-0 text-amber-400">✕</button>
        </div>
      )}

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
                    <tr key={r.id} className={`border-b border-[var(--line)]/50 ${highlight && highlight === r.jibun ? "bg-[var(--accent-soft)]" : ""}`}>
                      <td className="px-1.5 py-1">
                        <button onClick={() => setHighlight(r.jibun)} title="지도에서 강조" className="flex items-center gap-1">
                          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: rowStatus(r).color }} />
                          <span className="text-[var(--text-tertiary)]">{i + 1}</span>
                        </button>
                      </td>
                      <td className="px-1.5 py-1 min-w-[160px]"><input title={r.jibun || "지번"} className={inputCls} value={r.jibun} onChange={(e) => updateRow(projectId, r.id, { jibun: e.target.value })} /></td>
                      <td className="px-1.5 py-1 min-w-[90px]"><input title={r.owner || "소유자"} className={inputCls} value={r.owner} onChange={(e) => updateRow(projectId, r.id, { owner: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-16"><input title={r.share || "지분"} className={inputCls} value={r.share} onChange={(e) => updateRow(projectId, r.id, { share: e.target.value })} /></td>
                      <td className="px-1.5 py-1 w-20"><input className={inputCls} type="number" value={r.area_sqm ?? ""} onChange={(e) => updateRow(projectId, r.id, { area_sqm: e.target.value ? Number(e.target.value) : null })} /></td>
                      <td className="px-1.5 py-1 w-24">
                        <select className={inputCls} value={r.owner_type} onChange={(e) => updateRow(projectId, r.id, { owner_type: e.target.value as LandRow["owner_type"] })}>
                          <option value="">-</option><option value="사유지">사유지</option><option value="국공유지">국공유지</option>
                        </select>
                      </td>
                      <td className="px-1.5 py-1 w-36">
                        <input title={r.expected_price ? `${r.expected_price.toLocaleString()}원` : "매입예정가"} className={inputCls} type="number" value={r.expected_price ?? ""} onChange={(e) => updateRow(projectId, r.id, { expected_price: e.target.value ? Number(e.target.value) : null })} />
                        <div className="mt-0.5 flex flex-wrap items-center gap-1">
                          <button onClick={() => estimatePrice(r)} disabled={busy === r.id} title="공시지가×지역 시세보정 기반 적정 매입가(수정가능)" className="cursor-pointer rounded bg-[var(--accent-soft)] px-1 py-0.5 text-[9px] font-bold text-[var(--accent-strong)] disabled:opacity-50">적정</button>
                          <button onClick={() => deskAppraise(r)} disabled={busy === r.id} title="예상 시세 추정(공시지가 기준+실거래 비교+복수 시나리오 교차검증) — 감정평가 아님, 참고용·수정가능" className="cursor-pointer rounded border border-[var(--accent-strong)]/40 px-1 py-0.5 text-[9px] font-bold text-[var(--accent-strong)] disabled:opacity-50">예상시세</button>
                          <button onClick={() => deskAppraisalPdf(r)} disabled={busy === r.id} title="토지 예상가치 추정 리포트 PDF(감정평가서 아님)" className="cursor-pointer rounded border border-[var(--line)] px-1 py-0.5 text-[9px] font-bold text-[var(--text-secondary)] disabled:opacity-50">리포트↓</button>
                        </div>
                      </td>
                      <td className="px-1.5 py-1 w-28"><input className={inputCls} type="number" value={r.purchase_price ?? ""} onChange={(e) => updateRow(projectId, r.id, { purchase_price: e.target.value ? Number(e.target.value) : null })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.contracted} onChange={(e) => updateRow(projectId, r.id, { contracted: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.land_use_consent} onChange={(e) => updateRow(projectId, r.id, { land_use_consent: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 text-center"><input type="checkbox" checked={r.district_consent} onChange={(e) => updateRow(projectId, r.id, { district_consent: e.target.checked })} /></td>
                      <td className="px-1.5 py-1 whitespace-nowrap">
                        <button onClick={() => autofill(r)} disabled={busy === r.id} title="등기 권리분석으로 소유자·지분·면적 자동채움" className="mr-1 cursor-pointer rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] disabled:opacity-50">{busy === r.id ? "…" : "자동채움"}</button>
                        <button onClick={() => openAnalysis(r.jibun)} title="등기 권리분석 상세 페이지로 이동" className="cursor-pointer rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">분석 ↗</button>
                        {r.pdf_url && (
                          <a href={r.pdf_url} target="_blank" rel="noopener noreferrer" title="발급 등기부등본 PDF" className="ml-1 cursor-pointer rounded border border-[var(--accent-strong)]/40 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">PDF ↓</a>
                        )}
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

          {/* 구획도 (필지 전체) — 계약/동의 상태색상 + 행 클릭 하이라이트 */}
          <div>
            <div className="mb-2 flex flex-wrap gap-3 text-[11px]">
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />계약완료</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-500" />동의(미계약)</span>
              <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-rose-500" />미동의·미계약</span>
              <span className="text-[var(--text-hint)]">· 표의 번호/지도 필지 클릭 시 상호 강조</span>
            </div>
            <ParcelBoundaryMap
              parcels={rows.map((r) => r.jibun).filter(Boolean)}
              statusColors={statusColors}
              statusLabels={statusLabels}
              highlight={highlight}
              onParcelClick={(a) => setHighlight(a)}
            />
          </div>

          {/* 구획도 주변 토지 실거래·시세(공시지가는 '적정' 분석으로 확인) */}
          {(highlight || rows.find((r) => r.jibun.trim())?.jibun) && (
            <div>
              <p className="mb-2 text-sm font-bold text-[var(--text-primary)]">
                📈 주변 토지 실거래·시세 <span className="text-[11px] font-normal text-[var(--text-secondary)]">— {highlight || rows.find((r) => r.jibun.trim())?.jibun} 기준 반경 1km</span>
              </p>
              <NearbyTransactionsMap address={highlight || rows.find((r) => r.jibun.trim())?.jibun || ""} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
