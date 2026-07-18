"use client";

/**
 * 시장조사보고서 — 비동기 작업 제출 + 폴링 헬퍼(lib/registry-analyze.ts analyzeRegistry 패턴 적응).
 *
 * 모바일 안정: 단일 블로킹 POST 대신 POST /market/report/jobs 로 제출(job_id) 후 짧은 요청으로
 * 폴링한다(캐시 적중 시 제출 단계에서 즉시 result 반환 — 폴링 생략). 화면 복귀(visibilitychange)
 * 시 즉시 1회 재확인해 응답 지연을 줄인다(registry-analyze.ts와 동일 관례).
 *
 * 리로드 복원: 진행 중 job_id를 sessionStorage(키 "propai:market-report:active-job")에 보존해
 * 탭 종료·새로고침 후에도 이어서 폴링한다(design-audit DesignAuditWorkspace.tsx:284-322 패턴).
 */

import { apiClient } from "@/lib/api-client";

export const MARKET_REPORT_JOB_STORAGE_KEY = "propai:market-report:active-job";

export type MarketReportJobBody = Record<string, unknown>;

type SubmitResp = { job_id: string | null; status: string; result?: unknown };
type StatusResp = { status: string; result?: unknown; error?: string };

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
 * 진행 중 잡을 sessionStorage에 기록(리로드 복원용).
 *
 * address(옵션): 제출 당시 분석 대상 주소 — resumeMarketReportJob의 stale 가드 재료(아래).
 * 미전달(구 호출부)이면 null로 저장 — 가드는 이 경우 항상 통과(무회귀).
 */
export function saveActiveMarketReportJob(jobId: string, startedAt: number, address?: string | null): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      MARKET_REPORT_JOB_STORAGE_KEY,
      JSON.stringify({ jobId, startedAt, address: address ?? null }),
    );
  } catch {
    /* noop — sessionStorage 비활성 환경 */
  }
}

/** 완료·실패 시 진행 잡 흔적 제거. */
export function clearActiveMarketReportJob(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(MARKET_REPORT_JOB_STORAGE_KEY);
  } catch {
    /* noop */
  }
}

/** 리로드 복원 — 진행 중이던 잡(jobId·startedAt·address)을 sessionStorage에서 읽는다. 없으면 null. */
export function readActiveMarketReportJob(): { jobId: string; startedAt: number; address: string | null } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(MARKET_REPORT_JOB_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { jobId?: string; startedAt?: number; address?: string | null };
    if (!parsed?.jobId) {
      window.sessionStorage.removeItem(MARKET_REPORT_JOB_STORAGE_KEY);
      return null;
    }
    return { jobId: parsed.jobId, startedAt: parsed.startedAt ?? Date.now(), address: parsed.address ?? null };
  } catch {
    return null;
  }
}

/** job_id 폴링(4초 간격 · 최대 5분). 완료 시 결과, 실패 시 에러 throw. */
async function pollMarketReportJob<T>(jobId: string): Promise<T> {
  const deadline = Date.now() + 5 * 60 * 1000;
  while (Date.now() < deadline) {
    await waitTick(4000);
    let s: StatusResp;
    try {
      s = await apiClient.get<StatusResp>(`/market/report/jobs/${encodeURIComponent(jobId)}`, {
        useMock: false,
        timeoutMs: 15000,
      });
    } catch {
      continue; // 네트워크 일시 오류 → 다음 폴링 재시도
    }
    if (s.status === "done" && s.result) return s.result as T;
    if (s.status === "error") throw new Error(s.error || "시장조사보고서 생성에 실패했습니다.");
  }
  throw new Error("시장조사보고서 생성 시간이 초과되었습니다. 잠시 후 다시 시도하세요.");
}

/**
 * 보고서 실행(제출 → 폴링). 캐시 적중 시 제출 응답에 result가 바로 실려온다(폴링 생략).
 * 진행 중엔 sessionStorage에 기록하고, 완료/실패 시(성공·에러 모두) 흔적을 제거한다.
 * body.address가 문자열이면 stale 가드 재료로 함께 저장한다(resumeMarketReportJob 참고).
 */
export async function submitMarketReportJob<T = unknown>(body: MarketReportJobBody): Promise<T> {
  const startedAt = Date.now();
  const job = await apiClient.post<SubmitResp>("/market/report/jobs", {
    body,
    useMock: false,
    timeoutMs: 30000,
  });
  if (job.status === "done" && job.result) return job.result as T;
  if (!job.job_id) throw new Error("보고서 작업 제출에 실패했습니다.");
  const address = typeof body.address === "string" ? body.address : null;
  saveActiveMarketReportJob(job.job_id, startedAt, address);
  try {
    return await pollMarketReportJob<T>(job.job_id);
  } finally {
    clearActiveMarketReportJob();
  }
}

/**
 * 리로드 복원 — 신규 제출 없이 기존 job_id를 이어서 폴링만 한다.
 *
 * stale 가드: currentAddress를 전달하면, sessionStorage에 저장된 잡의 address와 비교해
 * 서로 다르면(예: 리로드 사이 다른 프로젝트로 전환된 경우) 폴링을 시작하지 않고 흔적만
 * 제거한 뒤 null을 반환한다(엉뚱한 주소의 보고서가 현재 화면에 표시되는 사고 방지).
 * currentAddress 미전달(호출부가 아직 주소를 모름) 또는 저장된 address가 없으면(구 데이터)
 * 가드를 건너뛰고 항상 재개한다(무회귀).
 */
export async function resumeMarketReportJob<T = unknown>(
  jobId: string,
  currentAddress?: string,
): Promise<T | null> {
  if (currentAddress) {
    const active = readActiveMarketReportJob();
    if (active?.address && active.address !== currentAddress) {
      clearActiveMarketReportJob();
      return null;
    }
  }
  try {
    return await pollMarketReportJob<T>(jobId);
  } finally {
    clearActiveMarketReportJob();
  }
}
