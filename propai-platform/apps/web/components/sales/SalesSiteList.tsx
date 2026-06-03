"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { salesGlobal } from "@/lib/salesApi";
import type { Locale } from "@/i18n/config";

interface Site { id: string; site_code: string; site_name: string; development_type: string; status: string }
const DEV_TYPES = ["APT", "OFFICETEL", "KNOWLEDGE_CENTER", "HOTEL", "RETAIL"];
const FIELD_CLS = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)]";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">{label}</span>
      {children}
    </label>
  );
}

export default function SalesSiteList({ locale }: { locale: Locale }) {
  const [sites, setSites] = useState<Site[]>([]);
  const [form, setForm] = useState({ site_name: "", development_type: "APT", project_id: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const load = () => salesGlobal.get<Site[]>("/sites").then(setSites).catch(() => setSites([]));
  useEffect(() => { load(); }, []);

  const provision = async () => {
    if (!form.site_name || !form.project_id) { setErr("현장명과 프로젝트 ID가 필요합니다."); return; }
    setBusy(true); setErr("");
    try {
      await salesGlobal.post("/provision", form);
      setForm({ site_name: "", development_type: "APT", project_id: "" });
      load();
    } catch {
      setErr("프로비저닝 실패 (권한/프로젝트 ID 확인).");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🏗️</span>
        <div>
          <h1 className="text-lg font-black text-[var(--text-primary)]">분양 현장 관리</h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">현장(분양 사이트)을 프로비저닝하고 동호/분양가/계약/수수료/데스크를 운영합니다.</p>
        </div>
        <Link href={`/${locale}/sales/projection`}
          className="ml-auto rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-black text-[var(--accent-strong)]">
          시행사 투영뷰 →
        </Link>
      </div>

      {/* 프로비저닝 */}
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
        <h2 className="mb-3 text-sm font-bold text-[var(--text-primary)]">새 현장 프로비저닝</h2>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="현장명">
            <input value={form.site_name} onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              placeholder="예: 강남 더샵 1차" className={FIELD_CLS + " w-56"} />
          </Field>
          <Field label="개발 유형">
            <select value={form.development_type} onChange={(e) => setForm({ ...form, development_type: e.target.value })}
              className={FIELD_CLS + " w-44"}>
              {DEV_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="프로젝트 ID">
            <input value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
              placeholder="프로젝트 UUID" className={FIELD_CLS + " w-72"} />
          </Field>
          <button onClick={provision} disabled={busy}
            className="rounded-lg bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white shadow-[var(--shadow-sm)] transition hover:opacity-90 disabled:opacity-50">
            {busy ? "생성 중…" : "프로비저닝"}
          </button>
        </div>
        {err && <p className="mt-2 text-xs font-semibold text-rose-400">{err}</p>}
      </div>

      {/* 현장 목록 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {sites.length === 0 && <p className="text-sm text-[var(--text-secondary)]">현장이 없습니다. 위에서 프로비저닝하세요.</p>}
        {sites.map((s) => (
          <Link key={s.id} href={`/${locale}/sales/${s.site_code}`}
            className="block rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)]">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-[var(--text-primary)]">{s.site_name}</h3>
              <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">{s.status}</span>
            </div>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">{s.development_type} · {s.site_code}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
