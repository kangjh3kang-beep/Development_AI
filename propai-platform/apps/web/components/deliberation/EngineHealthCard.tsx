"use client";

/**
 * 심의분석 엔진 헬스카드 — BFF `/api/v1/deliberation/health`(화이트리스트 프록시) 상태 표시.
 *
 * 엔진(별도 서비스) 연결/구성 상태를 인증된 BFF 경유로만 조회(브라우저 직결·핑거프린트 노출 0).
 * ok=연결됨+필드, degraded=미연결+사유(무음0), 실패=확인 실패. apiClient가 Bearer 자동 부착.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api-client";

type EngineFields = {
  database_configured: boolean | null;
  sheet_classifier_live: boolean | null;
  jurisdiction_live: boolean | null;
  embedder_semantic: boolean | null;
};

type Health = { status: string; reason?: string; engine: EngineFields | null };

type View =
  | { phase: "loading" }
  | { phase: "ok"; engine: EngineFields | null }
  | { phase: "degraded"; reason: string }
  | { phase: "error" };

const FIELD_LABELS: Array<[keyof EngineFields, string]> = [
  ["database_configured", "DB"],
  ["sheet_classifier_live", "시트 분류기"],
  ["jurisdiction_live", "관할 해석"],
  ["embedder_semantic", "의미 임베더"],
];

// ★정직 3상 표기 — true=live(연결), false=mock(폴백), null/부재=미확인(구버전 엔진이 필드 미보고).
//   과거 `value ? "live" : "mock"`는 null(미보고)까지 "mock"으로 오표기해 실 PostGIS 가동을 mock으로 왜곡했다.
//   null과 false는 의미가 다르므로(미확인 ≠ 폴백) 라벨·색을 분리한다.
function fieldState(value: boolean | null | undefined): { text: string; cls: string } {
  if (value === true) return { text: "live", cls: "text-emerald-500" };
  if (value === false) return { text: "mock", cls: "text-amber-500" };
  return { text: "미확인", cls: "text-[var(--text-tertiary)]" }; // null/undefined = 엔진 미보고(구버전)
}

export function EngineHealthCard() {
  const [view, setView] = useState<View>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await apiClient.get<Health>("/deliberation/health");
        if (!alive) return;
        if (d.status === "ok") setView({ phase: "ok", engine: d.engine });
        else setView({ phase: "degraded", reason: d.reason || "unknown" });
      } catch {
        if (alive) setView({ phase: "error" });
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-5">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="relative z-10 flex items-center justify-between gap-3">
        <h2 className="text-sm font-black text-[var(--text-primary)]">엔진 연결 상태</h2>
        <StatusBadge view={view} />
      </div>
      {view.phase === "ok" && view.engine && (
        <ul className="relative z-10 mt-3 flex flex-wrap gap-2">
          {FIELD_LABELS.map(([key, label]) => {
            const st = fieldState(view.engine?.[key]);
            return (
              <li
                key={key}
                className="rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-2.5 py-0.5 text-[11px] text-[var(--text-secondary)]"
              >
                {label}: <span className={`font-semibold ${st.cls}`}>{st.text}</span>
              </li>
            );
          })}
        </ul>
      )}
      {view.phase === "degraded" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">
          엔진 미연결 — 사유: <span className="font-mono">{view.reason}</span>
        </p>
      )}
      {view.phase === "error" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">
          엔진 상태 확인 실패
        </p>
      )}
    </section>
  );
}

function StatusBadge({ view }: { view: View }) {
  const map: Record<View["phase"], { text: string; cls: string }> = {
    loading: { text: "확인 중…", cls: "text-[var(--text-tertiary)]" },
    ok: { text: "연결됨", cls: "text-emerald-500" },
    degraded: { text: "미연결", cls: "text-amber-500" },
    error: { text: "확인 실패", cls: "text-red-500" },
  };
  const { text, cls } = map[view.phase];
  return (
    <span className={`cc-label rounded-full border border-[var(--line)] px-2.5 py-0.5 text-[10px] font-semibold ${cls}`}>
      {text}
    </span>
  );
}
