"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { MyPageShell, formatKrw } from "./MyPageShell";

type TokenUsage = {
  scope: string;
  days: number;
  total_tokens: number;
  total_cost_krw: number;
  by_service: Array<{ service: string; tokens: number; cost_krw: number }>;
  daily: Array<{ date: string; tokens: number; cost_krw: number }>;
};

const PERIODS = [7, 30, 90] as const;

/** 서비스 키 → 통상어 라벨(미등록 키는 원문 표기 — 무날조). */
const SERVICE_LABELS: Record<string, string> = {
  market: "시장 분석",
  land: "토지 분석",
  design: "설계 지원",
  assistant: "AI 비서",
  report: "보고서 생성",
};

export function UsageClient({ locale }: { locale: Locale }) {
  const [days, setDays] = useState<number>(30);
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [loading, setLoading] = useState(true);
  // ★로드 실패를 '0원/사용 기록 없음'으로 위장하지 않도록 명시 오류 상태(성장루프 MEDIUM 수렴).
  const [error, setError] = useState(false);

  // 기간 변경은 이벤트에서 로딩 신호를 켠다(effect 내 직접 setState 회피 — lint 규칙).
  // ★usage=null로 초기화 — 새 기간 라벨 아래 이전 기간 수치가 사실처럼 노출되는 것을 막는다
  //   (성장루프 LOW 수렴: total은 '…'로 가려지나 서비스별·일별·토큰수는 stale 잔존했음).
  const changeDays = (p: number) => {
    setDays(p);
    setUsage(null);
    setLoading(true);
    setError(false);
  };

  useEffect(() => {
    let active = true;
    void apiClient
      .get<TokenUsage>(`/billing/token-usage?days=${days}`, { useMock: false })
      .then((u) => {
        if (active) {
          setUsage(u);
          setError(false);
        }
      })
      .catch(() => {
        if (active) {
          setUsage(null);
          setError(true);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [days]);

  const maxDailyCost = useMemo(
    () => Math.max(1, ...(usage?.daily ?? []).map((d) => d.cost_krw)),
    [usage],
  );

  return (
    <MyPageShell
      locale={locale}
      title="AI 사용내역"
      description="AI 분석에 사용한 코인을 기간·서비스·일별로 확인합니다. 모든 수치는 실제 호출 기록(실계측)에서 집계됩니다."
    >
      <div className="flex items-center gap-2">
        {PERIODS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => changeDays(p)}
            aria-pressed={days === p}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition ${
              days === p
                ? "bg-[var(--accent-strong)] text-white"
                : "border border-[var(--line)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            }`}
          >
            최근 {p}일
          </button>
        ))}
      </div>

      {/* ★총괄관리자(scope=platform)는 백엔드가 플랫폼 전체 사용량을 반환하므로, '본인' 수치로
          오인하지 않도록 관리자 뷰임을 명시한다(성장루프 LOW 수렴 — 문구·실계산 정합). */}
      {usage?.scope === "platform" ? (
        <div
          role="status"
          className="mt-4 rounded-[var(--radius-xl)] border border-[rgba(14,116,144,0.3)] bg-[rgba(14,116,144,0.08)] px-5 py-3 text-sm text-[var(--accent-strong)]"
        >
          관리자 뷰: 아래 수치는 <strong>플랫폼 전체 회원</strong>의 AI 사용량 합계입니다(본인 사용량 아님).
        </div>
      ) : null}

      {error ? (
        <div
          role="status"
          className="mt-4 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] px-5 py-3.5 text-sm text-[rgb(146,64,14)]"
        >
          사용내역을 불러오지 못했습니다. 잠시 후 새로고침해 주세요. (표시되는 수치가 없으므로 0원과
          혼동하지 않도록 안내드립니다.)
        </div>
      ) : (
      <>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">총 사용 코인</h2>
          <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
            {loading ? "…" : formatKrw(usage?.total_cost_krw)}
          </p>
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            {loading
              ? `최근 ${days}일`
              : `처리 토큰 ${Number(usage?.total_tokens ?? 0).toLocaleString("ko-KR")}개 · 최근 ${days}일`}
          </p>
        </section>

        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">서비스별 사용</h2>
          {(usage?.by_service ?? []).length === 0 ? (
            <p className="mt-3 text-sm text-[var(--text-tertiary)]">
              {loading ? "불러오는 중…" : "이 기간의 사용 기록이 없습니다."}
            </p>
          ) : (
            <ul className="mt-3 space-y-2">
              {(usage?.by_service ?? []).slice(0, 6).map((s) => (
                <li key={s.service} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--text-primary)]">
                    {SERVICE_LABELS[s.service] ?? s.service}
                  </span>
                  <span className="font-semibold text-[var(--text-primary)]">
                    {formatKrw(s.cost_krw)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* 일별 사용 차트(CSS 바) */}
      <section className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">일별 사용 추이</h2>
        {(usage?.daily ?? []).length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">
            {loading ? "불러오는 중…" : "이 기간의 사용 기록이 없습니다."}
          </p>
        ) : (
          <>
            <div
              className="mt-4 flex h-36 items-end gap-[3px] overflow-x-auto"
              role="img"
              aria-label={`일별 사용 코인 막대 그래프 — 상세 수치는 아래 표 참조(최근 ${days}일)`}
            >
              {(usage?.daily ?? []).map((d) => (
                <div key={d.date} className="group relative flex-1 min-w-[6px]">
                  <div
                    className="w-full rounded-t bg-[var(--accent-strong)] opacity-80 transition group-hover:opacity-100"
                    style={{ height: `${Math.max(4, (d.cost_krw / maxDailyCost) * 130)}px` }}
                  />
                  <span className="pointer-events-none absolute -top-9 left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded bg-[var(--text-primary)] px-2 py-1 text-[10px] text-white group-hover:block">
                    {d.date} · {formatKrw(d.cost_krw)}
                  </span>
                </div>
              ))}
            </div>
            {/* 접근성(성장루프 LOW 수렴): hover 전용 tooltip은 키보드·스크린리더가 못 읽으므로
                동일 데이터를 시각적으로 숨긴 표로 함께 제공한다(WCAG 1.1.1/2.1.1). */}
            <table className="sr-only">
              <caption>일별 AI 사용 코인</caption>
              <thead>
                <tr>
                  <th scope="col">일자</th>
                  <th scope="col">사용 코인(원)</th>
                </tr>
              </thead>
              <tbody>
                {(usage?.daily ?? []).map((d) => (
                  <tr key={d.date}>
                    <td>{d.date}</td>
                    <td>{formatKrw(d.cost_krw)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
          산출근거: AI 호출 1건마다 사용 토큰·비용이 기록되며, 위 수치는 해당 기록의 일별 합계입니다.
          서비스 사용료(프로젝트 생성 등)는 &lsquo;코인·결제&rsquo; 탭의 코인내역에서 확인할 수 있습니다.
        </p>
      </section>
      </>
      )}
    </MyPageShell>
  );
}
