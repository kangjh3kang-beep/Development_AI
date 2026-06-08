"use client";

import { useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { useSalesStore } from "@/store/useSalesStore";

interface Detail {
  unit: { dong: string; ho: string; floor: number; line: string; aspect?: string; status: string } | null;
  price?: { total_price: number; breakdown: { label: string; amount: number; vat_amount: number }[] } | null;
  contract?: { stage: string; total_price: number } | null;
  installments?: { seq: number; kind: string; amount: number; due_date?: string }[];
  history?: { ts: string; from_status?: string; to_status?: string }[];
}

export default function Unit360Panel({ siteCode }: { siteCode: string }) {
  const selectedUnit = useSalesStore((s) => s.selectedUnit);
  const select = useSalesStore((s) => s.select);
  const [d, setD] = useState<Detail | null>(null);
  // 계약 체결 진행/결과 메시지(버튼 중복클릭 방지 + 성공/실패 안내).
  const [signing, setSigning] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // 세대 상세를 다시 불러온다(계약 체결 직후 '계약' 섹션을 갱신하기 위해).
  const reload = () => {
    if (!selectedUnit) return;
    salesApi(siteCode).get<Detail>(`/units/${selectedUnit.id}/detail`).then(setD).catch(() => setD(null));
  };

  useEffect(() => {
    setMsg(null);
    if (!selectedUnit) { setD(null); return; }
    let alive = true;
    salesApi(siteCode).get<Detail>(`/units/${selectedUnit.id}/detail`)
      .then((r) => { if (alive) setD(r); }).catch(() => { if (alive) setD(null); });
    return () => { alive = false; };
  }, [selectedUnit, siteCode]);

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
        <Row k="상태" v={selectedUnit.status} />
        <Row k="분양가" v={d?.price ? won(d.price.total_price) : "-"} />
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
      {d?.history?.length ? (
        <Section title="상태 이력">
          {(d.history ?? []).map((h, i) => (
            <Row key={i} k={new Date(h.ts).toLocaleString("ko-KR")} v={`${h.from_status ?? "-"} → ${h.to_status}`} />
          ))}
        </Section>
      ) : null}
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
