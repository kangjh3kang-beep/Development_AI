"use client";

/**
 * 분석 히스토리(원장) 목록/최신 조회 훅 — GET /analysis-ledger/history 옵셔널 소비.
 *
 * 백엔드 계약: 엔트리 [{version, created_at, content_hash, payload:{...요약,
 *   input_signature, signature_parts}}] (JWT 필수). 응답 봉투는 라우터(analysis_ledger.py)의
 *   `{ok, count, history}` — 키는 "history"(레거시 "entries" 래핑도 방어적으로 함께 인식).
 * JWT 부재/401/403은 오류가 아니라 "히스토리 없음"으로 정직 처리한다(로그인 리다이렉트 금지 —
 * skipSessionExpiry). 그 외 오류만 error에 남긴다(무자료와 오류를 구분).
 *
 * 변동 감지(isChanged) 비교 계약(R1 REVISE) — 해시(input_signature) 비교는 사용하지 않는다
 * (프론트가 백엔드 옵션 canonical화를 완전히 재현하지 못하면 해시가 상시 어긋나 배너가 상시
 * 오발화했다). 대신 저장된 `signature_parts`(평문 배열, 순서 고정:
 * [address_norm, pnu, parcel_count, use_llm, options_summary, ...extra])만 비교 기준으로 삼되:
 *   · idx0(address_norm)·idx1(pnu) — 체인 불변 파트. 히스토리 자체가 이미 이 두 값으로 스코프되어
 *     있으므로(주소/PNU가 다르면 애초에 다른 체인을 조회) 비교 대상에서 제외한다.
 *   · idx2(parcel_count)·idx3(use_llm)·idx4(options_summary) — 실제 가변 입력. 이 3개만 비교한다.
 *   · idx3(use_llm)은 백엔드가 Python `str(bool(...))`(True/False)로 적재하고 프론트는
 *     `String(boolean)`(true/false)을 조립하므로 대소문자만 다르고 값은 같다 — 양측 lowercase로
 *     비교한다(대소문자 불일치로 인한 오탐 배너 차단).
 *   · idx4(options_summary)는 프론트가 optionsSummary() 헬퍼(아래)로 백엔드
 *     ledger_adapters._options_summary()를 그대로 미러링해 조립한 canonical 문자열이어야 한다
 *     (JSON.stringify는 키 순서에 민감해 저장값과 어긋난다 — 절대 사용 금지).
 *   · idx5+(예: market_report의 필지세트 지문)는 프론트가 재계산할 수 없는 파생값이라 비교에서
 *     제외한다(해당 변화는 "감지 한계"로 UI에 별도 정직 표기 — AnalysisHistoryCard 참고).
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError, hasAccessToken } from "@/lib/api-client";

export type AnalysisHistoryEntry = {
  version: number;
  created_at: string;
  content_hash: string;
  payload: Record<string, unknown> & {
    input_signature?: string | null;
    signature_parts?: string[] | null;
  };
};

// 라우터(analysis_ledger.py `/history`)의 실제 응답 키는 "history"다. "entries"는 과거 계약
// 추정으로 남겨둔 방어적 폴백(있으면 우선 — 미래 계약 변경에도 무회귀).
type HistoryResponse =
  | { entries?: AnalysisHistoryEntry[]; history?: AnalysisHistoryEntry[] }
  | AnalysisHistoryEntry[];

/**
 * 옵션 dict → 결정적 요약 문자열 — 백엔드 `ledger_adapters._options_summary()`의 TS 미러(단일
 * 소유자 산식을 프론트로 그대로 복제). 키를 정렬하고(중첩 dict도 재귀 정렬), 값 표기는 Python
 * `str()` 규약(bool→True/False, None→None)을 따른다 — JS의 소문자 true/false를 쓰면 백엔드가
 * 저장한 문자열과 바이트가 어긋나 변동감지가 항상 오탐한다.
 */
