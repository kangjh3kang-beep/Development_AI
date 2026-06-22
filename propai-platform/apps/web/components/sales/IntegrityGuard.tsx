"use client";

/**
 * 무결성 가드 — 분양 데이터 불변식 위반 실시간 적발.
 * 1호1계약(중복동호·다중계약)·수수료 배분초과(Σ>총액)·미보증 계약·미가격 세대.
 * 백엔드: GET /sales/integrity/check
 */

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ShieldCheck } from "lucide-react";
import { salesApi } from "@/lib/salesApi";

interface Finding { key: string; severity: "critical" | "high" | "medium"; count: number; title: string; detail: string }

const SEV: Record<string, { cls: string; label: string }> = {
  critical: { cls: "border-rose-500/40 bg-rose-500/10 text-rose-300", label: "심각" },
  high: { cls: "border-amber-500/40 bg-amber-500/10 text-amber-300", label: "주의" },
  medium: { cls: "border-sky-500/40 bg-sky-500/10 text-sky-300", label: "확인" },
};

export default function IntegrityGuard({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [ok, setOk] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(() => {
    setBusy(true);
    api.get<{ ok: boolean; findings: Finding[] }>("/integrity/check")
      .then((r) => { setOk(r.ok); setFindings(r.findings || []); })
      .catch(() => { setOk(null); setFindings([]); })
      .finally(() => setBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { run(); }, [run]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="inline-flex items-center gap-1.5 font-black text-[var(--text-primary)]"><ShieldCheck className="size-5" aria-hidden />무결성 가드</h2>
        <button onClick={run} disabled={busy} className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white disabled:opacity-50">
          {busy ? "점검 중…" : "재점검"}
        </button>
      </div>

      {busy && ok === null && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 text-center text-sm text-[var(--text-secondary)]">무결성 점검 중…</div>
      )}

      {ok === null && !busy && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-sm text-[var(--text-secondary)]">
          점검 결과를 불러오지 못했습니다. ‘재점검’을 눌러 다시 시도하세요.
        </div>
      )}

      {ok === true && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-5 text-center">
          <CheckCircle2 className="mx-auto size-8 text-emerald-300" aria-hidden />
          <p className="mt-1 text-sm font-bold text-emerald-300">무결성 위반 없음 — 1호1계약·배분·보증·가격 정상</p>
        </div>
      )}

      {findings.length > 0 && (
        <div className="space-y-2">
          {findings.map((f) => (
            <div key={f.key} className={`flex flex-wrap items-center gap-3 rounded-xl border p-4 ${SEV[f.severity]?.cls ?? "border-[var(--line)]"}`}>
              <span className="rounded-full border border-current px-2 py-0.5 text-[10px] font-black">{SEV[f.severity]?.label ?? f.severity}</span>
              <span className="font-bold text-[var(--text-primary)]">{f.title}</span>
              <span className="rounded-md bg-[var(--surface-strong)] px-2 py-0.5 text-xs font-bold">{f.count}건</span>
              <span className="w-full text-xs text-[var(--text-secondary)] sm:w-auto sm:flex-1">{f.detail}</span>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-[var(--text-hint)]">
        점검 항목: 중복 동·호 / 한 세대 다중 활성계약(1호1계약) · 수수료 배분 합계 초과(Σ≤총액) · 서명 계약 미보증(HUG/신탁) · 분양가능 세대 미가격.
      </p>
    </div>
  );
}
