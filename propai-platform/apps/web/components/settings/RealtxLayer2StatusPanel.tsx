"use client";

/**
 * 실거래 **2층 관측 표면** — 관리자 전용.
 *
 * GET /market/realtx-layer2/status → 저장 규모 · 수집 신선도 · 정정 탐지 판정
 *
 * ## 이 화면이 존재하는 이유
 *
 * `#855`·`#860`·`#884` 가 실거래 2층(저장·정정탐지)을 만들었고 프로덕션에 수천 행이
 * 쌓였는데 **읽는 코드가 0건**이었다(실측 2026-08-27). 수집이 조용히 멈춰도, 정정이
 * 쏟아져도 아무도 몰랐다.
 *
 * ★★그리고 **이 패널이 없으면 그 PR 자신이 같은 결함**이다 — 라우트를 만들고 아무도
 *   안 부르면 "소비처 0" 을 한 층 위에서 재발시키는 것이다. 저장소의
 *   `test_orphan_routes_ratchet` 이 실제로 그것을 잡았다(CI 실패 → 이 패널을 만든 계기).
 *
 * ## ★표시 규율 — 「모름」을 수치로 위장하지 않는다
 *
 * 백엔드가 `age_hours: null` · `stale: null` 을 주는 상태(미수집·시각이상)를 `0시간 전`
 * 같은 **그럴듯한 수**로 그리지 않는다. 그렇게 그리면 그것이 **관측으로 읽힌다**.
 *
 * ★`corrections.total = 0` 은 **여러 뜻**이다. `detection.state` 를 먼저 보라 —
 *   `미시험`(아직 돌 기회가 없었다)과 `관측됨_정정없음`(재관측했는데 안 변했다)은
 *   완전히 다른 사실이고, 섞어 읽으면 **정상을 장애로**(또는 그 반대로) 판정하게 된다.
 */

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ------------------------------------------------------------------ */
/*  백엔드 계약 (realtx_layer2_status.build_layer2_status 와 1:1)        */
/* ------------------------------------------------------------------ */

/** 백엔드 `detection_state()` 가 내는 닫힌 집합. 미래 값 대비해 string 도 수용. */
type DetectionState =
  | "미배포"
  | "미수집"
  | "미시험"
  | "상태소실"
  | "관측됨_정정없음"
  | "관측됨_정정있음"
  | "모순"
  | (string & {});

/** 백엔드 `freshness()` 가 내는 값. `NEVER_SCANNED`/`CLOCK_ANOMALY` 포함. */
type FreshnessState = "정상" | "낡음" | "미수집" | "시각이상" | (string & {});

interface Freshness {
  last_scanned_at: string | null;
  age_hours: number | null;
  state: FreshnessState;
  stale: boolean | null;
  newest_scanned_at?: string | null;
  scopes_in_window?: number;
}

interface Layer2Status {
  stored_rows: number | null;
  reobserved_rows: number | null;
  scopes: {
    total: number | null;
    baseline_done: number | null;
    sigungu_ever_scanned: number | null;
    trade_scopes?: number | null;
  };
  corrections: { total: number | null; by_kind: Record<string, number> };
  quota: {
    targets: number | null;
    daily_scopes: number | null;
    weekly_avg_per_day: number | null;
    baseline_targets: number;
    vs_baseline: number | null;
    limit: string;
    state: string;
  };
  detection: { state: DetectionState; meaning: string };
  collection: {
    recent: Freshness & { months: string[] };
    tail: Freshness & { probe_month: string };
  };
  as_of: string;
}

/* ------------------------------------------------------------------ */
/*  표시 헬퍼 — 「모름」은 수치가 아니다                                 */
/* ------------------------------------------------------------------ */

/** ★`null` 을 `0` 으로 접지 않는다. 접으면 「모름」이 **관측으로 읽힌다**. */
export function displayCount(n: number | null | undefined): string {
  return n === null || n === undefined ? "미상" : n.toLocaleString("ko-KR");
}

