"use client";

import { useDeferredValue, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@propai/ui";
import type {
  BimElementStatus,
  BimQuantityItem,
} from "@/mocks/module-data";

type IFCQuantityTableProps = {
  quantities: BimQuantityItem[];
  labels: {
    title: string;
    categoryLabel: string;
    quantityLabel: string;
    progressLabel: string;
    statusLabels: Record<BimElementStatus, string>;
  };
};

export function IFCQuantityTable({
  quantities,
  labels,
}: IFCQuantityTableProps) {
  const categories = useMemo(
    () => ["All", ...new Set(quantities.map((item) => item.category))],
    [quantities],
  );
  const [selectedCategory, setSelectedCategory] = useState("All");
  const deferredCategory = useDeferredValue(selectedCategory);

  const filtered = useMemo(() => {
    if (deferredCategory === "All") {
      return quantities;
    }

    return quantities.filter((item) => item.category === deferredCategory);
  }, [deferredCategory, quantities]);

  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 pt-0">
        <div className="flex flex-wrap gap-2">
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              onClick={() => setSelectedCategory(category)}
              className={`rounded-full border px-4 py-2 text-sm font-medium transition ${
                selectedCategory === category
                  ? "border-[var(--text-primary)] bg-[var(--foreground)] text-[#ffffff]"
                  : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)]"
              }`}
            >
              {category}
            </button>
          ))}
        </div>
        <div className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--line)]">
          <table className="min-w-full divide-y divide-[var(--line)] bg-[var(--surface-soft)] text-left text-sm">
            <thead className="bg-[var(--surface-muted)] text-[var(--text-secondary)]">
              <tr>
                <th className="px-4 py-3 font-medium">{labels.categoryLabel}</th>
                <th className="px-4 py-3 font-medium">Item</th>
                <th className="px-4 py-3 font-medium">{labels.quantityLabel}</th>
                <th className="px-4 py-3 font-medium">{labels.progressLabel}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--line)]">
              {filtered.map((item) => (
                <tr key={item.id}>
                  <td className="px-4 py-4 text-[var(--text-secondary)]">
                    {item.category}
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-[var(--text-primary)]">
                        {item.name}
                      </span>
                      <span className="rounded-full bg-[var(--surface-muted)] px-3 py-1 text-xs font-medium text-[var(--text-secondary)]">
                        {labels.statusLabels[item.status]}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-[var(--text-secondary)]">
                    {item.quantity.toLocaleString()} {item.unit}
                  </td>
                  <td className="px-4 py-4 text-[var(--text-secondary)]">
                    {item.progress}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
