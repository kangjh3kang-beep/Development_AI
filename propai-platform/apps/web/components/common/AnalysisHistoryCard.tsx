"use client";

/**
 * AnalysisHistoryCard — 분석 히스토리(원장) 열람 + 입력변동 감지 + 재분석 유도 공용 카드.
 *
 * 백엔드 계약(GET /analysis-ledger/history)을 옵셔널 소비 — 미구현·비로그인·404 모두
 * "히스토리 없음"으로 정직 처리한다(무목업). 재분석 실행 자체는 호스트가 이미 가진 실행 함수를
 * 그대로 호출한다(onReanalyze) — 이 카드는 실행 로직을 중복 보유하지 않는다.
 *
 * 변동 감지 배너: use-analysis-cache.ts의 "자동 재실행 금지" 철학을 그대로 따른다 — 배너는
 * 재분석을 "제안"만 하고, 클릭 전까지 아무것도 재실행하지 않는다.
 */

import { useEffect, useMemo, useState } from "react";
import { History, RotateCcw } from "lucide-react";
import { useAnalysisHistory, type AnalysisHistoryEntry } from "@/lib/use-analysis-history";
import { relativeKoreanTime } from "@/lib/use-analysis-cache";
import {
  AnalysisDiffTable,
  DIFF_FIELD_MAP,
  formatFieldValue,
  getFieldPath,
  type DiffAnalysisType,
} from "./AnalysisDiffTable";

