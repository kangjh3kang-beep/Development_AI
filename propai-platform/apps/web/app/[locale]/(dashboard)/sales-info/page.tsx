"use client";

/**
 * 분양정보 — 사업검토 메뉴.
 * 전국/시도별 분양·청약 공고 열람(상태칩) + 단지 상세(주택형·분양가·일정) +
 * 나의 관심지역 모니터링(별도 분류 피드) + 알림설정(인앱/SMS/카카오 알림톡).
 * 데이터: 청약홈(한국부동산원) 분양정보 API. 무자료 시 정직 표기(목업 없음).
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

/* eslint-disable @typescript-eslint/no-explicit-any */

type Item = {
  house_manage_no: string; pblanc_no: string; name: string; address: string;
  area_name: string; total_households: string; recruit_date: string;
  receipt_begin: string; receipt_end: string; developer: string; url: string;
  status: string;
};
type ListResp = { available: boolean; area?: string; count?: number; items: Item[]; note?: string };
type Interest = {
  id: string; label: string; area: string | null; sigungu: string | null;
  keyword: string | null; min_households: number; baseline_done: boolean;
};
type FeedItem = {
  id: string; title: string; body: string; payload: any; is_read: boolean;
  channels: string[]; created_at: string;
};
type Prefs = { phone: string; sms_enabled: boolean; kakao_enabled: boolean; inapp_enabled: boolean };

const STATUS_STYLE: Record<string, string> = {
  접수중: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  접수예정: "bg-sky-500/15 text-sky-400 border-sky-500/30",
  마감: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  미정: "bg-amber-500/15 text-amber-400 border-amber-500/30",
};
const eok = (man?: number | null) => {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const e = Math.floor(man / 10000), r = Math.round((man % 10000) / 1000);
    return r > 0 ? `${e}.${r}억` : `${e}억`;
  }
  return `${man.toLocaleString()}만`;
};

