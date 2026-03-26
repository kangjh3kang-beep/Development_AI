"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { motion } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { DigitalTwinDashboardData } from "@/components/cad/types";

const SENSOR_COLORS: Record<string, string> = {
  temperature: "#ef4444",
  vibration: "#f59e0b",
  pressure: "#3b82f6",
  humidity: "#10b981",
};

const SENSOR_LABELS: Record<string, string> = {
  temperature: "온도",
  vibration: "진동",
  pressure: "기압",
  humidity: "습도",
};

export function DigitalTwinAnomalyDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["digital-twin", "anomalies"],
    queryFn: () => apiClient.get<DigitalTwinDashboardData>("/digital-twin/anomalies"),
    refetchInterval: 30_000,
  });

  const [selectedSensor, setSelectedSensor] = useState<string>("vibration");

  // 선택된 센서 데이터만 필터링
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.anomalies
      .filter((a) => a.sensor_type === selectedSensor)
      .map((a) => ({
        time: new Date(a.timestamp).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }),
        value: Number(a.value.toFixed(2)),
        anomaly_score: Number(a.anomaly_score.toFixed(4)),
        is_anomaly: a.is_anomaly,
        severity: a.severity,
      }));
  }, [data, selectedSensor]);

  // 이상 포인트만 추출 (빨간점 강조용)
  const anomalyPoints = useMemo(() => {
    return chartData.filter((d) => d.is_anomaly).map((d) => ({
      ...d,
      z: 200,
    }));
  }, [chartData]);

  const sensorTypes = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.anomalies.map((a) => a.sensor_type))];
  }, [data]);

  if (isLoading) {
    return <SkeletonLoader count={3} itemClassName="h-48" />;
  }

  if (!data) return null;

  const { summary } = data;

  return (
    <section className="grid gap-6" aria-label="디지털 트윈 이상 감지">
      {/* KPI 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "활성 센서", value: summary.total_sensors, unit: "개", color: "text-cyan-400" },
          { label: "이상 감지", value: summary.anomalies_detected, unit: "건", color: "text-amber-400" },
          { label: "긴급 경고", value: summary.critical_count, unit: "건", color: "text-red-400" },
          { label: "주의 경고", value: summary.warning_count, unit: "건", color: "text-amber-400" },
        ].map((kpi, i) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.05 }}
          >
            <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
              <CardContent className="p-5">
                <p className="text-xs uppercase tracking-widest text-slate-400">{kpi.label}</p>
                <p className={`mt-2 text-3xl font-bold ${kpi.color}`}>
                  {kpi.value}
                  <span className="ml-1 text-sm font-normal text-slate-500">{kpi.unit}</span>
                </p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* 센서 필터 */}
      <div className="flex flex-wrap gap-2">
        {sensorTypes.map((type) => (
          <button
            key={type}
            onClick={() => setSelectedSensor(type)}
            className={`flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium transition ${
              selectedSensor === type
                ? "bg-white/10 text-white shadow-[0_0_12px_rgba(255,255,255,0.1)]"
                : "text-slate-500 hover:bg-white/5 hover:text-slate-300"
            }`}
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: SENSOR_COLORS[type] ?? "#6b7280" }}
            />
            {SENSOR_LABELS[type] ?? type}
          </button>
        ))}
      </div>

      {/* 시계열 차트 — 센서 값 추이 + 이상 감지 포인트 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-6">
          <CardTitle className="mb-1 text-base text-slate-200">
            센서 값 추이 — {SENSOR_LABELS[selectedSensor] ?? selectedSensor}
          </CardTitle>
          <p className="mb-4 text-xs text-slate-500">
            붉은색 포인트는 IsolationForest 이상 감지 구간입니다
          </p>
          <ResponsiveContainer width="100%" height={340}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)" }}
                axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              />
              <Tooltip
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid rgba(255,255,255,0.08)",
                  backgroundColor: "rgba(15,23,42,0.95)",
                  color: "#e2e8f0",
                  fontSize: 12,
                  backdropFilter: "blur(12px)",
                }}
                labelStyle={{ color: "#94a3b8" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={SENSOR_COLORS[selectedSensor] ?? "#6b7280"}
                strokeWidth={2}
                dot={(props: Record<string, unknown>) => {
                  const { cx, cy, payload } = props as {
                    cx: number;
                    cy: number;
                    payload: (typeof chartData)[number];
                  };
                  if (payload.is_anomaly) {
                    return (
                      <g key={`dot-${cx}-${cy}`}>
                        <circle cx={cx} cy={cy} r={6} fill="rgba(239,68,68,0.3)" />
                        <circle cx={cx} cy={cy} r={3.5} fill="#ef4444" stroke="#991b1b" strokeWidth={1} />
                      </g>
                    );
                  }
                  return <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={2} fill={SENSOR_COLORS[selectedSensor] ?? "#6b7280"} opacity={0.5} />;
                }}
                name={SENSOR_LABELS[selectedSensor] ?? selectedSensor}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 이상 스코어 산점도 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-6">
          <CardTitle className="mb-1 text-base text-slate-200">이상 스코어 분포</CardTitle>
          <p className="mb-4 text-xs text-slate-500">
            임계치(-0.3) 이하 구간이 붉은색으로 표시됩니다
          </p>
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)" }}
                name="시간"
              />
              <YAxis
                dataKey="anomaly_score"
                tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)" }}
                name="Score"
                domain={[-0.6, 0.6]}
              />
              <ZAxis range={[30, 200]} />
              <ReferenceLine y={-0.3} stroke="#ef4444" strokeDasharray="6 3" label={{ value: "임계치", fill: "#ef4444", fontSize: 10 }} />
              <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
              <Tooltip
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid rgba(255,255,255,0.08)",
                  backgroundColor: "rgba(15,23,42,0.95)",
                  color: "#e2e8f0",
                  fontSize: 12,
                }}
              />
              <Scatter
                data={chartData.filter((d) => !d.is_anomaly)}
                fill="#3b82f6"
                opacity={0.5}
                name="정상"
              />
              <Scatter
                data={anomalyPoints}
                fill="#ef4444"
                opacity={0.9}
                name="이상"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 마지막 스캔 시간 */}
      <p className="text-right text-[10px] text-slate-500">
        마지막 스캔: {new Date(summary.last_scan_at).toLocaleString("ko-KR")}
      </p>
    </section>
  );
}
