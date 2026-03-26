"use client";

import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useComplianceCheck } from "@/hooks/use-compliance-check";
import { useCadStore } from "@/store/use-cad-store";
import type { ComplianceCheckResponse } from "@/components/cad/types";

type ComplianceHudProps = {
  projectId: string;
};

type MetricRowProps = {
  label: string;
  metric: { current: number; limit: number; pass: boolean } | undefined;
  unit?: string;
};

function MetricRow({ label, metric, unit = "" }: MetricRowProps) {
  if (!metric) return null;
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-[rgba(19,33,47,0.72)]">{label}</span>
      <div className="flex items-center gap-2">
        <span
          className={`text-xs font-semibold ${metric.pass ? "text-emerald-600" : "text-red-600"}`}
        >
          {metric.current.toFixed(1)}
          {unit}
        </span>
        <span className="text-[10px] text-[rgba(19,33,47,0.44)]">
          / {metric.limit.toFixed(1)}
          {unit}
        </span>
        <span
          className={`inline-block h-2 w-2 rounded-full ${metric.pass ? "bg-emerald-500" : "bg-red-500"}`}
          aria-label={metric.pass ? "통과" : "위반"}
        />
      </div>
    </div>
  );
}

function ViolationList({
  violations,
}: {
  violations: ComplianceCheckResponse["violations"];
}) {
  if (violations.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1" aria-label="법규 위반 목록">
      {violations.map((v, i) => (
        <li
          key={`${v.violation_type}-${i}`}
          className={`rounded-lg px-2.5 py-1.5 text-xs ${
            v.severity === "error"
              ? "bg-red-50 text-red-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          <span className="font-medium">
            [{v.severity === "error" ? "오류" : "경고"}]
          </span>{" "}
          {v.message}
        </li>
      ))}
    </ul>
  );
}

export function ComplianceHud({ projectId }: ComplianceHudProps) {
  const designPayload = useCadStore((s) => s.toDesignPayload());
  const stablePayload = useMemo(
    () => designPayload,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(designPayload)],
  );

  const { data, isLoading, error } = useComplianceCheck(
    projectId,
    stablePayload,
  );

  const hasElements = stablePayload.points.length > 0;

  if (!hasElements) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="compliance-hud"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.2 }}
        className="absolute right-3 top-3 z-10 w-64 rounded-2xl border border-[var(--line)] bg-[var(--surface)]/95 p-4 shadow-lg backdrop-blur-sm"
        role="status"
        aria-label="건축법규 검증 현황"
        aria-live="polite"
      >
        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase tracking-widest text-[rgba(19,33,47,0.56)]">
            Compliance
          </h4>
          {isLoading && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)] border-t-transparent" aria-label="검증 중" />
          )}
          {data && !isLoading && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                data.is_compliant
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-red-100 text-red-700"
              }`}
            >
              {data.is_compliant ? "적합" : "위반"}
            </span>
          )}
        </div>

        {/* 에러 표시 */}
        {error && (
          <p className="mt-2 text-xs text-red-600" role="alert">
            {error}
          </p>
        )}

        {/* 메트릭 */}
        {data && !error && (
          <div className="mt-3 space-y-2">
            <MetricRow label="건폐율" metric={data.building_coverage_ratio} unit="%" />
            <MetricRow label="용적률" metric={data.floor_area_ratio} unit="%" />
            <MetricRow label="최고 높이" metric={data.max_height} unit="m" />
            <MetricRow label="이격거리" metric={data.setback} unit="m" />
            <MetricRow label="일조권" metric={data.sunlight} unit="h" />
            <ViolationList violations={data.violations} />
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
