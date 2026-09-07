/**
 * 권리분석 **추가 질의** — 이미 산출된 분석 JSON 으로 되묻는다.
 *
 * ★★**등기부를 다시 사지 않는다.** 등기부는 1,200원/필지 유료이고, 이 저장소가
 *   *«실패를 캐시하기 싫으면 **파생물(해석)만** 재계산하라 — 원본을 다시 사지 마라»*
 *   를 규율로 남겼다. 그래서 이 함수는 **호출부가 이미 가진 `analysis`** 를 보낸다 —
 *   주소·PNU 를 보내 서버가 다시 조회하게 하지 **않는다**.
 *
 * ★판정은 여기서 하지 않는다 — `isAnalyzed` 가 유일한 판정자다(형 컴포넌트의 규율과 동일).
 */
import { apiClient } from "@/lib/api-client";

export const MAX_QUESTION_CHARS = 500;

export interface RightsAnswer {
  ok: boolean;
  answer: string;
  basis: string;
  caveat: string;
}

/** 서버가 못 답하는 경우도 **사유를 실어** 돌려준다 — 무언 실패 금지. */
export async function askRightsQuestion(
  analysis: Record<string, unknown> | null | undefined,
  question: string,
): Promise<RightsAnswer> {
  const q = (question ?? "").trim();
  if (!q) return { ok: false, answer: "", basis: "", caveat: "질문을 입력해 주세요." };
  if (!analysis || typeof analysis !== "object") {
    return { ok: false, answer: "", basis: "", caveat: "권리분석 결과가 없습니다." };
  }
  try {
    const res = await apiClient.post<RightsAnswer>("/registry/rights/ask", {
      body: { analysis, question: q.slice(0, MAX_QUESTION_CHARS) },
    });
    return {
      ok: Boolean(res?.ok),
      answer: String(res?.answer ?? ""),
      basis: String(res?.basis ?? ""),
      caveat: String(res?.caveat ?? ""),
    };
  } catch (e) {
    // ★사유를 삼키지 않는다 — 진단 불가는 그 자체로 장애다(§유료 규율 4).
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, answer: "", basis: "", caveat: `추가 분석 실패: ${msg}` };
  }
}
