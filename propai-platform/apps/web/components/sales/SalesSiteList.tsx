"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { salesGlobal } from "@/lib/salesApi";
import type { Locale } from "@/i18n/config";

interface Site { id: string; site_code: string; site_name: string; development_type: string; status: string }
// 개발 유형 — 코드(값)와 일반인이 이해하는 한글 표기
const DEV_TYPES: { value: string; label: string }[] = [
  { value: "APT", label: "아파트" },
  { value: "OFFICETEL", label: "오피스텔" },
  { value: "KNOWLEDGE_CENTER", label: "지식산업센터" },
  { value: "HOTEL", label: "생활숙박시설/호텔" },
  { value: "RETAIL", label: "상가" },
];
const DEV_LABEL: Record<string, string> = Object.fromEntries(DEV_TYPES.map((d) => [d.value, d.label]));
const STATUS_LABEL: Record<string, string> = { PREP: "준비중", OPEN: "분양중", CLOSED: "분양종료" };
const FIELD_CLS = "rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2.5 text-sm text-[var(--text-primary)]";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-semibold text-[var(--text-secondary)]">{label}</span>
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

  const createSite = async () => {
    if (!form.site_name || !form.project_id) { setErr("현장 이름과 프로젝트 번호를 입력하세요."); return; }
    setBusy(true); setErr("");
    try {
      await salesGlobal.post("/provision", form);
      setForm({ site_name: "", development_type: "APT", project_id: "" });
      load();
    } catch {
      setErr("현장을 만들지 못했습니다. 권한 또는 프로젝트 번호를 확인하세요.");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🏗️</span>
        <div>
          <h1 className="text-lg font-black text-[var(--text-primary)]">분양 현장 관리</h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">분양 현장을 새로 만들고 세대·분양가·계약·수수료·안내데스크를 한곳에서 운영합니다.</p>
        </div>
        <Link href={`/${locale}/sales/projection`}
          className="ml-auto rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]">
          시행사 요약 보기 →
        </Link>
      </div>

      {/* 새 현장 만들기 — 부각(강조 카드) */}
      <div className="rounded-2xl border-2 border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] p-6 shadow-[var(--shadow-md)]">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xl">➕</span>
          <h2 className="text-base font-black text-[var(--text-primary)]">새 분양 현장 만들기</h2>
        </div>
        <p className="mb-4 text-xs text-[var(--text-secondary)]">현장 이름과 유형을 정하고, 연결할 프로젝트 번호를 입력하면 현장이 자동 구성됩니다(세대·차수·데스크 등).</p>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="현장 이름">
            <input value={form.site_name} onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              placeholder="예: 강남 더샵 1차" className={FIELD_CLS + " w-56"} />
          </Field>
          <Field label="현장 유형">
            <select value={form.development_type} onChange={(e) => setForm({ ...form, development_type: e.target.value })}
              className={FIELD_CLS + " w-44"}>
              {DEV_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="연결할 프로젝트 번호">
            <input value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
              placeholder="프로젝트 번호(분석에서 만든 프로젝트)" className={FIELD_CLS + " w-80"} />
          </Field>
          <button onClick={createSite} disabled={busy}
            className="rounded-xl bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-black text-white shadow-[var(--shadow-sm)] transition hover:opacity-90 disabled:opacity-50">
            {busy ? "만드는 중…" : "현장 만들기"}
          </button>
        </div>
        {err && <p className="mt-2 text-xs font-semibold text-rose-400">{err}</p>}
      </div>

      {/* 현장 목록 */}
      <div>
        <h2 className="mb-3 text-sm font-bold text-[var(--text-secondary)]">분양 현장 목록 ({sites.length})</h2>
        {sites.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center">
            <p className="text-sm text-[var(--text-secondary)]">아직 등록된 현장이 없습니다.</p>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">위의 <b className="text-[var(--accent-strong)]">‘새 분양 현장 만들기’</b>에서 첫 현장을 만들어 보세요.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {sites.map((s) => (
              <Link key={s.id} href={`/${locale}/sales/${s.site_code}`}
                className="block rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)]">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-[var(--text-primary)]">{s.site_name}</h3>
                  <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">{STATUS_LABEL[s.status] ?? s.status}</span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">{DEV_LABEL[s.development_type] ?? s.development_type}</p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