export default function SalesInfoPage() {
  const [tab, setTab] = useState<"browse" | "monitor">("browse");
  const [areas, setAreas] = useState<string[]>([]);
  const [area, setArea] = useState<string>("전국");
  const [list, setList] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    apiClient.get<{ areas: string[] }>("/presale/areas", { useMock: false })
      .then((r) => setAreas(["전국", ...(r.areas || [])])).catch(() => setAreas(["전국"]));
  }, []);

  const loadList = useCallback(async (a: string) => {
    setLoading(true);
    try {
      const q = a && a !== "전국" ? `?area=${encodeURIComponent(a)}&months_back=6` : "?months_back=6";
      const r = await apiClient.get<ListResp>(`/presale/list${q}`, { useMock: false, timeoutMs: 60000 });
      setList(r);
    } catch { setList({ available: false, items: [], note: "분양정보 조회 실패" }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (tab === "browse") loadList(area); }, [area, tab, loadList]);

  const openDetail = async (it: Item) => {
    setDetail({ _loading: true, name: it.name }); setDetailLoading(true);
    try {
      const d = await apiClient.get<any>(
        `/presale/detail?house_manage_no=${encodeURIComponent(it.house_manage_no)}&pblanc_no=${encodeURIComponent(it.pblanc_no)}`,
        { useMock: false, timeoutMs: 60000 });
      setDetail({ ...it, ...d });
    } catch { setDetail({ ...it, available: false, note: "상세 조회 실패" }); }
    finally { setDetailLoading(false); }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-5 p-1 pb-20">
      <header className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" /><i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10">
          <span className="cc-meta">사업검토 · 분양/청약</span>
          <h1 className="text-2xl font-black text-[var(--text-primary)]">분양정보 <span className="text-[var(--accent-strong)]">_</span></h1>
          <p className="text-sm text-[var(--text-secondary)]">전국·시도별 분양/청약 공고를 확인하고, 관심지역을 등록하면 신규·접수·마감을 모니터링해 알려드립니다.</p>
        </div>
      </header>

      <div className="flex gap-2">
        {([["browse", "분양 공고 열람"], ["monitor", "나의 관심지역 모니터링"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`rounded-xl px-4 py-2 text-sm font-bold transition-colors ${tab === k ? "bg-[var(--accent-strong)] text-white" : "border border-[var(--line-strong)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === "browse" && (
        <>
          <div className="flex flex-wrap gap-1.5">
            {areas.map((a) => (
              <button key={a} onClick={() => setArea(a)}
                className={`rounded-full border px-3 py-1.5 text-xs font-bold transition-all ${area === a ? "border-transparent bg-[var(--accent-strong)] text-white" : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"}`}>
                {a}
              </button>
            ))}
          </div>

          {loading && <div className="py-10 text-center text-sm text-[var(--text-secondary)]">분양정보 불러오는 중…</div>}

          {!loading && list && !list.available && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-[var(--text-secondary)]">
              ⚠️ {list.note || "분양정보를 불러올 수 없습니다."} <span className="text-[var(--text-hint)]">(청약홈 분양정보 API 활용신청·키 설정 후 표시됩니다)</span>
            </div>
          )}

          {!loading && list?.available && (
            <>
              <p className="text-xs text-[var(--text-hint)]">{list.area} · 총 {list.count}건 (최근 6개월 모집공고)</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {list.items.map((it) => (
                  <button key={`${it.house_manage_no}:${it.pblanc_no}`} onClick={() => openDetail(it)}
                    className="cc-panel text-left transition-transform hover:-translate-y-0.5">
                    <div className="cc-panel__body space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="text-sm font-bold text-[var(--text-primary)] leading-snug">{it.name}</h3>
                        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${STATUS_STYLE[it.status] || STATUS_STYLE.미정}`}>{it.status}</span>
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] line-clamp-1">{it.area_name} · {it.address}</p>
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-[var(--text-hint)]">
                        {it.total_households && <span>공급 {it.total_households}세대</span>}
                        {it.receipt_begin && <span>접수 {it.receipt_begin}~{it.receipt_end}</span>}
                        {it.developer && <span className="line-clamp-1">{it.developer}</span>}
                      </div>
                    </div>
                  </button>
                ))}
                {list.items.length === 0 && <p className="col-span-2 py-8 text-center text-sm text-[var(--text-secondary)]">해당 지역 최근 분양 공고가 없습니다.</p>}
              </div>
            </>
          )}
        </>
      )}

      {tab === "monitor" && <MonitorTab />}

      {detail && (
        <DetailModal detail={detail} loading={detailLoading} onClose={() => setDetail(null)} />
      )}
    </div>
  );
}

function DetailModal({ detail, loading, onClose }: { detail: any; loading: boolean; onClose: () => void }) {
  const rows: Array<[string, string]> = [
    ["모집공고일", detail.recruit_date], ["특별공급 접수", detail.special_date],
    ["일반 청약접수", detail.receipt_begin && `${detail.receipt_begin} ~ ${detail.receipt_end}`],
    ["당첨자 발표", detail.winner_date],
    ["계약기간", detail.contract_begin && `${detail.contract_begin} ~ ${detail.contract_end}`],
    ["입주예정", detail.move_in], ["시행사", detail.developer], ["시공사", detail.constructor],
    ["문의", detail.tel],
  ];
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-black text-[var(--text-primary)]">{detail.name}</h2>
            <p className="text-xs text-[var(--text-secondary)]">{detail.area_name} · {detail.address}</p>
          </div>
          <button onClick={onClose} className="rounded-lg border border-[var(--line-strong)] px-3 py-1 text-sm text-[var(--text-secondary)]">닫기</button>
        </div>

        {loading && <div className="py-10 text-center text-sm text-[var(--text-secondary)]">상세 불러오는 중…</div>}

        {!loading && detail.available === false && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-[var(--text-secondary)]">⚠️ {detail.note || "상세 정보를 불러올 수 없습니다."}</div>
        )}

        {!loading && detail.available !== false && (
          <div className="space-y-4">
            {(detail.price_min_man || detail.price_max_man) && (
              <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-4 py-3">
                <p className="text-xs text-[var(--text-secondary)]">분양가(주택형별 최고분양가 기준)</p>
                <p className="text-lg font-black text-[var(--accent-strong)]">{eok(detail.price_min_man)} ~ {eok(detail.price_max_man)}</p>
              </div>
            )}
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {rows.filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="text-sm"><span className="text-[var(--text-hint)]">{k}</span><br /><span className="font-medium text-[var(--text-primary)]">{v}</span></div>
              ))}
            </div>
            {Array.isArray(detail.models) && detail.models.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-[10px] uppercase tracking-wide text-[var(--text-hint)]">
                    <th className="pb-1">주택형</th><th className="pb-1 text-right">공급면적</th><th className="pb-1 text-right">세대</th><th className="pb-1 text-right">분양가(최고)</th>
                  </tr></thead>
                  <tbody>
                    {detail.models.map((m: any, i: number) => (
                      <tr key={i} className="border-t border-[var(--line)]">
                        <td className="py-1.5 font-medium text-[var(--text-primary)]">{m.house_ty}</td>
                        <td className="py-1.5 text-right text-[var(--text-secondary)]">{m.supply_area_m2}㎡</td>
                        <td className="py-1.5 text-right text-[var(--text-secondary)]">{m.supply_households}</td>
                        <td className="py-1.5 text-right cc-num font-bold text-[var(--text-primary)]">{eok(m.price_man)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {detail.url && <a href={detail.url} target="_blank" rel="noopener noreferrer" className="inline-block rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white">청약홈 공고 보기 ↗</a>}
          </div>
        )}
      </div>
    </div>
  );
}

function MonitorTab() {
  const [interests, setInterests] = useState<Interest[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [prefs, setPrefs] = useState<Prefs>({ phone: "", sms_enabled: false, kakao_enabled: false, inapp_enabled: true });
  const [form, setForm] = useState({ label: "", area: "", sigungu: "", keyword: "", min_households: 0 });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [areas, setAreas] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const [i, f, p] = await Promise.all([
        apiClient.get<{ interests: Interest[] }>("/presale/interests", { useMock: false }),
        apiClient.get<{ items: FeedItem[] }>("/presale/monitor/feed", { useMock: false }),
        apiClient.get<Prefs>("/presale/notify/prefs", { useMock: false }),
      ]);
      setInterests(i.interests || []); setFeed(f.items || []); setPrefs(p);
    } catch { setMsg("모니터링 정보를 불러오지 못했습니다(로그인 필요)."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { apiClient.get<{ areas: string[] }>("/presale/areas", { useMock: false }).then((r) => setAreas(r.areas || [])).catch(() => {}); }, []);

  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true); setMsg("");
    try { await fn(); setMsg(ok); await load(); }
    catch { setMsg("처리 실패 — 입력/권한을 확인하세요."); }
    finally { setBusy(false); }
  };
  const addInterest = () => act(() => apiClient.post("/presale/interests", { body: { ...form, area: form.area || null }, useMock: false }), "관심지역이 등록되었습니다. 신규·접수·마감 시 알려드립니다.").then(() => setForm({ label: "", area: "", sigungu: "", keyword: "", min_households: 0 }));
  const removeInterest = (id: string) => act(() => apiClient.delete(`/presale/interests/${id}`, { useMock: false }), "삭제되었습니다.");
  const runNow = () => act(() => apiClient.post("/presale/monitor/run-now", { useMock: false }), "지금 점검을 완료했습니다.");
  const savePrefs = () => act(() => apiClient.put("/presale/notify/prefs", { body: prefs, useMock: false }), "알림 설정이 저장되었습니다.");
  const testNotify = () => act(() => apiClient.post("/presale/notify/test", { useMock: false }), "테스트 알림을 발송했습니다(인앱 + 설정 채널).");
  const markRead = () => act(() => apiClient.post("/presale/monitor/read", { body: {}, useMock: false }), "모두 읽음 처리했습니다.");

  return (
    <div className="space-y-5">
      {msg && <div className="rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">{msg}</div>}

      {/* 관심지역 등록 */}
      <section className="cc-panel"><div className="cc-panel__body space-y-3">
        <h2 className="text-sm font-bold text-[var(--text-primary)]">관심지역 등록</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="관심지역 이름(예: 분당 신규)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <select value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            <option value="">전국</option>
            {areas.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <input value={form.sigungu} onChange={(e) => setForm({ ...form, sigungu: e.target.value })} placeholder="시군구/동 키워드(선택, 예: 분당구)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <input value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })} placeholder="단지명/시행사 키워드(선택)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <input type="number" value={form.min_households || ""} onChange={(e) => setForm({ ...form, min_households: Number(e.target.value || 0) })} placeholder="최소 공급세대(선택)" className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
          <button onClick={addInterest} disabled={busy || !form.label.trim()} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">등록</button>
        </div>
      </div></section>

      {/* 관심지역 목록 */}
      {interests.length > 0 && (
        <section className="cc-panel"><div className="cc-panel__body space-y-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-[var(--text-primary)]">모니터링 중 ({interests.length})</h2>
            <button onClick={runNow} disabled={busy} className="rounded-md border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-3 py-1 text-xs font-bold text-[var(--accent-strong)] disabled:opacity-50">지금 점검</button>
          </div>
          {interests.map((it) => (
            <div key={it.id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--line)] px-3 py-2">
              <div className="min-w-0 text-sm">
                <span className="font-medium text-[var(--text-primary)]">{it.label}</span>
                <span className="ml-2 text-xs text-[var(--text-hint)]">{[it.area || "전국", it.sigungu, it.keyword, it.min_households ? `${it.min_households}세대+` : ""].filter(Boolean).join(" · ")}</span>
              </div>
              <button onClick={() => removeInterest(it.id)} disabled={busy} className="shrink-0 rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-bold text-rose-400 disabled:opacity-50">삭제</button>
            </div>
          ))}
        </div></section>
      )}

      {/* 모니터링 피드 */}
      <section className="cc-panel"><div className="cc-panel__body space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[var(--text-primary)]">특이점 알림 피드</h2>
          {feed.length > 0 && <button onClick={markRead} disabled={busy} className="text-xs font-bold text-[var(--text-hint)] hover:text-[var(--text-secondary)]">모두 읽음</button>}
        </div>
        {feed.length === 0 && <p className="py-6 text-center text-sm text-[var(--text-secondary)]">아직 알림이 없습니다. 관심지역을 등록하면 신규·접수·마감 특이점을 여기에 모아드립니다.</p>}
        {feed.map((f) => (
          <div key={f.id} className={`rounded-lg border px-3 py-2 ${f.is_read ? "border-[var(--line)] opacity-70" : "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)]/40"}`}>
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-bold text-[var(--text-primary)]">{f.title}</p>
              <div className="flex shrink-0 gap-1">
                {f.channels?.filter((c) => c !== "inapp").map((c) => <span key={c} className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-hint)]">{c === "kakao" ? "톡" : c === "sms" ? "문자" : c}</span>)}
              </div>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">{f.body}</p>
            {f.payload?.url && <a href={f.payload.url} target="_blank" rel="noopener noreferrer" className="text-[11px] font-bold text-[var(--accent-strong)]">공고 보기 ↗</a>}
          </div>
        ))}
      </div></section>

      {/* 알림 설정 */}
      <section className="cc-panel"><div className="cc-panel__body space-y-3">
        <h2 className="text-sm font-bold text-[var(--text-primary)]">알림 설정</h2>
        <input value={prefs.phone} onChange={(e) => setPrefs({ ...prefs, phone: e.target.value })} placeholder="휴대폰 번호(문자/알림톡 수신용, 예: 01012345678)" className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)]" />
        <div className="flex flex-wrap gap-3 text-sm">
          {([["inapp_enabled", "인앱 알림"], ["kakao_enabled", "카카오 알림톡"], ["sms_enabled", "문자(SMS)"]] as const).map(([k, label]) => (
            <label key={k} className="flex items-center gap-1.5 text-[var(--text-secondary)]">
              <input type="checkbox" checked={(prefs as any)[k]} onChange={(e) => setPrefs({ ...prefs, [k]: e.target.checked })} /> {label}
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={savePrefs} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50">설정 저장</button>
          <button onClick={testNotify} disabled={busy} className="rounded-lg border border-[var(--line-strong)] px-4 py-2 text-sm font-bold text-[var(--text-secondary)] disabled:opacity-50">테스트 발송</button>
        </div>
        <p className="text-[10px] text-[var(--text-hint)]">※ 문자·알림톡은 발송사 연동(관리자 설정) 후 동작합니다. 미연동 시 인앱 알림만 적재됩니다.</p>
      </div></section>
    </div>
  );
}
