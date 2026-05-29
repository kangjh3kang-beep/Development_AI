"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiClient } from "@/lib/api-client";

type KdxTick = {
  time: string;
  index: number;
  volume: number;
};

type WebSocketTickPayload = {
  event_type?: string;
  timestamp?: number;
  seoul_index?: number;
  transaction_volume?: number;
};

export default function KdxRealtimeChart() {
  const [data, setData] = useState<KdxTick[]>([]);

  useEffect(() => {
    const { apiBaseUrl } = apiClient.getRuntimeConfig();
    const accessToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem("propai_access_token")?.trim() ?? ""
        : "";

    if (!accessToken) {
      return;
    }
    const baseUrl = new URL(
      apiBaseUrl,
      typeof window !== "undefined" ? window.location.origin : "http://localhost:3000",
    );
    const socketProtocol = baseUrl.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(
      `${socketProtocol}//${baseUrl.host}/api/v1/kdx/stream?token=${encodeURIComponent(accessToken)}`,
    );

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data) as WebSocketTickPayload;

      if (
        payload.event_type !== "market_tick" ||
        typeof payload.timestamp !== "number" ||
        typeof payload.seoul_index !== "number" ||
        typeof payload.transaction_volume !== "number"
      ) {
        return;
      }

      const time = new Date(payload.timestamp * 1000).toLocaleTimeString(
        "ko-KR",
        {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        },
      );
      const index = payload.seoul_index;
      const volume = payload.transaction_volume;

      setData((current) => {
        const next = [
          ...current,
          {
            time,
            index,
            volume,
          },
        ];

        return next.slice(-30);
      });
    };

    return () => ws.close();
  }, []);

  return (
    <div className="h-[400px] w-full rounded-xl border border-slate-200 bg-white p-4 shadow-lg dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-4 flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500" />
        </span>
        KDX realtime property index
      </h3>
      <ResponsiveContainer width="100%" height="85%">
        <AreaChart data={data}>
          <defs>
            <linearGradient id="colorIndex" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#334155" strokeDasharray="3 3" opacity={0.5} />
          <XAxis dataKey="time" stroke="#64748b" fontSize={12} minTickGap={20} />
          <YAxis stroke="#64748b" fontSize={12} domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              borderColor: "#334155",
              borderRadius: "8px",
              color: "#f8fafc",
            }}
            itemStyle={{ color: "#bae6fd" }}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="index"
            stroke="#3b82f6"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#colorIndex)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
