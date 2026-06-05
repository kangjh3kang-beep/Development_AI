/**
 * 분석 원장(해시체인) 클라이언트 헬퍼 — write-through 적재 + 최신 복원 + 무결성 검증.
 * 백엔드 /api/v1/analysis-ledger/*. apiClient가 /api/v1 prefix·인증헤더 처리.
 */

import { apiClient } from "@/lib/api-client";

export type LedgerKey = { pnu?: string | null; address?: string | null; projectId?: string | null };

export type LedgerLatest = {
  ok: boolean;
  data?:
    | { version: number; content_hash: string; created_at: string; payload: Record<string, unknown> }
    | Record<string, { version: number; content_hash: string; created_at: string; payload: Record<string, unknown> }>
    | null;
};

export type LedgerVerify = {
  ok: boolean; verified?: boolean; length?: number; head_version?: number;
  broken?: { version: number; issue: string }[]; message?: string;
};

function qs(analysisType: string, key: LedgerKey): string {
  const q = new URLSearchParams();
  q.set("analysis_type", analysisType);
  if (key.pnu) q.set("pnu", key.pnu);
  if (key.address) q.set("address", key.address);
  if (key.projectId) q.set("project_id", key.projectId);
  return q.toString();
}

/** 분석 결과를 원장에 적재(버전+해시체인). best-effort(실패해도 흐름 영향 없음). */
export async function appendLedger(
  analysisType: string, payload: unknown, key: LedgerKey, source: "quick" | "project",
): Promise<{ ok?: boolean; version?: number; unchanged?: boolean; quota_exceeded?: boolean; message?: string } | null> {
  try {
    return await apiClient.post("/analysis-ledger/append", {
      body: {
        analysis_type: analysisType, payload,
        pnu: key.pnu || undefined, address: key.address || undefined,
        project_id: key.projectId || undefined, source,
      },
      useMock: false,
    });
  } catch {
    return null;
  }
}

/** 체인 최신 분석 복원(서버·기기간 공유). */
export async function latestLedger(analysisType: string, key: LedgerKey): Promise<LedgerLatest | null> {
  try {
    return await apiClient.get<LedgerLatest>(`/analysis-ledger/latest?${qs(analysisType, key)}`, { useMock: false });
  } catch {
    return null;
  }
}

/** 체인 무결성 검증(변조 탐지). */
export async function verifyLedger(analysisType: string, key: LedgerKey): Promise<LedgerVerify | null> {
  try {
    return await apiClient.get<LedgerVerify>(`/analysis-ledger/verify?${qs(analysisType, key)}`, { useMock: false });
  } catch {
    return null;
  }
}
