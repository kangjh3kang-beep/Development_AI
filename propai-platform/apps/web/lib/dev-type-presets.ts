/**
 * 개발유형(M01~M15) 코드↔라벨 **프론트 정본**.
 *
 * ## 왜 뽑아냈나
 *
 * 같은 목록이 최소 두 곳에 복제돼 있었고 **길이가 달랐다**(실측 2026-09-07):
 *
 *     components/feasibility/ProjectTypeSelector.tsx   15개  ← 전수
 *     components/feasibility/BudgetExecutionPanel.tsx   8개  ← 부분집합
 *
 * ★`BudgetExecutionPanel` 은 주석에 *"개발방식 옵션(**M01~M15**)"* 이라 적어 놓고
 *   실제로는 8개다. 그 파일은 백엔드 `budget_template.METHOD_LABELS` 와의 정합을
 *   근거로 대므로 **여기서 강제로 15개로 늘리지 않는다**(다른 축일 수 있다 — 미측정).
 *   대신 이 정본을 만들어 **새 소비처가 또 손목록을 만들지 않게** 한다.
 *
 * ## 축
 *
 * 백엔드 정본은 `apps/api/app/services/feasibility/unit_standards.py` 의
 * `_EXCLUSIVE`(15키)다. 전용률이 **분양가를 직접 결정**하므로(M06 0.75 ↔ M07 0.60 =
 * 공급 평당가 **+25%**) 코드가 어긋나면 값이 조용히 달라진다.
 */

export type DevTypePreset = { code: string; label: string };

/** M01~M15 전수. ★순서는 코드 오름차순 — 화면이 이 순서를 그대로 쓴다. */
export const DEV_TYPE_PRESETS: readonly DevTypePreset[] = [
  { code: "M01", label: "재개발" },
  { code: "M02", label: "재건축" },
  { code: "M03", label: "역세권개발" },
  { code: "M04", label: "지역주택조합" },
  { code: "M05", label: "임대협동조합" },
  { code: "M06", label: "일반분양" },
  { code: "M07", label: "주상복합" },
  { code: "M08", label: "오피스텔" },
  { code: "M09", label: "지식산업센터" },
  { code: "M10", label: "단독주택" },
  { code: "M11", label: "전원주택" },
  { code: "M12", label: "타운하우스" },
  { code: "M13", label: "도시형생활" },
  { code: "M14", label: "공공임대" },
  { code: "M15", label: "민간리츠" },
] as const;

/**
 * 백엔드 `unit_standards._EXCLUSIVE` 의 전용률.
 *
 * ★**표시 전용이다 — 계산에 쓰지 마라.** 계산은 백엔드가 한다. 여기 있는 이유는
 *   사용자가 «유형을 바꾸면 분양가가 왜 바뀌는지» 를 화면에서 이해할 수 있게 하기
 *   위해서다. 값이 어긋나면 **설명이 거짓**이 되므로 잠금이 백엔드 표와 대조한다.
 */
export const DEV_TYPE_EXCLUSIVE_RATIO: Readonly<Record<string, number>> = {
  M01: 0.75, M02: 0.75, M03: 0.65, M04: 0.75, M05: 0.7,
  M06: 0.75, M07: 0.6, M08: 0.55, M09: 0.55, M10: 0.85,
  M11: 0.85, M12: 0.8, M13: 0.65, M14: 0.7, M15: 0.75,
};

/** 코드 → 라벨. 모르는 코드는 코드를 그대로 돌려준다(지어내지 않는다). */
export function devTypeLabel(code: string | null | undefined): string {
  if (!code) return "";
  return DEV_TYPE_PRESETS.find((p) => p.code === code)?.label ?? code;
}