export function AnalysisHistoryCard({
  analysisType,
  address,
  pnu,
  currentSignatureParts,
  onReanalyze,
  reanalyzing = false,
  refreshSignal,
  className = "",
}: {
  analysisType: DiffAnalysisType;
  address?: string | null;
  pnu?: string | null;
  /** analysisSignature(...) 호출 순서와 동일한 파트 배열 — 변동 감지 비교에 사용. */
  currentSignatureParts: Array<string | number | null | undefined>;
  /** 호스트의 기존 실행 함수 — "이 입력으로 재분석" 클릭 시 그대로 호출(로직 중복 없음). */
  onReanalyze?: () => void;
  reanalyzing?: boolean;
  /** 값이 바뀔 때마다 히스토리를 재조회(호스트가 새 분석 완료 후 갱신 신호로 사용). */
  refreshSignal?: string | number;
  className?: string;
}) {
  const { entries, latest, loading, error, isChanged, refetch } = useAnalysisHistory({
    analysisType,
    address,
    pnu,
  });
  const [open, setOpen] = useState(false);
  const [openVersion, setOpenVersion] = useState<number | null>(null);
  const [compareSet, setCompareSet] = useState<number[]>([]);

  // 호스트가 새 분석을 완료했을 때 히스토리를 다시 불러온다(카드 언마운트 없이).
  useEffect(() => {
    if (refreshSignal === undefined) return;
    void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  const changed = useMemo(() => isChanged(currentSignatureParts), [isChanged, currentSignatureParts]);
  const fields = DIFF_FIELD_MAP[analysisType] ?? [];
  const firstField = fields[0];

  if (!address) return null; // 분석 대상 없음 — 카드 자체를 렌더하지 않는다(소음 제거).

  const toggleCompare = (version: number) => {
    setCompareSet((prev) => {
      if (prev.includes(version)) return prev.filter((v) => v !== version);
      if (prev.length >= 2) return [prev[1], version]; // 최근 선택 2개만 유지
      return [...prev, version];
    });
  };

  const compareEntries = compareSet
    .map((v) => entries.find((e) => e.version === v))
    .filter((e): e is AnalysisHistoryEntry => !!e)
    .sort((a, b) => a.version - b.version);

  return (
    <section className={`sa-di-block ${className}`}>
      <button type="button" onClick={() => setOpen((v) => !v)} className="sa-di-block__head">
        <span className="sa-di-block__icon" aria-hidden>
          <History className="size-3.5" />
        </span>
        <span className="sa-di-block__title">
          분석 히스토리{entries.length > 0 ? ` (${entries.length})` : ""}
        </span>
        {latest && (
          <span className="sa-di-eyebrow">
            최신 v{latest.version} · {relativeKoreanTime(new Date(latest.created_at).getTime())}
          </span>
        )}
        <span className="sa-di-block__chevron" data-open={open ? "true" : "false"}>
          ▾
        </span>
      </button>

      {changed && (
        <div className="border-t border-[var(--line-subtle)] px-4 py-3">
          {/* 변동감지 배너 — --status-warning(DESIGN.md B1: "조건부·협의중·미지급·변동감지" 용도). */}
          <div className="rounded-[var(--radius-sm)] border border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-3">
            <p className="font-mono text-[10px] font-bold uppercase tracking-wide text-[var(--status-warning)]">
              입력 변동 감지
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              마지막 분석 이후 입력이 변경되었습니다 — 재분석을 제안합니다(자동으로 다시 실행되지 않습니다).
            </p>
            {onReanalyze && (
              <button
                type="button"
                onClick={onReanalyze}
                disabled={reanalyzing}
                className="mt-2 rounded-lg border border-[var(--status-warning)]/40 bg-[var(--surface)] px-3 py-1.5 text-xs font-bold text-[var(--status-warning)] hover:bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] disabled:opacity-50"
              >
                {reanalyzing ? "재분석 중…" : "재분석 실행"}
              </button>
            )}
          </div>
        </div>
      )}

      {open && (
        <div className="sa-di-block__body space-y-3">
          {loading && <p className="sa-di-empty">히스토리를 불러오는 중…</p>}
          {!loading && error && <p className="sa-di-empty">{error}</p>}
          {!loading && !error && entries.length === 0 && (
            <p className="sa-di-empty">저장된 분석 히스토리가 없습니다.</p>
          )}

          {!loading && entries.length > 0 && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="sa-di-eyebrow">버전 목록 · 비교할 2개를 선택하세요</p>
                {onReanalyze && (
                  <button
                    type="button"
                    onClick={onReanalyze}
                    disabled={reanalyzing}
                    className="inline-flex items-center gap-1 text-xs font-bold text-[var(--accent-strong)] hover:opacity-80 disabled:opacity-50"
                  >
                    <RotateCcw className="size-3" aria-hidden />
                    {reanalyzing ? "재분석 중…" : "이 입력으로 재분석"}
                  </button>
                )}
              </div>
              {/* market_report만: 필지세트 지문(6번째 시그니처 파트)은 프론트가 재계산할 수 없어
                  변동감지 비교에서 제외한다 — 필지 '개수'는 그대로 잡히지만, 동일 개수의 필지를
                  다른 구성으로 교체한 경우는 배너로 잡히지 않을 수 있다(정직 표기, 무날조). */}
              {analysisType === "market_report" && (
                <p className="text-[10px] leading-snug text-[var(--text-hint)]">
                  ※ 감지 한계: 필지 수가 같고 구성만 바뀐 경우(예: A+B → A+C 2필지)는 자동 변동감지에
                  걸리지 않을 수 있습니다 — 필지 구성을 바꿨다면 수동으로 재분석해 주세요.
                </p>
              )}
              {onReanalyze && (
                <p className="text-[10px] leading-snug text-[var(--text-hint)]">
                  입력이 바뀌지 않았다면 서버에 저장된 결과로 즉시 복원됩니다(재계산 비용 0).
                </p>
              )}

              <ul className="sa-di-rows">
                {entries.map((e) => {
                  const summary = firstField
                    ? formatFieldValue(getFieldPath(e.payload, firstField.key), firstField.fmt, firstField.unit)
                    : "";
                  return (
                    <li key={e.version} className="sa-di-row items-center">
                      <label className="flex min-w-0 items-center gap-2">
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 shrink-0 accent-[var(--accent-strong)]"
                          checked={compareSet.includes(e.version)}
                          onChange={() => toggleCompare(e.version)}
                          aria-label={`v${e.version} 비교 선택`}
                        />
                        <button
                          type="button"
                          onClick={() => setOpenVersion((v) => (v === e.version ? null : e.version))}
                          className="truncate text-left text-xs font-semibold text-[var(--text-primary)] hover:text-[var(--accent-strong)]"
                        >
                          v{e.version} · {relativeKoreanTime(new Date(e.created_at).getTime())}
                        </button>
                      </label>
                      <span className="sa-di-row__value">{summary || "—"}</span>
                    </li>
                  );
                })}
              </ul>

              {openVersion != null &&
                (() => {
                  const e = entries.find((x) => x.version === openVersion);
                  if (!e) return null;
                  return (
                    <div className="sa-di-sub">
                      <p className="sa-di-eyebrow">v{e.version} 요약</p>
                      <dl className="sa-di-rows mt-2">
                        {fields.map((f) => (
                          <div key={f.key} className="sa-di-row">
                            <dt className="sa-di-row__label">{f.label}</dt>
                            <dd className="sa-di-row__value">
                              {formatFieldValue(getFieldPath(e.payload, f.key), f.fmt, f.unit)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  );
                })()}

              {compareEntries.length === 2 && (
                <div className="sa-di-sub">
                  <p className="sa-di-eyebrow">
                    v{compareEntries[0].version} → v{compareEntries[1].version} 비교
                  </p>
                  <div className="mt-2">
                    <AnalysisDiffTable
                      analysisType={analysisType}
                      oldEntry={compareEntries[0]}
                      newEntry={compareEntries[1]}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
