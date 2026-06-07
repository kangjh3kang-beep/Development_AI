"use client";

import { useCallback } from "react";

import {
  useProjectContextStore,
  type AnalysisCacheKind,
} from "@/store/useProjectContextStore";

/**
 * 무거운 휘발성 분석(지형·환경·AVM·디지털트윈 등)의 영속 캐시 훅.
 *
 * 철학(사용자 합의): ① 한번 분석하면 프로젝트 스냅샷에 영속 → 재방문 시 즉시 재사용,
 * ② 입력(원·첨부·보강 데이터) 시그니처가 같으면 검증된 결과를 반복 제공(재실행 없음),
 * ③ 입력이 바뀌면 결과는 유지하되 stale=true로 "재분석 제안"을 띄운다(자동 재실행 안 함).
 *
 * @param kind 분석 종류
 * @param signature 재분석 트리거가 되는 입력값들의 결정적 문자열(빈 문자열이면 비교 불가로 간주)
 */
export function useAnalysisCache<T = unknown>(
  kind: AnalysisCacheKind,
  signature: string,
) {
  const entry = useProjectContextStore((s) => s.analysisCache?.[kind] ?? null);
  const setCache = useProjectContextStore((s) => s.setAnalysisCache);

  const hasCache = !!entry;
  // 시그니처가 비어있으면(입력 미확정) 신선도 판정을 보류 → 캐시가 있으면 그대로 보여주되 stale 아님.
  const isFresh = !!entry && (signature === "" || entry.signature === signature);
  const isStale = hasCache && signature !== "" && entry!.signature !== signature;
  const cached = (entry?.data ?? undefined) as T | undefined;
  const at = entry?.at ?? null;

  const save = useCallback(
    (data: T) => setCache(kind, signature, data),
    [kind, signature, setCache],
  );

  return { cached, hasCache, isFresh, isStale, at, save };
}

/** 입력값들을 결정적 문자열 시그니처로 결합(undefined/null은 빈칸). */
export function analysisSignature(
  ...parts: Array<string | number | null | undefined>
): string {
  return parts
    .map((p) => (p === null || p === undefined ? "" : String(p)))
    .join("|");
}

/** "방금/N분 전/N시간 전/N일 전" 한국어 상대시각(분석 산출 시각 표기용). */
export function relativeKoreanTime(at: number | null): string {
  if (!at) return "";
  const diff = Date.now() - at;
  if (diff < 60_000) return "방금 분석됨";
  const min = Math.floor(diff / 60_000);
  if (min < 60) return `${min}분 전 분석`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 전 분석`;
  const day = Math.floor(hr / 24);
  return `${day}일 전 분석`;
}
