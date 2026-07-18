"use client";

/**
 * AnalysisDiffTable — 분석 히스토리 두 버전 간 핵심 지표 비교 표(sa-di 토큰 기반).
 *
 * 타입별 키맵(DIFF_FIELD_MAP)에 정의된 필드만 old/new/Δ로 나열한다. 결측값은 "—"(무날조 —
 * 값이 없다고 0으로 채우지 않는다). 수치 필드만 증감(Δ)을 계산하고, 텍스트 필드(용도지역·등급·
 * 판정 등)는 값만 나열한다(증감 개념이 없음).
 *
 * getFieldPath/formatFieldValue는 AnalysisHistoryCard(항목 열람 시 단건 요약)와 공유한다 —
 * 표시 규칙을 두 곳에 중복 정의하지 않는다.
 */

import { formatManwon } from "@/lib/formatters";

export type DiffAnalysisType = "feasibility" | "regulation" | "market_report" | "permit_ai";

export type DiffFieldFmt = "number" | "percent" | "won" | "manwon" | "text";

export type DiffFieldDef = {
  key: string; // payload 내 경로(점 표기 — 예: "limits.far.effective")
  label: string;
  unit?: string;
  fmt: DiffFieldFmt;
  /**
   * effective 값이 old/new 모두 결측일 때만 추가로 표시할 폴백 필드(법정 한도) — 자연녹지 등
   * 실효치가 산출되지 않는 부지도 있어, 그런 경우 "——"만 찍고 끝나지 않도록 법정 값을 별도
   * 행으로 보여준다(무날조 — 값이 있을 때만 행을 추가, 없으면 폴백도 "—").
   */
  fallback?: { key: string; label: string };
};

/** 분석 유형별 비교 항목 키맵 — 백엔드 원장 payload 요약 필드와 1:1. */
export const DIFF_FIELD_MAP: Record<DiffAnalysisType, DiffFieldDef[]> = {
  feasibility: [
    { key: "profit_rate_pct", label: "수익률", unit: "%", fmt: "percent" },
    { key: "npv_won", label: "NPV", fmt: "won" },
    { key: "total_revenue_won", label: "총 매출", fmt: "won" },
    { key: "net_profit_won", label: "순이익", fmt: "won" },
    { key: "grade", label: "등급", fmt: "text" },
  ],
  regulation: [
    { key: "zone_type", label: "용도지역", fmt: "text" },
    // ★버그 수정: 과거 key="limits.far"(dict 자체)를 percent fmt로 렌더해 "[object Object]"가
    //   찍혔다. limits.{far,bcr}는 {legal,ordinance,effective} dict이므로 leaf인 .effective로
    //   내려간다(실효 한도 — 조례반영). effective가 없으면(old/new 모두) .legal 폴백 행을 추가한다.
    { key: "limits.far.effective", label: "실효 용적률", unit: "%", fmt: "percent", fallback: { key: "limits.far.legal", label: "법정 용적률" } },
    { key: "limits.bcr.effective", label: "실효 건폐율", unit: "%", fmt: "percent", fallback: { key: "limits.bcr.legal", label: "법정 건폐율" } },
    { key: "parcel_count", label: "필지 수", unit: "필지", fmt: "number" },
  ],
  market_report: [
    { key: "trade_count", label: "거래 건수", unit: "건", fmt: "number" },
    { key: "avg_price_10k", label: "평균 거래가", fmt: "manwon" },
    { key: "parcel_count", label: "필지 수", unit: "필지", fmt: "number" },
  ],
  permit_ai: [
    { key: "verdict", label: "판정", fmt: "text" },
    { key: "development_methods", label: "개발방식", fmt: "text" },
  ],
};

/** 점 표기 경로("a.b.c")로 payload 값을 안전 조회. 중간 경로 부재 시 undefined(예외 던지지 않음). */
export function getFieldPath(payload: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object" && key in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[key];
    }
    return undefined;
  }, payload);
}

/** 결측/비수치 텍스트 표시 — 배열은 ", " 조인, 그 외는 String() (결측은 "—", 가짜값 금지). */
function textOf(v: unknown): string {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.length > 0 ? v.join(", ") : "—";
  return String(v);
}

