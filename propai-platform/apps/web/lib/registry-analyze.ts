"use client";

/**
 * 등기 권리분석 — 비동기 작업 제출 + 폴링 헬퍼.
 *
 * 모바일 안정: 50초짜리 단일 동기요청 대신 작업을 제출(job_id)하고 짧은 요청으로 폴링한다.
 * 서버가 결과를 보관하므로 앱 전환·화면잠금 후 복귀해도 결과를 그대로 가져온다.
 * - 캐시 적중 시 제출 단계에서 즉시 결과 반환(폴링 생략).
 * - 화면 복귀(visibilitychange) 시 즉시 1회 재확인하여 응답 지연을 줄인다.
 */

import { apiClient } from "@/lib/api-client";

export type RegistryAnalyzeBody = Record<string, unknown>;

type SubmitResp = { job_id: string | null; status: string; result?: unknown };
type StatusResp = { status: string; result?: unknown; error?: string };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** 화면이 보일 때까지 대기(백그라운드면 즉시 깨어나지 않음). 최대 ms 대기 후 반환. */
function waitTick(ms: number): Promise<void> {
  return new Promise<void>((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      document.removeEventListener("visibilitychange", onVis);
      resolve();
    };
    const onVis = () => {
      if (document.visibilityState === "visible") finish();
    };
    document.addEventListener("visibilitychange", onVis);
    setTimeout(finish, ms);
  });
}

/**
 * 등기 분석 실행(제출→폴링). 완료 결과(Result) 반환.
 * @param body /registry/analyze 와 동일 본문
 * @param onProgress 경과 안내 콜백(선택)
 */
export async function analyzeRegistry<T = unknown>(
  body: RegistryAnalyzeBody,
  onProgress?: (msg: string) => void,
): Promise<T> {
  const job = await apiClient.post<SubmitResp>("/registry/analyze/jobs", {
    body,
    useMock: false,
    timeoutMs: 30000,
  });

  if (job.status === "done" && job.result) return job.result as T;
  if (!job.job_id) throw new Error("작업 제출에 실패했습니다.");

  const jobId = job.job_id;
  const deadline = Date.now() + 5 * 60 * 1000; // 최대 5분
  let n = 0;
  while (Date.now() < deadline) {
    await waitTick(4000);
    n += 1;
    if (onProgress) onProgress(`등기부 발급·분석 중… (${n * 4}초 경과, 최대 1분)`);
    let s: StatusResp;
    try {
      s = await apiClient.get<StatusResp>(`/registry/analyze/jobs/${jobId}`, {
        useMock: false,
        timeoutMs: 30000,
      });
    } catch {
      continue; // 네트워크 일시 오류 → 다음 폴링 재시도
    }
    if (s.status === "done") return s.result as T;
    if (s.status === "error") throw new Error(s.error || "등기 분석에 실패했습니다.");
  }
  throw new Error("등기 분석 시간이 초과되었습니다. 잠시 후 다시 시도하세요.");
}

// ─────────────────────────────────────────────────────────────────────────────
// 일괄 분석 결과 요약 — **왜 멈췄는지**를 한 줄로 말한다
// ─────────────────────────────────────────────────────────────────────────────
//
// ★왜 필요한가 (2026-08-24 실장애):
//   사용자가 77필지를 일괄 분석했는데 수십 건 성공 후 나머지가 전부 실패했다.
//   실제 원인은 **하이픈 민원캐시(선불 잔액) 소진**이었고, 충전하자 즉시 복구됐다.
//   그런데 화면은 **행이 조용히 비어 있을 뿐**이었다 — 개수(`N/M`)만 있고 **사유가 없었다**.
//   사유는 응답의 `message` 에 들어 있었는데 UI 는 그것을 **존재 여부로만** 썼다
//   (`b.result?.message ? "미확보" : "실패"`).
//
//   ★사용자가 원인을 알아야 스스로 조치한다(충전이면 충전, 주소 오류면 수정).
//     개수만 보여 주면 "시스템이 고장났나" 로 읽고 기다리게 된다.

/** 일괄 결과 한 건 — 화면이 누적해 둔 모양(성공/실패 무관). */
export type BatchOutcome = {
  jibun: string;
  result: { status?: string; message?: string; ai?: unknown } | null;
};

export type BatchSummary = {
  /** 권리분석(ai)까지 나온 건수. */
  ok: number;
  /** 전체 시도 건수. */
  total: number;
  /** 실패 건수(= total − ok). */
  failed: number;
  /** 사유별 건수(많은 순). 사유가 없으면 빈 배열. */
  reasons: { reason: string; count: number }[];
  /** 가장 많은 실패 사유(없으면 null) — 화면 머리말에 한 줄로 쓴다. */
  topReason: string | null;
};

/** 사유 문자열을 **집계 가능한 단위**로 줄인다(필지 주소·번호가 섞이면 전부 다른 사유가 된다). */
function normalizeReason(msg: string): string {
  return msg
    .replace(/\s+/g, " ")
    .replace(/[0-9]{6,}/g, "…")        // 고유번호·PNU 등 긴 숫자
    .trim()
    .slice(0, 120);
}

/**
 * 일괄 결과 → 요약. **사유를 지어내지 않는다** — 응답이 사유를 안 주면 그 사실을 그대로 센다.
 *
 * ★`ai` 가 있어야 성공이다. `status:"ok"` 만 보고 성공이라 하면, 등기 본문을 못 얻어
 *   권리분석이 비어 있는 건(`status:"empty"`)이 성공으로 셈해진다.
 */
export function summarizeBatch(items: readonly BatchOutcome[]): BatchSummary {
  const total = items.length;
  const ok = items.filter((b) => b.result && b.result.ai).length;
  const counts = new Map<string, number>();
  for (const b of items) {
    if (b.result && b.result.ai) continue;
    const raw = (b.result?.message || "").trim();
    // 요청 자체가 실패해 result 가 없으면 그렇게 말한다(사유 없음과 구분).
    const reason = raw
      ? normalizeReason(raw)
      : b.result
        ? "사유 미제공(공급자가 이유를 주지 않음)"
        : "요청 실패(네트워크·시간초과)";
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  const reasons = [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
  return { ok, total, failed: total - ok, reasons, topReason: reasons[0]?.reason ?? null };
}
