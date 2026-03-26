"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { IoTDashboardData, MaintenanceAlert } from "@/components/cad/types";

const SEVERITY_STYLES: Record<
  MaintenanceAlert["severity"],
  { bg: string; text: string; label: string }
> = {
  critical: { bg: "bg-red-50", text: "text-red-700", label: "긴급" },
  warning: { bg: "bg-amber-50", text: "text-amber-700", label: "주의" },
  info: { bg: "bg-sky-50", text: "text-sky-700", label: "정보" },
};

const LINE_COLORS: Record<string, string> = {
  temperature: "#ef4444",
  humidity: "#3b82f6",
  co2: "#8b5cf6",
  energy: "#10b981",
};

export function IoTDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "iot"],
    queryFn: () => apiClient.get<IoTDashboardData>("/analytics/iot"),
  });

  // 센서 데이터를 타임스탬프 기준으로 피벗
  const chartData = useMemo(() => {
    if (!data) return [];
    const byTime = new Map<string, Record<string, number | string>>();
    for (const s of data.sensors) {
      const hour = new Date(s.timestamp).toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      });
      const existing = byTime.get(hour) ?? { time: hour };
      existing[s.sensor_type] = s.value;
      byTime.set(hour, existing);
    }
    return Array.from(byTime.values());
  }, [data]);

  const sensorTypes = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.sensors.map((s) => s.sensor_type))];
  }, [data]);

  if (isLoading) {
    return <SkeletonLoader count={3} itemClassName="h-48" />;
  }

  if (!data) return null;

  return (
    <section className="grid gap-6" aria-label="IoT/Proptech 대시보드">
      {/* 센서 요약 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {data.sensor_summary.map((s) => (
          <Card key={s.type} className="bg-[var(--surface-strong)]">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-widest text-[rgba(19,33,47,0.56)]">
                {s.type}
              </p>
              <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">
                {s.avg_value.toFixed(1)}
                <span className="ml-1 text-sm font-normal text-[rgba(19,33,47,0.52)]">
                  {s.unit}
                </span>
              </p>
              <p className="mt-1 text-xs text-[rgba(19,33,47,0.48)]">
                활성 센서 {s.count}개
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* 센서 라인 차트 */}
      <Card>
        <CardContent className="p-6">
          <CardTitle className="mb-4 text-lg">실시간 센서 추이</CardTitle>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(19,33,47,0.06)" />
              <XAxis dataKey="time" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid var(--line)",
                  fontSize: 13,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {sensorTypes.map((type) => (
                <Line
                  key={type}
                  type="monotone"
                  dataKey={type}
                  stroke={LINE_COLORS[type] ?? "#6b7280"}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name={type}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* 예측 정비 알림 */}
      <Card>
        <CardContent className="p-6">
          <CardTitle className="mb-4 text-lg">예측 정비 알림</CardTitle>
          <ul className="space-y-3" aria-label="정비 알림 목록">
            {data.alerts.map((alert) => {
              const style = SEVERITY_STYLES[alert.severity];
              return (
                <li
                  key={alert.id}
                  className={`rounded-xl ${style.bg} p-4`}
                  role="alert"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className={`text-sm font-semibold ${style.text}`}>
                        {alert.equipment_name}
                      </p>
                      <p className="mt-1 text-xs text-[rgba(19,33,47,0.72)]">
                        {alert.message}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-bold ${style.bg} ${style.text}`}
                    >
                      {style.label}
                    </span>
                  </div>
                  <div className="mt-2 flex gap-4 text-[11px] text-[rgba(19,33,47,0.52)]">
                    <span>예상 고장: {alert.predicted_failure_date}</span>
                    <span>신뢰도: {(alert.confidence * 100).toFixed(0)}%</span>
                  </div>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
