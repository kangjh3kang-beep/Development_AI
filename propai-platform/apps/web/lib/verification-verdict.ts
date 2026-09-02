/**
 * AI 검증 배지의 판정 → 표기 매핑 (순수·컴포넌트 밖).
 *
 * ★컴포넌트 밖으로 꺼낸 이유: 이 **판단**이 결함이 살던 자리인데, 1,400줄짜리 화면 안에
 * 있으면 행위를 태우는 테스트를 쓸 수 없어 「재료만 잠그고 판단은 무잠금」이 된다.
 *
 * ## 종전 결함 (2026-08-27 실측)
 *
 * `VERDICT_META[result.verdict] || VERDICT_META.warn` 이었다. `verdict` 는
 * `verifier_service.py:187` 의 `data.get("verdict") or "pass"` — **LLM 자유 JSON** 이고
 * 백엔드에 정규화가 **0건**이다(대조군: 같은 파일 verdict 라인 15개 생존).
 * 그래서 LLM 이 `"FAIL"` 을 뱉으면 **"오류 발견"이 "주의"로 강등**됐다.
 * 프론트 타입 `"pass"|"warn"|"fail"|string` 은 **열린 유니온**이라 tsc 가 안 잡는다.
 */

import { AlertTriangle, CheckCircle2, HelpCircle, XCircle, type LucideIcon } from "lucide-react";

import { resolveKnown, shortenUnknownKey } from "@/lib/unknown-value";

export type VerdictMeta = { label: string; cls: string; icon: LucideIcon };

/**
 * ★표를 **닫힌 유니온에 결속**한다 — 여기 값을 추가하면 tsc 가 표를 채우라고 강제한다.
 * 종전 `Record<string, …>` 은 아무것도 강제하지 않았다. (선례: `LegacyLedgerTable.tsx:100`
 * 의 `Record<LedgerCheck["verdict"], …>` — 동료 세션 `-0b` 가 짚어 줬다.)
 *
 * ★백엔드 응답 타입(`"pass"|"warn"|"fail"| string`)에 결속하면 **안 된다**: `| string` 이
 *   유니온을 삼켜서 tsc 가 아무것도 안 잡는다. 그래서 여기서 **따로 닫는다.**
 */
export type KnownVerdict = "pass" | "warn" | "fail";

export const VERDICT_META: Record<KnownVerdict, VerdictMeta> = {
  pass: { label: "검증 통과", cls: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]", icon: CheckCircle2 },
  warn: { label: "주의", cls: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]", icon: AlertTriangle },
  fail: { label: "오류 발견", cls: "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]", icon: XCircle },
};

/**
 * 미지 판정의 표기 — **중립 회색**.
 *
 * ★`warn` 을 쓰지 않는다: 그것이 종전 결함이다(fail 강등).
 * ★`pass` 계열도 쓰지 않는다: 모르는 것을 통과로 보이게 하면 더 나쁘다.
 * 이 저장소가 이미 쓰는 중립 표기(`LEVEL_CHIP.low`)와 같은 토큰을 쓴다.
 */
export const UNKNOWN_VERDICT_CLS =
  "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]";

/**
 * 판정 문자열 → 표기. 표기 흔들림(`"FAIL"`·공백)은 **복원**하고,
 * 진짜 모르는 값은 **중립 + 원값 노출**로 접는다(진단 불가는 그 자체로 장애다).
 */
export function resolveVerdictMeta(raw: unknown): VerdictMeta {
  const found = resolveKnown(VERDICT_META, raw);
  if (found.known) return found.value;

  const shown = shortenUnknownKey(found.key);
  return {
    label: shown ? `판정 불명 (${shown})` : "판정 불명",
    cls: UNKNOWN_VERDICT_CLS,
    icon: HelpCircle,
  };
}