/** ★나이를 말할 수 없는 상태는 **상태 이름 그대로** 보여 준다(수치 위장 금지). */
export function displayAge(f: Pick<Freshness, "age_hours" | "state">): string {
  if (f.age_hours === null || f.age_hours === undefined) return f.state;
  if (f.age_hours < 24) return `${f.age_hours.toFixed(1)}시간 전`;
  return `${(f.age_hours / 24).toFixed(1)}일 전`;
}

/** 판정별 색. ★`stale === null`(판정 불가)은 **정상색으로 칠하지 않는다**. */
export function toneFor(state: string): "ok" | "warn" | "unknown" {
  if (state === "관측됨_정정없음" || state === "관측됨_정정있음" || state === "정상") return "ok";
  if (state === "모순" || state === "낡음" || state === "시각이상") return "warn";
  return "unknown"; // 미배포 · 미수집 · 미시험 · 상태소실 — **모른다**
}

const TONE_CLASS: Record<string, string> = {
  ok: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  unknown: "text-slate-500 dark:text-slate-400",
};

/* ------------------------------------------------------------------ */

export function RealtxLayer2StatusPanel() {
  const [data, setData] = useState<Layer2Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<Layer2Status>("/market/realtx-layer2/status");
      setData(res);
    } catch (e) {
      // ★사유를 삼키지 않는다 — 진단 불가는 그 자체로 장애다.
      setError(e instanceof ApiClientError ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <Card><CardContent>실거래 2층 상태 조회 중…</CardContent></Card>;

  if (error) {
    return (
      <Card>
        <CardContent>
          <h3 className="font-semibold">실거래 2층 상태</h3>
          <p className="text-amber-700 dark:text-amber-400">조회 실패 — {error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const { detection, collection, corrections, quota, scopes } = data;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-semibold">실거래 2층 — 수집·정정 탐지</h3>
          <button type="button" onClick={() => void load()} className="text-xs underline">
            새로고침
          </button>
        </div>

        {/* ★판정을 맨 위에 — corrections=0 이 무엇을 뜻하는지 여기서 갈린다 */}
        <div>
          <span className={`font-semibold ${TONE_CLASS[toneFor(detection.state)]}`}>
            {detection.state}
          </span>
          <p className="text-sm text-slate-600 dark:text-slate-300">{detection.meaning}</p>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
          <div><dt className="text-slate-500">저장 거래</dt><dd>{displayCount(data.stored_rows)}행</dd></div>
          <div><dt className="text-slate-500">재관측</dt><dd>{displayCount(data.reobserved_rows)}행</dd></div>
          <div><dt className="text-slate-500">정정</dt><dd>{displayCount(corrections.total)}건</dd></div>
          <div><dt className="text-slate-500">스코프</dt><dd>{displayCount(scopes.total)}</dd></div>
          <div><dt className="text-slate-500">수집 대상 시군구</dt><dd>{displayCount(quota.targets)}</dd></div>
          <div>
            <dt className="text-slate-500">일일 쿼터</dt>
            {/* ★한도는 **미측정**이다 — 지어내지 않는다 */}
            <dd>{displayCount(quota.daily_scopes)} 스코프 · 한도 {quota.limit}</dd>
          </div>
        </dl>

        {/* 두 창은 주기가 다르므로 **따로** 보여 준다 */}
        <div className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <span className="text-slate-500">최근 창(매일) </span>
            <span className={TONE_CLASS[toneFor(collection.recent.state)]}>
              {collection.recent.state}
            </span>
            <span className="text-slate-500"> · {displayAge(collection.recent)}</span>
          </div>
          <div>
            <span className="text-slate-500">꼬리 창(주 1회) </span>
            <span className={TONE_CLASS[toneFor(collection.tail.state)]}>
              {collection.tail.state}
            </span>
            <span className="text-slate-500"> · {displayAge(collection.tail)}</span>
          </div>
        </div>

        {Object.keys(corrections.by_kind).length > 0 && (
          <ul className="text-sm text-slate-600 dark:text-slate-300">
            {Object.entries(corrections.by_kind).map(([kind, n]) => (
              <li key={kind}>{kind}: {n.toLocaleString("ko-KR")}건</li>
            ))}
          </ul>
        )}

        <p className="text-xs text-slate-500">기준 시각 {data.as_of}</p>
      </CardContent>
    </Card>
  );
}
