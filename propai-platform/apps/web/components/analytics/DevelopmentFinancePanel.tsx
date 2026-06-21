"use client";

/**
 * 개발금융(PF·브릿지·이자·LTV·DSCR) 패널.
 * 수지(P2)에서 흘러온 총사업비·공사비·토지를 컨텍스트에서 자동주입해 진입 시 자동 산출한다.
 * /api/v2/feasibility/development-finance(finance_cost_engine 재사용)로 PF대출·금리·총이자·
 * LTV·DSCR·자기자본비율을 반환. 수지 미완료면 정직하게 안내(무목업).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type LoanLeg = {
  amount_won: number;
  rate: number;
  interest_won: number;
  guarantee_fee_won?: number;
  arrangement_fee_won?: number;
  months: number;
  total_cost_won: number;
};

type DevelopmentFinanceResult = {
  total_project_cost_won: number;
  equity_won: number;
  equity_ratio: number;
  pf_loan: LoanLeg;
  bridge_loan: LoanLeg;
  total_debt_won: number;
  ltv: number;
  dscr: number | null;
  annual_debt_service_won: number;
  total_financing_cost_won: number;
};

const eok = (won: number | null | undefined) =>
  won != null
    ? `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`
    : "—";

const pct = (ratio: number | null | undefined) =>
  ratio != null ? `${(ratio * 100).toFixed(1)}%` : "—";

export function DevelopmentFinancePanel() {
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const cost = useProjectContextStore((s) => s.costData);
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const markFinanceUpdated = useProjectContextStore((s) => s.markFinanceUpdated);

  const totalCostWon = feas?.totalCostWon ?? null;
  const constructionWon = cost?.totalConstructionCostWon ?? null;
  // 토지비: 부지 추정시세 우선, 없으면 (총사업비 - 공사비) 근사
  const landWon =
    site?.estimatedValue ??
    (totalCostWon != null && constructionWon != null
      ? Math.max(0, totalCostWon - constructionWon)
      : null);
  // 연 NOI: 수지 매출 기반 단순 근사(임대형 추정용). 없으면 미산정(분양형으로 간주).
  const annualNoiWon =
    feas?.totalRevenueWon != null ? Math.round(feas.totalRevenueWon * 0.04) : null;

  const [result, setResult] = useState<DevelopmentFinanceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // isStale 가드: 마지막 산출에 사용한 총사업비를 기억해 동일값 재호출(무한루프) 방지.
  const lastComputedCostRef = useRef<number | null>(null);

  const compute = useCallback(async () => {
    if (totalCostWon == null || totalCostWon <= 0) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiClient.postV2<DevelopmentFinanceResult>(
        "/feasibility/development-finance",
        {
          body: {
            total_project_cost_won: totalCostWon,
            equity_ratio: 0.3,
            land_cost_won: landWon ?? undefined,
            construction_cost_won: constructionWon ?? undefined,
            annual_noi_won: annualNoiWon ?? undefined,
          },
        },
      );
      setResult(r);
      lastComputedCostRef.current = totalCostWon;
      // 모세혈관: finance updatedAt stamp → 수지·공사비 갱신 대비 staleness 추적 활성화.
      markFinanceUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "개발금융 산정 실패");
    } finally {
      setBusy(false);
    }
  }, [totalCostWon, landWon, constructionWon, annualNoiWon, markFinanceUpdated]);

  // 진입 시 자동 산출 + 수지 총사업비 갱신(isStale) 시 자동 재계산. 동일값이면 스킵.
  useEffect(() => {
    if (totalCostWon == null || totalCostWon <= 0) return;
    if (lastComputedCostRef.current === totalCostWon) return;
    void compute();
  }, [totalCostWon, compute]);

  const hasFeasibility = totalCostWon != null && totalCostWon > 0;

  return (
    <Card>
      <CardContent className="p-6 space-y-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">
              개발금융 (PF·이자·DSCR)
            </h3>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              수지분석의 총사업비·공사비·토지를 자동 연동해 PF대출·금리·총이자·LTV·DSCR을
              산출합니다. 수지 갱신 시 자동 재계산됩니다.
            </p>
          </div>
          {hasFeasibility ? (
            <button
              type="button"
              onClick={() => void compute()}
              disabled={busy}
              className="h-9 shrink-0 rounded-lg border border-[var(--border)] px-4 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50"
            >
              {busy ? "산정 중…" : "재계산"}
            </button>
          ) : null}
        </div>

        {!hasFeasibility ? (
          <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
            수지분석(총사업비)이 아직 없습니다. <b>수지분석을 완료하면</b> 총사업비가 연동되어
            개발금융(PF·이자·LTV·DSCR)이 <b>자동 산출</b>됩니다.
          </div>
        ) : null}

        {error ? (
          <p className="text-xs font-semibold text-red-500">{error}</p>
        ) : null}

        {result ? (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Tile label="PF 대출액" value={eok(result.pf_loan.amount_won)} accent />
              <Tile label="PF 금리(연)" value={pct(result.pf_loan.rate)} />
              <Tile
                label="총 이자"
                value={eok(
                  result.pf_loan.interest_won + result.bridge_loan.interest_won,
                )}
                sub={`금융비 합계 ${eok(result.total_financing_cost_won)}`}
              />
              <Tile label="LTV" value={pct(result.ltv)} />
              <Tile
                label="DSCR"
                value={result.dscr != null ? result.dscr.toFixed(2) : "산정불가"}
                sub={
                  result.dscr == null ? "임대 NOI 없음(분양형)" : undefined
                }
              />
              <Tile label="자기자본 비율" value={pct(result.equity_ratio)} />
              <Tile label="자기자본" value={eok(result.equity_won)} />
              <Tile
                label="브릿지 대출"
                value={eok(result.bridge_loan.amount_won)}
                sub={`금리 ${pct(result.bridge_loan.rate)}`}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <p className="text-[11px] font-bold uppercase tracking-widest text-[var(--text-hint)]">
                  본PF
                </p>
                <dl className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                  <Row k="대출액" v={eok(result.pf_loan.amount_won)} />
                  <Row k="금리(연)" v={pct(result.pf_loan.rate)} />
                  <Row k={`이자(${result.pf_loan.months}개월)`} v={eok(result.pf_loan.interest_won)} />
                  <Row k="보증수수료" v={eok(result.pf_loan.guarantee_fee_won)} />
                  <Row k="합계" v={eok(result.pf_loan.total_cost_won)} />
                </dl>
              </div>
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <p className="text-[11px] font-bold uppercase tracking-widest text-[var(--text-hint)]">
                  브릿지론
                </p>
                <dl className="mt-2 space-y-1 text-xs text-[var(--text-secondary)]">
                  <Row k="대출액" v={eok(result.bridge_loan.amount_won)} />
                  <Row k="금리(연)" v={pct(result.bridge_loan.rate)} />
                  <Row k={`이자(${result.bridge_loan.months}개월)`} v={eok(result.bridge_loan.interest_won)} />
                  <Row k="주선수수료" v={eok(result.bridge_loan.arrangement_fee_won)} />
                  <Row k="합계" v={eok(result.bridge_loan.total_cost_won)} />
                </dl>
              </div>
            </div>

            <p className="text-[11px] leading-5 text-[var(--text-hint)]">
              총사업비 {eok(result.total_project_cost_won)} 기준. 금융비는 만기일시상환(복리)·
              표준 수수료율로 산정되며, 자금구조는 자기자본 30% 가정입니다.
              {result.dscr != null ? (
                <> DSCR(=연 NOI ÷ 연 이자 {eok(result.annual_debt_service_won)}, 부채상환 근사)은 임대형 NOI를
                  매출의 약 4%(개략 NOI 환산)로 추정한 기준이며, 분양형은 별도 현금흐름(DCF)을 참고하세요.</>
              ) : (
                <> DSCR은 임대 NOI(매출의 약 4% 개략 추정)가 없어 분양형으로 간주해 미산정했습니다 — 분양형은
                  별도 현금흐름(DCF)을 참고하세요.</>
              )}
            </p>
          </>
        ) : hasFeasibility && busy ? (
          <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm text-[var(--text-secondary)]">
            개발금융 자동 산출 중…
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
        {label}
      </p>
      <p
        className={`mt-1 text-lg font-[1000] ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}
      >
        {value}
      </p>
      {sub ? <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt>{k}</dt>
      <dd className="font-semibold text-[var(--text-primary)]">{v}</dd>
    </div>
  );
}