export function optionsSummary(options: Record<string, unknown> | null | undefined): string {
  if (!options || typeof options !== "object" || Array.isArray(options) || Object.keys(options).length === 0) {
    return "";
  }
  const fmt = (v: unknown): string => {
    if (v === null || v === undefined) return "None";
    if (typeof v === "boolean") return v ? "True" : "False";
    if (Array.isArray(v)) return "[" + v.map(fmt).join(",") + "]";
    if (typeof v === "object") {
      const entries = Object.entries(v as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
      return "{" + entries.map(([k, v2]) => `${k}:${fmt(v2)}`).join(",") + "}";
    }
    return String(v);
  };
  const entries = Object.entries(options).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return entries.map(([k, v]) => `${k}=${fmt(v)}`).join(",");
}

export function useAnalysisHistory(params: {
  analysisType: string;
  address?: string | null;
  pnu?: string | null;
}) {
  const { analysisType, address, pnu } = params;
  const [entries, setEntries] = useState<AnalysisHistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const refetch = useCallback(async () => {
    // 대상 주소 미확정이거나 비로그인이면 조회 자체를 생략 — 빈 상태를 정직 반환(무의미한 401 왕복 차단).
    if (!address || !hasAccessToken()) {
      setEntries([]);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams({ analysis_type: analysisType, address, include_payload: "true" });
      if (pnu) q.set("pnu", pnu);
      const r = await apiClient.get<HistoryResponse>(`/analysis-ledger/history?${q.toString()}`, {
        useMock: false,
        timeoutMs: 15000,
        // 선택형 위젯 — 만료 세션이어도 전역 로그인 리다이렉트를 유발하지 않는다.
        skipSessionExpiry: true,
      });
      // ★버그 수정: 라우터가 실제로 내려주는 봉투 키는 "history"다(analysis_ledger.py 확인).
      //   과거 "entries" 가정만 읽으면 실운영에서 상시 빈 배열 — 히스토리 카드가 영구 무자료로
      //   보였다(발견 즉시 수정 — 이 훅이 R1 REVISE의 소비 표면이라 여기서 함께 봉합).
      const list = Array.isArray(r) ? r : (r?.history ?? r?.entries ?? []);
      setEntries(list);
    } catch (e) {
      // 401/403(비로그인·권한없음)은 "무자료"로 정직 처리 — 그 외(5xx·네트워크)만 오류 표기.
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403 || e.status === 404)) {
        setEntries([]);
      } else {
        setEntries([]);
        setError("분석 히스토리 조회에 실패했습니다.");
      }
    } finally {
      setLoading(false);
    }
  }, [analysisType, address, pnu]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // 서버가 최신순으로 내려주지 않는 경우까지 대비해 version desc로 재정렬(무가정).
  const sorted = [...entries].sort((a, b) => (b.version ?? 0) - (a.version ?? 0));
  const latest = sorted[0] ?? null;

  const isChanged = useCallback(
    (currentParts: Array<string | number | null | undefined>): boolean => {
      if (!latest) return false;
      // 해시(input_signature) 비교는 완전 제거 — signature_parts(평문 배열)만 기준(파일 상단
      //   주석의 비교 계약 참고). 배열 자체가 없으면(구 데이터·비교 재료 미부착) 비교 기준
      //   없음으로 간주해 가짜 변동 배너를 띄우지 않는다.
      const stored = latest.payload?.signature_parts;
      if (!Array.isArray(stored) || stored.length === 0) return false;
      const cur = (i: number) => String(currentParts[i] ?? "");
      const st = (i: number) => String(stored[i] ?? "");
      // 체인 불변 파트(idx0 address_norm·idx1 pnu)는 비교 제외 — 히스토리가 이미 그 둘로
      // 스코프되어 있다. idx2 parcel_count / idx3 use_llm(대소문자 무관) / idx4 options_summary만
      // 비교한다. idx5+(예: market_report 필지세트 지문)는 프론트가 재계산 불가라 비교 제외.
      if (cur(2) !== st(2)) return true;
      if (cur(3).toLowerCase() !== st(3).toLowerCase()) return true;
      if (cur(4) !== st(4)) return true;
      return false;
    },
    [latest],
  );

  return { entries: sorted, latest, loading, error, refetch, isChanged };
}
