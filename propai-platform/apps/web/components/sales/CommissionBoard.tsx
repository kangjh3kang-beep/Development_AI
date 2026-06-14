"use client";

/**
 * 분양 수수료 — 1단(시행사 총액) 설정 + 2단(대행사→하위 배분, FIXED/RATE) 추가/삭제 + Σ≤총액 검증.
 * 백엔드: CRUD /commission-master · /commission-distribution + POST /commission/distribution/validate
 */

import { useCallback, useEffect, useState } from "react";
import { salesApi, won } from "@/lib/salesApi";
import { NumberInput } from "@/components/common/NumberInput";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";

interface Master { id?: string; basis: string; fixed_amount?: number | null; rate?: number | null; locked?: boolean }
interface Dist { id: string; master_id?: string; target_node_type?: string | null; target_node_id?: string | null; basis: string; value: number }

const BASIS_MASTER = [
  { value: "PER_CONTRACT_FIXED", label: "건당 고정액" },
  { value: "RATE_OF_PRICE", label: "분양가 요율(%)" },
  { value: "TOTAL_POOL", label: "총액 풀(정액)" },
];
const NODE_TYPES = [
  { value: "SUBAGENCY", label: "대대행" }, { value: "GM_DIRECTOR", label: "총괄본부장" },
  { value: "DIRECTOR", label: "본부장" }, { value: "TEAM_LEADER", label: "팀장" }, { value: "MEMBER", label: "팀원" },
  { value: "MGM", label: "부동산MGM" },  // 외부 부동산 추천 수수료(총액에서 차감·예약). 잔여는 대행사 귀속.
];
const NT: Record<string, string> = Object.fromEntries(NODE_TYPES.map((t) => [t.value, t.label]));
const fcls = "rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export default function CommissionBoard({ siteCode }: { siteCode: string }) {
  const api = salesApi(siteCode);
  const [master, setMaster] = useState<Master | null>(null);
  const [dist, setDist] = useState<Dist[]>([]);
  const [valid, setValid] = useState<{ total: number; allocated: number; valid: boolean } | null>(null);
  // 마스터 입력 폼
  const [mBasis, setMBasis] = useState("RATE_OF_PRICE");
  const [mFixed, setMFixed] = useState<number>(0);
  const [mRate, setMRate] = useState<number>(0.02);
  // 배분 입력 폼
  const [dType, setDType] = useState("MEMBER");
  const [dBasis, setDBasis] = useState("RATE");
  const [dValue, setDValue] = useState<number>(0.5);
  const [sample, setSample] = useState<number>(500000000);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  // loaded: 첫 데이터를 불러왔는지 여부(false면 '불러오는 중' 자리표시 표시).
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    // 최신(활성) 마스터 사용 — 백엔드 _active_master(effective_at 최신)와 일치. provision 자동생성분과
    // 사용자 설정분이 공존할 수 있어 마지막 항목(가장 최근 삽입)을 활성으로 본다.
    api.get<Master[]>("/commission-master")
      .then((m) => setMaster(m && m.length ? m[m.length - 1] : null)).catch(() => setMaster(null));
    // 배분 규칙 목록을 다 불러오면 '불러오는 중' 자리표시를 걷어낸다.
    api.get<Dist[]>("/commission-distribution").then((d) => setDist(d || [])).catch(() => setDist([])).finally(() => setLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteCode]);
  useEffect(() => { load(); }, [load]);

  const errText = (e: unknown) => (e instanceof Error && e.message ? e.message : "요청에 실패했습니다.");
  const saveMaster = async () => {
    setMsg(null);
    try {
      await api.post("/commission-master", {
        basis: mBasis,
        fixed_amount: mBasis === "RATE_OF_PRICE" ? undefined : mFixed,
        rate: mBasis === "RATE_OF_PRICE" ? mRate : undefined,
      });
      setMsg({ ok: true, text: "1단 마스터 저장 완료" }); load();
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const addDist = async () => {
    setMsg(null);
    if (!master?.id) { setMsg({ ok: false, text: "먼저 1단(시행사 총액)을 설정하세요." }); return; }
    try {
      await api.post("/commission-distribution", {
        master_id: master.id, target_node_type: dType, basis: dBasis, value: dValue,
      });
      setMsg({ ok: true, text: "배분 규칙 추가 완료" }); load();
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const delDist = async (id: string) => {
    setMsg(null);
    try { await api.del(`/commission-distribution/${id}`); load(); }
    catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };
  const check = async () => {
    setMsg(null);
    try {
      const r = await api.post<{ total: number; allocated: number; valid: boolean }>(
        "/commission/distribution/validate", { sample_price: sample });
      setValid(r);
    } catch (e) { setMsg({ ok: false, text: errText(e) }); }
  };

  // 처음 불러오는 중이면 회색 자리표시(스켈레톤)로 빈 화면 깜빡임을 막는다.
  if (!loaded) return <SkeletonLoader count={3} itemClassName="h-24 rounded-xl mb-3" />;
  return (
    <div className="space-y-4">
      {msg && (
        <p className={`rounded-lg px-3 py-2 text-sm font-semibold ${msg.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"}`}>
          {msg.text}
        </p>
      )}
      {/* 1단 마스터 */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-2 font-black text-[var(--text-primary)]">1단: 시행사 총액</h3>
        {master && (
          <p className="mb-2 text-xs text-[var(--text-secondary)]">
            현재: {BASIS_MASTER.find((b) => b.value === master.basis)?.label ?? master.basis}
            {master.basis === "RATE_OF_PRICE" ? ` · 요율 ${(Number(master.rate) * 100).toFixed(2)}%` : ` · ${won(master.fixed_amount || 0)}`}
            {master.locked ? " · 🔒확정" : ""}
          </p>
        )}
        <div className="flex flex-wrap items-end gap-2">
          <select value={mBasis} onChange={(e) => setMBasis(e.target.value)} className={`${fcls} w-40`}>
            {BASIS_MASTER.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
          </select>
          {mBasis === "RATE_OF_PRICE" ? (
            <input type="number" step="0.001" value={mRate} onChange={(e) => setMRate(Number(e.target.value))} placeholder="0.02 = 2%" className={`${fcls} w-32`} />
          ) : (
            <NumberInput value={mFixed} onChange={(n) => setMFixed(n ?? 0)} placeholder="금액(원)" className={`${fcls} w-40`} />
          )}
          <button onClick={saveMaster} className="rounded-lg bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white">총액 기준 저장</button>
        </div>
      </div>

      {/* 2단 배분 */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <h3 className="mb-2 font-black text-[var(--text-primary)]">2단: 대행사 배분 (직급별)</h3>
        <div className="mb-3 flex flex-wrap items-end gap-2">
          <select value={dType} onChange={(e) => setDType(e.target.value)} className={`${fcls} w-32`}>
            {NODE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <select value={dBasis} onChange={(e) => setDBasis(e.target.value)} className={`${fcls} w-28`}>
            <option value="RATE">총액 대비 %</option><option value="FIXED">정액(원)</option>
          </select>
          <input type="number" step={dBasis === "RATE" ? "0.01" : "1"} value={dValue} onChange={(e) => setDValue(Number(e.target.value))}
            placeholder={dBasis === "RATE" ? "0.5 = 50%" : "원"} className={`${fcls} w-32`} />
          <button onClick={addDist} className="rounded-lg border border-dashed border-[var(--line-strong)] px-3 py-2 text-xs font-bold text-[var(--accent-strong)]">＋ 배분 추가</button>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-[var(--line)] text-left text-[var(--text-secondary)]">
            <th className="py-1">대상</th><th>기준</th><th className="text-right">값</th><th /></tr></thead>
          <tbody>
            {dist.filter((d) => !master?.id || !d.master_id || d.master_id === master.id).map((d) => (
              <tr key={d.id} className="border-b border-[var(--line)] text-[var(--text-primary)]">
                <td className="py-1">{d.target_node_type ? (NT[d.target_node_type] ?? d.target_node_type) : "지정노드"}</td>
                <td>{d.basis === "FIXED" ? "정액" : "%"}</td>
                <td className="text-right">{d.basis === "FIXED" ? won(d.value) : `${(d.value * 100).toFixed(1)}%`}</td>
                <td className="text-right"><button onClick={() => delDist(d.id)} className="text-rose-500">✕</button></td>
              </tr>
            ))}
            {dist.length === 0 && <tr><td colSpan={4} className="py-3 text-[var(--text-tertiary)]">배분 규칙 없음. 직급별로 추가하세요(잔여는 대행사 귀속).</td></tr>}
          </tbody>
        </table>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-[var(--text-tertiary)]">검증 샘플 분양가</span>
          <NumberInput value={sample} onChange={(n) => setSample(n ?? 0)} className={`${fcls} w-40`} />
          <button onClick={check} className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white">Σ≤총액 검증</button>
          {valid && (
            <span className={`text-sm font-semibold ${valid.valid ? "text-emerald-400" : "text-rose-400"}`}>
              총액 {won(valid.total)} / 배분합 {won(valid.allocated)} → {valid.valid ? "정상(≤총액)" : "초과(오류)"}
            </span>
          )}
        </div>
      </div>
      <p className="text-[11px] text-[var(--text-hint)]">시행사 총액(1단) → 조직 직급별 배분(2단, cascade). 배분 합계는 항상 총액 이하여야 하며 잔여는 대행사 귀속(무결성). 계약 체결 시 자동 split.</p>
    </div>
  );
}
