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
