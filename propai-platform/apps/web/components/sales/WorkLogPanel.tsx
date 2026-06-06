"use client";

/**
 * Phase 1-D — 업무일지.
 *   · POST /sales/work-logs {log_date, summary, activities[], site_id?} → 작성(활동→고객 history 연계)
 *   · GET  /sales/work-logs?from_=&to=&site_id=                        → 목록(★파라미터명 from_)
 *   · GET  /sales/work-logs/summary?period=&site_id=                  → 실적집계(상담/방문/계약/메시지/일지수)
 *
 * 현장 컨텍스트: salesApi(siteCode)로 호출(X-Site-Token 자동첨부). site_id는 현재 현장(siteCode) 고정.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { salesApi } from "@/lib/salesApi";

interface Activity {
  customer_id?: string | null;
  kind?: string; // consult | visit | stage | note | message
  content?: string;
}

interface WorkLog {
  id?: string;
  log_date?: string | null;
  summary?: string | null;
  activities?: Activity[] | null;
  created_at?: string | null;
  author?: string | null;
}

interface SummaryResp {
  period?: string;
  consult?: number;
  visit?: number;
  contracts?: number;
  messages?: number;
  work_logs?: number;
  total?: number;
  by_site?: Record<string, unknown>;
}

const fcls =
  "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

const PERIODS: { key: string; label: string }[] = [
  { key: "day", label: "오늘" },
  { key: "week", label: "이번 주" },
  { key: "month", label: "이번 달" },
  { key: "quarter", label: "분기" },
  { key: "year", label: "연간" },
];

const ACT_KINDS: { key: string; label: string }[] = [
  { key: "consult", label: "상담" },
  { key: "visit", label: "방문" },
  { key: "note", label: "메모" },
  { key: "stage", label: "단계변경" },
];

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function WorkLogPanel({ siteCode }: { siteCode: string }) {
  const api = useMemo(() => salesApi(siteCode), [siteCode]);

  const [logs, setLogs] = useState<WorkLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const [summary, setSummary] = useState<SummaryResp | null>(null);
  const [period, setPeriod] = useState("month");

  // 작성 폼
  const [logDate, setLogDate] = useState(todayStr());
  const [logSummary, setLogSummary] = useState("");
  const [activities, setActivities] = useState<Activity[]>([{ kind: "consult", content: "" }]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ tone: "ok" | "warn" | "err"; text: string } | null>(null);

  // 기간 필터(목록)
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const loadLogs = useCallback(() => {
    setLoading(true);
    const qs = new URLSearchParams();
    if (from) qs.set("from_", from);
    if (to) qs.set("to", to);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    api
      .get<{ work_logs?: WorkLog[]; items?: WorkLog[] }>(`/work-logs${suffix}`)
      .then((r) => {
        setLogs(r.work_logs ?? r.items ?? []);
        setErr("");
      })
      .catch(() => setErr("업무일지를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [api, from, to]);

  const loadSummary = useCallback(() => {
    api
      .get<SummaryResp>(`/work-logs/summary?period=${encodeURIComponent(period)}`)
      .then((r) => setSummary(r))
      .catch(() => setSummary(null));
  }, [api, period]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);
  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const setActivity = (i: number, patch: Partial<Activity>) =>
    setActivities((prev) => prev.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  const addActivity = () => setActivities((prev) => [...prev, { kind: "consult", content: "" }]);
  const removeActivity = (i: number) => setActivities((prev) => prev.filter((_, idx) => idx !== i));

  const submit = async () => {
    if (!logSummary.trim()) {
      setToast({ tone: "warn", text: "업무 요약을 입력하세요." });
      return;
    }
    setSaving(true);
    try {
      const acts = activities
        .filter((a) => (a.content ?? "").trim())
        .map((a) => ({ kind: a.kind, content: (a.content ?? "").trim(), customer_id: a.customer_id || undefined }));
      await api.post("/work-logs", {
        log_date: logDate,
        summary: logSummary.trim(),
        activities: acts,
      });
      setLogSummary("");
      setActivities([{ kind: "consult", content: "" }]);
      setToast({ tone: "ok", text: "업무일지가 저장되었습니다." });
      loadLogs();
      loadSummary();
    } catch {
      setToast({ tone: "err", text: "저장에 실패했습니다." });
    } finally {
      setSaving(false);
    }
  };

  const toastCls =
    toast?.tone === "ok"
      ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
      : toast?.tone === "warn"
        ? "border-amber-400/40 bg-amber-500/10 text-amber-300"
        : "border-rose-400/40 bg-rose-500/10 text-rose-300";

  const cards: { label: string; value: number; cls: string }[] = [
    { label: "상담", value: summary?.consult ?? 0, cls: "text-sky-300" },
    { label: "방문", value: summary?.visit ?? 0, cls: "text-emerald-300" },
    { label: "계약", value: summary?.contracts ?? 0, cls: "text-rose-300" },
    { label: "메시지", value: summary?.messages ?? 0, cls: "text-amber-300" },
    { label: "일지", value: summary?.work_logs ?? 0, cls: "text-violet-300" },
  ];

  return (
    <div className="space-y-5">
      {toast && (
        <div className={`rounded-lg border px-3 py-2 text-xs font-semibold ${toastCls}`} role="status">
          {toast.text}
        </div>
      )}

      {/* 실적 요약 */}
      <section className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-black text-[var(--text-primary)]">📊 실적 요약</h2>
          <div className="flex flex-wrap gap-1.5">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                className={`rounded-lg px-2.5 py-1 text-xs font-bold transition ${
                  period === p.key
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line)] text-[var(--text-secondary)]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {cards.map((c) => (
            <div key={c.label} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-center">
              <div className={`text-xl font-black ${c.cls}`}>{c.value}</div>
              <div className="text-[11px] text-[var(--text-tertiary)]">{c.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 일지 작성 */}
      <section className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
        <h2 className="mb-2 font-black text-[var(--text-primary)]">✍️ 업무일지 작성</h2>
        <div className="mb-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] text-[var(--text-tertiary)]">일자</span>
            <input type="date" value={logDate} onChange={(e) => setLogDate(e.target.value)} className={fcls} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className="text-[10px] text-[var(--text-tertiary)]">업무 요약</span>
            <input
              value={logSummary}
              onChange={(e) => setLogSummary(e.target.value)}
              placeholder="오늘 업무 요약"
              className={`${fcls} min-w-[160px]`}
            />
          </label>
        </div>

        <div className="space-y-2">
          <span className="text-[10px] text-[var(--text-tertiary)]">활동(고객 연계)</span>
          {activities.map((a, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select value={a.kind} onChange={(e) => setActivity(i, { kind: e.target.value })} className={fcls}>
                {ACT_KINDS.map((k) => (
                  <option key={k.key} value={k.key}>
                    {k.label}
                  </option>
                ))}
              </select>
              <input
                value={a.content ?? ""}
                onChange={(e) => setActivity(i, { content: e.target.value })}
                placeholder="활동 내용"
                className={`${fcls} min-w-[140px] flex-1`}
              />
              <input
                value={a.customer_id ?? ""}
                onChange={(e) => setActivity(i, { customer_id: e.target.value })}
                placeholder="고객 ID(선택)"
                className={`${fcls} w-32`}
              />
              {activities.length > 1 && (
                <button
                  onClick={() => removeActivity(i)}
                  className="rounded-lg border border-[var(--line-strong)] px-2 py-1.5 text-xs font-bold text-[var(--text-secondary)]"
                >
                  −
                </button>
              )}
            </div>
          ))}
          <button
            onClick={addActivity}
            className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1 text-xs font-bold text-[var(--text-secondary)]"
          >
            ＋ 활동 추가
          </button>
        </div>

        <button
          onClick={submit}
          disabled={saving}
          className="mt-3 w-full rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-black text-white disabled:opacity-50"
        >
          {saving ? "저장 중…" : "업무일지 저장"}
        </button>
      </section>

      {/* 일지 목록 */}
      <section className="space-y-2">
        <div className="flex flex-wrap items-end gap-2">
          <h2 className="font-black text-[var(--text-primary)]">🗂 업무일지 목록</h2>
          <div className="ml-auto flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[var(--text-tertiary)]">시작일</span>
              <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={fcls} />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[var(--text-tertiary)]">종료일</span>
              <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={fcls} />
            </label>
            <button
              onClick={loadLogs}
              className="rounded-lg border border-[var(--line-strong)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)]"
            >
              조회
            </button>
          </div>
        </div>

        {loading ? (
          <div className="h-16 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]" />
        ) : err ? (
          <p className="rounded-xl border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-300">
            {err}
          </p>
        ) : logs.length === 0 ? (
          <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-4 text-xs text-[var(--text-secondary)]">
            업무일지가 없습니다. 위에서 작성하세요.
          </p>
        ) : (
          <ul className="space-y-2">
            {logs.map((l, i) => (
              <li key={l.id ?? i} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-black text-[var(--accent-strong)]">{l.log_date ?? "-"}</span>
                  {l.author && <span className="text-[10px] text-[var(--text-hint)]">{l.author}</span>}
                </div>
                {l.summary && <p className="whitespace-pre-wrap text-sm text-[var(--text-primary)]">{l.summary}</p>}
                {Array.isArray(l.activities) && l.activities.length > 0 && (
                  <ul className="mt-1.5 space-y-1">
                    {l.activities.map((a, j) => (
                      <li key={j} className="text-[11px] text-[var(--text-secondary)]">
                        · {ACT_KINDS.find((k) => k.key === a.kind)?.label ?? a.kind}
                        {a.content ? ` — ${a.content}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
