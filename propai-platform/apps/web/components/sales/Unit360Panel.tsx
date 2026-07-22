"use client";

import { useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { useSalesStore } from "@/store/useSalesStore";
import { unitStatusLabel } from "@/components/sales/unitStatus";

interface Detail {
  unit: { dong: string; ho: string; floor: number; line: string; aspect?: string; status: string } | null;
  price?: { total_price: number; breakdown: { label: string; amount: number; vat_amount: number }[] } | null;
  contract?: { stage: string; total_price: number } | null;
  installments?: { seq: number; kind: string; amount: number; due_date?: string }[];
  history?: { ts: string; from_status?: string; to_status?: string }[];
}

interface UnitEvent {
  seq: number; event_type: string; event_label: string;
  from_status?: string; to_status?: string; message?: string;
  occurred_at: string; content_hash: string;
}
// 상태 표시 라벨은 세대 상태 SSOT(unitStatus.unitStatusLabel) 소비 — 배치도·보드와 동일 표기.
// ★아래 ACTIONS_BY_STATUS 의 label 은 '상태'가 아니라 그 상태에서 실행할 '액션(전이)' 캡션이므로
//   별개다(예: AVAILABLE 에서 누르는 버튼 "동·호지정 대기"는 HOLD 로 보내는 동작 이름).
// 현재 상태에서 가능한 액션(컨텍스트 메뉴).
const ACTIONS_BY_STATUS: Record<string, { action: string; label: string; tone: "accent" | "warn" | "danger" }[]> = {
  AVAILABLE: [{ action: "HOLD_REQUEST", label: "동·호지정 대기", tone: "accent" }],
  HOLD: [
    { action: "CONTRACT_WAIT", label: "계약 대기", tone: "accent" },
    { action: "HOLD_CANCEL", label: "동·호지정 취소", tone: "warn" },
  ],
  APPLIED: [
    { action: "CONTRACT_SIGN", label: "계약 체결", tone: "accent" },
    { action: "CONTRACT_CANCEL", label: "계약 취소", tone: "warn" },
  ],
  CONTRACTED: [{ action: "CONTRACT_TERMINATE", label: "계약 해지", tone: "danger" }],
};

export default function Unit360Panel({ siteCode }: { siteCode: string }) {
  const selectedUnit = useSalesStore((s) => s.selectedUnit);
  const select = useSalesStore((s) => s.select);
  const units = useSalesStore((s) => s.units);
  const setUnits = useSalesStore((s) => s.setUnits);
  const [d, setD] = useState<Detail | null>(null);
  // 계약 체결 진행/결과 메시지(버튼 중복클릭 방지 + 성공/실패 안내).
  const [signing, setSigning] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  // 세대 액션·특이사항·이벤트 타임라인.
  const [events, setEvents] = useState<UnitEvent[]>([]);
  const [note, setNote] = useState("");
  const [acting, setActing] = useState(false);
  const status = selectedUnit?.status || "AVAILABLE";

  const loadEvents = (uid: string) => {
    salesApi(siteCode).get<UnitEvent[]>(`/units/${uid}/events`).then((r) => setEvents(r || [])).catch(() => setEvents([]));
  };

  // 세대 상세를 다시 불러온다(계약 체결 직후 '계약' 섹션을 갱신하기 위해).
  const reload = () => {
    if (!selectedUnit) return;
    salesApi(siteCode).get<Detail>(`/units/${selectedUnit.id}/detail`).then(setD).catch(() => setD(null));
  };

  useEffect(() => {
    setMsg(null); setEvents([]); setNote("");
    if (!selectedUnit) { setD(null); return; }
    let alive = true;
    salesApi(siteCode).get<Detail>(`/units/${selectedUnit.id}/detail`)
      .then((r) => { if (alive) setD(r); }).catch(() => { if (alive) setD(null); });
    loadEvents(selectedUnit.id);
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedUnit, siteCode]);

  // 세대 액션(상태전이/특이사항) — POST /units/{id}/action → 상태·타임라인 즉시 갱신.
  const doAction = async (action: string, message?: string) => {
    if (!selectedUnit || acting) return;
    setActing(true); setMsg(null);
    try {
      const r = await salesApi(siteCode).post<{ status?: string }>(`/units/${selectedUnit.id}/action`, { action, message });
      const newStatus = (r?.status || status) as typeof selectedUnit.status;
      select({ ...selectedUnit, status: newStatus });   // 패널 상태 즉시 반영
      setUnits((units || []).map((u) => (u.id === selectedUnit.id ? { ...u, status: newStatus } : u)));  // 보드 색상 즉시 반영
      loadEvents(selectedUnit.id);
      reload();
      if (action === "NOTE") setNote("");
      setMsg({ ok: true, text: action === "NOTE" ? "특이사항이 원장에 등록되었습니다(년월일·시분·해시)." : "처리되었습니다." });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error && e.message ? e.message : "처리에 실패했습니다." });
    } finally { setActing(false); }
  };

  // 계약 체결 — 선택한 세대로 계약 1건을 만든다(이후 수납·대출·전매 화면에서 선택 가능).
  const createContract = async () => {
    if (!selectedUnit) return;
    setSigning(true); setMsg(null);
    try {
      await salesApi(siteCode).post("/contracts", { unit_id: selectedUnit.id });
      setMsg({ ok: true, text: "계약을 체결했습니다. 수납·대출·전매 화면에서 선택할 수 있어요." });
      reload();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error && e.message ? e.message : "계약 체결에 실패했습니다." });
    } finally { setSigning(false); }
  };

  if (!selectedUnit) return null;
  return (
    <div className="fixed right-0 top-0 z-40 h-full w-[420px] overflow-y-auto border-l border-[var(--line)] bg-[var(--surface)] p-5 shadow-[var(--shadow-lg)]">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-black text-[var(--text-primary)]">{selectedUnit.dong}동 {selectedUnit.ho}호</h2>
        <button onClick={() => select(undefined)} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">✕</button>
      </div>
      <Section title="기본">
        <Row k="층/라인/향" v={`${selectedUnit.floor}F / ${selectedUnit.line} / ${selectedUnit.aspect ?? "-"}`} />
        <Row k="상태" v={unitStatusLabel(status)} />
        <Row k="분양가" v={d?.price ? won(d.price.total_price) : "-"} />
      </Section>

      {/* 세대 액션 — 현재 상태에서 가능한 컨텍스트 메뉴(상태전이). 각 이벤트는 원장에 년월일·시분 기록 */}
      <Section title="세대 액션">
        <div className="flex flex-wrap gap-2">
          {(ACTIONS_BY_STATUS[status] || []).map((a) => (
            <button key={a.action} onClick={() => doAction(a.action)} disabled={acting}
              className={`rounded-lg px-3 py-2 text-xs font-black text-white disabled:opacity-50 ${
                a.tone === "danger" ? "bg-[var(--status-error)]" : a.tone === "warn" ? "bg-amber-500" : "bg-[var(--accent-strong)]"}`}>
              {a.label}
            </button>
          ))}
          {(ACTIONS_BY_STATUS[status] || []).length === 0 && (
            <span className="text-xs text-[var(--text-tertiary)]">현재 상태에서 가능한 동작이 없습니다.</span>
          )}
        </div>
      </Section>

      {/* 특이사항 — 블록체인식 원장에 메시지 등록(년월일·시분·해시) */}
      <Section title="특이사항 등록">
        <div className="flex gap-2">
          <input value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="예: VIP 고객, 계약금 입금대기"
            onKeyDown={(e) => { if (e.key === "Enter" && note.trim()) void doAction("NOTE", note.trim()); }}
            className="flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
          <button onClick={() => note.trim() && doAction("NOTE", note.trim())} disabled={acting || !note.trim()}
            className="rounded-lg bg-[var(--surface-strong)] border border-[var(--line)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-50">등록</button>
        </div>
      </Section>
      {d?.price?.breakdown?.length ? (
        <Section title="분양가 구성">
          {(d.price.breakdown ?? []).map((b, i) => (
            <Row key={i} k={b.label} v={`${won(b.amount)}${b.vat_amount ? ` (+VAT ${won(b.vat_amount)})` : ""}`} />
          ))}
        </Section>
      ) : null}
      {d?.contract ? (
        <Section title="계약">
          <Row k="단계" v={d.contract.stage} />
          <Row k="계약금액" v={won(d.contract.total_price)} />
          {d.installments?.map((it, i) => (
            <Row key={i} k={`${it.kind} #${it.seq}`} v={`${won(it.amount)} / ${it.due_date ?? "-"}`} />
          ))}
        </Section>
      ) : (
        <Section title="계약">
          <p className="mb-2 text-sm text-[var(--text-tertiary)]">아직 계약이 없습니다.</p>
          {/* 계약 체결: 세대 가격표에서 금액을 자동으로 가져와 계약 1건을 만든다. */}
          <button onClick={createContract} disabled={signing || selectedUnit.status === "CONTRACTED"}
            className="w-full rounded-lg bg-[var(--accent-strong)] px-3 py-2 text-sm font-black text-white disabled:opacity-50">
            {signing ? "체결 중…" : "계약 체결"}
          </button>
        </Section>
      )}
      {msg && (
        <p className={`mb-4 rounded-lg px-3 py-2 text-sm font-semibold ${msg.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"}`}>
          {msg.text}
        </p>
      )}
      {/* 이벤트 타임라인 — 블록체인식 원장(년월일·시분 + 해시체인). 모든 액션·특이사항·추첨 기록 */}
      <Section title="이벤트 타임라인 (원장)">
        {events.length === 0 ? (
          <p className="text-xs text-[var(--text-tertiary)]">기록된 이벤트가 없습니다.</p>
        ) : (
          <ol className="relative space-y-2 border-l border-[var(--line)] pl-3">
            {events.slice().reverse().map((e) => (
              <li key={e.seq} className="relative">
                <span className="absolute -left-[1.07rem] top-1 h-2 w-2 rounded-full bg-[var(--accent-strong)]" aria-hidden />
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-[var(--text-primary)]">{e.event_label}{e.to_status ? ` · ${unitStatusLabel(e.to_status)}` : ""}</span>
                  <span className="text-[10px] tabular-nums text-[var(--text-tertiary)]">{new Date(e.occurred_at).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" })}</span>
                </div>
                {e.message && <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{e.message}</p>}
                <p className="mt-0.5 font-mono text-[9px] text-[var(--text-hint)]" title="content_hash(블록체인식 변조탐지)">#{e.seq} · {e.content_hash.slice(0, 12)}</p>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </div>
  );
}

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="mb-5">
    <h3 className="mb-2 text-sm font-bold text-[var(--accent-strong)]">{title}</h3>
    <div className="space-y-1">{children}</div>
  </div>
);
const Row = ({ k, v }: { k: string; v: string }) => (
  <div className="flex justify-between gap-3 text-sm">
    <span className="text-[var(--text-tertiary)]">{k}</span>
    <span className="text-right font-semibold text-[var(--text-primary)]">{v}</span>
  </div>
);
