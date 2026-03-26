"use client";

import { useState, useEffect } from "react";

export default function KdxSystemStatus() {
    const [tps, setTps] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setTps(Math.floor(Math.random() * 50) + 120); // Simulate 120~170 TPS
        }, 1000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg border border-slate-200 dark:border-slate-800">
                <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">KDX WebSocket Connection</p>
                <div className="mt-2 flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-2xl font-bold text-slate-800 dark:text-slate-100">STABLE</span>
                </div>
            </div>
            
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg border border-slate-200 dark:border-slate-800">
                <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Ingestion Pipeline Speed</p>
                <p className="mt-2 text-2xl font-bold text-blue-600 dark:text-blue-400">{tps} <span className="text-sm text-slate-400">txn/s</span></p>
            </div>

            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl shadow-lg border border-slate-200 dark:border-slate-800">
                <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Data Sync Latency</p>
                <p className="mt-2 text-2xl font-bold text-slate-800 dark:text-slate-100">LIVE <span className="text-sm text-slate-400">(~0.4s)</span></p>
            </div>
        </div>
    );
}
