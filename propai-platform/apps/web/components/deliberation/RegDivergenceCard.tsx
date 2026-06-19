"use client";

/**
 * 규제 출처 정합 카드 — BFF `/api/v1/deliberation/reg/divergence`(인증·읽기전용) 결과 표시.
 *
 * 플랫폼 권위 ZONE_LIMITS와 엔진 국가 1차출처(시행령 §84/§85)를 용도지역×지표(FAR/BCR) 전수 대조한
 * drift를 표면화 — 엔진 SSOT 일원화(authoritative 승격) 전 두 규제 사본의 비동기화 게이트.
 * 핵심: unexpected_platform_only(특별구역 allowlist 밖 platform_only = 엔진 규제 누락 회귀 신호)를
 * drift==0에 묻히지 않게 별도 경보로 노출. 엔진 미연결/거부 시 degrade 정직 안내(무음0).
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api-client";

type DivergenceResp = {
  degraded?: boolean;
  reason?: string;
  matched?: number;
  drift?: number;
  compared?: number;
  match_rate?: number | null;
  unexpected_platform_only?: string[];
  platform_only_zones?: string[];
  engine_only_zones?: string[];
  engine_meta?: { source?: string; version?: string } | null;
};

type View =
  | { phase: "loading" }
  | { phase: "degraded"; reason: string }
  | { phase: "ready"; data: DivergenceResp }
  | { phase: "error" };

export function RegDivergenceCard() {
  const [view, setView] = useState<View>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await apiClient.get<DivergenceResp>("/deliberation/reg/divergence");
        if (!alive) return;
        if (d.degraded) {
          setView({ phase: "degraded", reason: d.reason || "engine_unreachable" });
        } else {
          setView({ phase: "ready", data: d });
        }
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
        <h2 className="text-sm font-black text-[var(--text-primary)]">규제 출처 정합(reg drift)</h2>
        <span className="cc-label text-[10px] text-[var(--text-tertiary)]">
          플랫폼 ZONE_LIMITS vs 엔진 1차출처
        </span>
      </div>

      {view.phase === "loading" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">불러오는 중…</p>
      )}
      {view.phase === "degraded" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">
          엔진 미연결 — 대조 보류({view.reason})
        </p>
      )}
      {view.phase === "error" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">정합 조회 실패</p>
      )}
      {view.phase === "ready" && <ReadyBody data={view.data} />}
    </section>
  );
}

function ReadyBody({ data }: { data: DivergenceResp }) {
  const compared = data.compared ?? 0;
  const drift = data.drift ?? 0;
  const rate = data.match_rate;
  const unexpected = data.unexpected_platform_only || [];
  const engineOnly = data.engine_only_zones || [];
  // ★대조쌍 존재(compared>0)여야 match_rate가 의미. comparable=false면 '일치'로 위장 금지(정직 불변식).
  const comparable = rate != null;
  const pct = comparable ? Math.round(rate * 1000) / 10 : null;
  const aligned = comparable && drift === 0 && unexpected.length === 0;
  // 일치=emerald, 미일치(대조됨)=amber, 대조불가=중립(미일치 암시 회피·거짓 안심 금지).
  const tone = aligned
    ? "text-emerald-500"
    : comparable
      ? "text-amber-500"
      : "text-[var(--text-tertiary)]";

  return (
    <div className="relative z-10 mt-3 space-y-2">
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="text-[var(--text-secondary)]">대조 {compared}건 · drift {drift}</span>
        <span className={`font-semibold ${tone}`}>
          {pct == null ? "대조불가" : `${pct}%`}
          {aligned ? " · 일치" : ""}
        </span>
      </div>
      {unexpected.length > 0 && (
        // ★엔진 규제 누락 회귀 신호 — drift==0/대조불가여도 별도 경보(특별구역 외 platform_only).
        // role=alert: 핵심 회귀 신호를 스크린리더가 즉시 announce(a11y).
        <p
          role="alert"
          className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-500"
        >
          ⚠ 엔진 규제 누락 의심: {unexpected.join(", ")}
        </p>
      )}
      {engineOnly.length > 0 && (
        // 엔진만 보유(플랫폼 미수록) — 플랫폼이 미적용 중인 규제(중립 정보·경보 아님).
        <p className="text-[10px] text-[var(--text-tertiary)]">
          플랫폼 미수록(엔진만): {engineOnly.join(", ")}
        </p>
      )}
      {data.engine_meta?.version && (
        <p className="text-[10px] text-[var(--text-tertiary)]">
          엔진 출처 {data.engine_meta.source ? `${data.engine_meta.source} · ` : ""}v
          {data.engine_meta.version}
        </p>
      )}
    </div>
  );
}
