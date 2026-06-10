"use client";

/**
 * 관리자 — 과금 금액 설정 수정/변경.
 * GET/PUT /api/v1/billing/admin/config (관리자 권한). 등급요금·할증·서비스료·
 * 진행 단계 단계별·무료횟수 단가를 화면에서 직접 수정한다.
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Config = any;

const STAGE_LABELS: Record<string, string> = {
  site_analysis: "부지분석", design: "건축설계", cost: "공사비",
  feasibility: "수지분석", tax: "세금계산", esg: "ESG/탄소", report: "통합보고서",
};
const TIER_LABELS: Record<string, string> = { power: "파워", superpower: "슈퍼파워", master: "마스터" };

export default function BillingConfigPage() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [denied, setDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setMsg("");
    try {
      const c = await apiClient.get<Config>("/billing/admin/config", { useMock: false });
      setCfg(c);
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) setDenied(true);
      else setMsg("설정을 불러오지 못했습니다.");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const num = (v: string) => (v === "" ? 0 : Number(v.replace(/[^0-9.]/g, "")));
  const setTier = (t: string, k: string, v: string) =>
    setCfg((c: Config) => ({ ...c, tiers: { ...c.tiers, [t]: { ...c.tiers[t], [k]: num(v) } } }));
  const setStage = (s: string, v: string) =>
    setCfg((c: Config) => ({ ...c, service_fees: { ...c.service_fees, stages: { ...c.service_fees.stages, [s]: num(v) } } }));
  const setSvc = (k: string, v: string) =>
    setCfg((c: Config) => ({ ...c, service_fees: { ...c.service_fees, [k]: num(v) } }));
  const setFree = (sub: string, t: string, v: string) =>
    setCfg((c: Config) => ({ ...c, free_tier: { ...c.free_tier, [sub]: { ...c.free_tier[sub], [t]: num(v) } } }));

  // ── 구독 플랜 추가/삭제(과금설정과 통합) ──
  const [removed, setRemoved] = useState<string[]>([]);
  const PROTECTED = new Set(["free", "guest", "super_admin"]); // 시스템 보호 등급(삭제 불가)
  const setTierLabel = (t: string, v: string) =>
    setCfg((c: Config) => ({ ...c, tiers: { ...c.tiers, [t]: { ...c.tiers[t], label: v } } }));
  const addPlan = () => {
    // eslint-disable-next-line no-alert
    const raw = window.prompt("새 구독 플랜 식별자(영문 소문자/숫자, 예: pro, business)") || "";
    const key = raw.trim().toLowerCase().replace(/[^a-z0-9_]/g, "");
    if (!key) return;
    setCfg((c: Config) => (c.tiers[key] ? c : { ...c, tiers: { ...c.tiers, [key]: { fee_krw: 0, multiplier: 1, label: key } } }));
    setRemoved((r) => r.filter((x) => x !== key));
  };
  const deletePlan = (t: string) => {
    if (PROTECTED.has(t)) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm(`'${t}' 구독 플랜을 삭제할까요? (구독 중인 사용자 등급은 별도)`)) return;
    setCfg((c: Config) => { const tiers = { ...c.tiers }; delete tiers[t]; return { ...c, tiers }; });
    setRemoved((r) => Array.from(new Set([...r, t])));
  };

  const save = async () => {
    setSaving(true); setMsg("");
    try {
      // 삭제목록(_remove_tiers) 동봉 → 백엔드가 해당 플랜 제거.
      await apiClient.put<Config>("/billing/admin/config", { body: { ...cfg, _remove_tiers: removed }, useMock: false });
      setRemoved([]);
      setMsg("저장되었습니다. 즉시 적용됩니다.");
    } catch {
      setMsg("저장 실패 — 관리자 권한을 확인하세요.");
    } finally { setSaving(false); }
  };

  if (denied) return <div className="p-8 text-[var(--text-secondary)]">관리자 권한이 필요합니다.</div>;
  if (loading || !cfg) return <div className="p-8 text-[var(--text-secondary)]">불러오는 중…</div>;

  const Field = ({ label, value, onChange, suffix = "원" }: { label: string; value: number; onChange: (v: string) => void; suffix?: string }) => (
    <label className="flex items-center justify-between gap-3 rounded-lg bg-[var(--surface-muted)] px-3 py-2">
      <span className="text-xs text-[var(--text-secondary)]">{label}</span>
      <span className="flex items-center gap-1">
        <input value={value ?? 0} onChange={(e) => onChange(e.target.value)}
          className="cc-num w-24 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2 py-1 text-right text-sm font-bold text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-strong)]" />
        <span className="text-[10px] text-[var(--text-hint)]">{suffix}</span>
      </span>
    </label>
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-20">
      <div className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-lg)]">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 flex items-end justify-between gap-4">
          <div className="space-y-1.5">
            <span className="cc-meta">BILLING · RATE CONTROL</span>
            <h1 className="text-2xl font-black text-[var(--text-primary)]">과금 금액 설정 <span className="text-[var(--accent-strong)]">_</span></h1>
            <p className="text-sm text-[var(--text-secondary)]">구독 등급·서비스 사용료·단계별 과금 금액을 수정합니다 (관리자 전용, 즉시 적용)</p>
          </div>
          <button onClick={save} disabled={saving}
            className="rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] px-6 py-2.5 text-sm font-black text-white disabled:opacity-50">
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
      {msg && <div className="rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] px-4 py-2.5 text-sm text-[var(--text-secondary)]">{msg}</div>}

      {/* 구독 플랜 (과금설정 통합) — 추가·삭제·이름·월요금·할증배수 */}
      <section className="cc-panel">
        <header className="cc-panel__head flex items-center justify-between">
          <div>
            <span className="cc-meta">SUBSCRIPTION · PLANS</span>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">구독 플랜 관리 (추가·삭제·요금)</h2>
          </div>
          <button onClick={addPlan} className="rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-bold text-[var(--accent-strong)] hover:opacity-90">
            + 플랜 추가
          </button>
        </header>
        <div className="cc-panel__body">
          <div className="grid gap-4 md:grid-cols-3">
            {Object.keys(cfg.tiers).map((t) => (
              <div key={t} className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <input
                    value={cfg.tiers[t].label ?? TIER_LABELS[t] ?? t}
                    onChange={(e) => setTierLabel(t, e.target.value)}
                    className="w-full rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2 py-1 text-sm font-bold text-[var(--accent-strong)] focus:outline-none focus:border-[var(--accent-strong)]"
                    placeholder="플랜 이름"
                  />
                  {!PROTECTED.has(t) && (
                    <button onClick={() => deletePlan(t)} title="플랜 삭제"
                      className="shrink-0 rounded-md border border-rose-500/30 px-2 py-1 text-[11px] font-bold text-rose-400 hover:bg-rose-500/10">
                      삭제
                    </button>
                  )}
                </div>
                <p className="text-[10px] text-[var(--text-hint)]">식별자: {t}{PROTECTED.has(t) ? " · 시스템" : ""}</p>
                <Field label="월 요금" value={cfg.tiers[t].fee_krw} onChange={(v) => setTier(t, "fee_krw", v)} />
                <Field label="기본 사용량(포함)" value={cfg.tiers[t].base_quota_krw ?? 0} onChange={(v) => setTier(t, "base_quota_krw", v)} />
                <Field label="초과 마진율(내부)" value={cfg.tiers[t].overage_margin_pct ?? 0} onChange={(v) => setTier(t, "overage_margin_pct", v)} suffix="%" />
              </div>
            ))}
          </div>
          <p className="text-[10px] text-[var(--text-hint)] mt-3">※ 플랜 핵심: <b>기본 사용량(포함)</b>까지 무료, 초과분은 <b>원가 × (1+초과 마진율)</b>로 과금. 콘텐츠/서비스 이용료(아래)는 전 플랜 동일. 마진율은 내부 정책(사용자 미노출). 시스템 플랜(free·guest·super_admin) 삭제 불가.</p>
        </div>
      </section>

      {/* 서비스 사용료 */}
      <section className="cc-panel">
        <header className="cc-panel__head">
          <span className="cc-meta">SERVICE · FEE</span>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">서비스 사용료 (LLM 과금과 별개)</h2>
        </header>
        <div className="cc-panel__body">
          <div className="grid gap-2 md:grid-cols-2">
            <Field label="프로젝트 생성" value={cfg.service_fees.project_create} onChange={(v) => setSvc("project_create", v)} />
            <Field label="토지분석(구독자)" value={cfg.service_fees.land_analysis} onChange={(v) => setSvc("land_analysis", v)} />
            <Field label="분양현장 생성" value={cfg.service_fees.sales_provision ?? 0} onChange={(v) => setSvc("sales_provision", v)} />
          </div>
        </div>
      </section>

      {/* 진행 단계 단계별 */}
      <section className="cc-panel">
        <header className="cc-panel__head">
          <span className="cc-meta">PIPELINE · STAGE</span>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">진행 단계 단계별 과금</h2>
        </header>
        <div className="cc-panel__body">
          <div className="grid gap-2 md:grid-cols-2">
            {Object.keys(cfg.service_fees.stages).map((s) => (
              <Field key={s} label={STAGE_LABELS[s] || s} value={cfg.service_fees.stages[s]} onChange={(v) => setStage(s, v)} />
            ))}
          </div>
        </div>
      </section>

      {/* 비구독 무료/초과 */}
      <section className="cc-panel">
        <header className="cc-panel__head">
          <span className="cc-meta">FREE TIER · QUOTA</span>
          <h2 className="text-sm font-bold text-[var(--text-primary)]">비구독 정책 (토지분석)</h2>
        </header>
        <div className="cc-panel__body">
          <div className="grid gap-2 md:grid-cols-2">
            <Field label="일반회원 무료 횟수" value={cfg.free_tier.analysis_quota.free} onChange={(v) => setFree("analysis_quota", "free", v)} suffix="회" />
            <Field label="일반회원 초과 단가" value={cfg.free_tier.analysis_fee.free} onChange={(v) => setFree("analysis_fee", "free", v)} />
            <Field label="비회원 무료 횟수" value={cfg.free_tier.analysis_quota.guest} onChange={(v) => setFree("analysis_quota", "guest", v)} suffix="회" />
            <Field label="비회원 초과 단가" value={cfg.free_tier.analysis_fee.guest} onChange={(v) => setFree("analysis_fee", "guest", v)} />
          </div>
        </div>
      </section>
    </div>
  );
}
