"use client";

/**
 * 표준설계 참조 라이브러리 — 관리자 페이지(P7).
 * 관리자가 도면 사례(DXF/PDF/이미지) + 메타를 업로드하면 라이브러리에 적재되고,
 * 설계 스튜디오 생성 시 '유사 사례'로 검색·활용된다. (업로드/삭제는 관리자 전용 — API 게이트)
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { sanitizeSvgMarkup } from "@/components/cad/ReferenceAssemblyCard";

/* eslint-disable @typescript-eslint/no-explicit-any */

type Ref = {
  id: string; title: string; building_use: string | null; zone_code: string | null;
  area_sqm: number | null; total_units: number | null; floors: number | null;
  unit_types: string[]; file_url: string | null; file_type: string | null;
  source: string | null; note: string | null; created_at: string | null;
  /** U4(R7) 확장 — 구버전 백엔드 응답엔 없으므로 optional(부재 시 미표시). */
  has_geometry?: boolean;
  thumbnail_svg?: string | null;
};

const USES = ["공동주택", "오피스텔", "근린생활시설", "업무시설", "숙박시설", "단독주택"];
const ZONES = ["1R", "2R", "3R", "QR", "GC", "NC", "QI"];
const UNIT_OPTS = ["29A", "39A", "49A", "59A", "74A", "84A", "114A"];

