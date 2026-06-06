"use client";

/**
 * Phase 1-C — 세대배치도 실시간 동호수 선점 보드.
 *
 * 백엔드 계약(_workspace/61, prefix /api/v1/sales, 헤더 X-Site-Code+X-Site-Token+Bearer):
 *   - GET  /sales/units/board                  → {counts, units:[{unit_id,dong,ho,floor,line,status,
 *                                                 expires_at,held,held_by_me,held_by}]} (만료 HOLD=AVAILABLE)
 *   - POST /sales/units/{id}/hold    {minutes?} → 200 {hold_token, expires_at, ttl_minutes} | 409 | 404
 *   - POST /sales/units/{id}/release {hold_token?} → 200 {released} | 409 | 404
 *   - POST /sales/units/{id}/reserve {hold_token, customer_id?} → 200 {reserved,status:CONTRACTED} | 409
 *   - WS   /ws/sales/board:{site_id}            → {type:UNIT_STATUS, event, unit_id, status, expires_at}
 *
 * 동작: 보드 렌더(동/호/층, status 색상) → 가능세대 클릭=hold(TTL 카운트다운) → release/reserve.
 *       WS 수신으로 타직원 hold/release/reserve 즉시 반영. 낙관적 업데이트는 서버응답/WS로 교정.
 *       본인 hold TTL 만료 시 클라타이머가 자동 AVAILABLE 전환(백엔드 lazy expire 정합).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { salesApi } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { connectUnitBoardWs, type UnitBoardWsHandle, type UnitBoardWsStatus, type UnitStatusEvent } from "@/lib/unitBoardWs";

// ── 보드 모델 ─────────────────────────────────────────────────────
type BoardStatus = "AVAILABLE" | "HOLD" | "CONTRACTED";

interface BoardUnit {
  unit_id: string;
  dong: string;
  ho: string;
  floor: number;
  line?: string | null;
  status: BoardStatus | string;
  expires_at?: string | null;
  held?: boolean;
  held_by_me?: boolean;
  held_by?: string | null;
}

interface BoardResponse {
  site_id?: string;
  channel?: string;
  counts?: Record<string, number>;
  units?: BoardUnit[];
}

interface HoldResponse {
  ok?: boolean;
  unit_id?: string;
  hold_token?: string;
  expires_at?: string;
  ttl_minutes?: number;
}

interface ReserveResponse {
  reserved?: boolean;
  status?: string;
  dong?: string;
  ho?: string;
}

interface ConflictDetail {
  message?: string;
  current_status?: string;
  held_by_me?: boolean;
}

interface CustomerRow {
  id: string;
  name?: string | null;
  phone?: string | null;
  phone_masked?: string | null;
}

// 본인이 보유한 hold 토큰(unit_id → token). 보드 응답엔 토큰이 없으므로 클라가 hold 응답에서 보관.
type HoldTokens = Record<string, string>;
type Toast = { tone: "ok" | "warn" | "err"; text: string };

const COLOR: Record<string, string> = {
  AVAILABLE: "bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25",
  HOLD: "bg-amber-500/15 border-amber-500/40 text-amber-300",
  HOLD_ME: "bg-[var(--accent-strong)]/25 border-[var(--accent-strong)] text-[var(--text-primary)] ring-2 ring-[var(--accent-strong)]",
  CONTRACTED: "bg-rose-500/15 border-rose-500/40 text-rose-300",
};
const LABELS: Record<string, string> = {
  AVAILABLE: "분양가능",
  HOLD: "선점중(타인)",
  HOLD_ME: "내 선점",
  CONTRACTED: "계약완료",
};

function fmtCountdown(ms: number): string {
  if (ms <= 0) return "00:00";
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function conflictDetail(e: unknown): ConflictDetail | null {
  if (e instanceof ApiClientError && e.payload && typeof e.payload === "object") {
    const p = e.payload as { detail?: unknown };
    if (p.detail && typeof p.detail === "object") return p.detail as ConflictDetail;
    if (typeof p.detail === "string") return { message: p.detail };
  }
  return null;
}

export default function UnitLiveBoard({ siteCode }: { siteCode: string }) {
  const [units, setUnits] = useState<BoardUnit[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [holdTokens, setHoldTokens] = useState<HoldTokens>({});
  const [wsStatus, setWsStatus] = useState<UnitBoardWsStatus>("closed");
  const [busy, setBusy] = useState<string | null>(null); // 진행중 unit_id(중복클릭 방지)
  const [toast, setToast] = useState<Toast | null>(null);
  const [now, setNow] = useState(() => Date.now());
  // 확정(reserve) 고객 선택 모달 상태.
  const [reserveFor, setReserveFor] = useState<BoardUnit | null>(null);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [custLoading, setCustLoading] = useState(false);

  const api = useMemo(() => salesApi(siteCode), [siteCode]);
  const wsRef = useRef<UnitBoardWsHandle | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = useCallback((t: Toast) => {
    setToast(t);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  // ── 보드 조회 ───────────────────────────────────────────────────
  const loadBoard = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true);
      try {
        const r = await api.get<BoardResponse>("/units/board");
        setUnits(Array.isArray(r?.units) ? r.units : []);
        setCounts(r?.counts ?? {});
        setErr("");
      } catch {
        if (!opts?.silent) setErr("세대 보드를 불러오지 못했습니다.");
      } finally {
        if (!opts?.silent) setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    loadBoard();
  }, [loadBoard]);

  // ── WS 구독(현장 채널) ──────────────────────────────────────────
  useEffect(() => {
    if (!siteCode) return;
    const handle = connectUnitBoardWs(
      siteCode,
      (ev) => {
        if (ev.type !== "UNIT_STATUS") return;
        const m = ev as UnitStatusEvent;
        if (!m.unit_id) return;
        setUnits((prev) =>
          prev.map((u) => {
            if (u.unit_id !== m.unit_id) return u;
            const nextStatus = (m.status as BoardStatus) ?? u.status;
            // 타직원의 hold/reserve/release를 보드에 반영. held_by_me 는 내 토큰 보유 여부로 판단.
            const heldByMe = nextStatus === "HOLD" ? u.held_by_me : false;
            return {
              ...u,
              status: nextStatus,
              expires_at: m.expires_at ?? (nextStatus === "HOLD" ? u.expires_at : null),
              held: nextStatus === "HOLD",
              held_by_me: heldByMe,
            };
          }),
        );
      },
      (s) => {
        setWsStatus(s);
        // 재연결(open)되면 그동안 놓친 변경을 보드 재조회로 보정.
        if (s === "open") loadBoard({ silent: true });
      },
    );
    wsRef.current = handle;
    return () => {
      handle.close();
      wsRef.current = null;
    };
  }, [siteCode, loadBoard]);

  // ── 카운트다운/만료 타이머(1s) ──────────────────────────────────
  useEffect(() => {
    const hasHold = units.some((u) => u.status === "HOLD" && u.expires_at);
    if (!hasHold) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [units]);

  // 본인 hold TTL 만료 시 UI 자동 AVAILABLE 전환(백엔드 lazy expire 정합).
  useEffect(() => {
    let changed = false;
    const expired: string[] = [];
    const next = units.map((u) => {
      if (u.status === "HOLD" && u.expires_at) {
        const left = new Date(u.expires_at).getTime() - now;
        if (left <= 0) {
          changed = true;
          if (u.held_by_me) expired.push(u.unit_id);
          return { ...u, status: "AVAILABLE" as BoardStatus, expires_at: null, held: false, held_by_me: false };
        }
      }
      return u;
    });
    if (changed) {
      setUnits(next);
      if (expired.length) {
        setHoldTokens((prev) => {
          const cp = { ...prev };
          expired.forEach((id) => delete cp[id]);
          return cp;
        });
        flash({ tone: "warn", text: "선점 시간이 만료되어 분양가능으로 전환되었습니다." });
      }
    }
  }, [now, units, flash]);

  // ── 선점(hold) ──────────────────────────────────────────────────
  const doHold = useCallback(
    async (u: BoardUnit) => {
      if (busy) return;
      setBusy(u.unit_id);
      // 낙관적 업데이트(서버 응답/WS로 교정).
      setUnits((prev) => prev.map((x) => (x.unit_id === u.unit_id ? { ...x, status: "HOLD", held: true, held_by_me: true } : x)));
      try {
        const r = await api.post<HoldResponse>(`/units/${u.unit_id}/hold`, {});
        if (r?.hold_token) setHoldTokens((prev) => ({ ...prev, [u.unit_id]: r.hold_token as string }));
        setUnits((prev) =>
          prev.map((x) =>
            x.unit_id === u.unit_id
              ? { ...x, status: "HOLD", held: true, held_by_me: true, expires_at: r?.expires_at ?? x.expires_at }
              : x,
          ),
        );
        flash({ tone: "ok", text: `${u.dong}동 ${u.ho}호 선점 완료 (${r?.ttl_minutes ?? 5}분)` });
      } catch (e) {
        const d = conflictDetail(e);
        // 충돌/실패 → 낙관적 변경 롤백 후 최신 보드 재조회.
        await loadBoard({ silent: true });
        if (e instanceof ApiClientError && e.status === 409) {
          flash({ tone: "warn", text: d?.held_by_me ? "이미 본인이 선점한 세대입니다." : "이미 다른 직원이 선점한 세대입니다." });
        } else if (e instanceof ApiClientError && e.status === 404) {
          flash({ tone: "err", text: "세대를 찾을 수 없습니다." });
        } else {
          flash({ tone: "err", text: "선점에 실패했습니다." });
        }
      } finally {
        setBusy(null);
      }
    },
    [api, busy, flash, loadBoard],
  );

  // ── 해제(release) ───────────────────────────────────────────────
  const doRelease = useCallback(
    async (u: BoardUnit) => {
      if (busy) return;
      setBusy(u.unit_id);
      const token = holdTokens[u.unit_id];
      setUnits((prev) =>
        prev.map((x) => (x.unit_id === u.unit_id ? { ...x, status: "AVAILABLE", held: false, held_by_me: false, expires_at: null } : x)),
      );
      try {
        await api.post(`/units/${u.unit_id}/release`, token ? { hold_token: token } : {});
        setHoldTokens((prev) => {
          const cp = { ...prev };
          delete cp[u.unit_id];
          return cp;
        });
        flash({ tone: "ok", text: `${u.dong}동 ${u.ho}호 선점 해제` });
      } catch (e) {
        await loadBoard({ silent: true });
        if (e instanceof ApiClientError && e.status === 409) flash({ tone: "warn", text: "해제할 수 없는 상태입니다." });
        else flash({ tone: "err", text: "해제에 실패했습니다." });
      } finally {
        setBusy(null);
      }
    },
    [api, busy, flash, holdTokens, loadBoard],
  );

  // ── 확정(reserve) ───────────────────────────────────────────────
  const openReserve = useCallback(
    (u: BoardUnit) => {
      setReserveFor(u);
      setCustLoading(true);
      api
        .get<{ customers?: CustomerRow[]; items?: CustomerRow[] }>("/my-customers?limit=200")
        .then((r) => setCustomers(r?.customers ?? r?.items ?? []))
        .catch(() => setCustomers([]))
        .finally(() => setCustLoading(false));
    },
    [api],
  );

  const doReserve = useCallback(
    async (u: BoardUnit, customerId?: string) => {
      const token = holdTokens[u.unit_id];
      if (!token) {
        flash({ tone: "warn", text: "선점 토큰이 없습니다. 다시 선점 후 확정하세요." });
        return;
      }
      setBusy(u.unit_id);
      try {
        const r = await api.post<ReserveResponse>(`/units/${u.unit_id}/reserve`, {
          hold_token: token,
          ...(customerId ? { customer_id: customerId } : {}),
        });
        if (r?.reserved) {
          setUnits((prev) =>
            prev.map((x) => (x.unit_id === u.unit_id ? { ...x, status: "CONTRACTED", held: false, held_by_me: false, expires_at: null } : x)),
          );
          setHoldTokens((prev) => {
            const cp = { ...prev };
            delete cp[u.unit_id];
            return cp;
          });
          flash({ tone: "ok", text: `${u.dong}동 ${u.ho}호 계약 확정` });
        } else {
          await loadBoard({ silent: true });
          flash({ tone: "warn", text: "확정에 실패했습니다." });
        }
        setReserveFor(null);
      } catch (e) {
        await loadBoard({ silent: true });
        setReserveFor(null);
        if (e instanceof ApiClientError && e.status === 409) {
          flash({ tone: "warn", text: "선점이 만료되었거나 이미 처리된 세대입니다. 다시 시도하세요." });
        } else {
          flash({ tone: "err", text: "확정에 실패했습니다." });
        }
      } finally {
        setBusy(null);
      }
    },
    [api, flash, holdTokens, loadBoard],
  );

  // ── 파생: 동/층 그룹 + 통계 ─────────────────────────────────────
  const byDong = useMemo(() => {
    const g: Record<string, Record<number, BoardUnit[]>> = {};
    for (const u of units) {
      (g[u.dong] ??= {})[u.floor] ??= [];
      g[u.dong][u.floor].push(u);
    }
    return g;
  }, [units]);

  const stats = useMemo(() => {
    const c: Record<string, number> = { AVAILABLE: 0, HOLD: 0, CONTRACTED: 0, ...counts };
    if (!counts || Object.keys(counts).length === 0) {
      c.AVAILABLE = 0;
      c.HOLD = 0;
      c.CONTRACTED = 0;
      for (const u of units) c[u.status] = (c[u.status] ?? 0) + 1;
    }
    const total = units.length;
    const sold = c.CONTRACTED || 0;
    const ratio = total ? Math.round((sold / total) * 1000) / 10 : 0;
    return { c, total, ratio };
  }, [counts, units]);

  const visualStatus = (u: BoardUnit): string => {
    if (u.status === "HOLD") return u.held_by_me ? "HOLD_ME" : "HOLD";
    return u.status;
  };

  const myHoldUnit = reserveFor;

  return (
    <div className="space-y-4">
      {/* 통계 + WS 상태 */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {[
          ["총 세대", `${stats.total}`],
          ["분양률", `${stats.ratio}%`],
          ["분양가능", `${stats.c.AVAILABLE ?? 0}`],
          ["선점중", `${stats.c.HOLD ?? 0}`],
          ["계약", `${stats.c.CONTRACTED ?? 0}`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-2.5 text-center">
            <p className="text-[10px] text-[var(--text-tertiary)]">{k}</p>
            <p className="text-base font-black text-[var(--text-primary)]">{v}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs font-semibold">
          <i
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              wsStatus === "open" ? "bg-emerald-400" : wsStatus === "connecting" ? "bg-amber-400 animate-pulse" : "bg-zinc-500"
            }`}
          />
          <span className="text-[var(--text-secondary)]">
            {wsStatus === "open" ? "실시간 연결됨" : wsStatus === "connecting" ? "연결 중…" : "연결 끊김(재연결 시도)"}
          </span>
        </span>
        <button
          onClick={() => loadBoard()}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-xs font-bold text-[var(--text-secondary)]"
        >
          새로고침
        </button>
        <div className="ml-auto flex flex-wrap gap-3 text-xs">
          {Object.entries(LABELS).map(([k, v]) => (
            <span key={k} className="flex items-center gap-1.5 text-[var(--text-secondary)]">
              <i className={`inline-block h-3 w-3 rounded ${COLOR[k].split(" ")[0]}`} />
              {v}
            </span>
          ))}
        </div>
      </div>

      {toast && (
        <div
          role="status"
          className={`rounded-lg border px-3 py-2 text-xs font-semibold ${
            toast.tone === "ok"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : toast.tone === "warn"
                ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                : "border-rose-500/40 bg-rose-500/10 text-rose-300"
          }`}
        >
          {toast.text}
        </div>
      )}

      {err && <p className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{err}</p>}
      {loading && <p className="text-sm text-[var(--text-tertiary)]">세대 보드를 불러오는 중…</p>}
      {!loading && !err && units.length === 0 && (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 text-sm text-[var(--text-secondary)]">
          아직 세대가 없습니다. 동·호표를 먼저 생성하세요.
        </p>
      )}

      {/* 보드 그리드 */}
      {!loading && units.length > 0 && (
        <div className="space-y-6">
          {Object.entries(byDong).map(([dong, floors]) => (
            <div key={dong} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
              <h3 className="mb-2 font-bold text-[var(--text-primary)]">{dong}동</h3>
              <div className="space-y-1">
                {Object.entries(floors)
                  .sort((a, b) => Number(b[0]) - Number(a[0]))
                  .map(([f, us]) => (
                    <div key={f} className="flex items-center gap-1">
                      <span className="w-10 shrink-0 text-xs font-semibold text-[var(--text-tertiary)]">{f}F</span>
                      <div className="flex flex-wrap gap-1">
                        {us
                          .sort((a, b) => (a.ho || "").localeCompare(b.ho || ""))
                          .map((u) => {
                            const vs = visualStatus(u);
                            const left = u.expires_at ? new Date(u.expires_at).getTime() - now : 0;
                            const isMine = u.status === "HOLD" && u.held_by_me;
                            const urgent = isMine && left > 0 && left <= 60_000;
                            const clickable = u.status === "AVAILABLE" && !busy;
                            return (
                              <button
                                key={u.unit_id}
                                disabled={busy === u.unit_id || (u.status !== "AVAILABLE" && !isMine)}
                                onClick={() => {
                                  if (u.status === "AVAILABLE") doHold(u);
                                }}
                                title={
                                  u.status === "HOLD" && !u.held_by_me
                                    ? "다른 직원이 선점 중"
                                    : u.status === "CONTRACTED"
                                      ? "계약 완료"
                                      : u.ho
                                }
                                className={`relative flex h-14 w-16 flex-col items-center justify-center rounded border text-[11px] font-medium transition ${
                                  COLOR[vs] ?? COLOR.AVAILABLE
                                } ${clickable ? "cursor-pointer" : "cursor-default"} ${busy === u.unit_id ? "opacity-60" : ""}`}
                              >
                                <span className="font-bold">{u.ho}</span>
                                {u.status === "HOLD" && !u.held_by_me && (
                                  <span className="text-[9px] leading-none">🔒 선점중</span>
                                )}
                                {isMine && (
                                  <span className={`text-[9px] leading-none tabular-nums ${urgent ? "text-rose-300 font-black" : ""}`}>
                                    ⏱ {fmtCountdown(left)}
                                  </span>
                                )}
                                {u.status === "CONTRACTED" && <span className="text-[9px] leading-none">계약</span>}
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  ))}
              </div>
              {/* 내 선점 세대 액션(해제/확정) */}
              {Object.values(floors)
                .flat()
                .some((u) => u.status === "HOLD" && u.held_by_me) && (
                <div className="mt-2 flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-2">
                  {Object.values(floors)
                    .flat()
                    .filter((u) => u.status === "HOLD" && u.held_by_me)
                    .map((u) => (
                      <span
                        key={u.unit_id}
                        className="flex items-center gap-1.5 rounded-lg border border-[var(--accent-strong)]/50 bg-[var(--surface-strong)] px-2 py-1 text-[11px]"
                      >
                        <b className="text-[var(--text-primary)]">
                          {u.ho}호
                        </b>
                        <button
                          disabled={busy === u.unit_id}
                          onClick={() => openReserve(u)}
                          className="rounded bg-[var(--accent-strong)] px-2 py-0.5 font-bold text-white disabled:opacity-50"
                        >
                          계약확정
                        </button>
                        <button
                          disabled={busy === u.unit_id}
                          onClick={() => doRelease(u)}
                          className="rounded border border-[var(--line)] px-2 py-0.5 font-semibold text-[var(--text-secondary)] disabled:opacity-50"
                        >
                          해제
                        </button>
                      </span>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 확정 고객선택 모달 */}
      {myHoldUnit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setReserveFor(null)}>
          <div
            className="w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-black text-[var(--text-primary)]">
              {myHoldUnit.dong}동 {myHoldUnit.ho}호 계약 확정
            </h3>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">계약 고객을 선택하면 연계됩니다(선택 안 해도 확정 가능).</p>
            <div className="mt-3 max-h-64 space-y-1 overflow-y-auto">
              {custLoading && <p className="text-sm text-[var(--text-tertiary)]">고객 목록 로딩 중…</p>}
              {!custLoading && customers.length === 0 && (
                <p className="text-sm text-[var(--text-tertiary)]">등록된 고객이 없습니다. 고객 없이 확정합니다.</p>
              )}
              {customers.map((c) => (
                <button
                  key={c.id}
                  disabled={busy === myHoldUnit.unit_id}
                  onClick={() => doReserve(myHoldUnit, c.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-left text-sm hover:border-[var(--accent-strong)] disabled:opacity-50"
                >
                  <span className="font-semibold text-[var(--text-primary)]">{c.name || "(이름없음)"}</span>
                  <span className="text-xs text-[var(--text-tertiary)]">{c.phone_masked || c.phone || ""}</span>
                </button>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button
                disabled={busy === myHoldUnit.unit_id}
                onClick={() => doReserve(myHoldUnit)}
                className="flex-1 rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                고객 없이 확정
              </button>
              <button
                onClick={() => setReserveFor(null)}
                className="rounded-lg border border-[var(--line)] px-3 py-2 text-sm font-semibold text-[var(--text-secondary)]"
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
