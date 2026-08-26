"use client";

/**
 * 토지필지 종합분석 **P2 — 매입전략 분류** 화면 배선.
 *
 * 【왜 이 파일이 생겼나】백엔드 `POST /registry/survey/strategy` 는 배포돼 있는데
 * **프론트 소비처가 0** 이었다(계획서 §6 "소비처 0 해소"). 만들 게 아니라 **붙일 것**이었다.
 *
 * 【설계 제약 — 계획서가 못 박은 것】
 *  · **신규 화면 0개** — `ParcelSurveyQuotePanel` 의 필지 선택을 그대로 받아 쓰는 후속 단계다.
 *  · ⚠️**용량 불일치**: 엑셀 조서 상한 500행 vs P2 상한 **100**(`MAX_STRATEGY_PARCELS`).
 *    상한을 올리지 않는다(유료 경로라 길이가 곧 청구액이다) — **분할 안내 UX** 로 푼다.
 *  · **`scheme` 에 기본값을 몰래 넣지 않는다.** 보유기간 10년 요건은 주택법 계열에만 있어
 *    방식이 없으면 판정 자체가 성립하지 않는다. 미선택이면 **보내지 않고 막는다.**
 *
 * 【유료 경로 — 조용히 실행하지 않는다】
 * 이 호출은 필지당 **발급 1,200원 + 분석 2,000원** 이 실제로 나간다(P0 견적에서 비용을 확인한
 * 뒤 진입하는 단계다). 그래서 버튼 한 번에 바로 나가지 않고 **건수·예상비용을 보이고 확인**을 받는다.
 */

import { useMemo, useState } from "react";
import { AlertTriangle, Scale } from "lucide-react";
import { Card, CardContent } from "@propai/ui";

import { apiClient } from "@/lib/api-client";
import { idempotencyHeaders } from "@/lib/idempotency";
import { parcelDisplayAddress } from "@/lib/pnu";

/** 백엔드 `MAX_STRATEGY_PARCELS`(= `MAX_BULK_ITEMS`) 와 같은 값. 초과 시 상류가 422 로 거부한다. */
export const MAX_STRATEGY_PARCELS = 100;

/**
 * 사업방식 선택지.
 *
 * ★정본은 백엔드 `scenario_simulator._SCHEME_LEGAL_KEYS` 다. 여기 목록이 그와 어긋나면
 *   사용자가 고른 방식이 상류에서 **미등록으로 떨어져 전건 판정보류**가 된다(조용한 실패).
 *   그래서 `__tests__/strategy-scheme-parity.test.ts` 가 이 배열이 백엔드 키의
 *   **부분집합**인지 잠근다 — 오타·개명이 나면 테스트가 죽는다.
 * ★전체를 싣지 않고 **매입전략 판정이 의미 있는 방식**만 골랐다(단순 건축처럼 매도청구·수용
 *   제도가 없는 방식은 판정이 성립하지 않아 사용자를 헛되게 한다).
 */
export const STRATEGY_SCHEMES = [
  "재개발·재건축(정비사업)",
  "공공재개발·공공재건축",
  "가로주택정비사업",
  "소규모재개발사업",
  "소규모재건축사업",
  "자율주택정비사업",
  "모아주택/모아타운",
  "도시개발사업(도시개발법)",
  "도심복합개발사업",
] as const;

type StrategyRow = {
  address?: string | null;
  action?: string | null;
  reason?: string | null;
};

type StrategyResponse = {
  strategy?: {
    scheme?: string | null;
    governing_act?: string | null;
    instrument?: string | null;
    legal?: {
      basis?: string | null;
      consent_required?: boolean | null;
      consent_threshold_pct?: number | null;
    } | null;
    summary?: { row_count?: number; by_action?: Record<string, number> } | null;
    rows?: StrategyRow[] | null;
  } | null;
};

export type StrategyParcelInput = {
  address: string;
  pnu?: string | null;
  hasBuilding?: boolean | null;
  geometry?: unknown;
};

const ACTION_COLOR: Record<string, string> = {
  협의매수: "#10b981",
  매도청구: "#3b82f6",
  수용: "#f59e0b",
  제척검토: "#a855f7",
  판정보류: "#ef4444",
};