/** 단건 값 표기(단위 포함). fmt에 따라 mono 수치·통화 단위를 결정한다. */
export function formatFieldValue(v: unknown, fmt: DiffFieldFmt, unit?: string): string {
  if (v == null || v === "") return "—";
  if (fmt === "text") return textOf(v);
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return textOf(v);
  if (fmt === "won") return `${Math.round(n).toLocaleString("ko-KR")}원`;
  if (fmt === "manwon") return formatManwon(n);
  if (fmt === "percent") return `${n.toFixed(1)}${unit ?? "%"}`;
  return `${n.toLocaleString("ko-KR")}${unit ?? ""}`;
}

type Delta = { text: string; tone: "up" | "down" | "flat" };

/** 신구 값의 증감(Δ) — 수치 필드만. 텍스트 필드는 null(증감 개념 없음). */
function computeDelta(oldV: unknown, newV: unknown, fmt: DiffFieldFmt): Delta | null {
  if (fmt === "text") return null;
  const oldN = typeof oldV === "number" ? oldV : Number(oldV);
  const newN = typeof newV === "number" ? newV : Number(newV);
  if (!Number.isFinite(oldN) || !Number.isFinite(newN)) return null; // 둘 중 하나라도 결측이면 증감 계산 불가
  const d = newN - oldN;
  if (d === 0) return { text: "±0", tone: "flat" };
  const sign = d > 0 ? "+" : "-";
  const abs = Math.abs(d);
  let text: string;
  if (fmt === "won") text = `${sign}${Math.round(abs).toLocaleString("ko-KR")}원`;
  else if (fmt === "manwon") text = `${sign}${formatManwon(abs)}`;
  else if (fmt === "percent") text = `${sign}${abs.toFixed(1)}%p`;
  else text = `${sign}${abs.toLocaleString("ko-KR")}`;
  return { text, tone: d > 0 ? "up" : "down" };
}

const TONE_COLOR: Record<Delta["tone"], string> = {
  up: "var(--status-success)",
  down: "var(--status-error)",
  flat: "var(--text-secondary)",
};

export type DiffEntry = { version: number; created_at: string; payload: Record<string, unknown> };

export function AnalysisDiffTable({
  analysisType,
  oldEntry,
  newEntry,
}: {
  analysisType: DiffAnalysisType;
  oldEntry: DiffEntry;
  newEntry: DiffEntry;
}) {
  const fields = DIFF_FIELD_MAP[analysisType] ?? [];

  if (fields.length === 0) {
    return <p className="sa-di-empty">이 분석 유형은 비교 항목이 정의되어 있지 않습니다.</p>;
  }

  /** 한 행(항목·old·new·Δ) — 주 필드/폴백 필드 공용 렌더(중복 정의 금지). */
  const renderRow = (key: string, label: string, oldV: unknown, newV: unknown, fmt: DiffFieldFmt, unit?: string) => {
    const delta = computeDelta(oldV, newV, fmt);
    return (
      <tr key={key}>
        <td>{label}</td>
        <td className="sa-di-num">{formatFieldValue(oldV, fmt, unit)}</td>
        <td className="sa-di-num">{formatFieldValue(newV, fmt, unit)}</td>
        <td className="sa-di-num" style={{ color: delta ? TONE_COLOR[delta.tone] : "var(--text-hint)" }}>
          {delta ? delta.text : "—"}
        </td>
      </tr>
    );
  };

  return (
    <div className="overflow-x-auto">
      <table className="sa-di-table">
        <thead>
          <tr>
            <th>항목</th>
            <th className="sa-di-num">v{oldEntry.version}</th>
            <th className="sa-di-num">v{newEntry.version}</th>
            <th className="sa-di-num">증감(Δ)</th>
          </tr>
        </thead>
        <tbody>
          {fields.flatMap((f) => {
            const oldV = getFieldPath(oldEntry.payload, f.key);
            const newV = getFieldPath(newEntry.payload, f.key);
            const rows = [renderRow(f.key, f.label, oldV, newV, f.fmt, f.unit)];
            // 폴백(예: 실효 용적률 결측 시 법정 용적률) — old/new 모두 결측일 때만 추가 행.
            if (f.fallback && oldV == null && newV == null) {
              const oldFb = getFieldPath(oldEntry.payload, f.fallback.key);
              const newFb = getFieldPath(newEntry.payload, f.fallback.key);
              rows.push(renderRow(f.fallback.key, f.fallback.label, oldFb, newFb, f.fmt, f.unit));
            }
            return rows;
          })}
        </tbody>
      </table>
    </div>
  );
}
