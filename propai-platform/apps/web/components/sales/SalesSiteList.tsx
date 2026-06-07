"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { salesGlobal } from "@/lib/salesApi";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";
import type { Locale } from "@/i18n/config";

type DevType = { value: string; label: string };

interface Site { id: string; site_code: string; site_name: string; development_type: string; status: string }
interface Project { id: string; name: string }
// 개발 유형 — 코드(값)와 일반인이 이해하는 한글 표기
// 기본 현장유형(관리자 편집 목록 미설정 시 폴백). 운영값은 /admin/option-lists/sales_site_types.
const DEFAULT_DEV_TYPES: DevType[] = [
  { value: "APT", label: "아파트" },
  { value: "OFFICETEL", label: "오피스텔" },
  { value: "KNOWLEDGE_CENTER", label: "지식산업센터" },
  { value: "HOTEL", label: "생활숙박시설/호텔" },
  { value: "RETAIL", label: "상가" },
];
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
  const [devTypes, setDevTypes] = useState<DevType[]>(DEFAULT_DEV_TYPES);
  const [form, setForm] = useState({ site_name: "", development_type: "APT", project_id: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fee, setFee] = useState<number | null>(null); // 분양현장 생성 사용료(관리자 책정)

  const devLabel = (v: string) => devTypes.find((d) => d.value === v)?.label ?? v;

  // 연결할 프로젝트: 프로젝트 목록 단일출처(백엔드 동기화 스토어) 사용 — 드롭다운/프로젝트관리와 일치
  const storeProjects = useProjectStore((s) => s.projects);
  const syncFromBackend = useProjectStore((s) => s.syncFromBackend);
  const projects: Project[] = storeProjects.map((p) => ({ id: p.id, name: p.name || p.address || "(이름 없음)" }));

  const load = () => salesGlobal.get<Site[]>("/sites").then(setSites).catch(() => setSites([]));
  useEffect(() => {
    load();
    void syncFromBackend();
    // 현장유형: 관리자 편집 목록 로드(미설정 시 기본값 유지)
    apiClient
      .get<{ items?: DevType[] }>("/admin/option-lists/sales_site_types", { useMock: false })
      .then((r) => { if (r.items && r.items?.length) setDevTypes(r.items); })
      .catch(() => {});
    // 분양현장 생성 사용료 미리보기(관리자 책정 금액)
    apiClient
      .post<{ fee_krw?: number }>("/billing/preview-charge", { body: { action: "sales_provision" }, useMock: false })
      .then((r) => setFee(typeof r.fee_krw === "number" ? r.fee_krw : null))
      .catch(() => setFee(null));
  }, [syncFromBackend]);

  const createSite = async () => {
    if (!form.site_name || !form.project_id) { setErr("현장 이름과 프로젝트 번호를 입력하세요."); return; }
    setBusy(true); setErr("");
    try {
      await salesGlobal.post("/provision", form);
      setForm({ site_name: "", development_type: "APT", project_id: "" });
      load();
    } catch (e) {
      // 백엔드 detail(권한·프로젝트 번호 등)을 그대로 노출 — 원인 진단 가능
      let msg = "현장을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.";
      if (e instanceof ApiClientError) {
        const detail = (e.payload as { detail?: string } | null)?.detail;
        if (typeof detail === "string" && detail) msg = detail;
        else if (e.status === 403) msg = "분양현장 생성 권한이 없습니다.";
        else if (e.status === 400) msg = "현장 이름과 저장된 프로젝트를 확인하세요.";
      }
      setErr(msg);
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <span className="text-2xl">🏗️</span>
        <div>
          <h1 className="text-lg font-black text-[var(--text-primary)]">분양 현장 관리</h1>
          <p className="mt-0.5 text-xs text-[var(--text-secondary)]">시행·관리자 경로입니다. 현장을 만들고 설정·요약을 운영합니다. 현장 직원처럼 역할별 앱 화면을 쓰려면 <b className="text-[var(--accent-strong)]">‘현장앱 진입’</b>(2차 비밀번호)을 사용하세요.</p>
        </div>
        <Link href={`/${locale}/sales/sites`}
          className="ml-auto rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-black text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]">
          내 현장(앱) →
        </Link>
        <Link href={`/${locale}/sales/projection`}
          className="rounded-xl border border-[var(--accent-strong)] px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]">
          시행사 요약 보기 →
        </Link>
      </div>

      {/* 새 현장 만들기 — 부각(강조 카드) */}
      <div className="rounded-2xl border-2 border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] p-6 shadow-[var(--shadow-md)]">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xl">➕</span>
          <h2 className="text-base font-black text-[var(--text-primary)]">새 분양 현장 만들기</h2>
        </div>
        <p className="mb-1 text-xs text-[var(--text-secondary)]">현장 이름과 유형을 정하고, 연결할 프로젝트를 선택하면 현장이 자동 구성됩니다(세대·차수·데스크 등).</p>
        {fee != null && fee > 0 && (
          <p className="mb-4 text-xs font-semibold text-[var(--accent-strong)]">
            💳 현장 생성 시 사용료 <b>{fee.toLocaleString()}원</b>이 부과됩니다(관리자 책정).
          </p>
        )}
        {(fee == null || fee === 0) && <div className="mb-4" />}
        <div className="flex flex-wrap items-end gap-3">
          <Field label="현장 이름">
            <input value={form.site_name} onChange={(e) => setForm({ ...form, site_name: e.target.value })}
              placeholder="예: 강남 더샵 1차" className={FIELD_CLS + " w-56"} />
          </Field>
          <Field label="현장 유형">
            <select value={form.development_type} onChange={(e) => setForm({ ...form, development_type: e.target.value })}
              className={FIELD_CLS + " w-44"}>
              {devTypes.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="연결할 프로젝트">
            {projects.length > 0 ? (
              <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}
                className={FIELD_CLS + " w-72"}>
                <option value="">프로젝트 선택…</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : (
              <div className={FIELD_CLS + " w-72 flex items-center text-[var(--text-tertiary)]"}>
                <Link href={`/${locale}/projects`} className="text-[var(--accent-strong)] underline">프로젝트 관리</Link>
                <span className="ml-1">에서 먼저 프로젝트를 만드세요</span>
              </div>
            )}
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
              <div key={s.id}
                className="flex flex-col rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)]">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-[var(--text-primary)]">{s.site_name}</h3>
                  <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">{STATUS_LABEL[s.status] ?? s.status}</span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">{devLabel(s.development_type)}</p>
                {/* 관리(설정·요약) vs 현장앱 진입(2차비번 게이트) 명확 분리 */}
                <div className="mt-3 flex items-center gap-2">
                  <Link href={`/${locale}/sales/${s.site_code}`}
                    className="flex-1 rounded-lg border border-[var(--line-strong)] px-3 py-2 text-center text-xs font-bold text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]">
                    🛠 관리·설정
                  </Link>
                  {/* 현장앱 진입은 UUID(s.id)로 2차비번 게이트(/sales/sites/{id}/workspace)로 이동 */}
                  <Link href={`/${locale}/sales/sites/${s.id}/workspace`}
                    className="flex-1 rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-center text-xs font-black text-white transition hover:opacity-90">
                    🔐 현장앱 진입
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
