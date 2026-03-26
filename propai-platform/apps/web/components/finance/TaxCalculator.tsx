"use client";

import { useMemo, useState } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle, Input } from "@propai/ui";
import type { TaxScenario } from "@/mocks/module-data";

type TaxCalculatorProps = {
  locale: string;
  initialScenario: TaxScenario;
  labels: {
    title: string;
    description: string;
    acquisitionLabel: string;
    saleLabel: string;
    deductibleLabel: string;
    holdingYearsLabel: string;
    acquisitionTaxLabel: string;
    capitalGainsTaxLabel: string;
    localTaxLabel: string;
    totalTaxLabel: string;
    netLabel: string;
    resetLabel: string;
  };
};

type FormState = {
  acquisitionPrice: string;
  salePrice: string;
  deductibleCost: string;
  holdingYears: string;
};

function formatCurrency(locale: string, amount: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

function toPositiveNumber(value: string) {
  const normalized = Number(value);

  return Number.isFinite(normalized) && normalized > 0 ? normalized : 0;
}

export function TaxCalculator({
  locale,
  initialScenario,
  labels,
}: TaxCalculatorProps) {
  const initialFormState: FormState = {
    acquisitionPrice: String(initialScenario.acquisitionPrice),
    salePrice: String(initialScenario.salePrice),
    deductibleCost: String(initialScenario.deductibleCost),
    holdingYears: String(initialScenario.holdingYears),
  };

  const [form, setForm] = useState<FormState>(initialFormState);

  const calculated = useMemo(() => {
    const acquisitionPrice = toPositiveNumber(form.acquisitionPrice);
    const salePrice = toPositiveNumber(form.salePrice);
    const deductibleCost = toPositiveNumber(form.deductibleCost);
    const holdingYears = toPositiveNumber(form.holdingYears);
    const taxableGain = Math.max(salePrice - acquisitionPrice - deductibleCost, 0);
    const acquisitionTax = acquisitionPrice * 0.011;
    const capitalGainsRate = holdingYears >= 3 ? 0.18 : 0.22;
    const capitalGainsTax = taxableGain * capitalGainsRate;
    const localTax = capitalGainsTax * 0.1;
    const totalTax = acquisitionTax + capitalGainsTax + localTax;
    const netAmount = salePrice - totalTax;

    return {
      acquisitionTax,
      capitalGainsTax,
      localTax,
      totalTax,
      netAmount,
    };
  }, [form]);

  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <p className="text-sm leading-7 text-[rgba(19,33,47,0.72)]">
          {labels.description}
        </p>
      </CardHeader>
      <CardContent className="grid gap-5 pt-0 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="grid gap-4">
          <label className="grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]">
            {labels.acquisitionLabel}
            <Input
              inputMode="numeric"
              value={form.acquisitionPrice}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  acquisitionPrice: event.target.value,
                }))
              }
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]">
            {labels.saleLabel}
            <Input
              inputMode="numeric"
              value={form.salePrice}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  salePrice: event.target.value,
                }))
              }
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]">
            {labels.deductibleLabel}
            <Input
              inputMode="numeric"
              value={form.deductibleCost}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  deductibleCost: event.target.value,
                }))
              }
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[rgba(19,33,47,0.78)]">
            {labels.holdingYearsLabel}
            <Input
              inputMode="numeric"
              value={form.holdingYears}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  holdingYears: event.target.value,
                }))
              }
            />
          </label>
          <Button
            variant="secondary"
            onClick={() => {
              setForm(initialFormState);
            }}
          >
            {labels.resetLabel}
          </Button>
        </div>
        <div className="grid gap-3">
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
              {labels.acquisitionTaxLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[rgba(19,33,47,0.78)]">
              {formatCurrency(locale, calculated.acquisitionTax)}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
              {labels.capitalGainsTaxLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[rgba(19,33,47,0.78)]">
              {formatCurrency(locale, calculated.capitalGainsTax)}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
              {labels.localTaxLabel}
            </p>
            <p className="mt-3 text-sm font-semibold text-[rgba(19,33,47,0.78)]">
              {formatCurrency(locale, calculated.localTax)}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-white/80 px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
              {labels.totalTaxLabel}
            </p>
            <p className="mt-3 text-lg font-semibold text-[var(--spot)]">
              {formatCurrency(locale, calculated.totalTax)}
            </p>
          </div>
          <div className="rounded-[1.25rem] border border-[var(--line)] bg-[rgba(14,116,144,0.08)] px-4 py-4">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.48)]">
              {labels.netLabel}
            </p>
            <p className="mt-3 text-lg font-semibold text-[var(--foreground)]">
              {formatCurrency(locale, calculated.netAmount)}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
