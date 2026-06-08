"use client";

/**
 * 고객 CRM — AI 가망고객 예측(등급 A/B/C·다음액션) + 고객 추가 + 상담 기록.
 * 백엔드: /sales/customers · /sales/consultations · GET /sales/crm/grade-suggestions
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi } from "@/lib/salesApi";
import { apiClient } from "@/lib/api-client";
import CustomerCardDrawer from "@/components/sales/CustomerCardDrawer";

interface Pred {
  customer_id: string; name?: string | null; phone?: string | null; status?: string;
  current_grade?: string | null; score: number; suggested_grade: string; reasons: string[]; next_action: string;
}

// Phase 1-D — 현장별/통합(union) 고객 목록 행. 필드명은 백엔드 my-customers 응답과 1:1로 맞춘다
// (customer_id·stage·site_name). 예전엔 id·status·sites[]로 잘못 가정해 카드 클릭·단계표시가 전부 깨졌었음.
interface MyCustomer {
  customer_id: string;
  name?: string | null;
  phone?: string | null;
  phone_masked?: string | null;
  stage?: string | null; // 단계(LEAD/CONSULT/…)
  grade?: string | null; // 온도(A/B/C)
  masked?: boolean;
  site_id?: string | null;
  site_name?: string | null; // 통합뷰에서 현장칩으로 표시
  role_in_site?: string | null;
}

const GRADE: Record<string, string> = {
  A: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  B: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  C: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};
const GLABEL: Record<string, string> = { A: "핫(A)", B: "웜(B)", C: "콜드(C)" };
const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

// 단계(status) 라벨 — 백엔드 _STAGES 정합(목록 필터·칩 표시용).
const STAGE_OPTS: { key: string; label: string }[] = [
  { key: "", label: "전체 단계" },
  { key: "LEAD", label: "리드" },
  { key: "CONSULT", label: "상담" },
  { key: "VISIT", label: "방문" },
  { key: "RESERVED", label: "예약" },
  { key: "SIGNED", label: "계약" },
  { key: "MIDDLE", label: "중도금" },
  { key: "BALANCE", label: "잔금" },
  { key: "LOST", label: "이탈" },
];
const STAGE_LABEL: Record<string, string> = { LEAD: "리드", CONSULT: "상담", VISIT: "방문", RESERVED: "예약", SIGNED: "계약", MIDDLE: "중도금", BALANCE: "잔금", LOST: "이탈" };

export default function CrmPanel({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [preds, setPreds] = useState<Pred[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  // Phase 1-D — 현장별/통합 토글 + 단계/키워드 필터 + 카드 드로어.
  const [scope, setScope] = useState<"site" | "all">("site");
  const [stage, setStage] = useState("");
  const [q, setQ] = useState("");
  const [customers, setCustomers] = useState<MyCustomer[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listErr, setListErr] = useState("");
  const [drawer, setDrawer] = useState<{ id: string; name?: string | null } | null>(null);

  const load = useCallback(() => {
    api.get<{ customers: Pred[] }>("/crm/grade-suggestions").then((r) => setPreds(r.customers || [])).catch(() => setPreds([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  // 고객 목록 로딩. scope=site → salesApi(X-Site-Code 헤더로 현장 자동 인식), scope=all → apiClient(전역토큰·union·마스킹).
  const loadCustomers = useCallback(() => {
    setListLoading(true);
    setListErr("");
    const qs = new URLSearchParams({ scope });
    // ※ 현장별(site)일 때는 site_id 쿼리를 보내지 않는다. 백엔드 site_id는 UUID만 받는데
    //   여기 siteCode는 사람이 읽는 코드(예: GANGNAM-1)라 보내면 422가 난다.
    //   대신 salesApi가 붙이는 X-Site-Code 헤더로 백엔드가 현장을 자동 인식한다.
    if (stage) qs.set("stage", stage);
    if (q.trim()) qs.set("q", q.trim());
    const path = `/sales/my-customers?${qs.toString()}`;
    const req =
      scope === "site"
        ? api.get<{ customers?: MyCustomer[]; items?: MyCustomer[] }>(`/my-customers?${qs.toString()}`)
        : apiClient.get<{ customers?: MyCustomer[]; items?: MyCustomer[] }>(path);
    req
      .then((r) => setCustomers(r.customers ?? r.items ?? []))
      .catch(() => {
        setCustomers([]);
        setListErr("고객 목록을 불러오지 못했습니다.");
      })
      .finally(() => setListLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode, scope, stage, q]);
  useEffect(() => { loadCustomers(); }, [loadCustomers]);

  const addCustomer = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try { await api.post("/customers", { name: name.trim(), phone_e164: phone.trim() || undefined, status: "LEAD" }); setName(""); setPhone(""); load(); }
    finally { setBusy(false); }
  };
  const applyGrade = async (p: Pred) => { await api.patch(`/customers/${p.customer_id}`, { grade: p.suggested_grade }); load(); };
  const logConsult = async (p: Pred) => {
    await api.post("/consultations", { customer_id: p.customer_id, consulted_at: new Date().toISOString(), channel: "VISIT", next_action: p.next_action });
    load();
  };
  const applyAll = async () => { for (const p of preds) await api.patch(`/customers/${p.customer_id}`, { grade: p.suggested_grade }); load(); };

  return (
    <div className="space-y-4">
      {/* 고객 추가 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">고객명</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="홍길동" className={`${fcls} min-w-[120px]`} /></label>
        <label className="flex flex-1 flex-col gap-1"><span className="text-[10px] text-[var(--text-tertiary)]">연락처</span>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="01012345678" className={`${fcls} min-w-[120px]`} /></label>
        <button onClick={addCustomer} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50">＋ 고객 추가</button>
      </div>

      {/* Phase 1-D — 현장별/통합 토글 + 단계/키워드 필터 + 고객 목록(카드 → 상세 드로어) */}
      <section className="space-y-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="sa-seg" role="tablist" aria-label="고객 범위">
            {(["site", "all"] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={scope === s}
                data-active={scope === s}
                onClick={() => setScope(s)}
                className="sa-seg__item"
              >
                {s === "site" ? "현장별" : "통합"}
              </button>
            ))}
          </div>
          <select value={stage} onChange={(e) => setStage(e.target.value)} className={fcls}>
            {STAGE_OPTS.map((o) => (
              <option key={o.key} value={o.key}>{o.label}</option>
            ))}
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이름·연락처 검색"
            className={`${fcls} min-w-[120px] flex-1`}
          />
          <button onClick={loadCustomers} className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)]">조회</button>
        </div>

        {scope === "all" && (
          <p className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-300">
            통합뷰는 요약·마스킹(010****5678)만 표시됩니다. 연락처 등 민감상세는 해당 현장 진입(2차인증) 후 열람하세요.
          </p>
        )}

        {listLoading ? (
          <div className="h-14 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--surface-strong)]" />
        ) : listErr ? (
          <p className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-300">{listErr}</p>
        ) : customers.length === 0 ? (
          <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-4 text-xs text-[var(--text-secondary)]">고객이 없습니다.</p>
        ) : (
          <ul className="space-y-2">
            {customers.map((c) => {
              const masked = c.masked || scope === "all";
              const clickable = !masked && !!c.customer_id;
              return (
                <li key={c.customer_id}>
                  <button
                    type="button"
                    disabled={!clickable}
                    onClick={() => clickable && setDrawer({ id: c.customer_id, name: c.name })}
                    className={`flex w-full flex-wrap items-center gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-left transition ${
                      clickable ? "hover:border-[var(--accent-strong)]" : "cursor-default"
                    }`}
                  >
                    {c.grade && (
                      <span className={`rounded-full border px-2 py-0.5 text-[10px] font-black ${GRADE[c.grade] ?? ""}`}>
                        {GLABEL[c.grade] ?? c.grade}
                      </span>
                    )}
                    <span className="font-bold text-[var(--text-primary)]">{c.name || "-"}</span>
                    <span className="text-xs text-[var(--text-tertiary)]">{masked ? (c.phone_masked || "010****") : (c.phone || "")}</span>
                    {c.stage && (
                      <span className="rounded-md bg-[var(--surface-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
                        {STAGE_LABEL[c.stage] ?? c.stage}
                      </span>
                    )}
                    {scope === "all" && c.site_name && (
                      <span className="rounded-md bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
                        {c.site_name}
                      </span>
                    )}
                    {clickable && <span className="ml-auto text-[11px] font-bold text-[var(--accent-strong)]">상세 →</span>}
                    {masked && <span className="ml-auto text-[10px] text-[var(--text-hint)]">현장 진입 후 열람</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <div className="flex items-center justify-between">
        <h2 className="font-black text-[var(--text-primary)]">🤖 AI 가망고객 예측 ({preds.length})</h2>
        <div className="flex gap-2">
          <button onClick={load} className="rounded-lg border border-[var(--line-strong)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)]">재예측</button>
          {preds.length > 0 && <button onClick={applyAll} className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white">등급 일괄 반영</button>}
        </div>
      </div>

      {preds.length === 0 ? (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">고객이 없습니다. 위에서 추가하거나 데스크 체크인으로 유입됩니다.</p>
      ) : (
        <div className="space-y-2">
          {preds.map((p) => (
            <div key={p.customer_id} className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-black ${GRADE[p.suggested_grade] ?? ""}`}>{GLABEL[p.suggested_grade] ?? p.suggested_grade}</span>
              <span className="font-bold text-[var(--text-primary)]">{p.name || "-"}</span>
              {p.phone && <span className="text-xs text-[var(--text-tertiary)]">{p.phone}</span>}
              <span className="rounded-md bg-[var(--surface-strong)] px-2 py-0.5 text-xs font-bold text-[var(--accent-strong)]">{p.score}점</span>
              <span className="w-full text-xs text-[var(--text-secondary)] sm:w-auto sm:flex-1">
                {p.reasons.join(" · ") || "활동 이력 없음"} → <b className="text-[var(--text-primary)]">{p.next_action}</b>
              </span>
              <button onClick={() => logConsult(p)} className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)]">상담 기록</button>
              <button onClick={() => applyGrade(p)} className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-bold text-white">
                등급 반영{p.current_grade ? `(현:${p.current_grade})` : ""}
              </button>
            </div>
          ))}
        </div>
      )}
      <p className="text-[11px] text-[var(--text-hint)]">예측 가중: 상담횟수·통화시간·마케팅수신동의·최근상담·방문이력 → A(핫)/B(웜)/C(콜드). 상담 기록 시 점수·등급이 갱신됩니다.</p>

      {drawer && (
        <CustomerCardDrawer
          siteCode={siteCode}
          customerId={drawer.id}
          customerName={drawer.name}
          onClose={() => setDrawer(null)}
          onChanged={() => { loadCustomers(); load(); }}
        />
      )}
    </div>
  );
}