export function ParcelPurchaseStrategyPanel({ parcels }: { parcels: StrategyParcelInput[] }) {
  const [scheme, setScheme] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState<StrategyResponse | null>(null);

  const count = parcels.length;
  const overCap = count > MAX_STRATEGY_PARCELS;
  // 발급 1,200 + 분석 2,000 = 필지당 3,200원(계획서 §P2). 실제 청구는 성공 건만이라 **상한**이다.
  const estimatedWon = count * 3200;

  const summary = res?.strategy?.summary;
  const byAction = useMemo(() => Object.entries(summary?.by_action ?? {}), [summary]);

  const run = async () => {
    // ★scheme 미선택이면 **보내지 않는다** — 기본값을 몰래 넣으면 판정 근거가 없는 결과가 나온다.
    if (!scheme || overCap || count === 0) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        scheme,
        parcels: parcels.map((p) => ({
          // ★형제 누락 봉합(2026-08-21) — 같은 화면의 `ParcelSurveyQuotePanel` 은 이미
          //   `parcelDisplayAddress` 를 쓰는데 여기만 원본을 보내고 있었다.
          //   이 `address` 는 등기 조회 키로도 쓰인다(`routers/registry.py`) —
          //   **지번 없는 동 단위 주소는 등기조회를 깨뜨린다**(2026-08-18 실측 결함).
          //   ★파생 지번은 **바로 아래 함께 보내는 그 PNU** 에서 나오므로 둘이 모순될 수 없다.
          address: parcelDisplayAddress(p.address, p.pnu),
          ...(p.pnu ? { pnu: p.pnu } : {}),
          ...(p.hasBuilding != null ? { has_building: p.hasBuilding } : {}),
          ...(p.geometry ? { geometry: p.geometry } : {}),
        })),
      };
      // ★★멱등키 필수 — 이 호출은 **필지당 3,200원**(발급 1,200 + 분석 2,000)이 실제로 나간다.
      //   최대 100필지면 1회 32만원이라 **중복 실행의 손해가 가장 큰 경로**다.
      //   백엔드는 `charge_once(endpoint="registry.survey_strategy")` 로 가드하지만
      //   **키를 안 보내면 그 가드는 아무것도 막지 못한다**(#671 이 고친 결함 클래스:
      //   "백엔드는 가드했는데 프론트가 키를 안 보내 보호가 0"). 그 파생형 락이 이 호출부를 잡았다.
      //   ★스코프는 백엔드 endpoint 명과 맞춘다 — 갈리면 사람이 두 이름을 대조해야 한다.
      //   ★키는 (스코프 + 요청 지문)에서 파생되므로 **같은 필지·같은 방식의 재실행은 재청구되지 않고**,
      //     필지나 방식을 바꾸면 새 키가 나와 정상 청구된다.
      const r = await apiClient.post<StrategyResponse>("/registry/survey/strategy", {
        body,
        headers: idempotencyHeaders("registry.survey_strategy", body),
        timeoutMs: 120000,
      });
      setRes(r);
    } catch (e: unknown) {
      // ★원인을 지어내지 않는다 — 상류가 준 메시지만 보인다(#677 이 세운 원칙).
      setError(e instanceof Error ? e.message : "매입전략 분석에 실패했습니다.");
      setRes(null);
    } finally {
      setBusy(false);
    }
  };

  if (count === 0) return null;

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <div className="flex items-center gap-3">
          <Scale className="size-6 shrink-0 text-[var(--accent-strong)]" aria-hidden />
          <div>
            <h3 className="text-base font-black text-[var(--text-primary)]">
              매입전략 분류 <span className="text-xs font-bold text-[var(--text-tertiary)]">P2</span>
            </h3>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              선택 필지를 발급·권리분석한 뒤 협의매수·매도청구·수용·제척검토로 분류합니다.
            </p>
          </div>
        </div>

        {/* ⚠️용량 불일치 — 상한을 올리지 않고 분할을 안내한다(계획서 §6) */}
        {overCap && (
          <div
            role="alert"
            className="sa-chip--warning mt-4 flex items-start gap-2 rounded-xl border p-3"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p className="text-xs text-[var(--text-secondary)]">
              선택 <b>{count}</b>필지는 1회 분석 상한(<b>{MAX_STRATEGY_PARCELS}</b>필지)을 넘습니다.
              상한을 넘겨 보내면 서버가 거부하며, <b>조용히 잘라내지 않습니다</b> — 뺀 필지를 모른 채
              결과를 신뢰하게 되기 때문입니다. <b>{MAX_STRATEGY_PARCELS}필지 이하로 나눠</b> 실행하세요.
            </p>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="min-w-[240px] flex-1 text-xs text-[var(--text-secondary)]">
            사업방식 <span className="text-[var(--danger)]">*</span>
            <select
              value={scheme}
              onChange={(e) => setScheme(e.target.value)}
              className="mt-1 h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)]"
            >
              {/* ★기본 선택을 두지 않는다 — 방식이 없으면 판정이 성립하지 않는다 */}
              <option value="">선택하세요</option>
              {STRATEGY_SCHEMES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="text-xs text-[var(--text-secondary)]">
            선택 <b>{count}</b>필지 · 예상비용 <b>최대 {estimatedWon.toLocaleString()}원</b>
            <div className="text-[11px] text-[var(--text-hint)]">
              발급·분석에 성공한 건만 청구됩니다.
            </div>
          </div>
        </div>

        {/* ★**왜 못 누르는지 말한다.** 2026-08-25 사용자 신고: *"매입전략 분석 시작 버튼이
            활성화되지 않고 기능을 사용할 수 없다"*. 조건 자체는 옳다(방식이 없으면 판정이
            성립하지 않는다) — 결함은 **비활성의 사유가 화면에 없다**는 것이었다.
            라벨의 빨간 `*` 하나로는 회색 버튼과 연결되지 않는다.
            ★`overCap` 은 이미 위에 경고가 있으므로 여기서는 미선택만 말한다(중복 금지). */}
        {!scheme && !overCap && (
          <p
            data-testid="strategy-disabled-reason"
            className="mt-3 text-xs font-semibold text-[var(--status-warning)]"
          >
            위에서 <b>사업방식</b>을 먼저 선택하세요 — 방식에 따라 협의매수·매도청구·수용·제척
            판정 기준이 달라져, 선택 전에는 분석을 시작할 수 없습니다.
          </p>
        )}

        {/* ★유료 실행이라 한 번의 확인을 받는다 */}
        {!confirmed ? (
          <button
            type="button"
            onClick={() => setConfirmed(true)}
            disabled={!scheme || overCap}
            className="mt-4 inline-flex h-10 items-center rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white disabled:opacity-50"
          >
            매입전략 분석 시작
          </button>
        ) : (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void run()}
              disabled={busy || !scheme || overCap}
              className="inline-flex h-10 items-center rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white disabled:opacity-50"
            >
              {busy ? "분석 중…" : `확인 — ${count}필지 실행`}
            </button>
            <button
              type="button"
              onClick={() => setConfirmed(false)}
              className="inline-flex h-10 items-center rounded-xl border border-[var(--line)] px-4 text-sm font-bold text-[var(--text-secondary)]"
            >
              취소
            </button>
          </div>
        )}

        {error && (
          <p role="alert" className="mt-3 text-xs font-bold text-[var(--danger)]">
            {error}
          </p>
        )}

        {summary && (
          <div className="mt-5 grid gap-3">
            <div className="flex flex-wrap gap-2">
              {byAction.map(([action, n]) => (
                <span
                  key={action}
                  className="rounded-full px-3 py-1 text-xs font-black text-white"
                  style={{ background: ACTION_COLOR[action] ?? "var(--text-tertiary)" }}
                >
                  {action} {n}
                </span>
              ))}
            </div>
            {/* ★판정 근거를 반드시 보인다 — 근거 없이 "매도청구 가능"만 내면 무엇을 충족해야
                하는지 사용자가 모른다(백엔드 legal 블록이 그래서 있다). */}
            {res?.strategy?.legal?.basis && (
              <p className="text-[11px] text-[var(--text-hint)]">
                근거: {res.strategy.legal.basis}
                {res.strategy.legal.consent_threshold_pct != null &&
                  ` · 동의요건 ${res.strategy.legal.consent_threshold_pct}%`}
              </p>
            )}
            {/* ★사업방식이 상류에서 해석되지 않으면 전건 판정보류가 된다 — 조용히 두지 않는다 */}
            {res?.strategy?.governing_act == null && (
              <p role="alert" className="text-[11px] font-bold" style={{ color: "var(--status-warning)" }}>
                선택한 사업방식이 매도청구·수용 제도 대상으로 등록돼 있지 않아 판정이 보류됩니다.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
