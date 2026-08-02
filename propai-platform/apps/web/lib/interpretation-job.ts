/**
 * AI 해석 2단계 수신 공용 로직 — 제출하고, 끝날 때까지 기다렸다가, 결과만 돌려준다.
 *
 * ## 왜 공용으로 빼는가
 *
 * 종합분석은 **한 번에 다 받으면 통째로 실패한다.** 결정론 분석은 몇 초면 끝나는데 AI 해석
 * 2종이 125초를 넘겨서, 중간 경로(Cloudflare)가 응답을 잘라버리고 **분석 결과까지 함께
 * 사라진다.** 그래서 해석은 별도 작업으로 제출하고 폴링으로 받는다.
 *
 * 그런데 이 처리가 종합분석 화면에만 들어가 있었고, 같은 API를 쓰는 **프로젝트 AI 인사이트
 * 카드는 옛 방식 그대로**여서 라이브에서 100% 실패하고 있었다(실측: 캐시가 가장 두터운 주소도
 * 99.9초, 신규 주소는 125.2초에 잘림 — 클라이언트 90초 타임아웃에 먼저 걸린다). 한 곳을
 * 고치면 두 곳이 함께 따라오도록 여기로 모은다.
 */

import { apiClient } from "@/lib/api-client";

export type InterpretationParts = Record<string, unknown>;

export interface InterpretationOptions {
  llmProvider?: string | null;
  llmModel?: string | null;
  /** 폴링 간격(ms). 기본 3초. */
  pollIntervalMs?: number;
  /** 전체 대기 상한(ms). 기본 5분 — 해석 실측 소요가 125초 이상이라 여유를 둔다. */
  deadlineMs?: number;
  /**
   * 취소 신호. 화면을 떠나면 폴링을 멈추기 위해 쓴다.
   *
   * ★없으면 사용자가 탭을 바꿔 컴포넌트가 사라져도 최대 5분간 3초마다 조회가 계속된다.
   *   종전 단발 호출(90초)보다 노출 창이 길어지는 구간이라 취소를 붙였다.
   */
  signal?: AbortSignal;
}

/** 취소됐을 때 던지는 오류 — 호출부가 '실패'와 구분해 조용히 무시할 수 있게 한다. */
export class InterpretationAborted extends Error {
  constructor() {
    super("해석 수신이 취소되었습니다.");
    this.name = "InterpretationAborted";
  }
}

interface JobStatus {
  status?: string;
  result?: InterpretationParts;
  error?: string;
}

/**
 * 1단계 결과를 넘겨 AI 해석만 생성해 받는다.
 *
 * 백엔드가 작업번호(job_id)를 주면 폴링하고, 예전처럼 결과를 바로 주면 그대로 쓴다
 * (백엔드·프론트 배포 순서가 어긋나도 깨지지 않는다).
 *
 * 실패는 **던진다** — 호출부가 "분석 실패"로 승격할지, 해석 필드만 정직 표기할지 정한다.
 */
export async function fetchInterpretation(
  core: unknown,
  opts: InterpretationOptions = {},
): Promise<InterpretationParts | null> {
  const { llmProvider, llmModel, signal } = opts;
  const pollIntervalMs = opts.pollIntervalMs ?? 3000;
  const deadlineMs = opts.deadlineMs ?? 5 * 60 * 1000;
  const abortedCheck = () => {
    if (signal?.aborted) throw new InterpretationAborted();
  };

  abortedCheck();
  const submitted = await apiClient.post<InterpretationParts>("/analysis/interpretation", {
    body: {
      result: core,
      llm_provider: llmProvider || undefined,
      llm_model: llmModel || undefined,
    },
    useMock: false,
  });

  const jobId = (submitted as { job_id?: string })?.job_id;
  if (!jobId) {
    // 구버전 백엔드(동기 응답) — 받은 값을 그대로 쓴다.
    return submitted;
  }

  const deadline = Date.now() + deadlineMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, pollIntervalMs));
    abortedCheck();
    const job = await apiClient.get<JobStatus>(`/analysis/interpretation/${jobId}`, {
      useMock: false,
    });
    if (job?.status === "done") return job.result ?? null;
    if (job?.status === "error") throw new Error(job.error || "해석 생성에 실패했습니다.");
  }
  throw new Error("해석 생성이 시간 내에 완료되지 않았습니다.");
}