export default function DesignReferencesPage() {
  const [items, setItems] = useState<Ref[]>([]);
  const [form, setForm] = useState({
    title: "", building_use: "공동주택", zone_code: "2R",
    area_sqm: "", total_units: "", floors: "", source: "", note: "",
  });
  const [unitTypes, setUnitTypes] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await apiClient.get<{ items: Ref[] }>("/design-references", { useMock: false });
      setItems(r.items || []);
    } catch { setMsg("목록을 불러오지 못했습니다(로그인 필요)."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleUnit = (u: string) =>
    setUnitTypes((p) => (p.includes(u) ? p.filter((x) => x !== u) : [...p, u]));

  const upload = async () => {
    if (!form.title.trim()) { setMsg("사례 제목을 입력하세요."); return; }
    setBusy(true); setMsg("");
    try {
      const fd = new FormData();
      fd.append("title", form.title);
      fd.append("building_use", form.building_use);
      fd.append("zone_code", form.zone_code);
      if (form.area_sqm) fd.append("area_sqm", form.area_sqm);
      if (form.total_units) fd.append("total_units", form.total_units);
      if (form.floors) fd.append("floors", form.floors);
      fd.append("unit_types", JSON.stringify(unitTypes));
      if (form.source) fd.append("source", form.source);
      if (form.note) fd.append("note", form.note);
      if (file) fd.append("file", file);
      const r = await apiClient.post<any>("/design-references", { body: fd, useMock: false, timeoutMs: 120000 });
      setMsg(r?.ok ? "사례가 등록되었습니다." : (r?.detail || "등록 처리됨"));
      setForm({ title: "", building_use: "공동주택", zone_code: "2R", area_sqm: "", total_units: "", floors: "", source: "", note: "" });
      setUnitTypes([]); setFile(null);
      await load();
    } catch (e: any) {
      setMsg(e?.message?.includes("403") ? "관리자만 업로드할 수 있습니다." : "업로드 실패 — 입력/권한/스토리지 설정을 확인하세요.");
    } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    if (!confirm("이 사례를 삭제할까요?")) return;
    setBusy(true);
    try { await apiClient.delete(`/design-references/${id}`, { useMock: false }); await load(); }
    catch { setMsg("삭제 실패(관리자 권한 필요)."); }
    finally { setBusy(false); }
  };

  // U4(R7): DXF 기하 업로드 — 등록된 사례에 파싱 가능한 기하를 부여(조립 가능 사례로 전환).
  const uploadGeometry = async (id: string, f: File) => {
    setBusy(true); setMsg("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await apiClient.post<any>(`/design-references/${id}/geometry`, { body: fd, useMock: false, timeoutMs: 120000 });
      setMsg(r?.ok ? "DXF 기하가 등록되었습니다 — 설계 생성 시 '조립 가능' 사례로 표시됩니다." : (r?.detail || "기하 등록 처리됨"));
      await load();
    } catch (e: any) {
      setMsg(e?.message?.includes("403") ? "관리자만 기하를 등록할 수 있습니다." : "DXF 기하 등록 실패 — 파일/권한/서버 설정을 확인하세요.");
    } finally { setBusy(false); }
  };

  const won = (n: number | null) => (n ? `${Math.round(n).toLocaleString("ko-KR")}㎡` : "-");

  return (
    <div className="mx-auto max-w-4xl space-y-5 p-1 pb-20">
      <header className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" /><i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10">
          <span className="cc-meta">설계 참고 · 표준설계 라이브러리</span>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">표준설계 참조 라이브러리 <span className="text-[var(--accent-strong)]">_</span></h1>
          <p className="text-sm text-[var(--text-secondary)]">도면 사례(DXF/PDF/이미지)와 메타를 등록하면, 설계 생성 시 유사 사례로 검색·활용됩니다. (업로드·삭제는 관리자)</p>
        </div>
      </header>

      {msg && <div className="rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">{msg}</div>}

      <section className="cc-panel"><div className="cc-panel__body space-y-3">
        <h2 className="text-sm font-bold text-[var(--text-primary)]">사례 등록</h2>
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="사례 제목(예: 분당 84㎡ 판상형 표준)" className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
        <div className="grid gap-2 sm:grid-cols-3">
          <select value={form.building_use} onChange={(e) => setForm({ ...form, building_use: e.target.value })} className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            {USES.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select value={form.zone_code} onChange={(e) => setForm({ ...form, zone_code: e.target.value })} className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            {ZONES.map((z) => <option key={z} value={z}>{z}</option>)}
          </select>
          <input value={form.area_sqm} onChange={(e) => setForm({ ...form, area_sqm: e.target.value })} type="number" placeholder="대지면적(㎡)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <input value={form.total_units} onChange={(e) => setForm({ ...form, total_units: e.target.value })} type="number" placeholder="세대수" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <input value={form.floors} onChange={(e) => setForm({ ...form, floors: e.target.value })} type="number" placeholder="층수" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="출처(선택)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {UNIT_OPTS.map((u) => (
            <button key={u} onClick={() => toggleUnit(u)} className={`rounded-full border px-3 py-1 text-xs font-bold ${unitTypes.includes(u) ? "border-transparent bg-[var(--accent-strong)] text-white" : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>{u}</button>
          ))}
        </div>
        <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="메모(선택)" className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
        <div className="flex items-center gap-2">
          <input type="file" accept=".dxf,.dwg,.pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs text-[var(--text-secondary)] file:mr-2 file:rounded-lg file:border-0 file:bg-[var(--surface-muted)] file:px-3 file:py-1.5 file:text-xs file:font-bold file:text-[var(--text-secondary)]" />
          {file && <span className="text-[11px] text-[var(--text-hint)]">{file.name}</span>}
        </div>
        <button onClick={upload} disabled={busy || !form.title.trim()} className="w-full rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{busy ? "등록 중…" : "사례 등록"}</button>
        <p className="text-[10px] text-[var(--text-hint)]">※ 파일은 선택(메타만 등록도 가능). DXF/DWG/PDF/이미지 최대 25MB. 저작권 확인 후 업로드하세요.</p>
      </div></section>

      <section className="cc-panel"><div className="cc-panel__body">
        <h2 className="mb-3 text-sm font-bold text-[var(--text-primary)]">등록된 사례 ({items.length})</h2>
        {items.length === 0 && <p className="py-6 text-center text-sm text-[var(--text-secondary)]">아직 등록된 사례가 없습니다.</p>}
        <div className="grid gap-2 sm:grid-cols-2">
          {items.map((it) => {
            const thumb = sanitizeSvgMarkup(it.thumbnail_svg);
            return (
              <div key={it.id} className="rounded-lg border border-[var(--line)] px-3 py-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2">
                    {/* U4(R7): 도면 썸네일(inline SVG) — script 제거 가드 통과 시에만 렌더 */}
                    {thumb && (
                      <div
                        className="h-14 w-16 shrink-0 overflow-hidden rounded-md border border-[var(--line)] bg-[var(--surface-muted)] [&_svg]:h-full [&_svg]:w-full"
                        role="img"
                        aria-label={`${it.title} 도면 썸네일`}
                        dangerouslySetInnerHTML={{ __html: thumb }}
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-[var(--text-primary)]">
                        {it.title}
                        {it.has_geometry === true && <span className="ml-1.5 rounded bg-[var(--accent-soft)] px-1.5 py-0.5 text-[9px] font-black text-[var(--accent-strong)]">기하 보유</span>}
                      </p>
                      <p className="text-[11px] text-[var(--text-secondary)]">{[it.building_use, it.zone_code, won(it.area_sqm), it.total_units ? `${it.total_units}세대` : "", it.floors ? `${it.floors}층` : ""].filter(Boolean).join(" · ")}</p>
                      {it.unit_types?.length > 0 && <p className="text-[10px] text-[var(--text-hint)]">{it.unit_types.join(", ")}</p>}
                      {it.file_url && <a href={it.file_url} target="_blank" rel="noopener noreferrer" className="text-[11px] font-bold text-[var(--accent-strong)]">도면 보기({it.file_type}) ↗</a>}
                    </div>
                  </div>
                  <button onClick={() => remove(it.id)} disabled={busy} className="shrink-0 rounded-md border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold text-rose-400">삭제</button>
                </div>
                {/* U4(R7): DXF 기하 업로드 — 조립(템플릿 어댑테이션) 가능 사례로 전환 */}
                <label className={`mt-2 inline-flex items-center gap-1 rounded-md border border-[var(--line)] bg-[var(--surface-muted)] px-2 py-1 text-[10px] font-bold text-[var(--text-secondary)] ${busy ? "opacity-50" : "cursor-pointer hover:border-[var(--accent-strong)]"}`}>
                  ⬆ DXF 기하 {it.has_geometry === true ? "교체" : "등록"}
                  <input
                    type="file"
                    accept=".dxf"
                    className="hidden"
                    disabled={busy}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) uploadGeometry(it.id, f);
                      e.target.value = "";
                    }}
                  />
                </label>
              </div>
            );
          })}
        </div>
      </div></section>
    </div>
  );
}
