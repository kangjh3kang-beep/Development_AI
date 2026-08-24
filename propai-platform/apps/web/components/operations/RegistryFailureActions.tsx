"use client";

/**
 * 분석되지 않은 필지를 **작업 목록**으로 보여 준다.
 *
 * ## 왜 이 화면이 있나
 *
 * 등기 권리분석은 다섯 단계가 모두 성공해야 결과가 된다(주소 특정 · 발급 · 잔액 · 본문 추출 ·
 * 해석). 그 곱셈 때문에 **모든 필지에서 항상 성공하는 것은 구조상 불가능**하다.
 * 그렇다면 완성도를 가르는 것은 **남는 실패를 어떻게 다루는가**다 —
 * 성공률이 같아도 "분석 불가"는 막다른 길이고, "12건이 이 사유로 안 됐습니다 —
 * 이렇게 하면 됩니다"는 작업 목록이다.
 *
 * ## 이 화면이 조심하는 것 (볼트 2026-08-02 W3 교훈)
 *
 * · **"부실할수록 깨끗해 보이는 역선택"** — 분류가 실패를 못 세면 화면이 오히려 깨끗해진다.
 *   그래서 조치를 못 고른 건도 `사유 확인 필요` 묶음으로 **반드시 보인다**.
 * · **빈 컨테이너 착시** — “실패 0”과 “아직 분석 안 함”은 다르다. 둘 다 빈 목록이지만
 *   화면은 다른 말을 한다.
 * · **할 수 없는 일을 버튼으로 만들지 않는다** — 재시도 버튼은 `canRetry` 인 묶음에만.
 */

import { useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";

import {
  FAILURE_ACTION_INFO,
  groupFailures,
  type BatchOutcome,
} from "@/lib/registry-analyze";

export function RegistryFailureActions({
  items,
  onRetry,
  className = "",
}: {
  items: readonly BatchOutcome[];
  /** 한 묶음을 통째로 다시 시도한다. 화면은 어떤 조회인지 모른다 — 호출측이 안다. */
  onRetry?: (group: readonly BatchOutcome[]) => Promise<void> | void;
  className?: string;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const groups = groupFailures(items);
  const total = items.length;
  const failed = groups.reduce((n, g) => n + g.count, 0);

  // ★“아직 분석 안 함”과 “실패 0”은 다르다. 둘 다 목록이 비지만 같은 말을 하면 안 된다.
  if (total === 0) return null;
  if (failed === 0) {
    return (
      <p className={`text-[11px] font-bold text-[var(--status-success)] ${className}`} data-testid="failures-none">
        {total}필지 모두 분석됐습니다.
      </p>
    );
  }

  return (
    <div className={`space-y-2 ${className}`} data-testid="failure-actions">
      <p className="text-[11px] font-bold text-[var(--text-primary)]">
        분석되지 않은 {failed}필지 — 사유별로 다음 조치가 다릅니다
      </p>

      {groups.map((g) => {
        const info = FAILURE_ACTION_INFO[g.action];
        return (
          <div
            key={g.action}
            data-testid={`failure-group-${g.action}`}
            className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-[11px]"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-bold text-[var(--text-primary)]">{info.label}</span>
              <span className="rounded-full border border-[var(--line-strong)] px-2 py-0.5 font-bold text-[var(--text-secondary)]">
                {g.count}필지
              </span>

              {info.canRetry && onRetry && (
                <button
                  type="button"
                  disabled={busy !== null}
                  data-testid={`failure-retry-${g.action}`}
                  onClick={async () => {
                    setBusy(g.action);
                    try {
                      await onRetry(g.items);
                    } finally {
                      setBusy(null);
                    }
                  }}
                  className="ml-auto inline-flex items-center gap-1 rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 font-bold text-white disabled:opacity-50"
                >
                  {busy === g.action ? (
                    <Loader2 className="size-3 animate-spin" aria-hidden />
                  ) : (
                    <RotateCcw className="size-3" aria-hidden />
                  )}
                  {g.count}필지 다시 시도
                </button>
              )}
            </div>

            <p className="mt-1 text-[var(--text-secondary)]">{info.hint}</p>

            {/* 사유 원문 — 안내가 일반화된 만큼, 실제로 무엇이 왔는지도 남긴다. */}
            <p className="mt-0.5 truncate text-[var(--text-hint)]" title={g.reason}>
              사유: {g.reason}
            </p>

            {/* 어느 필지인지 말한다. 개수만 보면 무엇을 고쳐야 할지 모른다. */}
            <p className="mt-0.5 truncate text-[var(--text-hint)]">
              {g.items.slice(0, 6).map((b) => b.jibun).join(" · ")}
              {g.count > 6 && ` 외 ${g.count - 6}필지`}
            </p>
          </div>
        );
      })}
    </div>
  );
}
