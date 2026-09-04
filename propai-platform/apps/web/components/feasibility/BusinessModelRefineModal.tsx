"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { NumberInput } from "@/components/common/NumberInput";
import type { RecommendedModel } from "./AutoRecommendPanel";

/* ── Types ── */

interface RefinedParams {
  total_gfa_sqm: number;
  total_households: number;
  avg_sale_price_per_pyeong: number;
  equity_won: number;
  project_months: number;
  discount_rate: number;
}

interface BusinessModelRefineModalProps {
  model: RecommendedModel;
  equity: number; // 억원
  onConfirm: (params: RefinedParams) => void;
  onClose: () => void;
}

/* ── Component ── */

export function BusinessModelRefineModal({
  model,
  equity,
  onConfirm,
  onClose,
}: BusinessModelRefineModalProps) {
  const [totalGfa, setTotalGfa] = useState(model.total_gfa_sqm.toString());
  const [totalHouseholds, setTotalHouseholds] = useState(model.total_households.toString());
  const [avgSalePrice, setAvgSalePrice] = useState(model.avg_sale_price_per_pyeong.toString());
  const [equityEok, setEquityEok] = useState(equity.toString());
  const [projectMonths, setProjectMonths] = useState(model.project_months.toString());
  const [discountRate, setDiscountRate] = useState("8");

  const handleSubmit = () => {
    onConfirm({
      total_gfa_sqm: parseFloat(totalGfa) || 0,
      total_households: parseInt(totalHouseholds, 10) || 0,
      avg_sale_price_per_pyeong: parseFloat(avgSalePrice) || 0,
      equity_won: (parseFloat(equityEok) || 0) * 100_000_000,
      project_months: parseInt(projectMonths, 10) || 36,
      discount_rate: (parseFloat(discountRate) || 8) / 100,
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
        className="relative w-full max-w-lg overflow-hidden rounded-[var(--radius-xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-2xl"
      >
        {/* Header */}
        <div className="border-b border-[var(--line)] p-8 pb-6">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xl">{"\uD83D\uDCDD"}</span>
            <h3 className="text-xl font-[1000] tracking-tight text-[var(--text-primary)]">
              사업모델 상세 설정
            </h3>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            <span className="font-[800] text-[var(--accent-strong)]">{model.type_code}</span>
            {" "}{model.type_name} — AI 추천값을 기반으로 세부 조건을 조정할 수 있습니다.
          </p>
        </div>

        {/* Body */}
        <div className="p-8 space-y-6">
          {/* Section: 기본 정보 */}
          <div className="space-y-4">
            <h4 className="label-caps text-[var(--text-hint)]">
              기본 정보
            </h4>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FieldInput
                label="총연면적"
                value={totalGfa}
                onChange={setTotalGfa}
                unit="m\u00B2"
                comma
                decimal
              />
              <FieldInput
                label="총세대수"
                value={totalHouseholds}
                onChange={setTotalHouseholds}
                unit="세대"
                comma
              />
              <FieldInput
                label="평균분양가"
                value={avgSalePrice}
                onChange={setAvgSalePrice}
                unit="만원/평"
                comma
                className="sm:col-span-2"
              />
            </div>
          </div>

          {/* Section: 사업비 조정 */}
          <div className="space-y-4">
            <h4 className="label-caps text-[var(--text-hint)]">
              사업비 조정
            </h4>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FieldInput
                label="자기자본"
                value={equityEok}
                onChange={setEquityEok}
                unit="억원"
                comma
                decimal
              />
              <FieldInput
                label="사업기간"
                value={projectMonths}
                onChange={setProjectMonths}
                unit="개월"
                type="number"
              />
              <FieldInput
                label="할인율"
                value={discountRate}
                onChange={setDiscountRate}
                unit="%"
                type="number"
              />
            </div>
          </div>

          {/* AI Tip */}
          <div className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)]/50 p-5 flex gap-3">
            <span className="text-lg shrink-0">{"\uD83D\uDCA1"}</span>
            <div className="text-sm text-[var(--text-secondary)]">
              <span className="font-[800] text-[var(--accent-strong)]">AI 추천:</span>{" "}
              분양가를{" "}
              <span className="font-[800] text-[var(--text-primary)]">
                {(parseFloat(avgSalePrice) * 1.08).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}만원
              </span>
              으로 상향하면 수익률{" "}
              <span className="font-[800] text-emerald-400">2.3%p 향상</span> 가능
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-4 border-t border-[var(--line)] p-8 pt-6">
          <button
            onClick={onClose}
            className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-6 py-3 text-sm font-[800] text-[var(--text-secondary)] transition-all hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-[900] text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 hover:shadow-lg"
          >
            수지분석으로 진행 {"\u2192"}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

/* ── Field Input Sub-component ── */

function FieldInput({
  label,
  value,
  onChange,
  unit,
  type = "text",
  className = "",
  comma = false,
  decimal = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  unit: string;
  type?: string;
  className?: string;
  comma?: boolean;
  decimal?: boolean;
}) {
  const inputCls =
    "w-full rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 pr-16 text-sm font-[700] text-[var(--text-primary)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/20 transition-all tabular-nums";
  return (
    <div className={className}>
      <label className="mb-1.5 block text-[10px] font-[800] text-[var(--text-hint)] tracking-wider">
        {label}
      </label>
      <div className="relative">
        {comma ? (
          <NumberInput
            allowDecimal={decimal}
            value={value === "" ? null : Number(value)}
            onChange={(n) => onChange(n != null ? String(n) : "")}
            className={inputCls}
          />
        ) : (
          <input
            type={type}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className={inputCls}
          />
        )}
        <span className="absolute right-4 top-1/2 -translate-y-1/2 text-xs font-bold text-[var(--text-hint)]">
          {unit}
        </span>
      </div>
    </div>
  );
}
