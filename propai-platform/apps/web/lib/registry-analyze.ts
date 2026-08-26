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

/**
 * **무과금 재조회가 보장되는 기간(일).**
 *
 * 백엔드 `app/services/registry/registry_analysis_service.py` 의 `_ANALYZE_DB_TTL`
 * (= `7 * 24 * 3600`)과 **같은 값**이어야 한다. 이 상수는 화면 문구가 인용한다.
 *
 * ★왜 상수로 두나(2026-08-25): 화면이 *"동일 물건 재조회 무료"* 라고 **조건 없이**
 * 말하고 있었다. 그런데 무과금은 **성공한 분석이 캐시에 살아 있는 동안만** 참이다 —
 * 캐시가 만료되거나(7일) 그때 **실패했던** 건은 다시 발급·분석되어 청구될 수 있다
 * (`_cache_success` 가 성공만 저장한다 · 같은 파일 §발급 원본 캐시 주석).
 * 기간 없는 "무료"는 8일째에 **거짓이 된다.**
 *
 * 두 값이 갈리면 `lib/__tests__/registry-free-requery-parity.test.ts` 가 잡는다.
 */
export const FREE_REQUERY_DAYS = 7;

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
  result: {
    status?: string;
    message?: string;
    ai?: { generated?: boolean; failure_reason?: string } | null;
  } | null;
  /**
   * 이 결과가 나온 **필지 행**의 id. 재시도가 그 행(지번·PNU·면적)을 되찾는 데 쓴다 —
   * 지번만으로 다시 조회하면 그 행의 PNU·면적이 빠져 **대표값이 섞인다**(이 저장소가
   * 반복해 데인 결함). 목록 표시에는 필요 없어 선택 필드다.
   */
  rowId?: string;
};

/**
 * 이 건이 **권리분석까지 나왔는가**. 백엔드 `_cache_success`(registry_analysis_service.py)와
 * **같은 계약**이다 — 서버가 "성공 캐시"로 인정하는 기준과 화면이 "성공"이라 세는 기준이
 * 갈리면 안 된다.
 *
 * ★`ai` 의 **존재**로 세면 안 된다. LLM 이 실패해도 서버는 `ai` 를 dict 로 돌려주고
 *   (`generated:false` · `summary:"분석 불가"` · `safety_grade:"주의"`), 그러면 화면이
 *   **분석 못 한 건을 성공으로 센다**. 라이브 실측(2026-08-24 오산 내삼미동 448-2·347-8):
 *   PDF 는 발급됐고 `status:"ok"` 인데 권리분석만 폴백이었다.
 */
export function isAnalyzed(b: BatchOutcome): boolean {
  return Boolean(b.result?.ai?.generated);
}

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
 * 이 건이 **왜 분석되지 않았는지** 한 줄. 행과 요약이 **같은 함수**를 쓴다 — 두 표면이
 * 서로 다른 사유를 말하면 사용자는 어느 쪽을 믿을지 알 수 없다.
 *
 * 사유의 출처는 층마다 다르다. **덜 구체적인 것으로 덮지 않도록** 구체적인 순서로 읽는다:
 *  1. `ai.failure_reason` — 등기는 받았고 **권리분석(LLM)만** 실패한 경우. 종전엔 이 필드가
 *     응답에 실려 오는데도 화면이 한 곳도 쓰지 않아, 사용자에게는 "분석 불가" 네 글자만 갔다.
 *  2. `message` — 발급 자체가 안 된 경우(잔액 부족·본문 미확보 등).
 *  3. 응답은 왔는데 아무 사유가 없으면 **그 사실을 그대로 말한다**(지어내지 않는다).
 *  4. 응답 자체가 없으면 요청 단계 실패.
 */
export function rowReason(b: BatchOutcome): string {
  const ai = (b.result?.ai?.failure_reason || "").trim();
  if (ai) return `권리분석 실패 — ${ai}`;
  const msg = (b.result?.message || "").trim();
  if (msg) return msg;
  return b.result ? "사유 미제공(공급자가 이유를 주지 않음)" : "요청 실패(네트워크·시간초과)";
}

/**
 * 일괄 결과 → 요약. **사유를 지어내지 않는다** — 응답이 사유를 안 주면 그 사실을 그대로 센다.
 *
 * ★성공은 `isAnalyzed`(= `ai.generated`)로만 센다. `status:"ok"` 도, `ai` 의 존재도
 *   성공이 아니다 — 둘 다 권리분석이 실패한 건을 통과시킨다.
 */
export function summarizeBatch(items: readonly BatchOutcome[]): BatchSummary {
  const total = items.length;
  const ok = items.filter(isAnalyzed).length;
  const counts = new Map<string, number>();
  for (const b of items) {
    if (isAnalyzed(b)) continue;
    const reason = normalizeReason(rowReason(b));
    counts.set(reason, (counts.get(reason) ?? 0) + 1);
  }
  const reasons = [...counts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
  return { ok, total, failed: total - ok, reasons, topReason: reasons[0]?.reason ?? null };
}

/* ────────────────────────────────────────────────────────────────────────────
 * 실패를 **작업 목록**으로 — 예외 계층 제품화
 *
 * 성공률이 같아도 "분석 불가"는 막다른 길이고, "12건이 이 사유로 안 됐습니다 — 이렇게 하면
 * 됩니다"는 작업 목록이다. 100% 가 구조상 불가능한 세계에서 완성도를 가르는 것은 이쪽이다.
 *
 * ★조치를 **지어내지 않는다.** 아래 분류는 전부 우리가 실제로 받는 응답에서만 도출하고,
 *   각 조치는 화면에 실재하는 통로를 가리킨다(재시도 버튼 · 직접 입력란 · 지번 칸 · 충전).
 * ──────────────────────────────────────────────────────────────────────────── */

/** 실패 건에 대해 사용자가 **실제로 할 수 있는** 다음 행동. */
export type FailureAction =
  /** 등기는 확보됐고 해석(LLM)만 실패 — 재발급 없이 해석만 다시 시도한다. */
  | "reinterpret"
  /** 등기 본문을 못 얻었다(이미지 PDF 등) — 등기부 내용을 직접 입력하면 분석된다. */
  | "enter_manually"
  /** 주소에 번지가 없다 — 지번을 채우면 조회할 수 있다. */
  | "fix_jibun"
  /** 공급자 선불 잔액이 부족하다 — 충전해야 발급된다. */
  | "recharge"
  /** 요청 자체가 실패했다(네트워크·시간초과) — 다시 시도한다. */
  | "retry"
  /** 사유를 못 받았다 — 지어내지 않고 그대로 말한다. */
  | "unknown";

const _JIBUN = /번지|지번/;
const _BALANCE = /잔액|잔고|충전|민원캐시|캐시가 부족|포인트/;
const _BODY = /본문|이미지 형식|직접 입력|갑구/;

/**
 * 이 실패에 대해 **무엇을 할 수 있는가**. `rowReason` 과 같은 입력을 보되 판정 축이 다르다
 * (그쪽은 "왜", 이쪽은 "그래서 뭘").
 */
export function failureAction(b: BatchOutcome): FailureAction {
  if (isAnalyzed(b)) return "unknown"; // 성공 건은 조치 대상이 아니다(호출측이 걸러 온다)
  if (!b.result) return "retry";
  if ((b.result.ai?.failure_reason || "").trim()) return "reinterpret";
  const msg = (b.result.message || "").trim();
  if (!msg) return "unknown";
  if (_BALANCE.test(msg)) return "recharge";
  if (_JIBUN.test(msg)) return "fix_jibun";
  if (_BODY.test(msg) || b.result.status === "empty") return "enter_manually";
  return "retry";
}

/**
 * 조치의 사람 읽는 이름과 안내. `canRetry` 가 참인 것만 화면이 버튼으로 만든다.
 *
 * ★변이 감사 메모(설명 가능한 생존 — 2026-08-24, kill 23 / 생존 13):
 *   아래 `label`·`hint` 문자열 변경은 대부분 **생존한다**. 그것을 구멍으로 보지 않는다 —
 *   이 문구들은 **계약이 아니라 표현**이라, 단언을 걸면 문구를 다듬을 때마다 깨지는
 *   취약한 락이 된다(점수만 오르고 잠기는 것은 없다).
 *
 *   **예외는 하나** — `reinterpret.hint` 다. 그 문구가 "무과금"이라고 단정하면 **거짓이 된다**
 *   (발급 재사용은 프로세스 단위·6시간이라 보장이 아니다). 거짓이 될 수 있는 문구는
 *   표현이 아니라 계약이므로 그것만 테스트가 잠근다
 *   (`registry-failure-actions.test.ts` — "남아 있으면" 포함 · "무과금" 금지).
 *
 *   반대로 `canRetry` 는 **동작을 정하는 값**이라 전부 잠겨 있다(kill).
 */
export const FAILURE_ACTION_INFO: Record<
  FailureAction,
  { label: string; hint: string; canRetry: boolean }
> = {
  reinterpret: {
    label: "해석 다시 시도",
    // ★"무과금"이라고 **단정하지 않는다.** 발급 재사용은 프로세스 단위·6시간이라
    //   보장이 아니다 — 보장할 수 없는 것을 보장으로 말하면 그게 곧 거짓이 된다.
    hint: "등기부는 이미 받았습니다. 최근 발급분이 남아 있으면 다시 발급하지 않고 해석만 다시 합니다.",
    canRetry: true,
  },
  enter_manually: {
    label: "등기부 내용 직접 입력",
    hint: "발급 PDF가 이미지라 본문을 읽지 못했습니다. 위 ‘등기부등본 내용 직접 입력’에 붙여 넣으면 분석됩니다.",
    canRetry: false,
  },
  fix_jibun: {
    label: "지번 채우기",
    hint: "등기부는 필지 단위 문서입니다. 목록에서 그 행의 주소에 번지(예: 448-2)까지 넣어 주세요.",
    canRetry: false,
  },
  recharge: {
    label: "공급자 잔액 충전",
    hint: "발급 공급자의 선불 잔액이 부족합니다. 충전 후 다시 시도하면 발급됩니다.",
    canRetry: false,
  },
  retry: {
    label: "다시 시도",
    hint: "요청이 도중에 끊겼습니다. 다시 시도해 주세요(발급이 안 됐다면 발급 비용이 듭니다).",
    canRetry: true,
  },
  unknown: {
    label: "사유 확인 필요",
    hint: "공급자가 실패 사유를 주지 않았습니다. 반복되면 관리자에게 이 지번을 알려 주세요.",
    canRetry: true,
  },
};

export type FailureGroup = {
  action: FailureAction;
  /** 이 묶음의 대표 사유(가장 많은 것). */
  reason: string;
  count: number;
  /** 재시도 대상 행 — 화면이 이 목록으로 일괄 재시도한다. */
  items: BatchOutcome[];
};

/**
 * 실패 건을 **조치별로** 묶는다(많은 순). 성공 건은 들어오지 않는다.
 *
 * ★사유가 아니라 **조치**로 묶는 이유: 사용자가 하는 일은 사유마다가 아니라 조치마다 같다.
 *   사유별로 늘어놓으면 12줄이 되지만 조치로 묶으면 보통 2~3덩어리다.
 */
export function groupFailures(items: readonly BatchOutcome[]): FailureGroup[] {
  const buckets = new Map<FailureAction, BatchOutcome[]>();
  for (const b of items) {
    if (isAnalyzed(b)) continue;
    const a = failureAction(b);
    const cur = buckets.get(a);
    if (cur) cur.push(b);
    else buckets.set(a, [b]);
  }
  return [...buckets.entries()]
    .map(([action, group]) => {
      // 대표 사유 = 그 묶음에서 가장 많은 정규화 사유.
      const counts = new Map<string, number>();
      for (const g of group) {
        const r = normalizeReason(rowReason(g));
        counts.set(r, (counts.get(r) ?? 0) + 1);
      }
      const reason = [...counts.entries()].sort((x, y) => y[1] - x[1])[0][0];
      return { action, reason, count: group.length, items: group };
    })
    .sort((a, b) => b.count - a.count || a.action.localeCompare(b.action));
}
